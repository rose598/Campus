"""
GraphCampus 前端主入口
Streamlit 多页面应用配置 + 侧边栏导航路由
"""

import streamlit as st
import importlib.util
from pathlib import Path

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

        # 导航菜单（文件名与规划书对齐：01~05）
        pages = {
            "📡 活动推送": "activity_push",
            "❓ 知识问答": "campus_qa",
            "📚 课程资料": "course_materials",
            "🗺️ 课程地图": "course_map",
            "⚙️ 系统设置": "settings",
        }

        # 初始化当前页面状态
        if not get_state("current_page"):
            set_state("current_page", "activity_push")

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
                <p>v1.0.0 · 四人团队开发</p>
            </div>
            """,
            unsafe_allow_html=True,
        )


# ── 页面路由 ──────────────────────────────────────────────
def _load_page_module(file_path: Path):
    """
    从文件路径动态加载 Python 模块（支持以数字开头的文件名）

    Args:
        file_path: 页面 .py 文件路径

    Returns:
        加载后的模块对象，失败返回 None
    """
    if not file_path.exists():
        return None
    spec = importlib.util.spec_from_file_location(file_path.stem, str(file_path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def route_page():
    """根据 session_state 路由到对应页面"""
    current = get_state("current_page", "activity_push")

    # 页面文件映射（key → 文件名）
    page_files = {
        "activity_push": "01_activity_push.py",
        "campus_qa": "02_campus_qa.py",
        "course_materials": "03_course_materials.py",
        "settings": "04_settings.py",
        "onboarding": "05_onboarding.py",
        "course_map": "page_course_map.py",
    }

    if current in page_files:
        pages_dir = Path(__file__).parent / "pages"
        file_path = pages_dir / page_files[current]
        module = _load_page_module(file_path)
        if module and hasattr(module, "main"):
            module.main()
        else:
            _render_placeholder(current)
    else:
        _render_placeholder(current)


def _render_placeholder(page_key: str):
    """渲染占位页面（页面模块未实现时）"""
    page_names = {
        "activity_push": "活动推送",
        "campus_qa": "知识问答",
        "course_materials": "课程资料",
        "settings": "系统设置",
        "onboarding": "新手引导",
        "course_map": "课程地图",
    }

    name = page_names.get(page_key, page_key)

    st.markdown(f"## 🚧 {name}")
    st.info(f"**{name}** 页面正在开发中，敬请期待...")

    st.markdown(
        """
        ---
        ### 开发进度
        - [x] 活动推送 - Day 5 完成（含分数展示 + 推理链 + 排序筛选）
        - [x] 知识问答 - Day 6 完成（分类 Tab + 输入框 + 热门问题）
        - [x] 课程资料 - Day 3 占位（待 Day 15 完善）
        - [x] 系统设置 - Day 3 占位
        - [x] 课程地图 - Day 2 骨架
        - [x] 新手引导 - Day 5 完成（4 步引导流程）
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
