"""
校园知识问答页（02_campus_qa）
Day 10: 接入 chat_ui 组件，实现对话式问答交互
Day 13: 全面完善 — 空状态/加载态/错误态 + 欢迎引导 + 知识库统计
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
from components.loading_states import (
    render_page_state,
)
from components.error_handler import render_chat_error_message, render_error_page


# ── 对话历史 key（独立于其他页面）───────────────────────────────
QA_HISTORY_KEY = "qa_chat_history"
QA_ERROR_KEY = "qa_error_msg"
QA_ERROR_CODE_KEY = "qa_error_code"


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
                "relevance": 0.95,
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
                "relevance": 0.92,
            },
            {
                "title": "2025-2026学年转专业通知",
                "source": "jwc.example.edu.cn/notice/2026-06",
                "date": "2026-06-20",
                "snippet": "申请截止时间为8月31日，笔试时间9月5日...",
                "relevance": 0.78,
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
                "source": "https://campus.guide/express",
                "date": "2026-03-01",
                "snippet": "校园设有3个快递站点，南门菜鸟驿站支持所有主流快递...",
                "relevance": 0.88,
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
                "source": "card.example.edu.cn/guide.pdf",
                "date": "2025-09-01",
                "snippet": "校园卡丢失后请先挂失，再携带学生证到一卡通中心补办...",
                "relevance": 0.91,
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
    # 空问题检测
    if not question or not question.strip():
        return {"content": "请输入你的问题～", "sources": []}

    # 精确匹配
    if question in MOCK_ANSWERS:
        return MOCK_ANSWERS[question]

    # 模糊匹配（关键词）
    for key, answer in MOCK_ANSWERS.items():
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


def render_welcome_empty():
    """渲染无对话时的欢迎引导（空状态）"""
    st.markdown(
        """
        <div style="
            text-align: center;
            padding: 2rem 1rem;
            border: 2px dashed #e0e0e0;
            border-radius: 12px;
            background: linear-gradient(135deg, #f5f7fa 0%, #e8edf2 100%);
            margin: 1rem 0;
        ">
            <div style="font-size: 3rem; margin-bottom: 0.5rem;">🎓</div>
            <div style="font-size: 1.2rem; font-weight: 600; color: #1e3a5f; margin-bottom: 0.5rem;">
                你好！我是校园百事通
            </div>
            <div style="font-size: 0.9rem; color: #666; line-height: 1.8;">
                我可以帮你回答关于教务通知、校园生活、课程资料等问题。<br>
                点击下方热门问题快速开始，或直接在下方输入你的问题！
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # 快捷入口按钮
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("📋 教务通知", use_container_width=True, key="empty_quick_academic"):
            return "补考什么时候报名？"
    with col2:
        if st.button("🏠 生活指南", use_container_width=True, key="empty_quick_life"):
            return "快递站在哪里？"
    with col3:
        if st.button("📚 课程资料", use_container_width=True, key="empty_quick_course"):
            return "数据结构用什么教材？"
    return None


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


def render_chat_section(has_history: bool):
    """渲染对话区域（核心交互区）"""
    st.divider()
    st.markdown("### 💬 对话")

    # 有历史时才显示对话内容和工具栏
    if has_history:
        render_chat_history(QA_HISTORY_KEY)
        render_chat_toolbar(QA_HISTORY_KEY)
        st.divider()

    # 输入框（始终显示）
    user_input = render_chat_input(
        placeholder="输入你的校园问题...",
        button_label="🔍 提问",
        history_key=QA_HISTORY_KEY,
    )

    return user_input


def render_stats():
    """渲染知识库统计"""
    st.divider()

    history = get_state(QA_HISTORY_KEY, [])
    qa_count = sum(1 for m in history if m.get("role") == "user")
    source_count = sum(
        len(m.get("sources", []))
        for m in history
        if m.get("role") == "assistant"
    )

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("教务通知", "12 篇", help="已入库政策通知")

    with col2:
        st.metric("生活指南", "8 篇", help="已入库生活信息")

    with col3:
        st.metric("课程资料", "5 门", help="已入库课程")

    with col4:
        st.metric("累计问答", f"{qa_count} 次", help=f"引用来源 {source_count} 条")


def handle_question(question: str) -> None:
    """
    处理用户提问：记录用户消息 → 调用 Mock 引擎 → 记录助手回答
    含错误态处理

    Args:
        question: 用户问题文本
    """
    # 清除之前的错误状态
    set_state(QA_ERROR_KEY, None)

    # 记录用户消息
    add_chat_message("user", question, QA_HISTORY_KEY)

    # 使用 st.spinner 显示加载状态
    with st.spinner("🔍 百事通正在知识库中检索答案..."):
        try:
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

        except Exception as e:
            # 记录错误状态（E001 = LLM 服务不可用）
            set_state(QA_ERROR_KEY, f"问答引擎异常: {str(e)}")
            set_state(QA_ERROR_CODE_KEY, "E001")
            # 添加错误提示消息
            history = get_state(QA_HISTORY_KEY, [])
            history.append({
                "role": "system",
                "content": render_chat_error_message("E001"),
            })
            set_state(QA_HISTORY_KEY, history)


# ── 主入口 ──────────────────────────────────────────────────────

def main():
    """校园知识问答页主入口"""
    render_header()

    # ── 错误态检测 ──
    error_msg = get_state(QA_ERROR_KEY)
    if error_msg:
        error_code = get_state(QA_ERROR_CODE_KEY, "E001")

        def clear_error():
            set_state(QA_ERROR_KEY, None)
            set_state(QA_ERROR_CODE_KEY, None)

        if render_error_page(error_code, detail=error_msg, clear_callback=clear_error):
            st.rerun()
        return

    # ── 分类 Tab + 热门问题 ──
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

    # ── 对话区域 ──
    history = get_state(QA_HISTORY_KEY, [])
    has_history = len(history) > 0

    # 无对话时显示欢迎空状态
    if not has_history:
        quick_q = render_welcome_empty()
        if quick_q:
            handle_question(quick_q)
            st.rerun()

    user_input = render_chat_section(has_history)

    # 处理用户输入
    if user_input:
        handle_question(user_input)
        st.rerun()

    # ── 统计 ──
    if has_history:
        render_stats()


if __name__ == "__main__":
    main()
