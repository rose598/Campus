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
    /* 全局字体和间距（双选择器兼容新旧版 Streamlit） */
    .main .block-container, .block-container {
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

    /* ══ 移动端适配（Day 24）════════════════════════ */

    /* 输入框字号 ≥16px，避免 iOS 聚焦时自动放大页面 */
    input, textarea, select {
        font-size: 16px !important;
    }

    @media (max-width: 768px) {
        /* 内容区：减小内边距，预留底部安全区 */
        .main .block-container, .block-container {
            padding: 1rem 0.75rem 4.5rem;
            max-width: 100%;
        }

        /* 标题层级缩小 */
        h1 { font-size: 1.5rem !important; }
        h2 { font-size: 1.25rem !important; }
        h3 { font-size: 1.1rem !important; }
        h4 { font-size: 1rem !important; }

        /* 侧边栏全屏展开 */
        [data-testid="stSidebar"] {
            width: 100% !important;
        }

        /* 指标卡紧凑化（数据概览四宫格） */
        [data-testid="stMetric"] {
            padding: 0.5rem 0.6rem;
            background-color: #fafbfc;
            border-radius: 8px;
        }
        [data-testid="stMetricLabel"] { font-size: 0.78rem; }
        [data-testid="stMetricValue"] { font-size: 1.25rem; }

        /* 按钮触控区 ≥44px（iOS HIG 标准） */
        .stButton > button,
        .stDownloadButton > button,
        .stFormSubmitButton > button {
            min-height: 44px;
        }

        /* 表格横向滚动，避免撑破布局 */
        [data-testid="stDataFrame"],
        [data-testid="stTable"] {
            overflow-x: auto;
            max-width: 100%;
        }

        /* 聊天气泡紧凑化 */
        [data-testid="stChatMessage"] {
            padding: 0.5rem 0.6rem;
        }

        /* 自定义卡片移动端收缩（首页功能卡等） */
        .gc-card {
            min-height: auto !important;
            padding: 1rem !important;
        }

        /* expander 内文本紧凑 */
        .streamlit-expanderContent {
            font-size: 0.85rem;
        }

        /* 长文本/代码块自动换行 */
        pre, code {
            white-space: pre-wrap;
            word-break: break-word;
        }
    }

    /* 平板过渡（769-1024px）：适度收紧内容区 */
    @media (max-width: 1024px) and (min-width: 769px) {
        .main .block-container, .block-container {
            padding-left: 1.5rem;
            padding-right: 1.5rem;
        }
    }
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

        # 导航菜单（文件名与规划书对齐：00~06）
        pages = {
            "🏠 首页": "home",
            "📡 活动推送": "activity_push",
            "❓ 知识问答": "campus_qa",
            "📚 课程资料": "course_materials",
            "🎓 学伴对话": "study_buddy",
            "🗺️ 课程地图": "course_map",
            "⚙️ 系统设置": "settings",
        }

        # 初始化当前页面状态
        if not get_state("current_page"):
            set_state("current_page", "home")

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
    current = get_state("current_page", "home")

    # 页面文件映射（key → 文件名）
    page_files = {
        "home": "00_home.py",
        "activity_push": "01_activity_push.py",
        "campus_qa": "02_campus_qa.py",
        "course_materials": "03_course_materials.py",
        "study_buddy": "06_study_buddy.py",
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
        "home": "首页",
        "activity_push": "活动推送",
        "campus_qa": "知识问答",
        "course_materials": "课程资料",
        "study_buddy": "学伴对话",
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
