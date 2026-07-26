"""
课程资料收集与总结页（03_course_materials）
Day 15: 完整 UI — 课程列表 + 资料上传 + 总结卡片
支持课程浏览、资料上传模拟、AI 总结展示
"""

import streamlit as st

from state_sync import get_state, set_state
from components.loading_states import (
    render_empty,
    render_loading,
    render_page_state,
)
from components.course_card import (
    render_course_cards,
    render_summary_card,
    render_course_empty,
)


# ── 状态 key ──────────────────────────────────────────────
COURSE_SELECTED_KEY = "course_selected_code"
COURSE_ERROR_KEY = "course_error_msg"


# ── Mock 课程数据（占位，后续接入数据库）──────────────────────
MOCK_COURSES = [
    {
        "course_code": "CS201",
        "course_name": "数据结构",
        "teacher": "张教授",
        "semester": "2025-2026-1",
        "credits": 4.0,
        "material_count": 8,
        "summary_ready": True,
        "tags": ["必修", "核心"],
    },
    {
        "course_code": "CS301",
        "course_name": "操作系统",
        "teacher": "李教授",
        "semester": "2025-2026-1",
        "credits": 3.5,
        "material_count": 5,
        "summary_ready": True,
        "tags": ["必修"],
    },
    {
        "course_code": "CS302",
        "course_name": "计算机网络",
        "teacher": "王教授",
        "semester": "2025-2026-1",
        "credits": 3.0,
        "material_count": 3,
        "summary_ready": False,
        "tags": ["必修"],
    },
    {
        "course_code": "MA201",
        "course_name": "线性代数",
        "teacher": "赵教授",
        "semester": "2025-2026-1",
        "credits": 3.0,
        "material_count": 6,
        "summary_ready": True,
        "tags": ["必修", "基础"],
    },
    {
        "course_code": "CS401",
        "course_name": "人工智能导论",
        "teacher": "陈教授",
        "semester": "2025-2026-2",
        "credits": 3.0,
        "material_count": 2,
        "summary_ready": False,
        "tags": ["选修", "AI方向"],
    },
]

# Mock 课程总结数据
MOCK_SUMMARIES = {
    "CS201": {
        "outline": (
            "本课程系统讲解常用数据结构及其算法，包括线性表、栈与队列、"
            "树与二叉树、图、查找、排序等核心内容。"
        ),
        "key_points": [
            "第3章 树与二叉树 — 遍历算法、哈夫曼编码",
            "第5章 图 — DFS/BFS、最短路径、最小生成树",
            "第7章 排序 — 快速排序、归并排序、堆排序",
            "第8章 查找 — 哈希表、平衡二叉搜索树",
        ],
        "exam_focus": (
            "期末考试（60%）+ 实验报告（20%）+ 平时作业（20%）\n"
            "重点考察：算法时间/空间复杂度分析、手写排序/遍历算法"
        ),
        "references": [
            "《数据结构（C语言版）》严蔚敏",
            "《算法导论》Thomas H. Cormen 等",
            "LeetCode 精选 50 题（课程配套练习单）",
        ],
    },
    "CS301": {
        "outline": (
            "本课程介绍操作系统的基本原理，包括进程管理、内存管理、"
            "文件系统、I/O 系统等核心模块。"
        ),
        "key_points": [
            "第2章 进程与线程 — 调度算法、同步互斥",
            "第4章 内存管理 — 分页、分段、虚拟内存",
            "第6章 文件系统 — inode、目录结构、日志",
        ],
        "exam_focus": (
            "期末考试（50%）+ 实验项目（30%）+ 课堂参与（20%）\n"
            "重点考察：PV 操作、页面置换算法、文件系统计算"
        ),
        "references": [
            "《现代操作系统》Andrew S. Tanenbaum",
            "《操作系统概念》Abraham Silberschatz",
        ],
    },
    "MA201": {
        "outline": (
            "本课程讲授线性代数的基本理论与方法，包括行列式、矩阵、"
            "向量空间、线性方程组、特征值与特征向量等。"
        ),
        "key_points": [
            "第2章 矩阵运算 — 初等变换、逆矩阵、矩阵分解",
            "第4章 向量空间 — 基与维数、正交化",
            "第5章 特征值 — 特征多项式、对角化、二次型",
        ],
        "exam_focus": (
            "期末考试（70%）+ 平时作业（30%）\n"
            "重点考察：矩阵运算、线性方程组求解、特征值计算"
        ),
        "references": [
            "《线性代数》同济大学数学系",
            "《Introduction to Linear Algebra》Gilbert Strang",
        ],
    },
}


# ── 页面渲染 ──────────────────────────────────────────────────

