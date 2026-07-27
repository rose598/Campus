import time
import uuid
import logging
from pathlib import Path
from typing import Optional, Any
from contextlib import contextmanager

import structlog

from .config_loader import get

# 项目根目录（绝对路径）
_ROOT = Path(__file__).resolve().parent.parent

_structlog_configured = False


def _configure_structlog() -> None:
    """配置 structlog（仅执行一次）"""
    global _structlog_configured
    if _structlog_configured:
        return

    level_str = str(get("logging.level", "INFO")).upper()
    level = getattr(logging, level_str, logging.INFO)
    output = str(get("logging.output", "console"))

    # 构建 stdlib logging handler
    logger = logging.getLogger("graphcampus")
    logger.setLevel(level)
    logger.propagate = False

    if not logger.handlers:
        if output in ("console", "console+file"):
            sh = logging.StreamHandler()
            logger.addHandler(sh)

        if output in ("file", "console+file"):
            log_dir = _ROOT / "data" / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            fh = logging.FileHandler(log_dir / "graphcampus.log", encoding="utf-8")
            logger.addHandler(fh)

    # 配置 structlog
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(ensure_ascii=False),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    _structlog_configured = True


class NodeContext:
    """node() 上下文管理器内部对象，用于在 with 块中添加 detail"""

    def __init__(self, tracer: "Tracer", node_name: str):
        self._tracer = tracer
        self._node_name = node_name
        self.detail: dict[str, Any] = {}

    def add(self, key: str, value: Any) -> "NodeContext":
        self.detail[key] = value
        return self


class Tracer:
    """结构化日志 + 性能追踪 —— 每条请求生成 trace_id，贯穿所有节点"""

    def __init__(
        self,
        trace_id: Optional[str] = None,
        user_id: str = "default",
        session_id: Optional[str] = None,
    ):
        _configure_structlog()
        self.trace_id = trace_id or self._gen_trace_id()
        self.user_id = user_id
        self.session_id = session_id
        self._logger = structlog.get_logger("graphcampus").bind(
            trace_id=self.trace_id,
            user_id=self.user_id,
            session_id=self.session_id or "",
        )
        self._start_time = time.time()

    @staticmethod
    def _gen_trace_id() -> str:
        return uuid.uuid4().hex[:12]

    def log(
        self,
        level: str,
        message: str,
        node: Optional[str] = None,
        latency_ms: Optional[int] = None,
        detail: Optional[dict] = None,
    ) -> None:
        kwargs: dict[str, Any] = {}
        if node:
            kwargs["node"] = node
        if latency_ms is not None:
            kwargs["latency_ms"] = latency_ms
        if detail:
            kwargs["detail"] = detail

        log_method = getattr(self._logger, level.lower(), self._logger.info)
        log_method(message, **kwargs)

    def log_node(
        self,
        node_name: str,
        latency_ms: int,
        detail: Optional[dict] = None,
        level: str = "INFO",
    ) -> None:
        self.log(level, f"node={node_name}", node=node_name, latency_ms=latency_ms, detail=detail)

    @contextmanager
    def node(self, node_name: str):
        """上下文管理器：自动计时并记录节点执行

        用法:
            with tracer.node("intent_classifier") as ctx:
                intent = classify(query)
                ctx.add("intent", intent)
        """
        ctx = NodeContext(self, node_name)
        start = time.time()
        try:
            yield ctx
        finally:
            latency_ms = int((time.time() - start) * 1000)
            self.log_node(node_name, latency_ms, ctx.detail)

    def info(self, message: str, **kwargs) -> None:
        self.log("INFO", message, **kwargs)

    def warning(self, message: str, **kwargs) -> None:
        self.log("WARNING", message, **kwargs)

    def error(self, message: str, **kwargs) -> None:
        self.log("ERROR", message, **kwargs)

    def total_latency_ms(self) -> int:
        return int((time.time() - self._start_time) * 1000)

    def end_trace(self) -> None:
        self.log(
            "INFO",
            f"trace completed in {self.total_latency_ms()}ms",
            latency_ms=self.total_latency_ms(),
        )
