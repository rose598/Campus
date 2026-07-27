"""
通用状态组件
提供统一的空状态、加载态、错误态展示
供所有页面复用，确保 UI 风格一致
"""

import streamlit as st


# ── 空状态 ──────────────────────────────────────────────

def render_empty(
    icon: str = "📭",
    title: str = "暂无数据",
    description: str = "当前没有可展示的内容",
    action_label: str | None = None,
    action_key: str | None = None,
) -> bool:
    """
    渲染空状态占位

    Args:
        icon: 展示图标（emoji）
        title: 标题文本
        description: 描述文本
        action_label: 操作按钮文本（None 则不显示按钮）
        action_key: 按钮 widget key

    Returns:
        bool: 操作按钮是否被点击（无按钮时返回 False）
    """
    st.markdown(
        f"""
        <div style="
            text-align: center;
            padding: 3rem 1rem;
            border: 2px dashed #e0e0e0;
            border-radius: 12px;
            background-color: #fafafa;
            margin: 1rem 0;
        ">
            <div style="font-size: 3rem; margin-bottom: 0.5rem;">{icon}</div>
            <div style="font-size: 1.2rem; font-weight: 600; color: #333; margin-bottom: 0.3rem;">{title}</div>
            <div style="font-size: 0.9rem; color: #999;">{description}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if action_label and action_key:
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            return st.button(action_label, use_container_width=True, key=action_key)

    return False


# ── 加载态 ──────────────────────────────────────────────

def render_loading(message: str = "正在加载，请稍候...") -> None:
    """
    渲染加载状态

    Args:
        message: 加载提示文本
    """
    st.markdown(
        f"""
        <div style="
            text-align: center;
            padding: 2rem 1rem;
            border: 1px solid #e0e0e0;
            border-radius: 12px;
            background-color: #f0f7ff;
            margin: 1rem 0;
        ">
            <div style="font-size: 2rem; margin-bottom: 0.5rem;">⏳</div>
            <div style="font-size: 1rem; color: #555;">{message}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_skeleton(lines: int = 3) -> None:
    """
    渲染骨架屏（模拟内容加载中）

    Args:
        lines: 骨架行数
    """
    for i in range(lines):
        width = "100%" if i == 0 else f"{70 + (i * 7) % 30}%"
        st.markdown(
            f"""
            <div style="
                background: linear-gradient(90deg, #f0f0f0 25%, #e0e0e0 50%, #f0f0f0 75%);
                background-size: 200% 100%;
                animation: shimmer 1.5s infinite;
                height: 1rem;
                border-radius: 4px;
                width: {width};
                margin-bottom: 0.5rem;
            "></div>
            """,
            unsafe_allow_html=True,
        )


# ── 错误态 ──────────────────────────────────────────────

def render_error(
    title: str = "出错了",
    message: str = "发生了未知错误，请稍后重试",
    error_code: str | None = None,
    retry_key: str | None = None,
) -> bool:
    """
    渲染错误状态

    Args:
        title: 错误标题
        message: 错误详情
        error_code: 错误码（如 E001），若提供则自动从 error_handler 获取美化信息
        retry_key: 重试按钮 widget key（None 则不显示按钮）

    Returns:
        bool: 重试按钮是否被点击（无按钮时返回 False）
    """
    # 若有错误码，尝试从 error_handler 获取美化信息
    if error_code:
        try:
            from components.error_handler import get_error_info
            info = get_error_info(error_code)
            title = f"{info['icon']} {info['title']}"
            message = f"{info['message']}\n\n💡 {info['fallback']}"
            # 若未指定 retry_key 但该错误码支持重试，自动生成
            if retry_key is None and info.get("retry"):
                retry_key = f"auto_retry_{error_code}"
        except ImportError:
            pass

    error_display = f"`{error_code}` · " if error_code else ""

    st.error(
        f"**{title}**\n\n"
        f"{error_display}{message}"
    )

    if retry_key:
        return st.button("🔄 重试", use_container_width=True, key=retry_key)

    return False


# ── 兜底回复（LLM 不可用时）──────────────────────────────────

def render_fallback_response(
    message: str = "暂时无法获取回答，请稍后重试或换个问法试试",
) -> None:
    """渲染 LLM 降级兜底回复"""
    st.warning(
        f"🤖 **AI 暂时无法回答**\n\n{message}",
    )


# ── 页面级状态容器 ──────────────────────────────────────────────

def render_page_state(
    is_loading: bool = False,
    is_empty: bool = False,
    is_error: bool = False,
    loading_msg: str = "正在加载...",
    empty_icon: str = "📭",
    empty_title: str = "暂无数据",
    empty_desc: str = "",
    error_title: str = "出错了",
    error_msg: str = "",
    error_code: str | None = None,
) -> str:
    """
    统一的页面状态判断器，返回当前状态字符串

    使用方式：
        state = render_page_state(is_loading=True)
        if state != "ok":
            return  # 状态已渲染，无需继续

    Args:
        is_loading: 是否处于加载状态
        is_empty: 是否为空数据
        is_error: 是否为错误状态
        loading_msg: 加载提示
        empty_icon: 空状态图标
        empty_title: 空状态标题
        empty_desc: 空状态描述
        error_title: 错误标题
        error_msg: 错误信息
        error_code: 错误码

    Returns:
        str: "loading" / "empty" / "error" / "ok"
    """
    if is_error:
        render_error(title=error_title, message=error_msg, error_code=error_code)
        return "error"

    if is_loading:
        render_loading(loading_msg)
        return "loading"

    if is_empty:
        render_empty(icon=empty_icon, title=empty_title, description=empty_desc)
        return "empty"

    return "ok"
