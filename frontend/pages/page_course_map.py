"""
课程地图页
展示完整的课程知识图谱（Pyvis 交互式图）
支持搜索课程、节点高亮、缩放拖拽
"""

import json
from pathlib import Path

import streamlit as st

from global_styles import bootstrap_page

from state_sync import get_state, set_state


# 注意：页面配置已在 app.py 中统一设置，子页面不再重复调用 st.set_page_config()


# ── 数据加载 ──────────────────────────────────────────────
@st.cache_data
def load_courses() -> list[dict]:
    """加载课程数据（带缓存）"""
    data_path = Path(__file__).parent.parent.parent / "data" / "mock_courses.json"
    if data_path.exists():
        with open(data_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def build_course_graph(courses: list[dict]) -> dict:
    """构建课程图结构（邻接表）"""
    graph = {}
    course_map = {c["code"]: c for c in courses}

    for course in courses:
        code = course["code"]
        if code not in graph:
            graph[code] = {"course": course, "prerequisites": [], "successors": []}

        # 添加先修关系
        for prereq_code in course.get("prerequisites", []):
            if prereq_code in course_map:
                graph[code]["prerequisites"].append(prereq_code)
                if prereq_code not in graph:
                    graph[prereq_code] = {
                        "course": course_map[prereq_code],
                        "prerequisites": [],
                        "successors": [],
                    }
                graph[prereq_code]["successors"].append(code)

    return graph


# ── 页面渲染 ──────────────────────────────────────────────
def render_header():
    """渲染页面头部"""
    st.markdown(
        """
        <div style="text-align: center; padding: 1rem 0;">
            <h1>🗺️ 课程地图</h1>
            <p style="color: #666;">探索课程之间的先修关系，规划你的学习路径</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_search_bar(courses: list[dict]):
    """渲染搜索栏（widget 值自动存入 session_state，无需返回值）"""
    col1, col2 = st.columns([3, 1])

    with col1:
        st.text_input(
            "🔍 搜索课程",
            placeholder="输入课程名称或代码...",
            key="course_search",
        )

    with col2:
        # 学期筛选
        semesters = ["全部"] + sorted(set(c["semester"] for c in courses))
        st.selectbox(
            "学期筛选",
            semesters,
            key="semester_filter",
        )


def filter_courses(
    courses: list[dict],
    query: str,
    semester: str,
) -> list[dict]:
    """根据搜索条件过滤课程"""
    filtered = courses

    # 按搜索词过滤
    if query:
        query_lower = query.lower()
        filtered = [
            c
            for c in filtered
            if query_lower in c["name"].lower() or query_lower in c["code"].lower()
        ]

    # 按学期过滤
    if semester != "全部":
        filtered = [c for c in filtered if c["semester"] == semester]

    return filtered


def render_course_list(filtered_courses: list[dict]):
    """渲染课程列表"""
    if not filtered_courses:
        st.warning("未找到匹配的课程，请尝试其他搜索条件。")
        return

    st.markdown(f"**共找到 {len(filtered_courses)} 门课程**")

    # 按学期分组显示
    fall_courses = [c for c in filtered_courses if c["semester"] == "秋季"]
    spring_courses = [c for c in filtered_courses if c["semester"] == "春季"]

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### 🍂 秋季学期")
        for course in fall_courses:
            render_course_card(course)

    with col2:
        st.markdown("### 🌸 春季学期")
        for course in spring_courses:
            render_course_card(course)


def render_course_card(course: dict):
    """渲染单个课程卡片"""
    with st.container():
        st.markdown(
            f"""
            <div style="
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                padding: 1rem;
                margin: 0.5rem 0;
                background-color: white;
            ">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <div>
                        <strong style="color: #1e3a5f;">{course['name']}</strong>
                        <span style="color: #999; margin-left: 0.5rem;">{course['code']}</span>
                    </div>
                    <span style="
                        background-color: #e3f2fd;
                        color: #1976d2;
                        padding: 0.2rem 0.5rem;
                        border-radius: 4px;
                        font-size: 0.8rem;
                    ">{course['credits']} 学分</span>
                </div>
                <div style="margin-top: 0.5rem; color: #666; font-size: 0.9rem;">
                    👨‍🏫 {course['teacher']}
                </div>
                <div style="margin-top: 0.3rem; color: #999; font-size: 0.85rem;">
                    {course['description'][:50]}{'...' if len(course['description']) > 50 else ''}
                </div>
                <div style="margin-top: 0.5rem;">
                    {''.join(f'<span style="background-color: #f5f5f5; padding: 0.1rem 0.3rem; border-radius: 3px; margin-right: 0.3rem; font-size: 0.8rem;">先修: {p}</span>' for p in course.get('prerequisites', [])) or '<span style="color: #4caf50; font-size: 0.8rem;">无先修要求</span>'}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # 点击查看详情的按钮
        if st.button(
            f"查看详情: {course['name']}",
            key=f"detail_{course['code']}",
            use_container_width=True,
        ):
            set_state("selected_course", course["code"])
            set_state("current_page", "course_materials")
            st.rerun()


def render_graph_placeholder():
    """渲染图谱可视化占位区域"""
    st.divider()
    st.markdown("### 📊 课程关系图谱")

    st.info(
        """
        **图谱可视化功能开发中...**

        即将支持：
        - 🔵 交互式课程节点（点击查看详情）
        - ➡️ 先修关系连线（带箭头指示方向）
        - 🔍 节点搜索高亮
        - 📏 缩放和拖拽控制
        - 💡 详情浮窗预览

        _预计 Day 5 完成图谱可视化组件_
        """
    )

    # 占位图谱区域
    st.markdown(
        """
        <div style="
            border: 2px dashed #ccc;
            border-radius: 8px;
            height: 400px;
            display: flex;
            justify-content: center;
            align-items: center;
            background-color: #fafafa;
        ">
            <div style="text-align: center; color: #999;">
                <div style="font-size: 3rem;">🗺️</div>
                <div>课程知识图谱</div>
                <div style="font-size: 0.8rem;">Pyvis 交互式图谱即将上线</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_stats(courses: list[dict]):
    """渲染统计信息"""
    st.divider()
    st.markdown("### 📈 课程统计")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("课程总数", len(courses))

    with col2:
        total_credits = sum(c["credits"] for c in courses)
        st.metric("总学分", f"{total_credits:.1f}")

    with col3:
        teachers = len(set(c["teacher"] for c in courses))
        st.metric("授课教师", f"{teachers} 人")

    with col4:
        prereq_count = sum(len(c.get("prerequisites", [])) for c in courses)
        st.metric("先修关系数", prereq_count)


def render_onboarding_hint():
    """渲染冷启动引导提示"""
    if not get_state("onboarding_completed", False):
        st.markdown(
            """
            <div style="
                background-color: #fff3e0;
                border-left: 4px solid #ff9800;
                padding: 1rem;
                border-radius: 0 8px 8px 0;
                margin: 1rem 0;
            ">
                <strong>👋 欢迎新用户！</strong>
                <p style="margin: 0.5rem 0 0 0; color: #666;">
                    第一次使用？点击下方按钮开始引导，系统将帮你：
                </p>
                <ul style="color: #666; margin: 0.5rem 0;">
                    <li>选择你的专业方向</li>
                    <li>浏览课程体系</li>
                    <li>标记已修课程</li>
                    <li>生成个性化图谱</li>
                </ul>
            </div>
            """,
            unsafe_allow_html=True,
        )

        if st.button("🚀 开始新手引导", type="primary", use_container_width=True):
            set_state("onboarding_step", 0)
            set_state("current_page", "onboarding")
            st.rerun()


# ── 主入口 ──────────────────────────────────────────────
def main():
    """课程地图页主入口"""
    bootstrap_page()
    # 加载数据
    courses = load_courses()
    graph = build_course_graph(courses)

    # 渲染页面
    render_header()
    render_onboarding_hint()
    render_search_bar(courses)

    # 处理搜索
    query = st.session_state.get("course_search", "")
    semester = st.session_state.get("semester_filter", "全部")
    filtered = filter_courses(courses, query, semester)

    # 渲染内容
    render_course_list(filtered)
    render_graph_placeholder()
    render_stats(courses)


if __name__ == "__main__":
    main()
