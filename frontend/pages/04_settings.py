"""
系统设置页（04_settings）
配置管理 + 隐私控制 + 特征开关
"""

import streamlit as st

from state_sync import get_state, set_state


# ── 页面渲染 ──────────────────────────────────────────────

def render_header():
    """渲染页面头部"""
    st.markdown(
        """
        <div style="text-align: center; padding: 1rem 0;">
            <h1>⚙️ 系统设置</h1>
            <p style="color: #666;">管理系统配置、隐私模式和功能开关</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_config_section():
    """渲染配置管理区域"""
    st.markdown("### 📝 全局配置")

    st.info(
        "**配置管理开发中...**\n\n"
        "即将支持：\n"
        "- 🔧 LLM 模型选择与参数调整\n"
        "- 📊 RAG 检索参数（Top-K / chunk_size / RRF k）\n"
        "- 🔄 配置热加载（修改后无需重启）\n"
    )

    # LLM 配置占位
    with st.expander("🤖 LLM 配置", expanded=False):
        st.text_input("模型", value="gpt-4o-mini", disabled=True)
        st.slider("Temperature", 0.0, 1.0, 0.3, disabled=True)
        st.slider("最大重试次数", 1, 5, 3, disabled=True)

    # RAG 配置占位
    with st.expander("🔍 RAG 检索配置", expanded=False):
        st.slider("BM25 Top-K", 1, 20, 5, disabled=True)
        st.slider("Dense Top-K", 1, 20, 5, disabled=True)
        st.slider("RRF k", 1, 100, 60, disabled=True)
        st.slider("Chunk Size", 128, 1024, 512, disabled=True)


def render_feature_flags():
    """渲染特征开关"""
    st.divider()
    st.markdown("### 🚩 功能开关")

    st.info("功能开关管理开发中，当前所有功能默认开启。")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.toggle("📡 活动智能推送", value=True, disabled=True)

    with col2:
        st.toggle("❓ 校园知识问答", value=True, disabled=True)

    with col3:
        st.toggle("📚 课程资料总结", value=True, disabled=True)


def render_privacy_section():
    """渲染隐私控制"""
    st.divider()
    st.markdown("### 🔒 隐私控制")

    privacy_mode = get_state("privacy_mode", "standard")

    mode_options = {
        "offline": {
            "label": "🔒 离线模式",
            "desc": "纯 BM25 检索 + 规则推荐，不调用 LLM，完全本地运行",
        },
        "standard": {
            "label": "🟢 标准模式（默认）",
            "desc": "缓存命中优先，减少 LLM 调用，平衡性能与效果",
        },
    }

    selected_mode = st.radio(
        "选择隐私模式",
        options=list(mode_options.keys()),
        format_func=lambda x: mode_options[x]["label"],
        index=list(mode_options.keys()).index(privacy_mode) if privacy_mode in mode_options else 1,
        disabled=True,
    )

    if selected_mode in mode_options:
        st.caption(mode_options[selected_mode]["desc"])


def render_system_info():
    """渲染系统信息"""
    st.divider()
    st.markdown("### 📊 系统信息")

    # 2×2 网格：移动端避免四行堆叠占用过多纵向空间
    row1_cols = st.columns(2)
    row2_cols = st.columns(2)

    with row1_cols[0]:
        st.metric("版本", "v1.0.0")

    with row1_cols[1]:
        st.metric("数据库", "SQLite WAL")

    with row2_cols[0]:
        st.metric("缓存条目", "0")

    with row2_cols[1]:
        st.metric("运行状态", "✅ 正常")


# ── 主入口 ──────────────────────────────────────────────

def main():
    """系统设置页主入口"""
    render_header()
    render_config_section()
    render_feature_flags()
    render_privacy_section()
    render_system_info()


if __name__ == "__main__":
    main()
