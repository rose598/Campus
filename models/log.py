from pydantic import BaseModel, Field
from typing import Optional, Dict, Any


class LogEntry(BaseModel):
    trace_id: str = Field(..., min_length=1, description="请求链路追踪 ID")
    user_id: Optional[str] = Field(None, description="用户 ID")
    node: Optional[str] = Field(None, description="LangGraph 节点名称")
    level: str = Field(default="INFO", description="日志级别")
    message: str = Field(..., min_length=1, description="日志消息")
    detail: Optional[Dict[str, Any]] = Field(None, description="额外结构化信息")
    timestamp: float = Field(..., ge=0, description="Unix 时间戳")