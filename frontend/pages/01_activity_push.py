"""
活动智能推送页
基于 PPR 推荐引擎，展示与用户兴趣/课程匹配的活动推荐列表
支持推理链溯源、分数展示、排序筛选
"""

import streamlit as st

from state_sync import get_state
from components.loading_states import render_empty, render_page_state


# ── 示例数据（占位，后续接入 PPR 推荐引擎）────────────────────────────────────

MOCK_ACTIVITIES = [
    {
        "id": "act_001",
        "title": "大模型前沿技术讲座",
        "type": "讲座",
        "date": "2026-07-25",
        "location": "图书馆报告厅",
        "tags": ["人工智能", "深度学习", "NLP"],
        "score": 0.92,
        "reason_chain": ["你的兴趣: 人工智能", "→ 关联方向: 深度学习", "→ 匹配活动: 大模型讲座"],
    },
    {
        "id": "act_002",
        "title": "ACM-ICPC 区域赛选拔",
        "type": "竞赛",
        "date": "2026-08-10",
        "location": "计算机楼机房",
        "tags": ["算法", "竞赛", "数据结构"],
        "score": 0.85,
        "reason_chain": ["你的课程: 数据结构", "→ 关联技能: 算法设计", "→ 匹配活动: ACM 竞赛"],
    },
    {
        "id": "act_003",
        "title": "本科生科研训练计划申报",
        "type": "科研",
        "date": "2026-07-30",
        "location": "线上申报",
        "tags": ["科研", "机器学习", "计算机视觉"],
        "score": 0.78,
        "reason_chain": ["你的兴趣: 人工智能", "→ 关联方向: 计算机视觉", "→ 匹配活动: 科研项目"],
    },
    {
        "id": "act_004",
        "title": "数学建模竞赛培训",
        "type": "竞赛",
        "date": "2026-08-05",
        "location": "数学楼 201",
        "tags": ["数学建模", "优化", "编程"],
        "score": 0.71,
        "reason_chain": ["你的课程: 线性代数", "→ 关联技能: 数学建模", "→ 匹配活动: 建模竞赛"],
    },
]

ACTIVITY_TYPE_FILTER = ["全部", "讲座", "竞赛", "科研"]


# ── 页面渲染 ──────────────────────────────────────────────

