import time
import os
from typing import List, Dict, Literal

from pydantic import BaseModel, Field


class ComponentStatus(BaseModel):
    name: str = Field(..., min_length=1, description="组件名")
    status: Literal["healthy", "degraded", "error"] = Field(..., description="组件状态")
    message: str = Field(default="", description="状态说明")
    latency_ms: int = Field(default=0, ge=0, description="检查耗时")


class HealthReport(BaseModel):
    overall: Literal["healthy", "degraded", "error"] = Field(..., description="整体状态")
    components: List[ComponentStatus] = Field(default_factory=list, description="各组件状态")
    timestamp: float = Field(..., description="Unix 时间戳")
    total_latency_ms: int = Field(default=0, ge=0, description="总检查耗时")
    features: Dict[str, bool] = Field(default_factory=dict, description="当前特征开关快照")


def _timeit(fn):
    start = time.time()
    result = fn()
    latency_ms = int((time.time() - start) * 1000)
    return result, latency_ms


def _collect_features() -> Dict[str, bool]:
    try:
        from config.feature_flags import FeatureFlags
        return FeatureFlags.get_all()
    except Exception:
        return {}


def quick_check() -> HealthReport:
    start = time.time()
    components: List[ComponentStatus] = []

    # ── config ──
    def _check_config():
        from utils.config_loader import get
        name = get("app.name")
        if name:
            return ComponentStatus(name="config", status="healthy", message=f"app.name={name}")
        return ComponentStatus(name="config", status="error", message="app.name missing")

    try:
        c, lat = _timeit(_check_config)
        c.latency_ms = lat
        components.append(c)
    except Exception:
        components.append(ComponentStatus(name="config", status="error", message="config load failed"))

    # ── database (文件存在性检查，不建连接) ──
    def _check_db_file():
        from database.connection import DB_PATH
        path = str(DB_PATH)
        if os.path.exists(path):
            writable = os.access(path, os.W_OK)
            return ComponentStatus(
                name="database",
                status="healthy" if writable else "degraded",
                message=f"DB file exists at {path}" + ("" if writable else " (read-only)"),
            )
        return ComponentStatus(name="database", status="degraded", message=f"DB file not found at {path}")

    try:
        c, lat = _timeit(_check_db_file)
        c.latency_ms = lat
        components.append(c)
    except Exception:
        components.append(ComponentStatus(name="database", status="error", message="DB path check failed"))

    # ── features ──
    def _check_features():
        flags = _collect_features()
        if not flags:
            return ComponentStatus(name="features", status="degraded", message="no flags loaded")
        return ComponentStatus(name="features", status="healthy", message=f"{len(flags)} flags loaded")

    try:
        c, lat = _timeit(_check_features)
        c.latency_ms = lat
        components.append(c)
    except Exception:
        components.append(ComponentStatus(name="features", status="error", message="features check failed"))

    # ── 汇总 ──
    statuses = [c.status for c in components]
    if "error" in statuses:
        overall = "error"
    elif "degraded" in statuses:
        overall = "degraded"
    else:
        overall = "healthy"

    total_latency_ms = int((time.time() - start) * 1000)

    return HealthReport(
        overall=overall,
        components=components,
        timestamp=time.time(),
        total_latency_ms=total_latency_ms,
        features=_collect_features(),
    )


def full_check() -> HealthReport:
    report = quick_check()
    start = time.time()

    # ── embedding（不触发模型加载） ──
    def _check_embedding():
        try:
            from utils.embedding_client import EmbeddingClient
        except Exception:
            return ComponentStatus(
                name="embedding",
                status="degraded",
                message="EmbeddingClient import failed (dependency not installed)",
            )
        inst = EmbeddingClient._instance
        if inst is None:
            return ComponentStatus(
                name="embedding",
                status="degraded",
                message="EmbeddingClient not yet initialized",
            )
        if inst._model is None:
            return ComponentStatus(
                name="embedding",
                status="degraded",
                message="EmbeddingClient initialized but model not loaded",
            )
        return ComponentStatus(
            name="embedding",
            status="healthy",
            message="model loaded",
        )

    try:
        c, lat = _timeit(_check_embedding)
        c.latency_ms = lat
        report.components.append(c)
    except Exception:
        report.components.append(
            ComponentStatus(name="embedding", status="error", message="embedding check failed")
        )

    # ── llm_circuit ──
    def _check_llm_circuit():
        try:
            from utils import get_llm_client
            client = get_llm_client()
            cb = client._circuit
            if cb.is_open:
                return ComponentStatus(
                    name="llm_circuit",
                    status="degraded",
                    message=f"circuit breaker open (failures={cb.failure_count})",
                )
            return ComponentStatus(
                name="llm_circuit",
                status="healthy",
                message=f"circuit breaker closed (failures={cb.failure_count})",
            )
        except Exception:
            return ComponentStatus(name="llm_circuit", status="error", message="circuit check failed")

    try:
        c, lat = _timeit(_check_llm_circuit)
        c.latency_ms = lat
        report.components.append(c)
    except Exception:
        report.components.append(
            ComponentStatus(name="llm_circuit", status="error", message="circuit check failed")
        )

    # ── database 连接测试 ──
    def _check_db_connect():
        from database.connection import DB_PATH, get_connection
        try:
            conn = get_connection()
            conn.execute("SELECT 1")
            conn.close()
            return ComponentStatus(name="db_connect", status="healthy", message="connected OK")
        except Exception as exc:
            return ComponentStatus(
                name="db_connect",
                status="degraded" if os.path.exists(str(DB_PATH)) else "error",
                message=str(exc)[:100],
            )

    try:
        c, lat = _timeit(_check_db_connect)
        c.latency_ms = lat
        report.components.append(c)
    except Exception:
        report.components.append(
            ComponentStatus(name="db_connect", status="error", message="db connect check failed")
        )

    # ── 汇总 ──
    statuses = [c.status for c in report.components]
    if "error" in statuses:
        report.overall = "error"
    elif "degraded" in statuses:
        report.overall = "degraded"

    report.total_latency_ms += int((time.time() - start) * 1000)
    report.timestamp = time.time()

    return report


def run_health_check(full: bool = False) -> HealthReport:
    return full_check() if full else quick_check()
