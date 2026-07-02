"""
GraphCampus 前端主入口
Streamlit 多页面应用配置 + 侧边栏导航路由
"""

import streamlit as st

from state_sync import get_state, set_state, init_default_state


# ── 页面配置 ──────────────────────────────────────────────
st.set_page_config(
    page_title="GraphCampus - 智慧校园课程导航",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── 全局样式 ──────────────────────────────────────────────
st.markdown(
    """
    <style>
    /* 全局字体和间距 */
    .main .block-container {
        padding-top: 2rem;
        max-width: 1200px;
    }
    /* 侧边栏品牌色 */
    [data-testid="stSidebar"] {
        background-color: #f0f7ff;
    }
    /* 隐藏默认的多页面导航 */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    </style>
    """,
    unsafe_allow_html=True,
)


# ── 侧边栏导航 ──────────────────────────────────────────────
def render_sidebar():
    """渲染侧边栏导航菜单"""
    with st.sidebar:
        # 品牌 Logo
        st.markdown(
            """
            <div style="text-align: center; padding: 1rem 0;">
                <h1 style="color: #1e3a5f; margin: 0;">🎓 GraphCampus</h1>
                <p style="color: #666; font-size: 0.9rem;">智慧校园课程导航系统</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.divider()

        # 导航菜单
        pages = {
            "🗺️ 课程地图": "course_map",
            "📚 课程详情": "course_detail",
            "❓ 校园十万个为什么": "campus_qa",
            "💬 RAG 问答": "rag_chat",
            "📡 情报推送": "push_panel",
            "📝 课后复习": "review",
            "🔒 隐私控制": "privacy",
            "⚙️ 系统管理": "admin",
        }

        # 初始化当前页面状态
        if not get_state("current_page"):
            set_state("current_page", "course_map")

        # 渲染导航按钮
        for label, page_key in pages.items():
            if st.sidebar.button(
                label,
                key=f"nav_{page_key}",
                use_container_width=True,
                type="primary" if get_state("current_page") == page_key else "secondary",
            ):
                set_state("current_page", page_key)
                st.rerun()

        st.divider()

        # 底部信息
        st.markdown(
            """
            <div style="text-align: center; color: #999; font-size: 0.8rem;">
                <p>v1.0.0 · 三人团队开发</p>
            </div>
            """,
            unsafe_allow_html=True,
        )


# ── 页面路由 ──────────────────────────────────────────────
def route_page():
    """根据 session_state 路由到对应页面"""
    current = get_state("current_page", "course_map")

    # 页面模块映射（模块名不能以数字开头，使用映射表）
    page_modules = {
        "course_map": "pages.page_course_map",
        "course_detail": "pages.page_course_detail",
        "campus_qa": "pages.page_campus_qa",
        "rag_chat": "pages.page_rag_chat",
        "push_panel": "pages.page_push_panel",
        "review": "pages.page_review",
        "privacy": "pages.page_privacy",
        "admin": "pages.page_admin",
    }

    # 动态导入页面模块（延迟加载，避免未实现页面阻塞启动）
    if current in page_modules:
        try:
            module = __import__(page_modules[current], fromlist=["main"])
            # 执行页面模块的 main() 函数来渲染页面
            if hasattr(module, "main"):
                module.main()
        except ImportError:
            # 页面模块不存在时显示占位页
            _render_placeholder(current)
    else:
        _render_placeholder(current)


def _render_placeholder(page_key: str):
    """渲染占位页面（页面模块未实现时）"""
    page_names = {
        "course_map": "课程地图",
        "course_detail": "课程详情",
        "campus_qa": "校园十万个为什么",
        "rag_chat": "RAG 问答",
        "push_panel": "情报推送",
        "review": "课后复习",
        "privacy": "隐私控制",
        "admin": "系统管理",
    }

    name = page_names.get(page_key, page_key)

    st.markdown(f"## 🚧 {name}")
    st.info(f"**{name}** 页面正在开发中，敬请期待...")

    st.markdown(
        """
        ---
        ### 开发进度
        - [ ] 课程地图 - Day 2 骨架
        - [ ] 课程详情 - Day 5 完成
        - [ ] 校园十万个为什么 - Day 12 启动
        - [ ] RAG 问答 - Day 15 启动
        - [ ] 情报推送 - Day 10 完成
        - [ ] 课后复习 - Day 22 启动
        - [ ] 隐私控制 - Day 26 完成
        - [ ] 系统管理 - Day 27 完成
        """
    )


# ── 主入口 ──────────────────────────────────────────────
def main():
    """应用主入口"""
    # 初始化默认状态
    init_default_state()

    # 渲染侧边栏
    render_sidebar()

    # 路由到当前页面
    route_page()


if __name__ == "__main__":
    main()
