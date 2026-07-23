"""特征开关 – 运行时可通过 API 或管理界面修改，初始值从 config.yaml 加载"""
import sys
from pathlib import Path

# 将项目根目录加入 sys.path，以便导入 utils
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _load_flags_from_config() -> dict:
    """从 config.yaml 的 features 段加载特征开关初始值"""
    try:
        from utils.config_loader import get
        features = get("features")
        if isinstance(features, dict):
            return features
    except Exception:
        pass
    # 配置加载失败时的默认值
    return {
        "activity_push": True,
        "campus_qa": True,
        "course_summary": True,
        "semantic_cache": True,
        "offline_mode": False,
        "strict_privacy": False,
    }


class FeatureFlags:
    _flags: dict = _load_flags_from_config()

    @classmethod
    def is_enabled(cls, flag: str) -> bool:
        return cls._flags.get(flag, False)

    @classmethod
    def set_flag(cls, flag: str, value: bool) -> None:
        if flag in cls._flags:
            cls._flags[flag] = value

    @classmethod
    def get_all(cls) -> dict:
        return cls._flags.copy()

    @classmethod
    def reload(cls) -> None:
        """从 config.yaml 重新加载特征开关"""
        cls._flags = _load_flags_from_config()