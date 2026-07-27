"""
首页（00_home）
Day 20: 集成三功能入口 + 个人统计 + 快捷操作
作为应用默认着陆页，引导用户进入各功能模块
"""

import streamlit as st

from state_sync import get_state, set_state, get_user_profile, is_onboarding_completed


# ── 功能入口配置 ──────────────────────────────────────────────
FEATURE_ENTRIES = [
    {
        "key": "activity_push",
        "icon": "📡",
        "title": "活动智能推送",
        "description": "根据你的课程和兴趣，精准推荐匹配的讲座、竞赛和科研机会",
        "color": "#1976d2",
    },
    {
        "key": "campus_qa",
        "icon": "❓",
        "title": "校园知识问答",
        "description": "保研/转专业/选课等政策问题秒回，附带来源引用",
        "color": "#388e3c",
    },
    {
        "key": "course_materials",
        "icon": "📚",
        "title": "课程资料总结",
        "description": "上传课件/大纲/期末资料，AI 自动提取重点并生成结构化总结",
        "color": "#f57c00",
    },
]

# 附加功能入口
EXTRA_ENTRIES = [
    {
        "key": "study_buddy",
        "icon": "🎓",
        "label": "学伴对话",
        "description": "基于课程资料的 RAG 问答",
    },
    {
        "key": "course_map",
        "icon": "🗺️",
        "label": "课程地图",
        "description": "课程关系可视化",
    },
]


# ── 页面渲染 ──────────────────────────────────────────────────

def render_header():
    """渲染欢迎头部"""
    profile = get_user_profile()
    major = profile.get("major")
    interests = profile.get("interests", [])
    completed_courses = profile.get("completed_courses", [])

    # 问候语
    greeting = "欢迎回来" if is_onboarding_completed() else "你好"
    user_label = f"，{major}同学" if major else ""

    st.markdown(
        f"""
        <div style="
            text-align: center;
            padding: 1.5rem 0 1rem;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            border-radius: 16px;
            color: white;
            margin-bottom: 1.5rem;
        ">
            <div style="font-size: 2.5rem; margin-bottom: 0.3rem;">🎓</div>
            <h1 style="margin: 0; color: white;">{greeting}{user_label}！</h1>
            <p style="color: rgba(255,255,255,0.85); margin-top: 0.5rem; font-size: 1.1rem;">
                GraphCampus — 你的智慧校园课程导航助手
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # 用户画像摘要（已完成引导时显示）
    if is_onboarding_completed() and (major or interests or completed_courses):
        _render_profile_summary(major, interests, completed_courses)


def _render_profile_summary(major, interests, completed_courses):
    """渲染用户画像摘要卡片"""
    st.markdown("#### 👤 我的画像")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown(f"**🎓 专业**\n\n{major or '未设置'}")

    with col2:
        if interests:
            tags_html = " ".join(
                f"`{tag}`" for tag in interests[:5]
            )
            extra = f" +{len(interests) - 5}" if len(interests) > 5 else ""
            st.markdown(f"**🎯 兴趣方向**\n\n{tags_html}{extra}")
        else:
            st.markdown("**🎯 兴趣方向**\n\n未设置")

    with col3:
        if completed_courses:
            courses_text = "、".join(completed_courses[:4])
            extra = f"等 {len(completed_courses)} 门" if len(completed_courses) > 4 else ""
            st.markdown(f"**📚 已修课程**\n\n{courses_text}{extra}")
        else:
            st.markdown("**📚 已修课程**\n\n未设置")

    st.divider()


def render_feature_cards():
    """渲染三大功能入口卡片"""
    st.markdown("### 🚀 核心功能")
    st.caption("点击卡片进入对应功能模块")

    cols = st.columns(3)

    for i, entry in enumerate(FEATURE_ENTRIES):
        with cols[i]:
            # 卡片 HTML
            st.markdown(
                f"""
                <div style="
                    border: 2px solid {entry['color']};
                    border-radius: 12px;
                    padding: 1.2rem;
                    background-color: white;
                    min-height: 180px;
                    box-shadow: 0 2px 8px rgba(0,0,0,0.08);
                ">
                    <div style="font-size: 2.5rem; margin-bottom: 0.5rem;">
                        {entry['icon']}
                    </div>
                    <div style="
                        font-size: 1.1rem;
                        font-weight: 600;
                        color: {entry['color']};
                        margin-bottom: 0.4rem;
                    ">
                        {entry['title']}
                    </div>
                    <div style="
                        font-size: 0.85rem;
                        color: #666;
                        line-height: 1.5;
                    ">
                        {entry['description']}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            # 进入按钮
            if st.button(
                f"进入 {entry['title']}",
                key=f"home_enter_{entry['key']}",
                use_container_width=True,
                type="primary",
            ):
                set_state("current_page", entry["key"])
                st.rerun()


def render_stats_section():
    """渲染统计概览"""
    st.divider()
    st.markdown("### 📊 数据概览")

    # 动态统计
    qa_history = get_state("qa_chat_history", [])
    qa_count = sum(1 for m in qa_history if m.get("role") == "user")

    buddy_history = get_state("buddy_chat_history", [])
    buddy_count = sum(1 for m in buddy_history if m.get("role") == "user")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("推荐活动", "12 个", help="基于你的兴趣匹配")
    with col2:
        st.metric("知识问答", f"{qa_count} 次", help="累计提问次数")
    with col3:
        st.metric("入库课程", "5 门", help="已上传资料的课程")
    with col4:
        st.metric("学伴对话", f"{buddy_count} 次", help="课程资料问答次数")


def render_extra_entries():
    """渲染附加功能入口"""
    st.divider()
    st.markdown("### 🔧 更多功能")

    cols = st.columns(len(EXTRA_ENTRIES))
    for i, entry in enumerate(EXTRA_ENTRIES):
        with cols[i]:
            col_icon, col_info, col_btn = st.columns([1, 3, 2])
            with col_icon:
                st.markdown(f"### {entry['icon']}")
            with col_info:
                st.markdown(f"**{entry['label']}**")
                st.caption(entry["description"])
            with col_btn:
                if st.button(
                    "进入",
                    key=f"home_extra_{entry['key']}",
                    use_container_width=True,
                ):
                    set_state("current_page", entry["key"])
                    st.rerun()


def render_onboarding_hint():
    """渲染新手引导提示（未完成时显示）"""
    # 刚完成引导时显示成功提示
    just_completed = get_state("onboarding_just_completed", False)
    if just_completed:
        st.success(
            "🎉 **设置完成！** 你的个人画像已保存，活动推荐将更精准。"
        )
        set_state("onboarding_just_completed", False)

    if is_onboarding_completed():
        return

    st.divider()
    st.info(
        "💡 **提示**：你还没有完成新手引导，完善个人信息后推荐会更精准！"
    )
    if st.button("🚀 开始新手引导", key="home_start_onboarding"):
        set_state("current_page", "onboarding")
        st.rerun()


# ── 主入口 ──────────────────────────────────────────────────────

def main():
    """首页主入口"""
    render_header()
    render_onboarding_hint()
    render_feature_cards()
    render_stats_section()
    render_extra_entries()


if __name__ == "__main__":
    main()
