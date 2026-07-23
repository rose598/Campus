"""
课程资料收集与总结页（03_course_materials）
课程列表 + 资料上传 + 结构化总结展示
"""

import streamlit as st

from state_sync import get_state, set_state


# ── 页面渲染 ──────────────────────────────────────────────

def render_header():
    """渲染页面头部"""
    st.markdown(
        """
        <div style="text-align: center; padding: 1rem 0;">
            <h1>📚 课程资料收集与总结</h1>
            <p style="color: #666;">上传课件/大纲/期末资料，AI 帮你提取重点、生成结构化总结</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_course_list():
    """渲染课程列表"""
    st.markdown("### 📋 已入库课程")

    st.info(
        "**课程资料模块开发中...**\n\n"
        "即将支持：\n"
        "- 📄 课程大纲/课件/期末题上传（PDF/Word）\n"
        "- 🤖 LLM 自动提取知识点、重点章节、考核方式\n"
        "- 📊 生成结构化课程总结卡片\n"
        "- 🔍 对已入库资料的 RAG 问答检索\n"
    )

    st.markdown(
        """
        <div style="
            border: 2px dashed #ccc;
            border-radius: 8px;
            padding: 3rem;
            background-color: #fafafa;
            text-align: center;
        ">
            <div style="font-size: 3rem; margin-bottom: 1rem;">📚</div>
            <div style="color: #999; font-size: 1.1rem;">暂无已入库课程</div>
            <div style="color: #bbb; font-size: 0.9rem; margin-top: 0.5rem;">
                上传课程资料后将在此展示课程列表
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_upload_area():
    """渲染资料上传区域"""
    st.divider()
    st.markdown("### 📤 上传课程资料")

    uploaded_files = st.file_uploader(
        "拖拽或点击上传（支持 PDF / Word / PPT）",
        type=["pdf", "docx", "pptx"],
        accept_multiple_files=True,
        key="course_material_uploader",
    )

    if uploaded_files:
        st.success(f"已选择 {len(uploaded_files)} 个文件，点击开始解析")
        if st.button("🚀 开始解析", type="primary", use_container_width=True):
            st.info("解析功能开发中，敬请期待...")


def render_summary_placeholder():
    """渲染总结展示区域占位"""
    st.divider()
    st.markdown("### 📊 课程总结")

    st.markdown(
        """
        <div style="
            border: 2px dashed #ccc;
            border-radius: 8px;
            padding: 2rem;
            background-color: #fafafa;
            text-align: center;
        ">
            <div style="font-size: 2rem; margin-bottom: 0.5rem;">📊</div>
            <div style="color: #999;">课程总结将在此展示</div>
            <div style="color: #bbb; font-size: 0.85rem; margin-top: 0.3rem;">
                包含：课程大纲 / 重点章节 / 考核方式 / 参考资料
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ── 主入口 ──────────────────────────────────────────────

def main():
    """课程资料页主入口"""
    render_header()
    render_course_list()
    render_upload_area()
    render_summary_placeholder()


if __name__ == "__main__":
    main()
