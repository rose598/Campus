"""
冷启动引导页（05_onboarding）
新用户兴趣选择 → 专业方向 → 已修课程标记 → 进入首页
"""

import streamlit as st

from state_sync import get_state, set_state, update_user_profile, mark_onboarding_completed


# ── 步骤配置 ──────────────────────────────────────────────

STEPS = [
    {"key": "welcome",     "label": "欢迎",     "icon": "👋"},
    {"key": "major",       "label": "专业方向", "icon": "🎓"},
    {"key": "interests",   "label": "兴趣选择", "icon": "🎯"},
    {"key": "courses",     "label": "已修课程", "icon": "📚"},
    {"key": "done",        "label": "完成",     "icon": "✅"},
]

MAJOR_OPTIONS = [
    "计算机科学与技术",
    "软件工程",
    "人工智能",
    "数据科学与大数据",
    "信息安全",
    "其他",
]

INTEREST_TAGS = [
    "人工智能", "机器学习", "深度学习", "计算机视觉", "NLP",
    "算法竞赛", "系统架构", "数据库", "网络安全", "云计算",
    "前端开发", "后端开发", "移动开发", "游戏开发", "区块链",
]


# ── 页面渲染 ──────────────────────────────────────────────

def render_progress_bar():
    """渲染步骤进度条"""
    current_step = get_state("onboarding_step", 0)

    cols = st.columns(len(STEPS))
    for i, step in enumerate(STEPS):
        with cols[i]:
            is_done = i < current_step
            is_current = i == current_step

            bg_color = "#28a745" if is_done else ("#1976d2" if is_current else "#e0e0e0")
            text_color = "white" if is_done or is_current else "#999"

            st.markdown(
                f"""
                <div style="
                    text-align: center;
                    padding: 0.5rem;
                    background-color: {bg_color};
                    color: {text_color};
                    border-radius: 8px;
                    font-size: 0.85rem;
                    font-weight: {'600' if is_current else '400'};
                ">
                    {step['icon']} {step['label']}
                </div>
                """,
                unsafe_allow_html=True,
            )


def render_step_welcome():
    """渲染欢迎步骤"""
    st.markdown(
        """
        ### 👋 欢迎使用 GraphCampus！

        这是一个智慧校园助手，可以帮你：
        - 📡 **活动推送**：根据你的兴趣推荐讲座、竞赛、科研机会
        - ❓ **知识问答**：快速回答保研/转专业/选课等校园问题
        - 📚 **课程总结**：自动整理课件资料，生成结构化总结

        接下来花 1 分钟完善你的个人画像，让推荐更精准！
        """
    )

    if st.button("🚀 开始设置", type="primary", use_container_width=True):
        set_state("onboarding_step", 1)
        st.rerun()

    if st.button("跳过引导", use_container_width=True):
        mark_onboarding_completed()
        set_state("current_page", "course_map")
        st.rerun()


def render_step_major():
    """渲染专业选择步骤"""
    st.markdown("### 🎓 选择你的专业方向")

    selected_major = st.selectbox(
        "专业",
        MAJOR_OPTIONS,
        key="onboarding_major_select",
    )

    col_back, col_next = st.columns(2)

    with col_back:
        if st.button("← 上一步", use_container_width=True):
            set_state("onboarding_step", 0)
            st.rerun()

    with col_next:
        if st.button("下一步 →", type="primary", use_container_width=True):
            update_user_profile(major=selected_major)
            set_state("onboarding_step", 2)
            st.rerun()


def render_step_interests():
    """渲染兴趣选择步骤"""
    st.markdown("### 🎯 选择你感兴趣的方向（可多选）")

    selected_interests = st.multiselect(
        "兴趣方向",
        INTEREST_TAGS,
        default=get_state("onboarding_selected_interests", []),
        key="onboarding_interests_select",
    )

    col_back, col_next = st.columns(2)

    with col_back:
        if st.button("← 上一步", use_container_width=True):
            set_state("onboarding_step", 1)
            st.rerun()

    with col_next:
        if st.button("下一步 →", type="primary", use_container_width=True):
            update_user_profile(interests=selected_interests)
            set_state("onboarding_step", 3)
            st.rerun()


def render_step_courses():
    """渲染已修课程标记步骤"""
    st.markdown("### 📚 标记你已修的课程（可跳过）")

    st.info("课程数据加载后将在此展示可选课程列表，当前为占位状态。")

    # 占位课程列表
    sample_courses = [
        "高等数学", "线性代数", "数据结构", "算法设计",
        "操作系统", "计算机网络", "数据库原理", "软件工程",
    ]

    selected_courses = st.multiselect(
        "已修课程",
        sample_courses,
        key="onboarding_courses_select",
    )

    col_back, col_next = st.columns(2)

    with col_back:
        if st.button("← 上一步", use_container_width=True):
            set_state("onboarding_step", 2)
            st.rerun()

    with col_next:
        if st.button("完成设置 ✅", type="primary", use_container_width=True):
            update_user_profile(completed_courses=selected_courses)
            mark_onboarding_completed()
            set_state("current_page", "course_map")
            st.rerun()


# ── 主入口 ──────────────────────────────────────────────

def main():
    """冷启动引导页主入口"""
    st.markdown(
        """
        <div style="text-align: center; padding: 0.5rem 0;">
            <h1>🚀 新手引导</h1>
        </div>
        """,
        unsafe_allow_html=True,
    )

    render_progress_bar()
    st.divider()

    current_step = get_state("onboarding_step", 0)

    if current_step == 0:
        render_step_welcome()
    elif current_step == 1:
        render_step_major()
    elif current_step == 2:
        render_step_interests()
    elif current_step >= 3:
        render_step_courses()


if __name__ == "__main__":
    main()
