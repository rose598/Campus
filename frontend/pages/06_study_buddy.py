"""
学伴对话页（06_study_buddy）
Day 19: 对已入库课程资料进行 RAG 问答
独立对话历史 + 课程筛选 + Mock RAG 引擎 + 来源引用
"""

import streamlit as st

from state_sync import get_state, set_state, add_chat_message
from components.chat_ui import (
    render_chat_history,
    render_chat_input,
    render_chat_toolbar,
)
from components.loading_states import render_page_state
from components.error_handler import render_chat_error_message, render_error_page


# ── 状态 key（独立于其他页面）──────────────────────────────────
BUDDY_HISTORY_KEY = "buddy_chat_history"
BUDDY_ERROR_KEY = "buddy_error_msg"
BUDDY_ERROR_CODE_KEY = "buddy_error_code"
BUDDY_COURSE_KEY = "buddy_selected_course"


# ── Mock 课程列表（共享自 03 页，后续统一从数据库读取）──────────────
BUDDY_COURSES = [
    {"course_code": "CS201", "course_name": "数据结构", "material_count": 8},
    {"course_code": "CS301", "course_name": "操作系统", "material_count": 5},
    {"course_code": "CS302", "course_name": "计算机网络", "material_count": 3},
    {"course_code": "MA201", "course_name": "线性代数", "material_count": 6},
    {"course_code": "CS401", "course_name": "人工智能导论", "material_count": 2},
]


# ── Mock RAG 回答（按课程，后续替换为 buddy_agent）──────────────────
MOCK_BUDDY_ANSWERS = {
    "CS201": {
        "数据结构的排序算法有哪些": {
            "content": (
                "根据课程资料，常用排序算法包括：\n\n"
                "| 算法 | 平均时间 | 最坏时间 | 空间 | 稳定性 |\n"
                "|------|---------|---------|------|--------|\n"
                "| 快速排序 | O(n log n) | O(n²) | O(log n) | 不稳定 |\n"
                "| 归并排序 | O(n log n) | O(n log n) | O(n) | 稳定 |\n"
                "| 堆排序 | O(n log n) | O(n log n) | O(1) | 不稳定 |\n"
                "| 冒泡排序 | O(n²) | O(n²) | O(1) | 稳定 |\n\n"
                "**考试重点**：手写快排分区过程、归并排序合并步骤、堆排序建堆。"
            ),
            "sources": [
                {
                    "title": "第7章 排序算法课件",
                    "source": "CS201/ch07_sorting.pdf",
                    "date": "2025-10-15",
                    "snippet": "快速排序采用分治策略，选取基准元素将数组分为两部分...",
                    "relevance": 0.96,
                },
                {
                    "title": "期末考试复习提纲",
                    "source": "CS201/exam_outline.pdf",
                    "date": "2025-12-20",
                    "snippet": "重点考察：各排序算法的时间/空间复杂度比较及手写实现",
                    "relevance": 0.88,
                },
            ],
        },
        "二叉树遍历": {
            "content": (
                "二叉树有四种基本遍历方式：\n\n"
                "1. **前序遍历**（根→左→右）：用于复制树结构\n"
                "2. **中序遍历**（左→根→右）：BST 中可得到有序序列\n"
                "3. **后序遍历**（左→右→根）：用于释放树资源\n"
                "4. **层序遍历**（BFS）：用队列逐层访问\n\n"
                "```python\n"
                "def inorder(node):\n"
                "    if node:\n"
                "        inorder(node.left)\n"
                "        visit(node)\n"
                "        inorder(node.right)\n"
                "```\n\n"
                "**考点**：给定前序+中序，还原二叉树并写出后序序列。"
            ),
            "sources": [
                {
                    "title": "第3章 树与二叉树课件",
                    "source": "CS201/ch03_tree.pdf",
                    "date": "2025-09-20",
                    "snippet": "二叉树遍历是树结构的基础操作，前中后序均为递归定义...",
                    "relevance": 0.94,
                },
            ],
        },
    },
    "CS301": {
        "进程调度算法": {
            "content": (
                "操作系统常见进程调度算法：\n\n"
                "- **FCFS**（先来先服务）：简单但可能导致护航效应\n"
                "- **SJF**（最短作业优先）：平均等待时间最优，但可能饥饿\n"
                "- **优先级调度**：高优先级先执行，需防饥饿（老化技术）\n"
                "- **时间片轮转 RR**：每个进程分配固定时间片，适合交互式系统\n"
                "- **多级反馈队列**：综合以上优点，UNIX/Linux 常用\n\n"
                "**实验要求**：用 Python 模拟 RR 调度，计算平均周转时间。"
            ),
            "sources": [
                {
                    "title": "第2章 进程管理课件",
                    "source": "CS301/ch02_process.pdf",
                    "date": "2025-09-25",
                    "snippet": "时间片轮转调度中，时间片大小直接影响系统性能...",
                    "relevance": 0.93,
                },
                {
                    "title": "实验2 进程调度模拟",
                    "source": "CS301/lab02_scheduling.docx",
                    "date": "2025-10-10",
                    "snippet": "实现 FCFS/SJF/RR 三种调度算法，对比平均周转时间",
                    "relevance": 0.85,
                },
            ],
        },
    },
    "MA201": {
        "特征值": {
            "content": (
                "特征值与特征向量核心概念：\n\n"
                "**定义**：若 Ax = λx（x ≠ 0），则 λ 为特征值，x 为对应特征向量。\n\n"
                "**求解步骤**：\n"
                "1. 计算特征多项式 det(A - λI) = 0\n"
                "2. 求解所有特征根 λ₁, λ₂, ...\n"
                "3. 对每个 λ，求解 (A - λI)x = 0 得到特征向量\n\n"
                "**性质**：\n"
                "- 特征值之和 = 矩阵的迹（tr(A)）\n"
                "- 特征值之积 = det(A)\n"
                "- 实对称矩阵的特征值均为实数，不同特征值的特征向量正交"
            ),
            "sources": [
                {
                    "title": "第5章 特征值与特征向量",
                    "source": "MA201/ch05_eigenvalue.pdf",
                    "date": "2025-11-01",
                    "snippet": "特征多项式的求解方法及特征向量的计算步骤...",
                    "relevance": 0.97,
                },
            ],
        },
    },
}

