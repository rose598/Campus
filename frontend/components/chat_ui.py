"""
对话 UI 组件
提供通用的聊天对话界面：消息气泡、输入框、历史记录展示
供知识问答页、RAG 问答页、学伴对话页复用
"""

from typing import Optional

import streamlit as st

from state_sync import get_state, set_state, add_chat_message, get_chat_history, clear_chat_history


# ── 消息气泡 ──────────────────────────────────────────────

def render_message(role: str, content: str, sources: Optional[list[dict]] = None) -> None:
    """
    渲染单条消息气泡

    Args:
        role: 角色 ("user" / "assistant" / "system")
        content: 消息文本内容
        sources: 来源引用列表（仅 assistant 消息使用），每项格式:
            {"title": str, "source": str, "date": str, "snippet": str}
    """
    if role == "user":
        with st.chat_message("user", avatar="🧑"):
            st.markdown(content)

    elif role == "assistant":
        with st.chat_message("assistant", avatar="🤖"):
            st.markdown(content)
            # 来源引用卡片
            if sources:
                _render_sources(sources)

    elif role == "system":
        with st.chat_message("assistant", avatar="ℹ️"):
            st.info(content)


def _render_sources(sources: list[dict]) -> None:
    """渲染消息下方的来源引用卡片"""
    st.markdown("---")
    st.markdown("**📎 来源引用：**")
    for i, src in enumerate(sources, 1):
        title = src.get("title", "未知来源")
        source = src.get("source", "")
        date = src.get("date", "")
        snippet = src.get("snippet", "")

        with st.expander(f"[{i}] {title}"):
            if source:
                st.caption(f"📄 {source}")
            if date:
                st.caption(f"📅 {date}")
            if snippet:
                st.markdown(f"> {snippet}")


# ── 对话历史 ──────────────────────────────────────────────

def render_chat_history(history_key: str = "chat_history") -> None:
    """
    渲染聊天历史记录

    Args:
        history_key: 状态中存储聊天历史的 key（不带前缀）
    """
    history = get_state(history_key, [])
    for msg in history:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        sources = msg.get("sources")
        render_message(role, content, sources)


# ── 输入框 ──────────────────────────────────────────────

def render_chat_input(
    placeholder: str = "输入你的问题...",
    button_label: str = "📤 发送",
    history_key: str = "chat_history",
) -> Optional[str]:
    """
    渲染聊天输入框，返回用户输入的文本（无输入返回 None）

    Args:
        placeholder: 输入框占位文本
        button_label: 发送按钮文本
        history_key: 状态中存储聊天历史的 key

    Returns:
        str 或 None: 用户输入的文本
    """
    col_input, col_btn = st.columns([5, 1])

    with col_input:
        user_input = st.text_input(
            "聊天输入",
            placeholder=placeholder,
            key=f"{history_key}_input",
            label_visibility="collapsed",
        )

    with col_btn:
        submitted = st.button(
            button_label,
            type="primary",
            use_container_width=True,
            key=f"{history_key}_submit",
        )

    if submitted and user_input.strip():
        add_chat_message("user", user_input.strip(), history_key)
        return user_input.strip()

    return None


# ── 工具栏 ──────────────────────────────────────────────

def render_chat_toolbar(history_key: str = "chat_history") -> None:
    """
    渲染对话工具栏（清空历史等）

    Args:
        history_key: 状态中存储聊天历史的 key
    """
    col1, col2 = st.columns([1, 5])

    with col1:
        if st.button("🗑️ 清空对话", key=f"{history_key}_clear"):
            clear_chat_history(history_key)
            st.rerun()

    with col2:
        history = get_state(history_key, [])
        st.caption(f"共 {len(history)} 条消息")


# ── 完整对话区域 ──────────────────────────────────────────────

def render_chat_area(
    title: str = "💬 对话",
    placeholder: str = "输入你的问题...",
    history_key: str = "chat_history",
) -> Optional[str]:
    """
    渲染完整对话区域（标题 + 历史 + 工具栏 + 输入框）

    Args:
        title: 对话区域标题
        placeholder: 输入框占位文本
        history_key: 状态中存储聊天历史的 key

    Returns:
        str 或 None: 用户本次输入的文本
    """
    st.markdown(f"### {title}")

    # 历史记录
    render_chat_history(history_key)

    # 工具栏
    render_chat_toolbar(history_key)

    st.divider()

    # 输入框
    return render_chat_input(placeholder=placeholder, history_key=history_key)
