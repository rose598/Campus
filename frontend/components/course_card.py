"""
课程概览卡片组件（course_card）
将课程信息以可视化卡片形式展示
包含课程基本信息、资料统计、学习进度
供课程资料页、课程详情页复用
"""

from typing import Optional

import streamlit as st


# ── 课程概览卡片 ──────────────────────────────────────────────

def render_course_card(
    course_code: str = "",
    course_name: str = "未知课程",
    teacher: str = "",
    semester: str = "",
    credits: float = 0,
    material_count: int = 0,
    summary_ready: bool = False,
    tags: Optional[list[str]] = None,
    index: int = 0,
) -> bool:
    """
    渲染单个课程概览卡片

    Args:
        course_code: 课程代码（如 CS201）
        course_name: 课程名称
        teacher: 授课教师
        semester: 学期（如 2025-2026-2）
        credits: 学分
        material_count: 已上传资料数
        summary_ready: AI 总结是否已生成
        tags: 标签列表（如 ["必修", "核心"]）
        index: 编号（用于 widget key 区分）

    Returns:
        bool: 用户是否点击了"查看详情"
    """
    # 标签 HTML
    tags_html = ""
    if tags:
        tags_html = "".join(
            f'<span style="'
            f"background-color: #e3f2fd; color: #1976d2; "
            f"padding: 0.1rem 0.45rem; border-radius: 10px; "
            f"font-size: 0.75rem; margin-right: 0.25rem;"
            f'">{tag}</span>'
            for tag in tags
        )

    # 学分徽章
    credits_badge = ""
    if credits:
        credits_badge = (
            f"<span style='"
            f"background-color: #f57c00; color: white; "
            f"padding: 0.15rem 0.5rem; border-radius: 12px; "
            f"font-size: 0.75rem; font-weight: 600;"
            f"'>{credits} 学分</span>"
        )

    # 资料统计
    material_icon = "📄" if material_count > 0 else "📭"
    material_text = f"{material_count} 份资料" if material_count > 0 else "暂无资料"

    # 总结状态
    summary_badge = ""
    if summary_ready:
        summary_badge = (
            "<span style='"
            "background-color: #28a745; color: white; "
            "padding: 0.1rem 0.4rem; border-radius: 10px; "
            "font-size: 0.7rem; font-weight: 600;"
            "'>✅ 总结已生成</span>"
        )
    elif material_count > 0:
        summary_badge = (
            "<span style='"
            "background-color: #ffc107; color: #333; "
            "padding: 0.1rem 0.4rem; border-radius: 10px; "
            "font-size: 0.7rem; font-weight: 600;"
            "'>⏳ 待生成总结</span>"
        )

    # 教师/学期信息
    info_parts = []
    if teacher:
        info_parts.append(f"👨‍🏫 {teacher}")
    if semester:
        info_parts.append(f"📅 {semester}")
    info_line = " &nbsp;&nbsp; ".join(info_parts)

    st.markdown(
        f"""
        <div class="gc-card" style="
            border: 1px solid #e0e0e0;
            border-radius: 10px;
            padding: 1rem 1.2rem;
            margin: 0.5rem 0;
            background-color: white;
            box-shadow: 0 1px 3px rgba(0,0,0,0.05);
        ">
            <div style="display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 0.5rem;">
                <div style="flex: 1;">
                    <div style="display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap;">
                        <span style="font-size: 1.05rem; font-weight: 600; color: #1e3a5f;">
                            📚 {course_name}
                        </span>
                        {credits_badge}
                        {summary_badge}
                    </div>
                    <div style="color: #888; font-size: 0.8rem; margin-top: 0.3rem;">
                        {course_code} &nbsp;|&nbsp; {info_line}
                    </div>
                    <div style="margin-top: 0.4rem;">
                        {tags_html}
                    </div>
                </div>
                <div style="
                    text-align: right;
                    color: #666;
                    font-size: 0.85rem;
                ">
                    {material_icon} {material_text}
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # 查看详情按钮
    clicked = False
    if st.button(
        "📋 查看详情",
        key=f"course_detail_{index}_{course_code}",
        use_container_width=True,
    ):
        clicked = True

    return clicked


# ── 课程卡片列表 ──────────────────────────────────────────────

def render_course_cards(
    courses: list[dict],
    title: str = "📋 已入库课程",
    show_header: bool = True,
) -> Optional[int]:
    """
    渲染课程卡片列表

    Args:
        courses: 课程列表，每项 dict 包含 render_course_card 所需参数
        title: 区域标题（None 则不显示）
        show_header: 是否显示标题

    Returns:
        int 或 None: 被点击的课程索引
    """
    if not courses:
        return None

    if show_header:
        st.markdown(f"### {title}")
        st.caption(f"共 {len(courses)} 门课程")

    clicked_idx = None

    for i, course in enumerate(courses):
        was_clicked = render_course_card(
            course_code=course.get("course_code", ""),
            course_name=course.get("course_name", "未知课程"),
            teacher=course.get("teacher", ""),
            semester=course.get("semester", ""),
            credits=course.get("credits", 0),
            material_count=course.get("material_count", 0),
            summary_ready=course.get("summary_ready", False),
            tags=course.get("tags"),
            index=i,
        )
        if was_clicked:
            clicked_idx = i

    return clicked_idx


# ── 课程总结卡片 ──────────────────────────────────────────────

def render_summary_card(
    course_name: str = "未知课程",
    outline: str = "",
    key_points: Optional[list[str]] = None,
    exam_focus: str = "",
    references: Optional[list[str]] = None,
) -> None:
    """
    渲染课程 AI 总结卡片

    Args:
        course_name: 课程名称
        outline: 课程大纲摘要
        key_points: 重点章节列表
        exam_focus: 考核方式/重点
        references: 参考资料列表
    """
    st.markdown(
        f"""
        <div style="
            border: 2px solid #1976d2;
            border-radius: 12px;
            padding: 1.2rem;
            margin: 0.8rem 0;
            background-color: #f8faff;
        ">
            <div style="font-size: 1.1rem; font-weight: 600; color: #1e3a5f; margin-bottom: 0.8rem;">
                📊 {course_name} — AI 课程总结
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # 课程大纲
    if outline:
        st.markdown("**📝 课程大纲**")
        st.markdown(f"> {outline}")

    # 重点章节
    if key_points:
        st.markdown("**🔑 重点章节**")
        for point in key_points:
            st.markdown(f"- {point}")

    # 考核重点
    if exam_focus:
        st.markdown("**📝 考核方式与重点**")
        st.info(exam_focus)

    # 参考资料
    if references:
        st.markdown("**📚 参考资料**")
        for ref in references:
            st.markdown(f"- {ref}")


# ── 课程空状态 ──────────────────────────────────────────────

def render_course_empty() -> None:
    """渲染课程列表空状态"""
    st.markdown(
        """
        <div style="
            text-align: center;
            padding: 3rem 1rem;
            border: 2px dashed #e0e0e0;
            border-radius: 12px;
            background-color: #fafafa;
            margin: 1rem 0;
        ">
            <div style="font-size: 3rem; margin-bottom: 0.5rem;">📚</div>
            <div style="font-size: 1.1rem; font-weight: 600; color: #333; margin-bottom: 0.3rem;">
                暂无已入库课程
            </div>
            <div style="font-size: 0.9rem; color: #999;">
                上传课程资料后将在此展示课程列表和 AI 总结
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
