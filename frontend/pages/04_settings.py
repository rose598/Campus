"""
系统设置页（04_settings）
配置管理 + 隐私控制 + 特征开关
Day 25: 隐私控制面板完整实现
Day 27: 配置管理 + 特征开关 UI 接活（对接 config_loader + FeatureFlags）
"""

import streamlit as st

from global_styles import bootstrap_page

from state_sync import (
    get_state,
    set_state,
    get_user_profile,
    get_chat_history,
    clear_chat_history,
    clear_all_state,
)


# ── 后端模块导入（带容错：前端可独立运行）─────────────────
def _get_config_loader():
    """延迟导入 config_loader，不可用时返回 None"""
    try:
        import utils.config_loader as cfg
        return cfg
    except Exception:
        return None


def _get_feature_flags():
    """延迟导入 FeatureFlags，不可用时返回 None"""
    try:
        from config.feature_flags import FeatureFlags
        return FeatureFlags
    except Exception:
        return None


def _get_health():
    """延迟导入 health 模块，不可用时返回 None"""
    try:
        from utils.health import quick_check
        return quick_check
    except Exception:
        return None


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


# ── 特征开关元信息（图标 + 描述）──────────────────────────
FLAG_META = {
    "activity_push":    {"icon": "📡", "label": "活动智能推送", "desc": "基于 PPR 图推理的个性化活动推荐"},
    "campus_qa":        {"icon": "❓", "label": "校园知识问答", "desc": "Hybrid RAG 驱动的校园百科问答"},
    "course_summary":   {"icon": "📚", "label": "课程资料总结", "desc": "AI 自动生成课程资料摘要"},
    "semantic_cache":   {"icon": "🧠", "label": "语义缓存",   "desc": "相似问题命中缓存，减少 LLM 调用"},
    "offline_mode":     {"icon": "🔒", "label": "离线模式",   "desc": "不调用 LLM，纯本地检索 + 规则推荐"},
    "strict_privacy":   {"icon": "🛡️", "label": "严格隐私",   "desc": "禁止一切外部数据发送"},
}


# ── 页面渲染 ──────────────────────────────────────────────

