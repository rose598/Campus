"""
前端状态同步工具
封装 Streamlit session_state 的读写
提供统一的 set/get 接口，确保不同页面间的状态保持一致
"""

from typing import Any, Optional

import streamlit as st


# ── 状态前缀（避免命名冲突）──────────────────────────────────────────────
_PREFIX = "graphcampus_"


# ── 核心 API ──────────────────────────────────────────────
def set_state(key: str, value: Any) -> None:
    """
    设置全局状态值

    Args:
        key: 状态键名
        value: 状态值
    """
    full_key = f"{_PREFIX}{key}"
    st.session_state[full_key] = value


def get_state(key: str, default: Any = None) -> Any:
    """
    获取全局状态值

    Args:
        key: 状态键名
        default: 默认值（键不存在时返回）

    Returns:
        状态值或默认值
    """
    full_key = f"{_PREFIX}{key}"
    return st.session_state.get(full_key, default)


def has_state(key: str) -> bool:
    """
    检查状态键是否存在

    Args:
        key: 状态键名

    Returns:
        bool: 键是否存在
    """
    full_key = f"{_PREFIX}{key}"
    return full_key in st.session_state


def delete_state(key: str) -> None:
    """
    删除状态键

    Args:
        key: 状态键名
    """
    full_key = f"{_PREFIX}{key}"
    if full_key in st.session_state:
        del st.session_state[full_key]


def clear_all_state() -> None:
    """清除所有 GraphCampus 相关状态"""
    keys_to_delete = [
        k for k in st.session_state.keys() if k.startswith(_PREFIX)
    ]
    for key in keys_to_delete:
        del st.session_state[key]


# ── 业务状态快捷接口 ──────────────────────────────────────────────
def get_current_page() -> str:
    """获取当前页面标识"""
    return get_state("current_page", "home")


def set_current_page(page: str) -> None:
    """设置当前页面标识"""
    set_state("current_page", page)


def get_selected_course() -> Optional[str]:
    """获取当前选中的课程代码"""
    return get_state("selected_course")


def set_selected_course(course_code: str) -> None:
    """设置当前选中的课程代码"""
    set_state("selected_course", course_code)


def get_chat_history(history_key: str = "chat_history") -> list[dict]:
    """
    获取聊天历史记录

    Args:
        history_key: 状态中存储聊天历史的 key（不带前缀）
    """
    return get_state(history_key, [])


def add_chat_message(role: str, content: str, history_key: str = "chat_history") -> None:
    """
    添加聊天消息

    Args:
        role: 角色（user / assistant）
        content: 消息内容
        history_key: 状态中存储聊天历史的 key（不带前缀）
    """
    history = get_chat_history(history_key)
    history.append({"role": role, "content": content})
    set_state(history_key, history)


def clear_chat_history(history_key: str = "chat_history") -> None:
    """
    清除聊天历史

    Args:
        history_key: 状态中存储聊天历史的 key（不带前缀）
    """
    set_state(history_key, [])


def get_user_profile() -> dict:
    """获取用户画像"""
    return get_state(
        "user_profile",
        {
            "major": None,           # 专业
            "completed_courses": [],  # 已修课程
            "interests": [],          # 兴趣方向
        },
    )


def update_user_profile(**kwargs) -> None:
    """更新用户画像"""
    profile = get_user_profile()
    profile.update(kwargs)
    set_state("user_profile", profile)


def is_onboarding_completed() -> bool:
    """检查是否已完成新手引导"""
    return get_state("onboarding_completed", False)


def mark_onboarding_completed() -> None:
    """标记新手引导已完成"""
    set_state("onboarding_completed", True)


# ── 初始化默认状态 ──────────────────────────────────────────────
def init_default_state() -> None:
    """初始化应用默认状态（应用启动时调用）"""
    defaults = {
        "current_page": "home",
        "selected_course": None,
        "chat_history": [],
        "user_profile": {
            "major": None,
            "completed_courses": [],
            "interests": [],
        },
        "onboarding_completed": False,
        "privacy_mode": "standard",  # offline / standard / strict
    }

    for key, value in defaults.items():
        if not has_state(key):
            set_state(key, value)
