"""
来源引用卡片组件（source_card）
将 RAG 检索到的文档来源以可视化卡片形式展示
支持相关度分数、来源类型识别、关键词高亮、紧凑模式
供知识问答页、活动推送页、课程资料页复用
"""

import re
from typing import Optional

import streamlit as st


# ── 来源类型识别 ──────────────────────────────────────────────

_SOURCE_TYPE_MAP = {
    # 文件扩展名 → (图标, 标签, 颜色)
    ".pdf":  ("📕", "PDF",   "#e53935"),
    ".doc":  ("📘", "Word",  "#1e88e5"),
    ".docx": ("📘", "Word",  "#1e88e5"),
    ".ppt":  ("📙", "PPT",   "#fb8c00"),
    ".pptx": ("📙", "PPT",   "#fb8c00"),
    ".xls":  ("📗", "Excel", "#43a047"),
    ".xlsx": ("📗", "Excel", "#43a047"),
}

_URL_PATTERN = re.compile(r"https?://")


def _detect_source_type(source: str) -> tuple[str, str, str]:
    """
    根据来源路径/URL 自动识别类型

    Args:
        source: 来源路径或 URL

    Returns:
        (icon, label, color) 三元组
    """
    if not source:
        return ("📄", "文档", "#757575")

    source_lower = source.lower()

    # URL 检测
    if _URL_PATTERN.search(source_lower):
        return ("🌐", "网页", "#1976d2")

    # 文件扩展名检测
    for ext, (icon, label, color) in _SOURCE_TYPE_MAP.items():
        if source_lower.endswith(ext):
            return (icon, label, color)

    # 关键词检测
    if "notice" in source_lower or "通知" in source_lower:
        return ("📢", "通知", "#f57c00")
    if "policy" in source_lower or "政策" in source_lower:
        return ("📜", "政策", "#7b1fa2")

    return ("📄", "文档", "#757575")


# ── 关键词高亮 ──────────────────────────────────────────────

def _highlight_snippet(snippet: str, keywords: list[str]) -> str:
    """
    在摘要文本中高亮关键词

    Args:
        snippet: 摘要文本
        keywords: 需要高亮的关键词列表

    Returns:
        str: 高亮后的 HTML 文本
    """
    if not keywords or not snippet:
        return snippet

    result = snippet
    for kw in keywords:
        if not kw:
            continue
        # 使用 <mark> 标签高亮，避免重复替换
        pattern = re.compile(re.escape(kw), re.IGNORECASE)
        result = pattern.sub(
            f'<mark style="background-color: #fff9c4; padding: 0 0.15rem; border-radius: 2px;">{kw}</mark>',
            result,
        )
    return result


# ── 相关度分数徽章 ──────────────────────────────────────────────

def _relevance_badge(score: float) -> str:
    """
    生成相关度分数 HTML 徽章

    Args:
        score: 相关度分数 (0.0 ~ 1.0)

    Returns:
        str: HTML 徽章
    """
    pct = int(score * 100)
    if score >= 0.85:
        bg = "#28a745"
    elif score >= 0.7:
        bg = "#ffc107"
    elif score >= 0.5:
        bg = "#fd7e14"
    else:
        bg = "#6c757d"

    return (
        f"<span style='"
        f"background-color: {bg}; color: white; "
        f"padding: 0.1rem 0.5rem; border-radius: 12px; "
        f"font-size: 0.7rem; font-weight: 600; white-space: nowrap;"
        f"'>{pct}%</span>"
    )


# ── 单张来源卡片 ──────────────────────────────────────────────