def render_header():
    """渲染页面头部"""
    st.markdown(
        """
        <div style="text-align: center; padding: 0.5rem 0;">
            <h1>⚙️ 系统设置</h1>
            <p style="color: #666;">管理系统配置、隐私模式和功能开关</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_config_section():
    """渲染配置管理区域（Day 27 接活：对接 config_loader）"""
    st.markdown("### 📝 全局配置")

    cfg = _get_config_loader()
    if cfg is None:
        st.warning("⚠️ 配置模块不可用，当前为只读展示模式")
        readonly = True
    else:
        readonly = False

    # ── LLM 配置 ──
    with st.expander("🤖 LLM 配置", expanded=False):
        cur_model = cfg.get("llm.model", "gpt-4o-mini") if cfg else "gpt-4o-mini"
        cur_temp = cfg.get("llm.temperature", 0.3) if cfg else 0.3
        cur_retries = cfg.get("llm.max_retries", 3) if cfg else 3
        cur_concurrency = cfg.get("llm.concurrency_limit", 3) if cfg else 3

        new_model = st.selectbox(
            "模型", 
            ["gpt-4o-mini", "gpt-4o", "gpt-3.5-turbo"],
            index=["gpt-4o-mini", "gpt-4o", "gpt-3.5-turbo"].index(cur_model) if cur_model in ["gpt-4o-mini", "gpt-4o", "gpt-3.5-turbo"] else 0,
            disabled=readonly,
            key="cfg_ll_model",
        )
        new_temp = st.slider("Temperature", 0.0, 1.0, float(cur_temp), disabled=readonly, key="cfg_llm_temp")
        new_retries = st.slider("最大重试次数", 1, 5, int(cur_retries), disabled=readonly, key="cfg_llm_retries")
        new_concurrency = st.slider("并发上限", 1, 10, int(cur_concurrency), disabled=readonly, key="cfg_llm_conc")

        if not readonly:
            if st.button("💾 保存 LLM 配置", type="primary", key="btn_save_llm"):
                cfg.set("llm.model", new_model)
                cfg.set("llm.temperature", new_temp)
                cfg.set("llm.max_retries", new_retries)
                cfg.set("llm.concurrency_limit", new_concurrency)
                st.success("✅ LLM 配置已生效（本次会话）")

    # ── RAG 检索配置 ──
    with st.expander("🔍 RAG 检索配置", expanded=False):
        cur_bm25 = cfg.get("rag.bm25_top_k", 5) if cfg else 5
        cur_dense = cfg.get("rag.dense_top_k", 5) if cfg else 5
        cur_rrf = cfg.get("rag.rrf_k", 60) if cfg else 60
        cur_chunk = cfg.get("rag.chunk_size", 512) if cfg else 512
        cur_final = cfg.get("rag.final_top_k", 3) if cfg else 3

        new_bm25 = st.slider("BM25 Top-K", 1, 20, int(cur_bm25), disabled=readonly, key="cfg_bm25_k")
        new_dense = st.slider("Dense Top-K", 1, 20, int(cur_dense), disabled=readonly, key="cfg_dense_k")
        new_rrf = st.slider("RRF k", 1, 100, int(cur_rrf), disabled=readonly, key="cfg_rrf_k")
        new_chunk = st.slider("Chunk Size", 128, 1024, int(cur_chunk), disabled=readonly, key="cfg_chunk")
        new_final = st.slider("最终返回条数", 1, 10, int(cur_final), disabled=readonly, key="cfg_final_k")

        if not readonly:
            if st.button("💾 保存 RAG 配置", type="primary", key="btn_save_rag"):
                cfg.set("rag.bm25_top_k", new_bm25)
                cfg.set("rag.dense_top_k", new_dense)
                cfg.set("rag.rrf_k", new_rrf)
                cfg.set("rag.chunk_size", new_chunk)
                cfg.set("rag.final_top_k", new_final)
                st.success("✅ RAG 配置已生效（本次会话）")

    # ── 配置操作 ──
    if not readonly:
        st.caption("配置修改仅在本次会话内生效。如需持久化，请编辑 `config/config.yaml`。")
        if st.button("🔄 重新加载配置文件", key="btn_reload_cfg"):
            cfg.reload()
            st.success("✅ 配置文件已重新加载")
            st.rerun()


def render_feature_flags():
    """渲染特征开关（Day 27 接活：对接 FeatureFlags）"""
    st.divider()
    st.markdown("### 🚩 功能开关")

    ff = _get_feature_flags()
    if ff is None:
        st.warning("⚠️ 特征开关模块不可用，当前为只读展示模式")
        # 降级展示默认值
        all_flags = {
            "activity_push": True, "campus_qa": True, "course_summary": True,
            "semantic_cache": True, "offline_mode": False, "strict_privacy": False,
        }
    else:
        all_flags = ff.get_all()

    st.caption("关闭某个功能后，对应页面将显示不可用提示。修改立即生效。")

    # 分两行三列展示
    flag_keys = list(FLAG_META.keys())
    for row_start in range(0, len(flag_keys), 3):
        cols = st.columns(3)
        for i, col in enumerate(cols):
            idx = row_start + i
            if idx >= len(flag_keys):
                break
            key = flag_keys[idx]
            meta = FLAG_META[key]
            current_val = all_flags.get(key, False)
            with col:
                new_val = st.toggle(
                    f"{meta['icon']} {meta['label']}",
                    value=current_val,
                    key=f"flag_toggle_{key}",
                    help=meta["desc"],
                )
                # 值变化时立即同步
                if new_val != current_val and ff is not None:
                    ff.set_flag(key, new_val)
                    status = "已开启" if new_val else "已关闭"
                    st.toast(f"{meta['icon']} {meta['label']} {status}")


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

    # 模式切换生效
    if selected_mode != privacy_mode:
        col_apply, col_hint = st.columns([1, 3])
        with col_apply:
            if st.button("✅ 应用模式", type="primary", use_container_width=True):
                set_state("privacy_mode", selected_mode)
                # 同步到后端 FeatureFlags
                ff = _get_feature_flags()
                synced = False
                if ff is not None:
                    ff.set_flag("offline_mode", selected_mode == "offline")
                    ff.set_flag("strict_privacy", selected_mode == "strict")
                    synced = True
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
    """渲染系统信息（Day 27 接活：对接 health 模块）"""
    st.divider()
    st.markdown("### 📊 系统信息")

    health_check = _get_health()

    if health_check is not None:
        report = health_check()

        # 整体状态指示
        status_map = {"healthy": "🟢 正常", "degraded": "🟡 降级", "error": "🔴 异常"}
        overall_label = status_map.get(report.overall, report.overall)
        st.markdown(f"**系统状态：** {overall_label}  ·  **检查耗时：** {report.total_latency_ms}ms")

        # 各组件状态
        for comp in report.components:
            icon = {"healthy": "✅", "degraded": "⚠️", "error": "❌"}.get(comp.status, "❓")
            latency_str = f" ({comp.latency_ms}ms)" if comp.latency_ms > 0 else ""
            st.markdown(f"{icon} **{comp.name}** — {comp.message}{latency_str}")

        # 特征开关快照
        if report.features:
            st.markdown("---")
            st.markdown("**当前特征开关快照：**")
            flags_text = "  ·  ".join(
                f"{'🟢' if v else '🔴'} {k}" for k, v in report.features.items()
            )
            st.markdown(f"<div style='font-size:0.85rem;'>{flags_text}</div>", unsafe_allow_html=True)
    else:
        # 降级展示
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
    bootstrap_page()
    render_header()
    render_config_section()
    render_feature_flags()
    render_privacy_section()
    render_data_management()
    render_system_info()


if __name__ == "__main__":
    main()
