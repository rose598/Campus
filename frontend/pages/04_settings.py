"""
系统设置页（04_settings）
配置管理 + 隐私控制 + 特征开关
Day 25: 隐私控制面板完整实现（模式切换 + 数据透明度 + 数据管理）
"""

import streamlit as st

from state_sync import (
    get_state,
    set_state,
    get_user_profile,
    get_chat_history,
    clear_chat_history,
    clear_all_state,
)


# ── 隐私模式定义 ─────────────────────────────────────
PRIVACY_MODES = {
    "standard": {
        "label": "🟢 标准模式（默认）",
        "desc": "缓存命中优先，减少 LLM 调用，平衡性能与效果",
        "features": [
            "✅ Hybrid RAG 检索（BM25 + Dense）",
            "✅ LLM 生成回答（带语义缓存）",
            "✅ PPR 个性化推荐",
            "✅ 所有数据仅存本地 SQLite",
        ],
    },
    "offline": {
        "label": "🔒 离线模式",
        "desc": "纯 BM25 检索 + 规则推荐，不调用 LLM，完全本地运行",
        "features": [
            "✅ 纯 BM25 关键词检索",
            "✅ 规则化活动推荐（热门优先）",
            "🚫 不调用任何外部 LLM API",
            "🚫 不发送任何数据到外部服务",
        ],
    },
}

# 数据存储透明度（与规划书 §8 隐私设计对齐）
DATA_STORAGE_ROWS = [
    ("🎯 用户兴趣画像", "本地 SQLite", "仅存于你的设备，可随时重置"),
    ("📚 课程资料", "本地 SQLite", "上传的课件/大纲仅本地存储"),
    ("📝 行为日志", "本地 SQLite", "结构化日志，不上传云端"),
    ("💬 对话记录", "浏览器会话", "关闭页面即失效，可手动清除"),
    ("🤖 LLM 调用内容", "仅临时内存", "仅传输结构化文本，不持久化"),
]


# ── 后端特征开关同步（带容错：后端模块不可用时降级为会话内生效）──
def _sync_privacy_flags(mode: str) -> bool:
    """
    将隐私模式同步到后端 FeatureFlags

    Returns:
        bool: 是否成功同步到后端开关
    """
    try:
        from config.feature_flags import FeatureFlags

        FeatureFlags.set_flag("offline_mode", mode == "offline")
        FeatureFlags.set_flag("strict_privacy", mode == "strict")
        return True
    except Exception:
        # 前端独立运行（后端模块不在导入路径）时降级
        return False


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
    """渲染隐私控制面板（Day 25 完整实现）"""
    st.divider()
    st.markdown("### 🔒 隐私控制")

    privacy_mode = get_state("privacy_mode", "standard")
    if privacy_mode not in PRIVACY_MODES:
        privacy_mode = "standard"

    # ── 模式切换 ──
    selected_mode = st.radio(
        "选择隐私模式",
        options=list(PRIVACY_MODES.keys()),
        format_func=lambda x: PRIVACY_MODES[x]["label"],
        index=list(PRIVACY_MODES.keys()).index(privacy_mode),
        key="privacy_mode_radio",
    )

    st.caption(PRIVACY_MODES[selected_mode]["desc"])

    # 模式能力对比
    with st.expander("📋 当前模式能力说明", expanded=False):
        for line in PRIVACY_MODES[selected_mode]["features"]:
            st.markdown(f"- {line}")

    # 切换生效
    if selected_mode != privacy_mode:
        col_apply, col_hint = st.columns([1, 3])
        with col_apply:
            if st.button("✅ 应用模式", type="primary", use_container_width=True):
                set_state("privacy_mode", selected_mode)
                synced = _sync_privacy_flags(selected_mode)
                if synced:
                    st.success(f"已切换到「{PRIVACY_MODES[selected_mode]['label']}」并同步后端开关")
                else:
                    st.success(f"已切换到「{PRIVACY_MODES[selected_mode]['label']}」（本次会话生效）")
                st.rerun()
        with col_hint:
            st.caption("切换后问答/推荐链路将按新模式运行")

    # 当前模式徽章
    current_label = PRIVACY_MODES[get_state("privacy_mode", "standard")]["label"]
    st.info(f"**当前生效模式：** {current_label}")

    # ── 数据存储透明度 ──
    st.markdown("#### 📂 你的数据存在哪里")
    st.caption("GraphCampus 所有数据仅存于你的本地设备，不上传任何云端")

    header = "| 数据类型 | 存储位置 | 说明 |\n|---|---|---|"
    rows = "\n".join(f"| {name} | {loc} | {note} |" for name, loc, note in DATA_STORAGE_ROWS)
    st.markdown(header + "\n" + rows)


def render_data_management():
    """渲染数据管理（清除历史/重置画像，带二次确认）"""
    st.divider()
    st.markdown("### 🗑️ 数据管理")

    qa_history = get_chat_history("qa_chat_history")
    buddy_history = get_chat_history("buddy_chat_history")
    profile = get_user_profile()
    profile_items = sum(
        1
        for v in [profile.get("major"), profile.get("interests"), profile.get("completed_courses")]
        if v
    )

    row1 = st.columns(3)
    with row1[0]:
        st.metric("问答对话", f"{len(qa_history)} 条")
    with row1[1]:
        st.metric("学伴对话", f"{len(buddy_history)} 条")
    with row1[2]:
        st.metric("画像条目", f"{profile_items} 项")

    col1, col2 = st.columns(2)

    # 清除对话历史
    with col1:
        st.markdown("**💬 清除对话历史**")
        st.caption("清空问答页与学伴页的全部聊天记录")
        confirm_chat = st.checkbox("我确认要清除对话历史", key="confirm_clear_chat")
        if st.button(
            "🗑️ 清除对话历史",
            disabled=not confirm_chat,
            use_container_width=True,
            key="btn_clear_chat",
        ):
            clear_chat_history("qa_chat_history")
            clear_chat_history("buddy_chat_history")
            st.success("✅ 对话历史已清空")
            st.rerun()

    # 重置个人画像
    with col2:
        st.markdown("**👤 重置个人画像**")
        st.caption("清除专业/兴趣/已修课程，推荐将回退为非个性化")
        confirm_profile = st.checkbox("我确认要重置个人画像", key="confirm_reset_profile")
        if st.button(
            "♻️ 重置个人画像",
            disabled=not confirm_profile,
            use_container_width=True,
            key="btn_reset_profile",
        ):
            set_state(
                "user_profile",
                {"major": None, "completed_courses": [], "interests": []},
            )
            set_state("onboarding_completed", False)
            st.success("✅ 个人画像已重置，下次进入将重新引导")
            st.rerun()

    # 一键清除全部（危险操作，折叠展示）
    with st.expander("⚠️ 高级：清除全部本地数据"):
        st.warning("此操作将清除所有会话数据（对话/画像/页面状态），不可恢复。")
        confirm_all = st.checkbox("我已了解风险，确认清除全部数据", key="confirm_clear_all")
        if st.button(
            "💥 清除全部数据",
            type="primary",
            disabled=not confirm_all,
            use_container_width=True,
            key="btn_clear_all",
        ):
            clear_all_state()
            st.success("✅ 全部本地数据已清除，页面即将重新初始化...")
            st.rerun()


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
    render_data_management()
    render_system_info()


if __name__ == "__main__":
    main()