def render_header():
    """渲染页面头部"""
    st.markdown(
        """
        <div style="text-align: center; padding: 0.5rem 0;">
            <h1>📡 活动智能推送</h1>
            <p style="color: #666;">基于你的课程和兴趣，为你精准推荐匹配的讲座、竞赛和科研机会</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_filter_bar():
    """渲染筛选/排序工具栏"""
    col_type, col_sort, col_count = st.columns([2, 2, 1])

    with col_type:
        selected_type = st.selectbox(
            "活动类型",
            ACTIVITY_TYPE_FILTER,
            key="activity_type_filter",
        )

    with col_sort:
        sort_by = st.selectbox(
            "排序方式",
            ["推荐分数 ↓", "活动日期 ↑", "活动日期 ↓"],
            key="activity_sort_by",
        )

    with col_count:
        st.metric("推荐数", len(MOCK_ACTIVITIES))

    return selected_type, sort_by


def filter_and_sort_activities(
    activities: list[dict],
    activity_type: str,
    sort_by: str,
) -> list[dict]:
    """筛选并排序活动列表"""
    filtered = activities
    if activity_type != "全部":
        filtered = [a for a in filtered if a["type"] == activity_type]

    if sort_by == "推荐分数 ↓":
        filtered = sorted(filtered, key=lambda x: x["score"], reverse=True)
    elif sort_by == "活动日期 ↑":
        filtered = sorted(filtered, key=lambda x: x["date"])
    elif sort_by == "活动日期 ↓":
        filtered = sorted(filtered, key=lambda x: x["date"], reverse=True)

    return filtered


def render_activity_card(activity: dict):
    """渲染单个活动推荐卡片"""
    score = activity["score"]
    # 分数颜色
    if score >= 0.85:
        score_color = "#28a745"
    elif score >= 0.7:
        score_color = "#ffc107"
    else:
        score_color = "#6c757d"

    # 类型图标
    type_icons = {"讲座": "🎤", "竞赛": "🏆", "科研": "🔬"}
    type_icon = type_icons.get(activity["type"], "📌")

    st.markdown(
        f"""
        <div style="
            border: 1px solid #e0e0e0;
            border-radius: 10px;
            padding: 1.2rem;
            margin: 0.8rem 0;
            background-color: white;
            box-shadow: 0 1px 3px rgba(0,0,0,0.05);
        ">
            <div style="display: flex; justify-content: space-between; align-items: flex-start;">
                <div style="flex: 1;">
                    <div style="font-size: 1.1rem; font-weight: 600; color: #1e3a5f;">
                        {type_icon} {activity['title']}
                    </div>
                    <div style="margin-top: 0.4rem; color: #666; font-size: 0.9rem;">
                        📅 {activity['date']} &nbsp;&nbsp; 📍 {activity['location']}
                    </div>
                    <div style="margin-top: 0.5rem;">
                        {''.join(f'<span style="background-color: #e3f2fd; color: #1976d2; padding: 0.15rem 0.5rem; border-radius: 12px; font-size: 0.8rem; margin-right: 0.3rem;">{tag}</span>' for tag in activity['tags'])}
                    </div>
                </div>
                <div style="
                    background-color: {score_color};
                    color: white;
                    padding: 0.3rem 0.8rem;
                    border-radius: 20px;
                    font-size: 0.9rem;
                    font-weight: 600;
                    white-space: nowrap;
                ">
                    {score:.0%}
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_reason_chain(activity: dict):
    """渲染推理链（为什么推荐这个活动）"""
    st.markdown(f"**🔍 为什么推荐「{activity['title']}」？**")

    chain = activity.get("reason_chain", [])
    if chain:
        for step in chain:
            st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;{step}")
    else:
        st.caption("推理链生成中...")


def render_activities_list(activities: list[dict]):
    """渲染活动推荐列表（含推理链展开）"""
    if not activities:
        render_empty(
            icon="📭",
            title="暂无匹配的活动推荐",
            description="请调整筛选条件或完善你的兴趣画像，推荐将更精准",
        )
        return

    for activity in activities:
        render_activity_card(activity)

        # 推理链（用 expander 折叠）
        with st.expander(f"🔍 查看推理链 — {activity['title']}", expanded=False):
            render_reason_chain(activity)


def render_user_profile_hint():
    """渲染用户兴趣提示（展示当前 PPR 起点）"""
    profile = get_state("user_profile", {})
    interests = profile.get("interests", [])
    completed = profile.get("completed_courses", [])

    if not interests and not completed:
        st.info(
            "💡 **提示**：完善你的兴趣方向和已修课程，推荐将更精准！\n\n"
            "前往 [课程地图](#) 标记已修课程，或在系统设置中配置兴趣方向。"
        )
    else:
        tags = []
        if interests:
            tags += [f"🎯 {i}" for i in interests]
        if completed:
            tags += [f"📚 {c}" for c in completed[:5]]

        st.markdown(
            f"**你的 PPR 起点：** {' · '.join(tags)}",
        )


# ── 主入口 ──────────────────────────────────────────────

def main():
    """活动推送页主入口"""
    render_header()

    # 用户兴趣提示
    render_user_profile_hint()

    st.divider()

    # 筛选/排序
    selected_type, sort_by = render_filter_bar()

    # 过滤排序
    activities = filter_and_sort_activities(MOCK_ACTIVITIES, selected_type, sort_by)

    # 活动列表
    render_activities_list(activities)


if __name__ == "__main__":
    main()
