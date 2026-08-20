"""配置中心管理 API（Day 27）

为系统管理页（角色 B）提供统一的配置与特征开关管理能力：
- 配置项：列表 / 查询 / 更新（内存即时生效，可选持久化到 config.yaml）
- 特征开关：列表 / 切换（同步内存态，可选持久化）
- 健康摘要：LLM 熔断器 / 语义缓存统计

敏感键（api_key 等）在列表输出中自动脱敏。
持久化说明：yaml 回写会丢失原文件注释，因此默认先备份 config.yaml.bak。
"""
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

import utils.config_loader as loader
from config.feature_flags import FeatureFlags

_CONFIG_PATH = Path(__file__).resolve().parent / "config.yaml"
_SENSITIVE_KEYS = {"api_key", "password", "token", "secret"}
# 可选配置项：config.yaml 中未声明时仍在管理页展示（标记未设置）
_OPTIONAL_KEYS = ["llm.api_key", "llm.base_url"]


# ── 配置项 ─────────────────────────────────────────────────────────────


def list_configs() -> List[Dict[str, Any]]:
    """扁平化列出所有配置项：[{key, value, type, sensitive}]"""
    cfg = loader.load()
    items: List[Dict[str, Any]] = []
    _flatten(cfg, "", items)
    _append_optional(items)
    return items


def _append_optional(items: List[Dict[str, Any]]) -> None:
    """补充 config.yaml 中未声明的可选键（如 llm.api_key）"""
    existing = {i["key"] for i in items}
    for key in _OPTIONAL_KEYS:
        if key in existing:
            continue
        leaf = key.split(".")[-1]
        items.append({
            "key": key,
            "value": "(未设置)",
            "type": "unset",
            "sensitive": any(s in leaf.lower() for s in _SENSITIVE_KEYS),
        })


def _flatten(node: Any, prefix: str, out: List[Dict[str, Any]]) -> None:
    if isinstance(node, dict):
        for k, v in node.items():
            key = f"{prefix}.{k}" if prefix else k
            _flatten(v, key, out)
        return
    leaf = prefix.split(".")[-1]
    sensitive = any(s in leaf.lower() for s in _SENSITIVE_KEYS)
    out.append({
        "key": prefix,
        "value": "***" if sensitive and node else node,
        "type": type(node).__name__,
        "sensitive": sensitive,
    })


def get_config_item(key: str) -> Optional[Dict[str, Any]]:
    """查询单个配置项"""
    for item in list_configs():
        if item["key"] == key:
            return item
    return None


def update_config(key: str, value: Any, persist: bool = False) -> Dict[str, Any]:
    """更新配置项

    Args:
        key: 点分路径，如 "ppr.top_k"
        value: 新值（自动按原类型转换）
        persist: 是否写回 config.yaml（先备份）

    Returns:
        {"ok": bool, "key": str, "value": Any, "persisted": bool, "message": str}
    """
    old = loader.get(key)
    if old is not None and value is not None:
        try:
            value = type(old)(value)  # 按原类型转换（int/float/bool/str）
        except (TypeError, ValueError):
            pass

    loader.set(key, value)

    message = "内存态已更新（重启后失效）"
    if persist:
        try:
            _persist_to_yaml(key, value)
            message = "已持久化到 config.yaml（原文件备份为 config.yaml.bak）"
        except Exception as e:  # noqa: BLE001 持久化失败不影响内存态
            message = f"内存态已更新，但持久化失败: {e}"
            return {"ok": False, "key": key, "value": value,
                    "persisted": False, "message": message}

    return {"ok": True, "key": key, "value": value,
            "persisted": persist, "message": message}


def _persist_to_yaml(key: str, value: Any) -> None:
    """写回 config.yaml（先备份；yaml 回写会丢失注释）"""
    with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    target = data
    keys = key.split(".")
    for k in keys[:-1]:
        target = target.setdefault(k, {})
    target[keys[-1]] = value

    shutil.copy2(_CONFIG_PATH, _CONFIG_PATH.with_suffix(".yaml.bak"))
    with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)
    loader.reload()


def reload_config() -> Dict[str, Any]:
    """热加载：强制从文件重新读取配置 + 特征开关"""
    loader.reload()
    FeatureFlags.reload()
    return {"ok": True, "message": "配置与特征开关已从文件热加载"}


# ── 特征开关 ───────────────────────────────────────────────────────────


def list_flags() -> List[Dict[str, Any]]:
    """列出所有特征开关：[{name, enabled}]"""
    return [
        {"name": name, "enabled": bool(enabled)}
        for name, enabled in sorted(FeatureFlags.get_all().items())
    ]


def toggle_flag(name: str, enabled: bool, persist: bool = False) -> Dict[str, Any]:
    """切换特征开关

    Args:
        name: 开关名，如 "activity_push"
        enabled: 目标状态
        persist: 是否写回 config.yaml 的 features 段
    """
    FeatureFlags.set_flag(name, bool(enabled))

    message = "开关已切换（内存态）"
    if persist:
        try:
            _persist_to_yaml(f"features.{name}", bool(enabled))
            message = "开关已切换并持久化"
        except Exception as e:  # noqa: BLE001
            message = f"开关已切换，但持久化失败: {e}"

    return {"ok": True, "name": name, "enabled": bool(enabled), "message": message}


# ── 健康摘要 ───────────────────────────────────────────────────────────


def health_summary() -> Dict[str, Any]:
    """系统健康摘要（供管理页仪表盘）"""
    summary: Dict[str, Any] = {
        "flags": {f["name"]: f["enabled"] for f in list_flags()},
    }
    try:
        from utils import get_llm_client

        summary["llm"] = get_llm_client().health()
    except Exception as e:  # noqa: BLE001
        summary["llm"] = {"error": str(e)[:200]}
    return summary