def render_source_card(
    title: str = "未知来源",
    source: str = "",
    date: str = "",
    snippet: str = "",
    index: int = 0,
    clickable: bool = False,
    relevance: Optional[float] = None,
    highlight_keywords: Optional[list[str]] = None,
    compact: bool = False,
) -> bool:
    """
    渲染单张来源引用卡片

    Args:
        title: 来源标题
        source: 来源路径/URL
        date: 发布日期
        snippet: 内容摘要片段
        index: 编号（0 则不显示编号）
        clickable: 是否显示"查看原文"按钮
        relevance: 相关度分数 (0.0~1.0)，None 则不显示
        highlight_keywords: 需要在摘要中高亮的关键词
        compact: 紧凑模式（更小的卡片）

    Returns:
        bool: 用户是否点击了"查看原文"
    """
    # 来源类型
    type_icon, type_label, type_color = _detect_source_type(source)

    # 编号标签
    num_badge = (
        f"<span style='background-color: #1976d2; color: white; "
        f"padding: 0.1rem 0.45rem; border-radius: 50%; "
        f"font-size: 0.75rem; font-weight: 600; margin-right: 0.4rem;'>"
        f"{index}</span>"
        if index else ""
    )

    # 相关度徽章
    rel_badge = _relevance_badge(relevance) if relevance is not None else ""

    # 类型标签
    type_badge = (
        f"<span style='color: {type_color}; font-size: 0.75rem; "
        f"margin-left: 0.5rem;'>{type_icon} {type_label}</span>"
    )

    # 来源路径
    source_line = ""
    if source:
        font_size = "0.75rem" if compact else "0.8rem"
        source_line = (
            f"<div style='color: #888; font-size: {font_size}; margin-top: 0.2rem;'>"
            f"📄 {source}</div>"
        )

    # 日期
    date_line = ""
    if date:
        date_line = (
            f"<div style='color: #aaa; font-size: 0.75rem; margin-top: 0.15rem;'>"
            f"📅 {date}</div>"
        )

    # 摘要（支持关键词高亮）
    snippet_block = ""
    if snippet:
        display_snippet = _highlight_snippet(snippet, highlight_keywords or [])
        padding = "0.5rem" if compact else "0.8rem"
        font_size = "0.8rem" if compact else "0.85rem"
        snippet_block = (
            f"<div style='"
            f"border-left: 3px solid #e0e0e0; "
            f"padding-left: {padding}; margin-top: 0.4rem; "
            f"color: #555; font-size: {font_size}; line-height: 1.5;"
            f"'>{display_snippet}</div>"
        )

    # 卡片尺寸
    card_padding = "0.5rem 0.8rem" if compact else "0.8rem 1rem"
    title_size = "0.85rem" if compact else "0.9rem"

    st.markdown(
        f"""
        <div style="
            border: 1px solid #e8e8e8;
            border-radius: 8px;
            padding: {card_padding};
            margin: 0.3rem 0;
            background-color: #fafbfc;
        ">
            <div style="display: flex; align-items: center; flex-wrap: wrap; gap: 0.3rem;">
                {num_badge}
                <span style="font-weight: 600; color: #1e3a5f; font-size: {title_size};">
                    {title}
                </span>
                {type_badge}
                <div style="flex-grow: 1;"></div>
                {rel_badge}
            </div>
            {source_line}
            {date_line}
            {snippet_block}
        </div>
        """,
        unsafe_allow_html=True,
    )

    # 查看原文按钮（紧凑模式下不显示）
    clicked = False
    if clickable and source and not compact:
        if st.button(
            "🔗 查看原文",
            key=f"source_{index}_{title[:10]}",
            use_container_width=False,
        ):
            clicked = True

    return clicked


# ── 来源卡片列表 ──────────────────────────────────────────────

def render_source_cards(
    sources: list[dict],
    title: str = "📎 来源引用",
    show_header: bool = True,
    clickable: bool = False,
    highlight_keywords: Optional[list[str]] = None,
    compact: bool = False,
) -> Optional[int]:
    """
    渲染来源引用卡片列表

    Args:
        sources: 来源列表，每项 dict 包含:
            {"title": str, "source": str, "date": str, "snippet": str,
             "relevance": float (可选)}
        title: 区域标题（None 则不显示）
        show_header: 是否显示标题
        clickable: 卡片是否可点击
        highlight_keywords: 高亮关键词
        compact: 紧凑模式

    Returns:
        int 或 None: 被点击的卡片索引
    """
    if not sources:
        return None

    if show_header:
        st.markdown(f"### {title}")

    clicked_idx = None

    for i, src in enumerate(sources, 1):
        was_clicked = render_source_card(
            title=src.get("title", "未知来源"),
            source=src.get("source", ""),
            date=src.get("date", ""),
            snippet=src.get("snippet", ""),
            index=i,
            clickable=clickable,
            relevance=src.get("relevance"),
            highlight_keywords=highlight_keywords,
            compact=compact,
        )
        if was_clicked:
            clicked_idx = i - 1

    return clicked_idx


