import time
import threading
from typing import Optional, Any, Callable
from openai import OpenAI
from .config_loader import get
from .rate_limiter import RateLimiter as RL


class CircuitBreaker:
    """熔断器：连续失败 N 次后，在 reset_seconds 内快速拒绝"""

    def __init__(self, threshold: int = 5, reset_seconds: int = 30):
        self._threshold = threshold
        self._reset_seconds = reset_seconds
        self._failure_count = 0
        self._open_since: Optional[float] = None
        self._lock = threading.Lock()

    def call(self, fn: Callable, *args, **kwargs) -> Any:
        with self._lock:
            if self._is_open():
                raise CircuitBreakerOpenError(
                    f"熔断器已打开，{self._reset_seconds}s 内快速拒绝"
                )
        try:
            result = fn(*args, **kwargs)
            with self._lock:
                self._failure_count = 0
                self._open_since = None
            return result
        except Exception:
            with self._lock:
                self._failure_count += 1
                if self._failure_count >= self._threshold:
                    self._open_since = time.time()
            raise

    def _is_open(self) -> bool:
        if self._open_since is None:
            return False
        if time.time() - self._open_since >= self._reset_seconds:
            self._open_since = None
            self._failure_count = 0
            return False
        return True

    @property
    def is_open(self) -> bool:
        with self._lock:
            return self._is_open()

    @property
    def failure_count(self) -> int:
        return self._failure_count


class CircuitBreakerOpenError(Exception):
    pass


class ConcurrencyGuard:
    """并发控制：最大允许 N 个并行调用，超出则排队等待"""

    def __init__(self, max_concurrent: int = 3):
        self._semaphore = threading.Semaphore(max_concurrent)

    def call(self, fn: Callable, *args, **kwargs) -> Any:
        with self._semaphore:
            return fn(*args, **kwargs)


class LLMClient:
    """LLM 中枢 —— 统一入口，包含语义缓存 / 重试 / 熔断 / 并发控制 / 速率限制"""

    def __init__(self):
        self._provider = get("llm.provider", "openai")
        self._model = get("llm.model", "gpt-4o-mini")
        self._temperature = get("llm.temperature", 0.3)
        self._max_retries = get("llm.max_retries", 3)
        self._backoff_base = get("llm.backoff_base", 1.0)
        self._backoff_max = get("llm.backoff_max_seconds", 8)

        api_key = get("llm.api_key") or "sk-placeholder"
        base_url = get("llm.base_url")
        timeout_s = float(get("llm.timeout_seconds", 15))
        # SDK 层禁用自带重试（max_retries=0），重试统一由下方 _invoke 循环管理，
        # 避免 SDK 重试与项目重试叠加导致耗时失控
        client_kwargs = {"api_key": api_key, "timeout": timeout_s, "max_retries": 0}
        if base_url:
            client_kwargs["base_url"] = base_url
        self._client = OpenAI(**client_kwargs)

        threshold = get("llm.circuit_breaker_threshold", 5)
        reset_s = get("llm.circuit_breaker_reset_seconds", 30)
        self._circuit = CircuitBreaker(threshold=threshold, reset_seconds=reset_s)

        concurrency = get("llm.concurrency_limit", 3)
        self._concurrency = ConcurrencyGuard(max_concurrent=concurrency)

        self._rate_limiter = RL.from_config()

        # 语义缓存（惰性导入，避免与 rag 包产生循环依赖；导入失败则降级关闭）
        cache_enabled = get("features.semantic_cache", True)
        if cache_enabled:
            try:
                from rag.semantic_cache import SemanticCache
                self._semantic_cache = SemanticCache(
                    similarity_threshold=get("cache.semantic_similarity_threshold", 0.92),
                    ttl_seconds=get("cache.ttl_seconds", 3600),
                    max_size=get("cache.max_size", 1000),
                )
            except Exception:
                self._semantic_cache = None
        else:
            self._semantic_cache = None

        self._on_call: Optional[Callable] = None

    @property
    def model(self) -> str:
        return self._model

    @property
    def rate_limiter(self) -> RL:
        return self._rate_limiter

    def on_call(self, fn: Callable) -> None:
        """注册回调，每次 LLM 调用完成后触发，参数: (prompt_tokens, latency_ms)"""
        self._on_call = fn

    def call(self, system_prompt: str, user_message: str, user_id: str = "default") -> str:
        # ① 语义缓存查询（相似度 > 0.92 → 直接返回）
        query_embedding = None
        if self._semantic_cache is not None:
            try:
                from .embedding_client import EmbeddingClient
                emb_client = EmbeddingClient.get_instance()
                query_embedding = emb_client.embed(user_message)
                cached = self._semantic_cache.query(query_embedding)
                if cached is not None:
                    return cached
            except Exception:
                pass  # Embedding 不可用时跳过缓存，不影响主流程

        # ② 速率限制
        if not self._rate_limiter.check(user_id):
            raise RateLimitExceededError(
                "操作太频繁，请稍后再试"
            )

        # ③ 并发槽 + 熔断器 + 重试
        def _invoke():
            for attempt in range(self._max_retries + 1):
                try:
                    start = time.time()
                    resp = self._client.chat.completions.create(
                        model=self._model,
                        temperature=self._temperature,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_message},
                        ],
                    )
                    latency_ms = int((time.time() - start) * 1000)
                    usage = resp.usage
                    prompt_tokens = usage.prompt_tokens if usage else 0
                    if self._on_call:
                        self._on_call(prompt_tokens, latency_ms)
                    return resp.choices[0].message.content or ""
                except Exception as exc:
                    # 不可重试错误（鉴权/参数类）直接失败，不消耗重试次数
                    if not self._is_retryable(exc):
                        raise
                    if attempt >= self._max_retries:
                        raise
                    # 指数退避封顶，避免重试耗时失控
                    wait = min(self._backoff_base * (2 ** attempt), self._backoff_max)
                    time.sleep(wait)
            return ""

        result = self._concurrency.call(
            lambda: self._circuit.call(_invoke)
        )

        # ④ 写入语义缓存
        if self._semantic_cache is not None and result and query_embedding is not None:
            try:
                self._semantic_cache.put(query_embedding, result)
            except Exception:
                pass

        return result

    @staticmethod
    def _is_retryable(exc: Exception) -> bool:
        """区分可重试错误：超时/网络/5xx/限流可重试；鉴权/参数错误不可重试"""
        try:
            from openai import APIStatusError, AuthenticationError

            if isinstance(exc, AuthenticationError):
                return False
            if isinstance(exc, APIStatusError):
                return exc.status_code in (408, 429, 500, 502, 503, 504)
        except ImportError:
            pass
        # 超时/连接类错误均可重试
        return True

    def health(self) -> dict:
        """健康检查：熔断器状态 + 缓存统计（供系统管理页/监控使用）"""
        return {
            "provider": self._provider,
            "model": self._model,
            "circuit_open": self._circuit.is_open,
            "circuit_failure_count": self._circuit.failure_count,
            "cache_stats": self._semantic_cache.stats() if self._semantic_cache else None,
        }


class RateLimitExceededError(Exception):
    pass
