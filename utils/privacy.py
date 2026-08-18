# -*- coding: utf-8 -*-
"""
privacy.py — 隐私模式管理器

职责:
  - 支持离线模式（不调用外部 API）
  - 支持标准模式（正常联网操作）
  - 提供数据脱敏工具
  - 全局隐私状态管理

使用方式:
  from utils.privacy import PrivacyManager, privacy_mode

  # 全局设置隐私模式
  PrivacyManager.set_mode("offline")

  # 使用装饰器
  @privacy_mode("offline")
  def fetch_data():
      ...

  # 使用上下文管理器
  with PrivacyManager.offline_context():
      # 此块内禁用外部调用
      ...
"""

from __future__ import annotations

import functools
import hashlib
import logging
import re
from contextlib import contextmanager
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
#  隐私模式枚举
# ─────────────────────────────────────────────

class PrivacyMode(str, Enum):
    """隐私模式类型"""
    STANDARD = "standard"    # 标准模式：允许外部 API 调用
    OFFLINE = "offline"      # 离线模式：禁用外部 API，仅本地处理
    ANONYMIZED = "anonymized"  # 脱敏模式：处理前脱敏数据


# ─────────────────────────────────────────────
#  隐私管理器
# ─────────────────────────────────────────────

class PrivacyManager:
    """
    全局隐私模式管理器。

    使用单例模式确保全局一致的隐私状态。
    """

    _instance: Optional["PrivacyManager"] = None
    _mode: PrivacyMode = PrivacyMode.STANDARD

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def set_mode(cls, mode: str) -> None:
        """设置隐私模式"""
        mode_enum = PrivacyMode(mode)
        cls._mode = mode_enum
        logger.info("[PrivacyManager] 隐私模式切换: %s", mode)

    @classmethod
    def get_mode(cls) -> PrivacyMode:
        """获取当前隐私模式"""
        return cls._mode

    @classmethod
    def is_offline(cls) -> bool:
        """是否处于离线模式"""
        return cls._mode == PrivacyMode.OFFLINE

    @classmethod
    def is_anonymized(cls) -> bool:
        """是否处于脱敏模式"""
        return cls._mode == PrivacyMode.ANONYMIZED

    @classmethod
    @contextmanager
    def offline_context(cls):
        """离线模式上下文管理器"""
        old_mode = cls._mode
        cls._mode = PrivacyMode.OFFLINE
        try:
            yield
        finally:
            cls._mode = old_mode

    @classmethod
    @contextmanager
    def anonymized_context(cls):
        """脱敏模式上下文管理器"""
        old_mode = cls._mode
        cls._mode = PrivacyMode.ANONYMIZED
        try:
            yield
        finally:
            cls._mode = old_mode


# ─────────────────────────────────────────────
#  隐私模式装饰器
# ─────────────────────────────────────────────

def privacy_mode(mode: str = "offline"):
    """
    隐私模式装饰器。

    在函数执行期间临时切换隐私模式。

    示例:
        @privacy_mode("offline")
        def process_data():
            # 此函数内处于离线模式
            ...
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            with PrivacyManager.offline_context() if mode == "offline" else \
                 PrivacyManager.anonymized_context():
                return func(*args, **kwargs)
        return wrapper
    return decorator


def require_online(func: Callable) -> Callable:
    """
    要求在线模式的装饰器。

    如果当前处于离线模式，抛出异常或降级处理。
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        if PrivacyManager.is_offline():
            logger.warning(
                "[Privacy] 函数 %s 需要在线模式，当前为离线模式，跳过执行",
                func.__name__,
            )
            return None
        return func(*args, **kwargs)
    return wrapper


# ─────────────────────────────────────────────
#  数据脱敏工具
# ─────────────────────────────────────────────

