"""
校园知识问答页（02_campus_qa）
Day 10: 接入 chat_ui 组件，实现对话式问答交互
分类 Tab + 热门问题 + 对话历史 + Mock 百事通回答（含来源引用）
"""

from typing import Optional

import streamlit as st

from state_sync import get_state, set_state, add_chat_message
from components.chat_ui import (
    render_chat_history,
    render_chat_input,
    render_chat_toolbar,
)


# ── 对话历史 key（独立于其他页面）───────────────────────────────
QA_HISTORY_KEY = "qa_chat_history"


# ── 热门问题（按分类）──────────────────────────────────────────
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


# ── Mock 百事通回答（占位，后续接入 knowit_agent）──────────────────
MOCK_ANSWERS = {
    "补考什么时候报名？": {
        "content": (
            "根据教务处最新通知，**补考报名**一般安排在下学期开学前两周：\n\n"
            "- 📅 **报名时间**：开学第 1-2 周\n"
            "- 📝 **报名方式**：登录教务系统 → 补考申请 → 选择科目\n"
            "- 💰 **费用**：每科 50 元\n\n"
            "建议提前关注教务处公告，避免错过报名窗口。"
        ),
        "sources": [
            {
                "title": "教务处关于补考报名的通知",
                "source": "jwc.example.edu.cn/notice/2026-01",
                "date": "2026-01-15",
                "snippet": "补考报名时间为开学第1-2周，逾期不予受理...",
            },
        ],
    },
    "转专业需要什么条件？": {
        "content": (
            "转专业需满足以下条件：\n\n"
            "1. **成绩要求**：大一学年 GPA ≥ 3.0，无不及格科目\n"
            "2. **申请时间**：第二学年开学前\n"
            "3. **考核方式**：笔试 + 面试（由目标学院组织）\n"
            "4. **名额限制**：各专业接收比例不超过 10%\n\n"
            "⚠️ 注意：艺术类与普通类之间不可互转。"
        ),
        "sources": [
            {
                "title": "本科生转专业管理办法",
                "source": "jwc.example.edu.cn/policy/transfer",
                "date": "2025-09-01",
                "snippet": "转专业申请条件：GPA≥3.0，无不及格记录...",
            },
            {
                "title": "2025-2026学年转专业通知",
                "source": "jwc.example.edu.cn/notice/2026-06",
                "date": "2026-06-20",
                "snippet": "申请截止时间为8月31日，笔试时间9月5日...",
            },
        ],
    },
    "快递站在哪里？": {
        "content": (
            "校园内共有 **3 个快递站点**：\n\n"
            "- 📦 **南门快递中心**：菜鸟驿站，支持所有主流快递\n"
            "- 📦 **生活区快递柜**：丰巢柜，位于 3 号宿舍楼下\n"
            "- 📦 **教学楼快递代收点**：图书馆一楼便利店旁\n\n"
            "取件时间：8:00 - 21:00（含周末）。"
        ),
        "sources": [
            {
                "title": "校园生活指南 - 快递服务",
                "source": "campus.guide/express",
                "date": "2026-03-01",
                "snippet": "校园设有3个快递站点，南门菜鸟驿站支持所有主流快递...",
            },
        ],
    },
    "校园卡丢了怎么补办？": {
        "content": (
            "校园卡补办流程：\n\n"
            "1. **挂失**：立即在「校园卡 APP」或自助终端挂失\n"
            "2. **补办地点**：一卡通中心（行政楼 1 楼大厅）\n"
            "3. **所需材料**：学生证 / 身份证\n"
            "4. **费用**：补办工本费 20 元\n"
            "5. **领取时间**：即时制卡，当场可取\n\n"
            "💡 建议开通虚拟校园卡（手机 NFC），避免实体卡丢失。"
        ),
        "sources": [
            {
                "title": "一卡通使用指南",
                "source": "card.example.edu.cn/guide",
                "date": "2025-09-01",
                "snippet": "校园卡丢失后请先挂失，再携带学生证到一卡通中心补办...",
            },
        ],
    },
}

# 通用兜底回答
FALLBACK_ANSWER = {
    "content": (
        "感谢你的提问！百事通 Agent 正在学习中...\n\n"
        "目前我可以回答以下类型的校园问题：\n"
        "- 📋 教务通知（选课/补考/转专业）\n"
        "- 🏠 生活指南（快递/食堂/校园卡）\n"
        "- 📚 课程资料（教材/复习/实验报告）\n\n"
        "请尝试点击上方热门问题，或换个问法试试！"
    ),
    "sources": [],
}