def render_header():
    """渲染页面头部"""
    st.markdown(
        """
        <div style="text-align: center; padding: 0.5rem 0;">
            <h1>📚 课程资料收集与总结</h1>
            <p style="color: #666;">上传课件/大纲/期末资料，AI 帮你提取重点、生成结构化总结</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_course_overview(courses: list[dict]):
    """渲染课程统计概览"""
    total = len(courses)
    with_summary = sum(1 for c in courses if c.get("summary_ready"))
    total_materials = sum(c.get("material_count", 0) for c in courses)
    total_credits = sum(c.get("credits", 0) for c in courses)

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("课程总数", f"{total} 门")
    with col2:
        st.metric("总学分", f"{total_credits:.1f}")
    with col3:
        st.metric("资料总数", f"{total_materials} 份")
    with col4:
        st.metric("AI 总结", f"{with_summary}/{total} 门")


def render_course_list(courses: list[dict]):
    """渲染课程列表"""
    if not courses:
        render_course_empty()
        return None

    render_course_overview(courses)
    st.divider()

    # 搜索/筛选
    col_search, col_filter = st.columns([3, 1])
    with col_search:
        search_term = st.text_input(
            "搜索课程",
            placeholder="输入课程名称或代码...",
            key="course_search",
            label_visibility="collapsed",
        )
    with col_filter:
        sort_by = st.selectbox(
            "排序",
            ["资料数 ↓", "课程代码", "学分 ↓"],
            key="course_sort",
        )

    # 搜索过滤
    filtered = courses
    if search_term:
        term = search_term.lower()
        filtered = [
            c for c in courses
            if term in c.get("course_name", "").lower()
            or term in c.get("course_code", "").lower()
        ]

    # 排序
    if sort_by == "资料数 ↓":
        filtered = sorted(filtered, key=lambda x: x.get("material_count", 0), reverse=True)
    elif sort_by == "课程代码":
        filtered = sorted(filtered, key=lambda x: x.get("course_code", ""))
    elif sort_by == "学分 ↓":
        filtered = sorted(filtered, key=lambda x: x.get("credits", 0), reverse=True)

    if not filtered:
        render_empty(
            icon="🔍",
            title="未找到匹配课程",
            description=f"没有匹配「{search_term}」的课程，请尝试其他关键词",
        )
        return None

    # 课程卡片列表
    clicked_idx = render_course_cards(filtered)
    if clicked_idx is not None:
        # 返回排序后列表中的 course_code，而非索引
        return filtered[clicked_idx].get("course_code")
    return None


def render_upload_area():
    """渲染资料上传区域"""
    st.divider()
    st.markdown("### 📤 上传课程资料")

    # 选择目标课程
    course_options = [f"{c['course_code']} - {c['course_name']}" for c in MOCK_COURSES]
    target_course = st.selectbox(
        "上传到课程",
        ["请选择目标课程"] + course_options,
        key="course_upload_target",
    )

    uploaded_files = st.file_uploader(
        "拖拽或点击上传（支持 PDF / Word / PPT）",
        type=["pdf", "docx", "pptx"],
        accept_multiple_files=True,
        key="course_material_uploader",
    )

    if uploaded_files and target_course != "请选择目标课程":
        st.success(f"已选择 {len(uploaded_files)} 个文件，目标：{target_course}")

        # 文件列表预览
        for f in uploaded_files:
            st.caption(f"📄 {f.name} ({f.size / 1024:.1f} KB)")

        if st.button("🚀 开始解析", type="primary", use_container_width=True):
            # 模拟上传进度
            progress_bar = st.progress(0, text="正在上传并解析...")
            for i in range(100):
                progress_bar.progress(i + 1, text=f"解析中... {i + 1}%")
            st.success("✅ 解析完成！资料已入库，AI 总结将在后台生成。")
            st.balloons()

    elif uploaded_files and target_course == "请选择目标课程":
        st.warning("请先选择目标课程")


def render_course_detail(course: dict):
    """渲染课程详情页（大纲+重点+考题）"""
    course_code = course.get("course_code", "")
    course_name = course.get("course_name", "未知课程")

    st.divider()
    st.markdown(f"### 📋 {course_name} 详情")

    # 返回按钮
    if st.button("← 返回课程列表", key="course_back"):
        set_state(COURSE_SELECTED_KEY, None)
        st.rerun()

    summary = MOCK_SUMMARIES.get(course_code)

    if summary:
        render_summary_card(
            course_name=course_name,
            outline=summary.get("outline", ""),
            key_points=summary.get("key_points"),
            exam_focus=summary.get("exam_focus", ""),
            references=summary.get("references"),
        )
    elif course.get("summary_ready"):
        render_loading("AI 正在生成课程总结...")
    else:
        render_empty(
            icon="📊",
            title="暂无课程总结",
            description="上传更多资料后，AI 将自动生成结构化总结",
        )

    # 资料列表
    st.markdown("**📄 已入库资料**")
    material_count = course.get("material_count", 0)
    if material_count > 0:
        for i in range(min(material_count, 5)):
            st.caption(f"📄 资料_{i + 1}.pdf — 已解析 ✅")
        if material_count > 5:
            st.caption(f"... 还有 {material_count - 5} 份资料")
    else:
        st.caption("暂无资料")


# ── 主入口 ──────────────────────────────────────────────────────

def main():
    """课程资料页主入口"""
    render_header()

    # ── 错误态检测 ──
    error_msg = get_state(COURSE_ERROR_KEY)
    if error_msg:
        render_page_state(
            is_error=True,
            error_title="课程服务异常",
            error_msg=error_msg,
            error_code="E005",
        )
        if st.button("🔄 清除错误并返回", use_container_width=True, key="course_clear_error"):
            set_state(COURSE_ERROR_KEY, None)
            st.rerun()
        return

    # ── 课程详情视图 ──
    selected_code = get_state(COURSE_SELECTED_KEY)
    if selected_code:
        # 按 course_code 查找，避免排序后索引错位
        course = next((c for c in MOCK_COURSES if c["course_code"] == selected_code), None)
        if course:
            render_course_detail(course)
            return
        # 课程不存在，清除无效状态
        set_state(COURSE_SELECTED_KEY, None)

    # ── 课程列表视图 ──
    clicked_code = render_course_list(MOCK_COURSES)

    if clicked_code is not None:
        set_state(COURSE_SELECTED_KEY, clicked_code)
        st.rerun()

    # ── 上传区域 ──
    render_upload_area()


if __name__ == "__main__":
    main()