class DataAnonymizer:
    """
    数据脱敏工具。

    支持:
      - 姓名脱敏
      - 手机号脱敏
      - 学号脱敏
      - 邮箱脱敏
    """

    @staticmethod
    def anonymize_name(name: str) -> str:
        """姓名脱敏：保留姓氏，其余替换为 *"""
        if len(name) <= 1:
            return name
        return name[0] + "*" * (len(name) - 1)

    @staticmethod
    def anonymize_phone(phone: str) -> str:
        """手机号脱敏：保留前3后4"""
        if len(phone) == 11 and phone.isdigit():
            return f"{phone[:3]}****{phone[7:]}"
        return phone

    @staticmethod
    def anonymize_student_id(sid: str) -> str:
        """学号脱敏：保留前2后2"""
        if len(sid) >= 4:
            return f"{sid[:2]}{'*' * (len(sid) - 4)}{sid[-2:]}"
        return sid

    @staticmethod
    def anonymize_email(email: str) -> str:
        """邮箱脱敏：保留首字母和域名"""
        parts = email.split("@")
        if len(parts) == 2:
            local = parts[0]
            if len(local) > 1:
                return f"{local[0]}***@{parts[1]}"
        return email

    @classmethod
    def anonymize_text(cls, text: str) -> str:
        """对文本中的敏感信息进行脱敏"""
        # 手机号
        text = re.sub(
            r"1[3-9]\d{9}",
            lambda m: cls.anonymize_phone(m.group()),
            text,
        )
        # 邮箱
        text = re.sub(
            r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
            lambda m: cls.anonymize_email(m.group()),
            text,
        )
        return text

    @classmethod
    def anonymize_record(cls, record: Dict[str, Any]) -> Dict[str, Any]:
        """对字典记录进行脱敏"""
        result = record.copy()

        # 脱敏常见字段
        if "name" in result:
            result["name"] = cls.anonymize_name(str(result["name"]))
        if "phone" in result or "mobile" in result:
            key = "phone" if "phone" in result else "mobile"
            result[key] = cls.anonymize_phone(str(result[key]))
        if "student_id" in result or "sid" in result:
            key = "student_id" if "student_id" in result else "sid"
            result[key] = cls.anonymize_student_id(str(result[key]))
        if "email" in result:
            result["email"] = cls.anonymize_email(str(result["email"]))

        return result


# ─────────────────────────────────────────────
#  隐私感知的 LLM 客户端包装
# ─────────────────────────────────────────────

class PrivacyAwareLLMClient:
    """
    隐私感知的 LLM 客户端包装器。

    在离线模式下:
      - 不调用外部 API
      - 返回预设的降级回复
    """

    FALLBACK_RESPONSES = {
        "intent_classification": '{"intent": "general", "confidence": 0.5}',
        "summary": "无法生成摘要（离线模式）",
        "extraction": "{}",
        "default": "当前处于离线模式，无法调用 LLM。",
    }

    def __init__(self, llm_client=None):
        self._client = llm_client

    def call(self, system_prompt: str, user_msg: str, task_type: str = "default") -> str:
        """
        调用 LLM，根据隐私模式决定是否使用外部 API。
        """
        if PrivacyManager.is_offline():
            logger.debug("[PrivacyLLM] 离线模式，返回降级回复")
            return self.FALLBACK_RESPONSES.get(task_type, self.FALLBACK_RESPONSES["default"])

        if self._client:
            return self._client.call(system_prompt, user_msg)

        return self.FALLBACK_RESPONSES.get(task_type, self.FALLBACK_RESPONSES["default"])


# ─────────────────────────────────────────────
#  隐私感知的检索器包装
# ─────────────────────────────────────────────

class PrivacyAwareRetriever:
    """
    隐私感知的检索器。

    在脱敏模式下，对检索结果进行脱敏处理。
    """

    def __init__(self, retriever=None, anonymizer: Optional[DataAnonymizer] = None):
        self._retriever = retriever
        self._anonymizer = anonymizer or DataAnonymizer()

    def search(self, query: str, **kwargs) -> List[Dict[str, Any]]:
        """执行检索，根据隐私模式处理结果"""
        if not self._retriever:
            return []

        results = self._retriever.search(query, **kwargs)

        # 脱敏模式：对结果内容进行脱敏
        if PrivacyManager.is_anonymized():
            for r in results:
                if "content" in r:
                    r["content"] = self._anonymizer.anonymize_text(r["content"])

        return results


# ─────────────────────────────────────────────
#  命令行测试
# ─────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")

    print("=== 隐私模式测试 ===\n")

    # 测试模式切换
    print(f"初始模式: {PrivacyManager.get_mode()}")

    PrivacyManager.set_mode("offline")
    print(f"切换后: {PrivacyManager.get_mode()}")
    print(f"是否离线: {PrivacyManager.is_offline()}")

    # 测试上下文管理器
    with PrivacyManager.offline_context():
        print(f"上下文内: {PrivacyManager.get_mode()}")
    print(f"上下文外: {PrivacyManager.get_mode()}")

    # 测试脱敏
    anonymizer = DataAnonymizer()
    print(f"\n脱敏测试:")
    print(f"  姓名: 张三 → {anonymizer.anonymize_name('张三')}")
    print(f"  手机: 13812345678 → {anonymizer.anonymize_phone('13812345678')}")
    print(f"  学号: 2023001234 → {anonymizer.anonymize_student_id('2023001234')}")
    print(f"  邮箱: zhangsan@example.edu.cn → {anonymizer.anonymize_email('zhangsan@example.edu.cn')}")

    # 测试文本脱敏
    text = "联系人：李四，电话13987654321，邮箱lisi@school.edu.cn"
    print(f"\n文本脱敏:")
    print(f"  原文: {text}")
    print(f"  脱敏: {anonymizer.anonymize_text(text)}")

    print("\n[OK] 隐私模式测试完成")
