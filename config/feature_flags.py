"""特征开关 – 线程安全、支持动态注册和函数级拦截"""

import threading
from functools import wraps

import utils.config_loader as _cfg
from utils.error_codes import GraphCampusError, ErrorCode


def _load_flags_from_config() -> dict:
    """从 config.yaml 的 features 段加载特征开关初始值"""
    try:
        features = _cfg.get("features")
        if isinstance(features, dict):
            return features
    except Exception:
        pass
    return {
        "activity_push": True,
        "campus_qa": True,
        "course_summary": True,
        "semantic_cache": True,
        "offline_mode": False,
        "strict_privacy": False,
    }


class FeatureFlags:
    """特征开关 —— 线程安全，支持运行时修改和动态注册"""

    _flags: dict = _load_flags_from_config()
    _lock = threading.Lock()

    @classmethod
    def is_enabled(cls, flag: str) -> bool:
        with cls._lock:
            return cls._flags.get(flag, False)

    @classmethod
    def set_flag(cls, flag: str, value: bool) -> None:
        with cls._lock:
            cls._flags[flag] = value

    @classmethod
    def register_flag(cls, flag: str, default: bool = False) -> None:
        with cls._lock:
            if flag not in cls._flags:
                cls._flags[flag] = default

    @classmethod
    def get_all(cls) -> dict:
        with cls._lock:
            return cls._flags.copy()

    @classmethod
    def reload(cls) -> None:
        with cls._lock:
            _cfg.reload()
            cls._flags = _load_flags_from_config()


def require_feature(flag_name: str):
    """装饰器：被装饰函数调用时，若对应特征关闭则抛出 GraphCampusError(E008)

    用法:
        @require_feature("activity_push")
        def recommend_activities():
            ...
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not FeatureFlags.is_enabled(flag_name):
                raise GraphCampusError(
                    ErrorCode.E008,
                    detail=f"feature '{flag_name}' is disabled",
                )
            return func(*args, **kwargs)
        return wrapper
    return decorator
