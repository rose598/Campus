"""
来源引用卡片组件（source_card）
将 RAG 检索到的文档来源以可视化卡片形式展示
供知识问答页、活动推送页、课程资料页复用
"""

from typing import Optional

import streamlit as st


# ── 单张来源卡片 ──────────────────────────────────────────────

def render_source_card(
    title: str = "未知来源",
    source: str = "",
    date: str = "",
    snippet: str = "",
    index: int = 0,
    clickable: bool = False,
) -> bool:
    """
    渲染单张来源引用卡片

    Args:
        title: 来源标题（如 "教务处关于补考报名的通知"）
        source: 来源路径/URL（如 "jwc.example.edu.cn/notice/2026-01"）
        date: 发布日期（如 "2026-01-15"）
        snippet: 内容摘要片段
        index: 编号（0 则不显示编号）
        clickable: 是否显示"查看原文"按钮

    Returns:
        bool: 用户是否点击了"查看原文"
    """
    # 编号标签
    num_badge = f"<span style='background-color: #1976d2; color: white; padding: 0.1rem 0.45rem; border-radius: 50%; font-size: 0.75rem; font-weight: 600; margin-right: 0.4rem;'>{index}</span>" if index else ""

    # 来源链接
    source_line = ""
    if source:
        source_line = f"""
        <div style="color: #888; font-size: 0.8rem; margin-top: 0.3rem;">
            📄 {source}
        </div>
        """

    # 日期
    date_line = ""
    if date:
        date_line = f"""
        <div style="color: #aaa; font-size: 0.75rem; margin-top: 0.2rem;">
            📅 {date}
        </div>
        """

    # 摘要
    snippet_block = ""
    if snippet:
        snippet_block = f"""
        <div style="
            border-left: 3px solid #e0e0e0;
            padding-left: 0.8rem;
            margin-top: 0.6rem;
            color: #555;
            font-size: 0.85rem;
            line-height: 1.5;
        ">
            {snippet}
        </div>
        """

    st.markdown(
        f"""
        <div style="
            border: 1px solid #e8e8e8;
            border-radius: 8px;
            padding: 0.8rem 1rem;
            margin: 0.4rem 0;
            background-color: #fafbfc;
            transition: box-shadow 0.2s;
        ">
            <div style="display: flex; align-items: center;">
                {num_badge}
                <span style="font-weight: 600; color: #1e3a5f; font-size: 0.9rem;">
                    {title}
                </span>
            </div>
            {source_line}
            {date_line}
            {snippet_block}
        </div>
        """,
        unsafe_allow_html=True,
    )

    # 查看原文按钮
    clicked = False
    if clickable and source:
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
) -> Optional[int]:
    """
    渲染来源引用卡片列表

    Args:
        sources: 来源列表，每项 dict 包含:
            {"title": str, "source": str, "date": str, "snippet": str}
        title: 区域标题（None 则不显示）
        show_header: 是否显示"来源引用"标题
        clickable: 卡片是否可点击

    Returns:
        int 或 None: 被点击的卡片索引（无点击返回 None）
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
        )
        if was_clicked:
            clicked_idx = i - 1

    return clicked_idx


# ── 内联来源引用（紧凑版，用于消息气泡内）────────────────────────

def render_inline_sources(sources: list[dict]) -> None:
    """
    渲染消息气泡内的内联来源引用（紧凑展示）

    Args:
        sources: 来源列表
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

        with st.expander(f"[{i}] {title}"):
            if source:
                st.caption(f"📄 {source}")
            if date:
                st.caption(f"📅 {date}")
            if snippet:
                st.markdown(f"> {snippet}")
