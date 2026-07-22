import os
import threading
import yaml
from pathlib import Path
from typing import Any, Optional

_ROOT = Path(__file__).resolve().parent.parent
_CONFIG_PATH = _ROOT / "config" / "config.yaml"
_config_cache: Optional[dict] = None
_last_mtime: float = 0
_lock = threading.Lock()


def _find_project_root() -> Path:
    marker = Path(__file__).resolve().parent.parent
    if (marker / "config" / "config.yaml").exists():
        return marker
    return Path.cwd()


def _load_raw() -> dict:
    global _config_cache, _last_mtime
    with _lock:
        return _do_load_raw()


def _do_load_raw() -> dict:
    global _config_cache, _last_mtime
    root = _find_project_root()
    path = root / "config" / "config.yaml"
    if not path.exists():
        if _config_cache is None:
            raise FileNotFoundError(f"config.yaml not found at {path}")
        return _config_cache

    mtime = os.path.getmtime(path)
    if _config_cache is not None and mtime <= _last_mtime:
        return _config_cache

    with open(path, "r", encoding="utf-8") as f:
        _config_cache = yaml.safe_load(f) or {}
    _last_mtime = mtime
    return _config_cache


def load() -> dict:
    raw = _load_raw()
    return _override_from_env(raw)


def _override_from_env(config: dict) -> dict:
    env_map = {
        "LLM_PROVIDER": "llm.provider",
        "LLM_MODEL": "llm.model",
        "LLM_API_KEY": "llm.api_key",
        "LLM_BASE_URL": "llm.base_url",
        "EMBEDDING_MODEL": "embedding.model",
        "DB_PATH": "database.path",
    }
    for env_key, config_path in env_map.items():
        env_val = os.getenv(env_key)
        if env_val is None:
            continue
        keys = config_path.split(".")
        target = config
        for k in keys[:-1]:
            target = target.setdefault(k, {})
        target[keys[-1]] = env_val
    return config


def get(key: str, default: Any = None) -> Any:
    """获取配置项，如 get("llm.model")"""
    cfg = load()
    for k in key.split("."):
        if isinstance(cfg, dict):
            cfg = cfg.get(k)
        else:
            return default
    return cfg if cfg is not None else default


def reload() -> dict:
    """强制重新加载配置文件（热加载）"""
    global _config_cache, _last_mtime
    with _lock:
        _config_cache = None
        _last_mtime = 0
    return load()


def set(key: str, value: Any) -> None:
    """运行时修改配置项（仅内存，不持久化到文件）"""
    cfg = load()
    keys = key.split(".")
    target = cfg
    for k in keys[:-1]:
        target = target.setdefault(k, {})
    target[keys[-1]] = value