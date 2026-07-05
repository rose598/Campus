"""
中断交互弹窗组件

用于双路 LLM 验证流程中的用户交互：
- 中置信度（0.5 ≤ confidence < 1.0）：确认弹窗，展示两路差异
- 低置信度（confidence < 0.5）：编辑弹窗，手动编辑先修课程列表
- Node2Vec 链路预测：推荐弹窗，展示缺失先修关系

依赖：
    - streamlit >= 1.35（@st.dialog 装饰器）
    - frontend/state_sync.py（状态管理）
"""

import streamlit as st

from state_sync import get_state, set_state, delete_state

# ── 常量 ───────────────────────────────────────────────────────────────────────

# 置信度阈值
CONFIDENCE_HIGH = 1.0       # 高置信度：自动入库，无需弹窗
CONFIDENCE_MEDIUM_LOW = 0.5 # 中/低置信度分界

# 状态键（不带前缀，由 state_sync 自动加 graphcampus_ 前缀）
_KEY_INTERRUPT_RESULT = "interrupt_result"
_KEY_INTERRUPT_ACTIVE = "interrupt_active"


# ── 置信度等级判定 ────────────────────────────────────────────────────────────

def get_confidence_level(confidence: str) -> str:
    """
    根据置信度分数返回等级标签

    Args:
        confidence: 置信度等级字符串 ("high" | "medium" | "low")

    Returns:
        str: "high" / "medium" / "low"
    """
    level_map = {
        "high": "high",
        "medium": "medium",
        "low": "low",
    }
    return level_map.get(confidence, "medium")


def get_confidence_color(level: str) -> str:
    """返回置信度等级对应的颜色"""
    colors = {"high": "#28a745", "medium": "#ffc107", "low": "#dc3545"}
    return colors.get(level, "#6c757d")


def get_confidence_label(level: str) -> str:
    """返回置信度等级的中文标签"""
    labels = {"high": "高置信度", "medium": "中置信度", "low": "低置信度"}
    return labels.get(level, "未知")


# ── 置信度标签组件 ────────────────────────────────────────────────────────────

def render_confidence_tag(level: str) -> None:
    """
    渲染彩色置信度标签

    Args:
        level: 置信度等级 ("high" / "medium" / "low")
    """
    color = get_confidence_color(level)
    label = get_confidence_label(level)
    st.markdown(
        f"""<span style="
            background-color: {color};
            color: white;
            padding: 2px 10px;
            border-radius: 12px;
            font-size: 0.85em;
            font-weight: 600;
        ">{label}</span>""",
        unsafe_allow_html=True,
    )


# ── 确认弹窗（中置信度）──────────────────────────────────────────────────────

@st.dialog("⚠️ 先修课程确认", width="large")
def show_confirm_dialog(
    course_name: str,
    confidence: str,
    prereqs_a: list[str],
    prereqs_b: list[str],
    diff_items: list[dict],
) -> None:
    """
    中置信度确认弹窗

    展示两路 LLM 提取结果的差异，让用户确认或拒绝。

    Args:
        course_name: 当前课程名称
        confidence: 置信度等级 ("medium")
        prereqs_a: LLM-A 提取的先修课程列表
        prereqs_b: LLM-B 提取的先修课程列表
        diff_items: 差异项列表，每项格式:
            {"course": str, "in_a": bool, "in_b": bool}
    """
    # 置信度标签
    render_confidence_tag(confidence)

    st.markdown(f"### 📚 课程：{course_name}")
    st.markdown(
        "两路 AI 分析结果存在差异，请确认最终的先修课程列表。"
    )

    # 两路结果对比
    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("#### 🤖 AI-A 提取结果")
        if prereqs_a:
            for p in prereqs_a:
                st.markdown(f"- `{p}`")
        else:
            st.caption("（无先修课程）")

    with col_b:
        st.markdown("#### 🤖 AI-B 提取结果")
        if prereqs_b:
            for p in prereqs_b:
                st.markdown(f"- `{p}`")
        else:
            st.caption("（无先修课程）")

    # 差异项高亮
    if diff_items:
        st.markdown("---")
        st.markdown("#### 🔍 差异项")
        for item in diff_items:
            course = item.get("course", "")
            in_a = item.get("in_a", False)
            in_b = item.get("in_b", False)
            status_a = "✅" if in_a else "❌"
            status_b = "✅" if in_b else "❌"
            st.markdown(
                f"- **{course}** — AI-A: {status_a}　AI-B: {status_b}"
            )

    # 操作按钮
    st.markdown("---")
    col_confirm, col_reject = st.columns(2)

    with col_confirm:
        if st.button(
            "✅ 确认（取并集）",
            use_container_width=True,
            type="primary",
            key="confirm_merge_btn",
        ):
            merged = list(set(prereqs_a) | set(prereqs_b))
            _set_interrupt_result("confirm", {
                "course_name": course_name,
                "merged_prereqs": sorted(merged),
            })
            st.rerun()

    with col_reject:
        if st.button(
            "❌ 拒绝（丢弃结果）",
            use_container_width=True,
            key="confirm_reject_btn",
        ):
            _set_interrupt_result("reject", {
                "course_name": course_name,
            })
            st.rerun()


