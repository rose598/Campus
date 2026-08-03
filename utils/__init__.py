try:
    from .llm_client import LLMClient
    _llm_available = True
except Exception:
    LLMClient = None
    _llm_available = False

try:
    from .embedding_client import EmbeddingClient
    _embedding_available = True
except Exception:
    EmbeddingClient = None
    _embedding_available = False

try:
    from .rate_limiter import RateLimiter
except Exception:
    RateLimiter = None

try:
    from .tracer import Tracer
except Exception:
    Tracer = None

try:
    from .error_codes import GraphCampusError, ErrorCode
except Exception:
    GraphCampusError = None
    ErrorCode = None

__all__ = ["LLMClient", "EmbeddingClient", "RateLimiter", "Tracer", "GraphCampusError", "ErrorCode", "run_health_check"]

_llm_client_instance = None
_rate_limiter_instance = None


def get_llm_client():
    """获取 LLMClient 单例实例"""
    global _llm_client_instance
    if _llm_client_instance is None:
        from .llm_client import LLMClient
        _llm_client_instance = LLMClient()
    return _llm_client_instance


def get_embedding_client():
    """获取 EmbeddingClient 单例实例"""
    from .embedding_client import EmbeddingClient
    return EmbeddingClient.get_instance()


def get_rate_limiter():
    """获取 RateLimiter 单例实例"""
    global _rate_limiter_instance
    if _rate_limiter_instance is None:
        from .rate_limiter import RateLimiter
        _rate_limiter_instance = RateLimiter.from_config()
    return _rate_limiter_instance


def get_tracer(**kwargs):
    """创建新的 Tracer 实例（每次请求应创建新实例）"""
    from .tracer import Tracer
    return Tracer(**kwargs)


def run_health_check(full: bool = False):
    from .health import run_health_check as _check
    return _check(full=full)
