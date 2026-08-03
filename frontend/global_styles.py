"""
全局样式与页面引导（Day 26 复查修复）

背景：frontend/pages/ 目录会被 Streamlit 多页面机制自动发现。
用户直接访问子页面 URL（如 /settings）时，页面脚本独立执行，
不会经过 app.py，导致全局样式与页面配置缺失。

本模块提供 bootstrap_page()，供 app.py 与各页面 main() 调用，
确保任何入口下全局样式一致（重复调用安全）。
"""

import streamlit as st

# 全局 CSS（含 Day 24 移动端适配）
GLOBAL_CSS = """
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
"""


def bootstrap_page() -> None:
    """
    页面引导：注入页面配置 + 全局样式

    重复调用安全：set_page_config 仅首次生效，样式重复注入无副作用。
    """
    try:
        st.set_page_config(
            page_title="GraphCampus - 智慧校园课程导航",
            page_icon="🎓",
            layout="wide",
            initial_sidebar_state="expanded",
        )
    except st.errors.StreamlitAPIException:
        # 同一会话内 set_page_config 只能调用一次（经 app.py 进入时已设置）
        pass

    st.markdown(GLOBAL_CSS, unsafe_allow_html=True)
