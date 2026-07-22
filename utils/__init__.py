__all__ = ["LLMClient", "EmbeddingClient", "RateLimiter", "Tracer", "GraphCampusError", "ErrorCode"]

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