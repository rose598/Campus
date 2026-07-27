"""
统一错误处理组件（error_handler）
Day 22: 兜底交互 + 错误提示美化
将 ErrorCode 体系与前端 UI 打通，提供统一的错误展示、重试、降级兜底
"""

from typing import Optional

import streamlit as st


# ── 错误码定义（与 utils/error_codes.py 对齐，前端独立维护避免循环依赖）──────

ERROR_REGISTRY = {
    "E001": {
        "title": "AI 服务暂时不可用",
        "message": "问答引擎正在维护中，请稍后再试",
        "icon": "🤖",
        "retry": True,
        "fallback": "目前无法连接 AI 服务，你可以先浏览其他功能，稍后再回来提问。",
    },
    "E002": {
        "title": "智能搜索暂时降级",
        "message": "语义搜索不可用，已切换为关键词匹配模式",
        "icon": "🔍",
        "retry": True,
        "fallback": "当前使用关键词模式，结果可能不如语义搜索精准，建议稍后重试。",
    },
    "E003": {
        "title": "系统正在维护",
        "message": "数据库连接暂时中断，数据不会丢失",
        "icon": "🔧",
        "retry": True,
        "fallback": "系统维护期间，历史对话和本地数据仍可正常查看。",
    },
    "E004": {
        "title": "未找到相关信息",
        "message": "知识库中没有匹配的内容，换个问法试试",
        "icon": "🔎",
        "retry": False,
        "fallback": "试试缩短问题、使用关键词，或选择其他课程后再提问。",
    },
    "E005": {
        "title": "操作太频繁",
        "message": "请求过于频繁，请稍 30 秒后再试",
        "icon": "⏱️",
        "retry": True,
        "fallback": "你可以在等待期间浏览课程列表或查看已有总结。",
    },
    "E006": {
        "title": "文档解析失败",
        "message": "该文件格式不支持或文件已损坏",
        "icon": "📄",
        "retry": False,
        "fallback": "请确认文件为 PDF / Word / PPT 格式，且文件未损坏后重新上传。",
    },
    "E007": {
        "title": "系统配置异常",
        "message": "请联系管理员检查配置",
        "icon": "⚙️",
        "retry": False,
        "fallback": "配置异常不影响已有数据，但部分功能可能暂时不可用。",
    },
    "E008": {
        "title": "功能暂未开放",
        "message": "该功能正在开发中，敬请期待",
        "icon": "🚧",
        "retry": False,
        "fallback": "你可以先使用已开放的核心功能：活动推送、知识问答、课程资料。",
    },
}


def get_error_info(error_code: str) -> dict:
    """
    获取错误码对应的 UI 信息

    Args:
        error_code: 错误码（如 "E001"）

    Returns:
        dict: 包含 title/message/icon/retry/fallback 的字典
    """
    return ERROR_REGISTRY.get(error_code, {
        "title": "未知错误",
        "message": f"发生了未预期的错误（{error_code}），请稍后重试",
        "icon": "❓",
        "retry": True,
        "fallback": "如果问题持续出现，请联系管理员。",
    })


def render_error_banner(error_code: str, detail: str | None = None) -> bool:
    """
    渲染页面顶部错误横幅（用于阻断式错误）

    Args:
        error_code: 错误码
        detail: 额外错误详情

    Returns:
        bool: 重试按钮是否被点击
    """
    info = get_error_info(error_code)

    detail_text = f"\n\n📋 详情：{detail}" if detail else ""

    st.error(
        f"{info['icon']} **{info['title']}**\n\n"
        f"`{error_code}` · {info['message']}{detail_text}"
    )

    if info["retry"]:
        col1, col2 = st.columns([1, 3])
        with col1:
            return st.button(
                "🔄 重试",
                use_container_width=True,
                key=f"error_retry_{error_code}",
            )
    return False


def render_inline_error(error_code: str, key: str = "inline_error") -> None:
    """
    渲染内联错误提示（用于对话消息中的错误）

    Args:
        error_code: 错误码
        key: widget key
    """
    info = get_error_info(error_code)
    st.warning(
        f"{info['icon']} **{info['title']}**\n\n"
        f"{info['message']}\n\n"
        f"💡 {info['fallback']}"
    )


def render_chat_error_message(error_code: str) -> str:
    """
    生成用于聊天消息中的错误文本（插入到对话历史）

    Args:
        error_code: 错误码

    Returns:
        str: 格式化的错误文本
    """
    info = get_error_info(error_code)
    return (
        f"{info['icon']} **{info['title']}**\n\n"
        f"{info['message']}\n\n"
        f"💡 {info['fallback']}"
    )


def render_fallback_chat_response(error_code: str = "E001") -> None:
    """
    渲染 LLM 降级兜底回复（在对话区域内显示）

    Args:
        error_code: 错误码
    """
    info = get_error_info(error_code)
    st.info(
        f"🤖 **AI 暂时无法回答**（`{error_code}`）\n\n"
        f"{info['fallback']}"
    )


def render_error_page(
    error_code: str,
    detail: str | None = None,
    clear_callback=None,
) -> bool:
    """
    渲染完整错误页面（阻断式，用于页面级错误）

    Args:
        error_code: 错误码
        detail: 额外详情
        clear_callback: 清除错误的回调函数

    Returns:
        bool: 是否需要刷新页面
    """
    info = get_error_info(error_code)

    st.markdown(
        f"""
        <div style="
            text-align: center;
            padding: 2rem 1rem;
            border: 2px solid #ffcdd2;
            border-radius: 12px;
            background-color: #fff5f5;
            margin: 1rem 0;
        ">
            <div style="font-size: 3rem; margin-bottom: 0.5rem;">{info['icon']}</div>
            <div style="font-size: 1.3rem; font-weight: 600; color: #c62828; margin-bottom: 0.5rem;">
                {info['title']}
            </div>
            <div style="font-size: 0.9rem; color: #666;">
                <code>{error_code}</code> · {info['message']}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if detail:
        st.caption(f"📋 详情：{detail}")

    # 降级建议
    st.info(f"💡 **建议**：{info['fallback']}")

    # 操作按钮
    col1, col2 = st.columns(2)
    need_rerun = False

    with col1:
        if info["retry"]:
            if st.button("🔄 重试", use_container_width=True, key="error_page_retry"):
                if clear_callback:
                    clear_callback()
                need_rerun = True

    with col2:
        if st.button("🏠 返回首页", use_container_width=True, key="error_page_home"):
            from state_sync import set_state
            if clear_callback:
                clear_callback()
            set_state("current_page", "home")
            need_rerun = True

    return need_rerun