# 通用兜底回答
BUDDY_FALLBACK = {
    "content": (
        "这个问题我在已入库的课程资料中没有找到直接相关内容。\n\n"
        "我可以帮你回答以下课程的资料问题：\n"
        "- 📚 **数据结构**（CS201）— 排序算法、二叉树遍历、图算法\n"
        "- 🖥️ **操作系统**（CS301）— 进程调度、内存管理、文件系统\n"
        "- 📐 **线性代数**（MA201）— 特征值、矩阵运算、向量空间\n\n"
        "请先在上方选择课程，然后问我相关知识点！"
    ),
    "sources": [],
}


# ── Mock RAG 引擎 ──────────────────────────────────────────────
def mock_buddy_rag(question: str, course_code: str) -> dict:
    """
    Mock 学伴 RAG 引擎（后续替换为 buddy_agent 真实调用）

    Args:
        question: 用户问题
        course_code: 当前选中的课程代码

    Returns:
        dict: {"content": str, "sources": list[dict]}
    """
    if not question or not question.strip():
        return {"content": "请输入你的问题～", "sources": []}

    # 在当前课程的资料中查找
    course_answers = MOCK_BUDDY_ANSWERS.get(course_code, {})
    q_lower = question.lower()

    # 精确匹配
    if question in course_answers:
        return course_answers[question]

    # 关键词匹配
    for key, answer in course_answers.items():
        # 计算关键词重叠度
        q_words = set(q_lower)
        k_words = set(key.lower())
        overlap = len(q_words & k_words) / max(len(k_words), 1)
        if overlap > 0.45:
            return answer

    return BUDDY_FALLBACK


# ── 页面渲染 ──────────────────────────────────────────────────

