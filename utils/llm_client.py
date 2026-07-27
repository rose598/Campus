import time
import threading
from typing import Optional, Any, Callable, List, Tuple
from openai import OpenAI
from .config_loader import get
from .rate_limiter import RateLimiter as RL


class SemanticCache:
    """语义缓存 —— 余弦相似度匹配 + TTL 过期 + LRU 淘汰"""

    def __init__(
        self,
        similarity_threshold: float = 0.92,
        ttl_seconds: int = 3600,
        max_size: int = 1000,
    ):
        self._threshold = similarity_threshold
        self._ttl = ttl_seconds
        self._max_size = max_size
        # 存储: [(embedding, response, timestamp, last_access)]
        self._store: List[Tuple[List[float], str, float, float]] = []
        self._lock = threading.Lock()

    def query(self, embedding: List[float]) -> Optional[str]:
        """查询缓存，返回相似度超过阈值的缓存结果，否则返回 None"""
        import numpy as np

        now = time.time()
        best_score = -1.0
        best_idx = -1

        with self._lock:
            # 清理过期条目
            self._store = [
                entry for entry in self._store
                if now - entry[2] < self._ttl
            ]

            if not self._store:
                return None

            query_arr = np.array(embedding)
            query_norm = np.linalg.norm(query_arr)
            if query_norm == 0:
                return None

            for i, (cached_emb, _, _, _) in enumerate(self._store):
                cached_arr = np.array(cached_emb)
                cached_norm = np.linalg.norm(cached_arr)
                if cached_norm == 0:
                    continue
                score = float(np.dot(query_arr, cached_arr) / (query_norm * cached_norm))
                if score > best_score:
                    best_score = score
                    best_idx = i

            if best_score >= self._threshold and best_idx >= 0:
                # 更新 LRU 访问时间
                entry = self._store[best_idx]
                self._store[best_idx] = (entry[0], entry[1], entry[2], now)
                return entry[1]

        return None

    def put(self, embedding: List[float], response: str) -> None:
        """存入缓存"""
        now = time.time()
        with self._lock:
            # LRU 淘汰：超过 max_size 时删除最久未访问的
            if len(self._store) >= self._max_size:
                self._store.sort(key=lambda x: x[3])
                self._store = self._store[self._max_size // 4:]  # 淘汰 25%
            self._store.append((embedding, response, now, now))

    def clear(self) -> None:
        """清空缓存"""
        with self._lock:
            self._store.clear()


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

        api_key = get("llm.api_key") or "sk-placeholder"
        base_url = get("llm.base_url")
        client_kwargs = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url
        self._client = OpenAI(**client_kwargs)

        threshold = get("llm.circuit_breaker_threshold", 5)
        reset_s = get("llm.circuit_breaker_reset_seconds", 30)
        self._circuit = CircuitBreaker(threshold=threshold, reset_seconds=reset_s)

        concurrency = get("llm.concurrency_limit", 3)
        self._concurrency = ConcurrencyGuard(max_concurrent=concurrency)

        self._rate_limiter = RL.from_config()

        # 语义缓存
        cache_enabled = get("features.semantic_cache", True)
        if cache_enabled:
            self._semantic_cache = SemanticCache(
                similarity_threshold=get("cache.semantic_similarity_threshold", 0.92),
                ttl_seconds=get("cache.ttl_seconds", 3600),
                max_size=get("cache.max_size", 1000),
            )
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
                except Exception:
                    if attempt >= self._max_retries:
                        raise
                    wait = self._backoff_base * (2 ** attempt)
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


class RateLimitExceededError(Exception):
    pass
