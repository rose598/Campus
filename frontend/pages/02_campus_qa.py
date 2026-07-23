"""
校园知识问答页（02_campus_qa）
分类 Tab（教务通知/生活指南/课程资料）+ 问答输入框 + 回答展示区
"""

import streamlit as st

from state_sync import get_state


# ── 示例数据（占位，后续接入百事通 Agent）──────────────────────────────────────
HOT_QUESTIONS = {
    "academic": [
        "补考什么时候报名？",
        "转专业需要什么条件？",
        "选课系统什么时候开放？",
        "学分不够怎么办？",
    ],
    "life": [
        "快递站在哪里？",
        "食堂几点开门？",
        "校医院怎么挂号？",
        "校园卡丢了怎么补办？",
    ],
    "course": [
        "数据结构用什么教材？",
        "期末考试范围是什么？",
        "这门课有没有往年试题？",
        "实验报告怎么写？",
    ],
}

CATEGORY_INFO = {
    "academic": {
        "icon": "📋",
        "label": "教务通知",
        "description": "选课、补考、转专业、学分政策等教务相关问题",
        "color": "#1976d2",
    },
    "life": {
        "icon": "🏠",
        "label": "生活指南",
        "description": "快递、食堂、校医院、校园卡等校园生活问题",
        "color": "#388e3c",
    },
    "course": {
        "icon": "📚",
        "label": "课程资料",
        "description": "课程大纲、教材、复习资料、往年试题等",
        "color": "#f57c00",
    },
}


# ── 页面渲染 ──────────────────────────────────────────────
def render_header():
    """渲染页面头部"""
    st.markdown(
        """
        <div style="text-align: center; padding: 1rem 0;">
            <h1>❓ 校园知识问答</h1>
            <p style="color: #666;">有任何校园问题？问我就好！</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_category_tabs():
    """渲染分类 Tab"""
    tab1, tab2, tab3, tab4 = st.tabs(
        ["📋 教务通知", "🏠 生活指南", "📚 课程资料", "🌐 综合查询"]
    )
    return tab1, tab2, tab3, tab4


def render_search_box():
    """渲染搜索输入框"""
    st.markdown("### 💬 问我任何校园问题")

    col1, col2 = st.columns([4, 1])

    with col1:
        query = st.text_input(
            "问题输入",
            placeholder="例如：补考什么时候报名？",
            key="campus_qa_input",
            label_visibility="collapsed",
        )

    with col2:
        submit = st.button("🔍 提问", type="primary", use_container_width=True)

    return query, submit


def render_hot_questions(category: str):
    """渲染热门问题推荐"""
    info = CATEGORY_INFO.get(category, CATEGORY_INFO["academic"])

    st.markdown(f"### 🔥 {info['label']}热门问题")

    questions = HOT_QUESTIONS.get(category, [])

    cols = st.columns(2)
    for i, question in enumerate(questions):
        with cols[i % 2]:
            if st.button(
                question,
                key=f"hot_{category}_{i}",
                use_container_width=True,
            ):
                st.session_state["campus_qa_input"] = question
                st.rerun()


def render_answer_placeholder():
    """渲染回答展示区占位"""
    st.divider()
    st.markdown("### 💡 回答")

    st.info(
        """
        **百事通 Agent 开发中...**

        即将支持：
        - 🤖 智能分类路由（教务/生活/课程）
        - 📅 时间感知排序（最新信息优先）
        - 🔗 来源引用卡片（可追溯原文）
        - 💾 语义缓存（秒回常见问题）
        - 📊 多源融合（跨类别综合回答）
        """
    )

    st.markdown(
        """
        <div style="
            border: 2px dashed #ccc;
            border-radius: 8px;
            padding: 2rem;
            background-color: #fafafa;
            text-align: center;
        ">
            <div style="font-size: 2rem; margin-bottom: 1rem;">🤖</div>
            <div style="color: #999;">等待提问...</div>
            <div style="color: #bbb; font-size: 0.9rem;">输入你的问题，百事通将为你解答</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_source_cards_placeholder():
    """渲染来源引用卡片占位"""
    st.divider()
    st.markdown("### 📎 来源引用")
    st.warning("来源引用卡片功能开发中。")


def render_stats_placeholder():
    """渲染统计信息占位"""
    st.divider()
    st.markdown("### 📊 知识库统计")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("教务通知", "0 篇", help="数据采集后更新")

    with col2:
        st.metric("生活指南", "0 篇", help="数据采集后更新")

    with col3:
        st.metric("课程资料", "0 门", help="数据采集后更新")

    with col4:
        st.metric("累计问答", "0 次", help="上线后统计")


# ── 主入口 ──────────────────────────────────────────────
def main():
    """校园知识问答页主入口"""
    render_header()

    # 分类 Tab
    tab1, tab2, tab3, tab4 = render_category_tabs()

    with tab1:
        render_hot_questions("academic")
        render_search_box()

    with tab2:
        render_hot_questions("life")
        render_search_box()

    with tab3:
        render_hot_questions("course")
        render_search_box()

    with tab4:
        render_search_box()

    # 回答展示区
    render_answer_placeholder()
    render_source_cards_placeholder()
    render_stats_placeholder()


if __name__ == "__main__":
    main()