# ── 内联来源引用（紧凑版，用于消息气泡内）────────────────────────

def render_inline_sources(
    sources: list[dict],
    highlight_keywords: Optional[list[str]] = None,
) -> None:
    """
    渲染消息气泡内的内联来源引用（紧凑展示）

    Args:
        sources: 来源列表
        highlight_keywords: 高亮关键词
    """
    if not sources:
        return

    st.markdown("---")
    st.markdown("**📎 来源引用：**")

    for i, src in enumerate(sources, 1):
        title = src.get("title", "未知来源")
        source = src.get("source", "")
        date = src.get("date", "")
        snippet = src.get("snippet", "")
        relevance = src.get("relevance")

        # 标题行：编号 + 标题 + 相关度 + 类型
        type_icon, type_label, _ = _detect_source_type(source)
        header_parts = [f"[{i}] {title}"]
        if relevance is not None:
            pct = int(relevance * 100)
            header_parts.append(f"· {pct}%")
        header_parts.append(f"· {type_icon} {type_label}")

        with st.expander(" ".join(header_parts)):
            col1, col2 = st.columns(2)
            with col1:
                if source:
                    st.caption(f"📄 {source}")
            with col2:
                if date:
                    st.caption(f"📅 {date}")
            if snippet:
                display_snippet = _highlight_snippet(snippet, highlight_keywords or [])
                st.markdown(f"> {display_snippet}")


# ── 来源加载骨架屏 ──────────────────────────────────────────────

def render_sources_loading(count: int = 3) -> None:
    """
    渲染来源引用加载骨架屏

    Args:
        count: 骨架卡片数量
    """
    st.markdown("### 📎 来源引用")
    for _ in range(count):
        st.markdown(
            """
            <div style="
                border: 1px solid #e8e8e8;
                border-radius: 8px;
                padding: 0.8rem 1rem;
                margin: 0.3rem 0;
                background-color: #fafbfc;
            ">
                <div style="
                    background: linear-gradient(90deg, #f0f0f0 25%, #e0e0e0 50%, #f0f0f0 75%);
                    background-size: 200% 100%;
                    height: 0.9rem;
                    border-radius: 4px;
                    width: 60%;
                    margin-bottom: 0.5rem;
                "></div>
                <div style="
                    background: linear-gradient(90deg, #f0f0f0 25%, #e0e0e0 50%, #f0f0f0 75%);
                    background-size: 200% 100%;
                    height: 0.7rem;
                    border-radius: 4px;
                    width: 80%;
                    margin-bottom: 0.3rem;
                "></div>
                <div style="
                    background: linear-gradient(90deg, #f0f0f0 25%, #e0e0e0 50%, #f0f0f0 75%);
                    background-size: 200% 100%;
                    height: 0.7rem;
                    border-radius: 4px;
                    width: 40%;
                "></div>
            </div>
            """,
            unsafe_allow_html=True,
        )


# ── 来源空状态 ──────────────────────────────────────────────

def render_sources_empty(message: str = "暂无来源引用") -> None:
    """
    渲染来源引用空状态

    Args:
        message: 空状态提示文本
    """
    st.markdown(
        f"""
        <div style="
            text-align: center;
            padding: 1.5rem;
            border: 2px dashed #e0e0e0;
            border-radius: 8px;
            background-color: #fafafa;
            margin: 0.5rem 0;
        ">
            <div style="font-size: 1.5rem; margin-bottom: 0.3rem;">📎</div>
            <div style="color: #999; font-size: 0.9rem;">{message}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