def render_header():
    """渲染页面头部"""
    st.markdown(
        """
        <div style="text-align: center; padding: 0.5rem 0;">
            <h1>🎓 学伴对话</h1>
            <p style="color: #666;">基于已入库的课程资料，帮你精准回答知识点问题</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_course_selector():
    """渲染课程筛选器，返回选中的 course_code"""
    courses_with_materials = [
        c for c in BUDDY_COURSES if c.get("material_count", 0) > 0
    ]

    if not courses_with_materials:
        return None

    options = [
        f"{c['course_code']} - {c['course_name']}（{c['material_count']} 份资料）"
        for c in courses_with_materials
    ]

    # 恢复上次选中的课程
    prev = get_state(BUDDY_COURSE_KEY)
    default_idx = 0
    if prev:
        for i, c in enumerate(courses_with_materials):
            if c["course_code"] == prev:
                default_idx = i
                break

    selected = st.selectbox(
        "选择课程（针对该课程的资料进行问答）",
        options,
        index=default_idx,
        key="buddy_course_select",
    )

    # 提取 course_code
    course_code = selected.split(" - ")[0]
    set_state(BUDDY_COURSE_KEY, course_code)

    return course_code


def render_welcome(course_code: str, course_name: str):
    """渲染无对话时的欢迎引导"""
    st.markdown(
        f"""
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
                你好！我是你的学伴 AI
            </div>
            <div style="font-size: 0.9rem; color: #666; line-height: 1.8;">
                我正在学习 <strong>{course_name}（{course_code}）</strong> 的课程资料。<br>
                问我关于这门课的任何知识点，我会从课件和资料中寻找答案！
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # 快捷问题
    quick_questions = _get_quick_questions(course_code)
    if quick_questions:
        st.markdown("**💡 试试问我：**")
        cols = st.columns(min(len(quick_questions), 3))
        for i, q in enumerate(quick_questions):
            with cols[i % len(cols)]:
                if st.button(q, use_container_width=True, key=f"buddy_quick_{i}"):
                    return q
    return None


def _get_quick_questions(course_code: str) -> list[str]:
    """获取课程的快捷问题"""
    questions_map = {
        "CS201": ["数据结构的排序算法有哪些", "二叉树遍历", "图的最短路径算法"],
        "CS301": ["进程调度算法", "虚拟内存是什么", "文件系统 inode"],
        "MA201": ["特征值", "矩阵的逆怎么求", "向量空间基与维数"],
    }
    return questions_map.get(course_code, [])


def handle_buddy_question(question: str, course_code: str) -> None:
    """
    处理学伴问答：记录用户消息 → Mock RAG → 记录回答

    Args:
        question: 用户问题
        course_code: 当前课程代码
    """
    set_state(BUDDY_ERROR_KEY, None)

    add_chat_message("user", question, BUDDY_HISTORY_KEY)

    # 使用 st.spinner 显示加载状态
    with st.spinner("🤔 学伴正在从课程资料中查找答案..."):
        try:
            answer = mock_buddy_rag(question, course_code)

            history = get_state(BUDDY_HISTORY_KEY, [])
            history.append({
                "role": "assistant",
                "content": answer["content"],
                "sources": answer.get("sources"),
            })
            set_state(BUDDY_HISTORY_KEY, history)

        except Exception as e:
            set_state(BUDDY_ERROR_KEY, f"学伴引擎异常: {str(e)}")
            set_state(BUDDY_ERROR_CODE_KEY, "E001")
            history = get_state(BUDDY_HISTORY_KEY, [])
            history.append({
                "role": "system",
                "content": render_chat_error_message("E001"),
            })
            set_state(BUDDY_HISTORY_KEY, history)


def render_stats(course_code: str):
    """渲染当前课程资料统计"""
    course = next(
        (c for c in BUDDY_COURSES if c["course_code"] == course_code), None
    )
    if not course:
        return

    history = get_state(BUDDY_HISTORY_KEY, [])
    qa_count = sum(1 for m in history if m.get("role") == "user")
    source_count = sum(
        len(m.get("sources", []))
        for m in history
        if m.get("role") == "assistant"
    )

    st.divider()
    # 2×2 网格：移动端避免四行堆叠占用过多纵向空间
    row1_cols = st.columns(2)
    row2_cols = st.columns(2)
    with row1_cols[0]:
        st.metric("当前课程", course["course_name"])
    with row1_cols[1]:
        st.metric("入库资料", f"{course['material_count']} 份")
    with row2_cols[0]:
        st.metric("累计提问", f"{qa_count} 次")
    with row2_cols[1]:
        st.metric("引用来源", f"{source_count} 条")


# ── 主入口 ──────────────────────────────────────────────────────

def main():
    """学伴对话页主入口"""
    render_header()

    # ── 错误态检测 ──
    error_msg = get_state(BUDDY_ERROR_KEY)
    if error_msg:
        error_code = get_state(BUDDY_ERROR_CODE_KEY, "E001")

        def clear_error():
            set_state(BUDDY_ERROR_KEY, None)
            set_state(BUDDY_ERROR_CODE_KEY, None)

        if render_error_page(error_code, detail=error_msg, clear_callback=clear_error):
            st.rerun()
        return

    # ── 课程选择 ──
    course_code = render_course_selector()
    if not course_code:
        render_page_state(
            is_empty=True,
            empty_icon="📚",
            empty_title="暂无可用课程",
            empty_desc="请先在「课程资料」页上传课程文件",
        )
        return

    course_name = next(
        (c["course_name"] for c in BUDDY_COURSES if c["course_code"] == course_code),
        course_code,
    )

    # ── 对话区域 ──
    history = get_state(BUDDY_HISTORY_KEY, [])
    has_history = len(history) > 0

    # 无对话时显示欢迎
    if not has_history:
        quick_q = render_welcome(course_code, course_name)
        if quick_q:
            handle_buddy_question(quick_q, course_code)
            st.rerun()

    st.divider()
    st.markdown(f"### 💬 与学伴对话 · {course_name}")

    if has_history:
        render_chat_history(BUDDY_HISTORY_KEY)
        render_chat_toolbar(BUDDY_HISTORY_KEY)
        st.divider()

    user_input = render_chat_input(
        placeholder=f"问我关于{course_name}的任何问题...",
        button_label="🔍 提问",
        history_key=BUDDY_HISTORY_KEY,
    )

    if user_input:
        handle_buddy_question(user_input, course_code)
        st.rerun()

    # ── 统计 ──
    if has_history:
        render_stats(course_code)


if __name__ == "__main__":
    main()