# ── Mock 回答引擎 ──────────────────────────────────────────────
def mock_qa_engine(question: str) -> dict:
    """
    Mock 百事通问答引擎（后续替换为 knowit_agent 真实调用）

    Args:
        question: 用户问题

    Returns:
        dict: {"content": str, "sources": list[dict]}
    """
    # 精确匹配
    if question in MOCK_ANSWERS:
        return MOCK_ANSWERS[question]

    # 模糊匹配（关键词）
    for key, answer in MOCK_ANSWERS.items():
        # 简单关键词重叠检测
        q_chars = set(question)
        k_chars = set(key)
        overlap = len(q_chars & k_chars) / max(len(k_chars), 1)
        if overlap > 0.5:
            return answer

    return FALLBACK_ANSWER


# ── 页面渲染 ──────────────────────────────────────────────────

def render_header():
    """渲染页面头部"""
    st.markdown(
        """
        <div style="text-align: center; padding: 0.5rem 0;">
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


def render_hot_questions(category: str) -> Optional[str]:
    """
    渲染热门问题推荐按钮

    Returns:
        str 或 None: 被点击的问题文本
    """
    info = CATEGORY_INFO.get(category, CATEGORY_INFO["academic"])

    st.markdown(f"##### 🔥 {info['label']}热门问题")

    questions = HOT_QUESTIONS.get(category, [])

    cols = st.columns(2)
    for i, question in enumerate(questions):
        with cols[i % 2]:
            if st.button(
                question,
                key=f"hot_{category}_{i}",
                use_container_width=True,
            ):
                return question

    return None


def render_chat_section():
    """渲染对话区域（核心交互区）"""
    st.divider()
    st.markdown("### 💬 对话")

    # 渲染对话历史
    render_chat_history(QA_HISTORY_KEY)

    # 工具栏
    render_chat_toolbar(QA_HISTORY_KEY)

    st.divider()

    # 输入框
    user_input = render_chat_input(
        placeholder="输入你的校园问题...",
        button_label="🔍 提问",
        history_key=QA_HISTORY_KEY,
    )

    return user_input


def render_stats():
    """渲染知识库统计"""
    st.divider()

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("教务通知", "0 篇", help="数据采集后更新")

    with col2:
        st.metric("生活指南", "0 篇", help="数据采集后更新")

    with col3:
        st.metric("课程资料", "0 门", help="数据采集后更新")

    with col4:
        history = get_state(QA_HISTORY_KEY, [])
        qa_count = sum(1 for m in history if m.get("role") == "user")
        st.metric("累计问答", f"{qa_count} 次")


def handle_question(question: str) -> None:
    """
    处理用户提问：记录用户消息 → 调用 Mock 引擎 → 记录助手回答

    Args:
        question: 用户问题文本
    """
    # 记录用户消息
    add_chat_message("user", question, QA_HISTORY_KEY)

    # 调用 Mock 问答引擎
    answer = mock_qa_engine(question)

    # 记录助手回答（含来源引用）
    history = get_state(QA_HISTORY_KEY, [])
    history.append({
        "role": "assistant",
        "content": answer["content"],
        "sources": answer.get("sources"),
    })
    set_state(QA_HISTORY_KEY, history)


# ── 主入口 ──────────────────────────────────────────────────────

def main():
    """校园知识问答页主入口"""
    render_header()

    # 分类 Tab + 热门问题
    tab1, tab2, tab3, tab4 = render_category_tabs()

    clicked_question = None

    with tab1:
        q = render_hot_questions("academic")
        if q:
            clicked_question = q

    with tab2:
        q = render_hot_questions("life")
        if q:
            clicked_question = q

    with tab3:
        q = render_hot_questions("course")
        if q:
            clicked_question = q

    with tab4:
        st.markdown("##### 🌐 综合查询")
        st.caption("输入任意问题，百事通将自动分类并回答")

    # 处理热门问题点击
    if clicked_question:
        handle_question(clicked_question)
        st.rerun()

    # 对话区域
    user_input = render_chat_section()

    # 处理用户输入
    if user_input:
        handle_question(user_input)
        st.rerun()

    # 统计
    render_stats()


if __name__ == "__main__":
    main()