# ── 编辑弹窗（低置信度）──────────────────────────────────────────────────────

@st.dialog("✏️ 手动编辑先修课程", width="large")
def show_edit_dialog(
    course_name: str,
    confidence: str,
    suggested_prereqs: list[str],
    all_courses: list[dict],
) -> None:
    """
    低置信度编辑弹窗

    用户手动编辑先修课程列表，从已有课程中选择。

    Args:
        course_name: 当前课程名称
        confidence: 置信度等级 ("low")
        suggested_prereqs: AI 建议的先修课程（可能不准确）
        all_courses: 所有可选课程列表，每项格式:
            {"code": str, "name": str}
    """
    render_confidence_tag(confidence)

    st.markdown(f"### 📚 课程：{course_name}")
    st.warning(
        "AI 提取置信度过低，请手动确认或编辑先修课程列表。"
    )

    # 构建课程选项映射
    course_options = {
        c["code"]: f"{c['code']} - {c['name']}" for c in all_courses
    }
    course_labels = list(course_options.values())

    # 预选 AI 建议的先修课程
    default_selection = [
        course_options[c] for c in suggested_prereqs if c in course_options
    ]

    # 多选下拉框
    selected_labels = st.multiselect(
        "选择先修课程（可多选）",
        options=course_labels,
        default=default_selection,
        key="edit_prereq_select",
        help="从已有课程中选择作为先修课程",
    )

    # 反向映射：label → code
    label_to_code = {v: k for k, v in course_options.items()}
    selected_codes = [label_to_code[label] for label in selected_labels]

    # 预览区
    if selected_codes:
        st.markdown("#### 📋 当前选择的先修课程")
        for code in selected_codes:
            name = course_options.get(code, code)
            st.markdown(f"- `{code}` — {name.split(' - ', 1)[-1] if ' - ' in name else code}")

    # 操作按钮
    st.markdown("---")
    col_save, col_cancel = st.columns(2)

    with col_save:
        if st.button(
            "💾 保存",
            use_container_width=True,
            type="primary",
            key="edit_save_btn",
        ):
            _set_interrupt_result("save", {
                "course_name": course_name,
                "prereqs": selected_codes,
            })
            st.rerun()

    with col_cancel:
        if st.button(
            "取消",
            use_container_width=True,
            key="edit_cancel_btn",
        ):
            _set_interrupt_result("cancel", {"course_name": course_name})
            st.rerun()


# ── 链路预测弹窗 ──────────────────────────────────────────────────────────────

