from enum import Enum
from typing import Optional


class ErrorCode(Enum):
    """错误码体系 —— 全系统统一错误标识"""

    E001 = ("E001", "LLM 服务不可用", "AI 服务暂时不可用，请稍后再试")
    E002 = ("E002", "Embedding 服务不可用", "已切换为关键词模式")
    E003 = ("E003", "数据库连接失败", "系统正在维护")
    E004 = ("E004", "检索无结果", "未找到相关信息，换个问法试试")
    E005 = ("E005", "速率超限", "操作太频繁，请稍后再试")
    E006 = ("E006", "文档解析失败", "该文件格式不支持或已损坏")
    E007 = ("E007", "配置错误", "系统配置异常，请联系管理员")
    E008 = ("E008", "特征未启用", "该功能暂未开放")

    def __init__(self, code: str, message: str, user_message: str):
        self.code = code
        self.message = message
        self.user_message = user_message


class GraphCampusError(Exception):
    """项目统一异常基类"""

    def __init__(self, error_code: ErrorCode, detail: Optional[str] = None):
        self.error_code = error_code
        self.code = error_code.code
        self.message = error_code.message
        self.user_message = error_code.user_message
        self.detail = detail
        super().__init__(f"[{self.code}] {self.message}" + (f": {detail}" if detail else ""))

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "message": self.message,
            "user_message": self.user_message,
            "detail": self.detail,
        }


def get_error(code: str) -> Optional[ErrorCode]:
    for ec in ErrorCode:
        if ec.code == code:
            return ec
    return None


def raise_error(code: str, detail: Optional[str] = None) -> None:
    ec = get_error(code)
    if ec is None:
        raise ValueError(f"未知错误码: {code}")
    raise GraphCampusError(ec, detail)