@st.dialog("🔗 链路预测推荐", width="large")
def show_prediction_dialog(
    predictions: list[dict],
) -> None:
    """
    Node2Vec 链路预测弹窗

    展示模型发现的可能缺失的先修关系，让用户确认或拒绝。

    Args:
        predictions: 预测结果列表，每项格式:
            {
                "source": str,       # 源课程代码
                "target": str,       # 目标课程代码
                "source_name": str,  # 源课程名称
                "target_name": str,  # 目标课程名称
                "score": float,      # 相关性分数 (0-1)
            }
    """
    st.markdown("### 🔗 AI 发现可能缺失的先修关系")
    st.markdown(
        "基于课程图谱分析，以下课程对之间可能存在先修关系，请确认。"
    )

    if not predictions:
        st.info("暂无新的推荐。")
        if st.button("关闭", key="pred_close_empty_btn"):
            _set_interrupt_result("close", {})
            st.rerun()
        return

    # 按分数降序排列
    sorted_preds = sorted(predictions, key=lambda x: x.get("score", 0), reverse=True)

    # 用复选框逐条展示，用户勾选后统一确认
    selected_indices = []
    for i, pred in enumerate(sorted_preds):
        source = pred.get("source", "")
        target = pred.get("target", "")
        source_name = pred.get("source_name", source)
        target_name = pred.get("target_name", target)
        score = pred.get("score", 0.0)

        # 分数颜色
        if score >= 0.8:
            score_color = "#28a745"
        elif score >= 0.5:
            score_color = "#ffc107"
        else:
            score_color = "#6c757d"

        col_check, col_info = st.columns([1, 6])
        with col_check:
            checked = st.checkbox(
                "选择",
                key=f"pred_check_{i}",
                label_visibility="collapsed",
            )
            if checked:
                selected_indices.append(i)

        with col_info:
            st.markdown(
                f"""<div style="
                    border: 1px solid #dee2e6;
                    border-radius: 8px;
                    padding: 10px 12px;
                    margin-bottom: 4px;
                ">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <div>
                            <code>{source}</code> {source_name}
                            <span style="margin: 0 8px;">→</span>
                            <code>{target}</code> {target_name}
                        </div>
                        <span style="
                            background-color: {score_color};
                            color: white;
                            padding: 2px 10px;
                            border-radius: 12px;
                            font-size: 0.85em;
                            font-weight: 600;
                        ">相关性 {score:.0%}</span>
                    </div>
                </div>""",
                unsafe_allow_html=True,
            )

    # 操作按钮
    st.markdown("---")
    col_confirm, col_all, col_none = st.columns(3)

    with col_confirm:
        if st.button(
            "✅ 确认勾选项",
            use_container_width=True,
            type="primary",
            key="pred_confirm_selected_btn",
            disabled=len(selected_indices) == 0,
        ):
            accepted = [
                {"source": sorted_preds[i]["source"], "target": sorted_preds[i]["target"],
                 "score": sorted_preds[i].get("score", 0)}
                for i in selected_indices
            ]
            _set_interrupt_result("accept_prediction", {"accepted": accepted})
            st.rerun()

    with col_all:
        if st.button(
            "✅ 全部确认",
            use_container_width=True,
            key="pred_accept_all_btn",
        ):
            all_accepted = [
                {"source": p["source"], "target": p["target"], "score": p.get("score", 0)}
                for p in sorted_preds
            ]
            _set_interrupt_result("accept_all", {"accepted": all_accepted})
            st.rerun()

    with col_none:
        if st.button(
            "❌ 全部跳过",
            use_container_width=True,
            key="pred_skip_all_btn",
        ):
            _set_interrupt_result("skip_all", {})
            st.rerun()


# ── 结果读写工具 ──────────────────────────────────────────────────────────────

def _set_interrupt_result(action: str, data: dict) -> None:
    """
    写入中断交互结果

    Args:
        action: 用户操作 ("confirm" / "reject" / "save" / "cancel"
                / "accept_prediction" / "accept_all" / "skip_all" / "close")
        data: 操作附带的数据
    """
    set_state(_KEY_INTERRUPT_RESULT, {
        "action": action,
        "data": data,
    })
    # 清除中断状态，避免残留
    set_state(_KEY_INTERRUPT_ACTIVE, False)
    delete_state("interrupt_type")
    delete_state("interrupt_params")


def get_interrupt_result() -> dict | None:
    """
    获取中断交互结果

    Returns:
        dict 或 None: {"action": str, "data": dict}，无结果返回 None
    """
    return get_state(_KEY_INTERRUPT_RESULT)


def clear_interrupt_result() -> None:
    """清除中断交互结果（读取后调用，避免重复处理）"""
    delete_state(_KEY_INTERRUPT_RESULT)


def is_interrupt_active() -> bool:
    """检查是否有弹窗正在显示"""
    return get_state(_KEY_INTERRUPT_ACTIVE, False)


def trigger_interrupt(interrupt_type: str, **kwargs) -> None:
    """
    触发中断弹窗（供 Agent 节点调用）

    Args:
        interrupt_type: 弹窗类型 ("confirm" / "edit" / "prediction")
        **kwargs: 传递给对应弹窗函数的参数
    """
    set_state(_KEY_INTERRUPT_ACTIVE, True)
    set_state("interrupt_type", interrupt_type)
    set_state("interrupt_params", kwargs)


def render_interrupt_if_needed() -> dict | None:
    """
    检查并渲染中断弹窗（页面 main() 中调用）

    如果有待处理的中断，弹出对应弹窗并返回用户操作结果。
    无中断时返回 None。

    Returns:
        dict 或 None: 用户操作结果
    """
    # 先检查是否有已完成的结果
    result = get_interrupt_result()
    if result:
        clear_interrupt_result()
        return result

    # 检查是否有待触发的中断
    if not is_interrupt_active():
        return None

    interrupt_type = get_state("interrupt_type", "")
    params = get_state("interrupt_params", {})

    # 根据类型弹出对应弹窗
    if interrupt_type == "confirm":
        show_confirm_dialog(**params)
    elif interrupt_type == "edit":
        show_edit_dialog(**params)
    elif interrupt_type == "prediction":
        show_prediction_dialog(**params)
    else:
        # 未知类型，清除中断状态
        set_state(_KEY_INTERRUPT_ACTIVE, False)

    return None
