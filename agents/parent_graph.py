"""
父图编排 —— 路由 + 三子图并行（Fan-out） + 聚合

核心流程：
  router → [intel_agent, knowit_agent, buddy_agent] (并行 Fan-out via Send) → aggregator → END
"""
import time
from typing import Dict, Any, Optional, List

from langgraph.graph import StateGraph, END
from langgraph.types import Send
from langchain_core.runnables import RunnableConfig

from models.agent_state import AgentState
from agents.intel_agent import run_intel_node
from agents.knowit_agent import rewrite_query, classify_intent, retrieve_knowit, generate_knowit
from agents.buddy_agent import run_buddy_node
from utils import get_tracer


def node_router(state: AgentState, config: Optional[RunnableConfig] = None) -> Dict[str, Any]:
    """路由节点：解析用户意图，决定调用哪个子图"""
    tracer = _ensure_tracer(state, "router")
    messages = state.get("messages", [])

    user_query = ""
    for msg in reversed(messages):
        if getattr(msg, "type", "") == "human":
            user_query = getattr(msg, "content", "") or ""
            break

    intent = _rule_based_route(user_query)

    tracer.info(f"router decided: intent={intent}", node="router", detail={"query": user_query[:100], "intent": intent})

    return {"intent": intent}


def route_fan_agents(state: AgentState) -> List[Send]:
    """Fan-out：将 state 分发到三个并行子图"""
    targets = []

    # 情报官：始终参与（PPR 推荐）
    targets.append(Send("intel_agent", state))

    # 百事通：始终参与（问答核心）
    targets.append(Send("knowit_agent", state))

    # 学伴：Day 7 骨架，始终参与
    targets.append(Send("buddy_agent", state))

    return targets


def _rule_based_route(query: str) -> str:
    """基于关键词的规则路由（先于 LLM 分类，减少调用）"""
    q = query.lower() if query else ""

    kw_map = {
        "activity_push": ["活动", "讲座", "竞赛", "推荐", "推送", "科研机会", "信息", "情报",
                           "有什么活动", "最近活动", "推荐活动"],
        "campus_qa": ["政策", "保研", "转专业", "选课", "补考", "四六级", "食堂", "图书馆",
                       "宿舍", "住宿", "毕业", "学分", "通知", "规定", "条件", "要求"],
        "course_summary": ["课程资料", "课件", "大纲", "期末", "总结", "笔记", "复习",
                           "教材", "教学大纲", "考试重点", "考核"],
    }

    for intent, keywords in kw_map.items():
        for kw in keywords:
            if kw in q:
                return intent

    return "all"


def node_intel(state: AgentState, config: Optional[RunnableConfig] = None) -> Dict[str, Any]:
    """情报官包装节点（含计时日志）

    异常隔离：子图内部失败时返回降级结果，不阻断 Fan-out 其他分支。
    """
    tracer = _ensure_tracer(state, "intel_agent")
    start = time.time()

    try:
        result = run_intel_node(state)
    except Exception as e:  # noqa: BLE001 子图故障不冒泡
        tracer.error(f"intel failed: {e}", node="intel_agent")
        return {
            "intel_result": {
                "trace_id": state.get("trace_id", "unknown"),
                "recommendations": [],
                "status": "error",
                "error": str(e)[:200],
            }
        }

    latency_ms = int((time.time() - start) * 1000)
    recs = (result.get("intel_result", {}) or {}).get("recommendations", [])
    tracer.info(f"intel completed: {len(recs)} recommendations", node="intel_agent", latency_ms=latency_ms)

    return result


def node_knowit(state: AgentState, config: Optional[RunnableConfig] = None) -> Dict[str, Any]:
    """百事通全流程包装节点（查询改写 → 分类 → 检索 → 生成）

    异常隔离：任一环节异常时返回降级 qa_result，不阻断其他子图。
    """
    tracer = _ensure_tracer(state, "knowit_agent")
    start = time.time()

    try:
        return _run_knowit_pipeline(state, tracer, start)
    except Exception as e:  # noqa: BLE001 子图故障不冒泡
        tracer.error(f"knowit failed: {e}", node="knowit_agent")
        return {
            "qa_result": {
                "trace_id": state.get("trace_id", "unknown"),
                "answer": "校园问答服务暂时不可用，请稍后重试。",
                "sources": [],
                "status": "error",
                "error": str(e)[:200],
            }
        }


def _run_knowit_pipeline(state: AgentState, tracer, start: float) -> Dict[str, Any]:
    """百事通内部流水线（改写 → 分类 → 检索 → 生成）"""
    state_updates: Dict[str, Any] = {}

    # Step 0: 多轮对话查询改写（Day 11）
    with tracer.node("query_rewriter") as ctx:
        rewrite_result = rewrite_query(state)
        state_updates.update(rewrite_result)
        ctx.add("rewritten_query", rewrite_result.get("rewritten_query", "")[:100])

    merged_state = {**state, **state_updates}

    # Step 1: 意图分类
    with tracer.node("intent_classifier") as ctx:
        intent_result = classify_intent(merged_state)
        state_updates.update(intent_result)
        ctx.add("intent", intent_result.get("intent"))

    merged_state = {**state, **state_updates}

    # Step 2: BM25 检索
    with tracer.node("bm25_retriever") as ctx:
        retrieve_result = retrieve_knowit(merged_state)
        state_updates.update(retrieve_result)
        ctx.add("retrieved_count", len(retrieve_result.get("retrieved_docs", [])))

    merged_state = {**merged_state, **state_updates}

    # Step 3: LLM 生成
    with tracer.node("llm_generator") as ctx:
        generate_result = generate_knowit(merged_state)
        state_updates.update(generate_result)
        ans = (generate_result.get("qa_result", {}) or {}).get("answer", "")
        ctx.add("answer_length", len(ans))

    total_latency = int((time.time() - start) * 1000)
    tracer.info("knowit completed", node="knowit_agent", latency_ms=total_latency)

    return state_updates


def node_buddy(state: AgentState, config: Optional[RunnableConfig] = None) -> Dict[str, Any]:
    """学伴包装节点（异常隔离：失败返回降级结果）"""
    tracer = _ensure_tracer(state, "buddy_agent")
    start = time.time()

    try:
        result = run_buddy_node(state)
    except Exception as e:  # noqa: BLE001 子图故障不冒泡
        tracer.error(f"buddy failed: {e}", node="buddy_agent")
        return {
            "buddy_result": {
                "trace_id": state.get("trace_id", "unknown"),
                "courses_available": [],
                "summary": "课程资料服务暂时不可用，请稍后重试。",
                "status": "error",
                "error": str(e)[:200],
            }
        }

    latency_ms = int((time.time() - start) * 1000)
    tracer.info("buddy completed", node="buddy_agent", latency_ms=latency_ms)

    return result


def node_aggregator(state: AgentState, config: Optional[RunnableConfig] = None) -> Dict[str, Any]:
    """聚合节点：合并三个子图的输出"""
    tracer = _ensure_tracer(state, "aggregator")

    intel = state.get("intel_result") or {}
    knowit = state.get("qa_result") or {}
    buddy = state.get("buddy_result") or {}

    aggregated = {
        "intel": intel,
        "knowit": knowit,
        "buddy": buddy,
    }

    # intent 字段被两个命名空间共用：父图功能路由（activity_push/
    # campus_qa/course_summary/all）与百事通 QA 分类（policy/life/
    # course/general）。展示时非功能路由一律按 "all" 处理。
    intent = state.get("intent", "all")
    display_intent = intent if intent in ("activity_push", "campus_qa", "course_summary") else "all"

    # 构造最终回复文本
    final_response = _build_final_response(aggregated, display_intent)

    tracer.info(
        "aggregated results",
        node="aggregator",
        detail={
            "intent": intent,
            "intel_recs": len(intel.get("recommendations", [])),
            "knowit_answer_len": len(knowit.get("answer", "") or ""),
            "buddy_status": buddy.get("status"),
        },
    )

    return {
        "aggregated_result": aggregated,
        "final_response": final_response,
    }


def _build_final_response(aggregated: dict, intent: str) -> str:
    """将聚合结果转换为用户可读文本"""
    parts = []

    if intent in ("activity_push", "all"):
        intel_data = aggregated.get("intel", {})
        recs = intel_data.get("recommendations", [])
        if recs:
            lines = ["**📡 情报官 · 活动推荐**"]
            for i, r in enumerate(recs[:3]):
                chain = " → ".join(r.get("reasoning_chain", []))
                lines.append(f"{i + 1}. [{r['event_type']}] {r['event_title']}（推荐分 {r['score']:.4f}）")
                if chain:
                    lines.append(f"   > 推理链: {chain}")
            lines.append("")
            parts.append("\n".join(lines))

    if intent in ("campus_qa", "all"):
        knowit_data = aggregated.get("knowit", {})
        answer = knowit_data.get("answer")
        if answer:
            lines = ["**❓ 百事通 · 知识问答**"]
            lines.append(answer)
            sources = knowit_data.get("sources", [])
            if sources:
                lines.append("")
                lines.append("📎 参考来源：")
                for src in sources:
                    lines.append(f"  · {src.get('title', '')} ({src.get('category', '')})")
            lines.append("")
            parts.append("\n".join(lines))

    if intent in ("course_summary", "all"):
        buddy_data = aggregated.get("buddy", {})
        status = buddy_data.get("status", "")
        summary = buddy_data.get("summary", "")
        if status == "placeholder":
            courses = buddy_data.get("courses_available", [])
            if courses:
                parts.append(
                    "**📚 学伴 · 课程资料**\n"
                    + f"正在开发中，已收录 {len(courses)} 门课程。"
                )
            elif summary:
                parts.append(f"**📚 学伴 · 课程资料**\n{summary}")
        elif summary:
            lines = ["**📚 学伴 · 课程总结**", summary]
            parts.append("\n".join(lines))

    if not parts:
        return "暂无可用信息，请明确您的需求：活动推荐 / 政策问答 / 课程资料。"

    return "\n\n---\n\n".join(parts)


def _ensure_tracer(state: AgentState, fallback_node: str):
    """确保 state 中有 tracer，没有则创建临时 tracer"""
    trace_id = state.get("trace_id", "")
    if trace_id:
        return get_tracer(trace_id=trace_id, user_id=state.get("user_id", "default"))
    t = get_tracer(user_id=state.get("user_id", "default"))
    return t


# ── 图编译 ─────────────────────────────────────────────────


def compile_parent_graph() -> StateGraph:
    """编译 LangGraph 父图

    图结构:
        router
         ├── intel_agent
         ├── knowit_agent
         └── buddy_agent
               ↓
          aggregator → END
    """
    builder = StateGraph(AgentState)

    builder.add_node("router", node_router)
    builder.add_node("intel_agent", node_intel)
    builder.add_node("knowit_agent", node_knowit)
    builder.add_node("buddy_agent", node_buddy)
    builder.add_node("aggregator", node_aggregator)

    builder.set_entry_point("router")

    # router → 三子图并行 Fan-out (via Send)
    builder.add_conditional_edges("router", route_fan_agents, ["intel_agent", "knowit_agent", "buddy_agent"])

    # 三子图 → 聚合
    builder.add_edge("intel_agent", "aggregator")
    builder.add_edge("knowit_agent", "aggregator")
    builder.add_edge("buddy_agent", "aggregator")

    builder.add_edge("aggregator", END)

    return builder.compile()


class ParentGraph:
    """父图封装，统一调用接口"""

    def __init__(self):
        self._graph = compile_parent_graph()

    @property
    def graph(self):
        return self._graph

    def run(
        self,
        user_query: str,
        user_id: str = "default",
        courses: Optional[dict] = None,
        user_progress: Optional[dict] = None,
    ) -> Dict[str, Any]:
        """同步运行父图

        Args:
            user_query: 用户输入文本
            user_id: 用户标识
            courses: 用户已选课程 {code: Course}
            user_progress: 用户进度 {interests: [...]}

        Returns:
            dict: 包含 final_response / intel_result / qa_result / buddy_result
        """
        from langchain_core.messages import HumanMessage

        tracer = get_tracer(user_id=user_id)
        trace_id = tracer.trace_id

        initial_state: AgentState = {
            "user_id": user_id,
            "messages": [HumanMessage(content=user_query)],
            "courses": courses or {},
            "user_progress": user_progress or {},
            "trace_id": trace_id,
            "privacy_mode": False,
            "interrupt_flag": False,
        }

        result = self._graph.invoke(initial_state)

        tracer.end_trace()

        return {
            "trace_id": trace_id,
            "intent": result.get("intent", "all"),
            "final_response": result.get("final_response", ""),
            "intel_result": result.get("intel_result"),
            "qa_result": result.get("qa_result"),
            "buddy_result": result.get("buddy_result"),
            "aggregated_result": result.get("aggregated_result"),
        }

    def stream(
        self,
        user_query: str,
        user_id: str = "default",
        courses: Optional[dict] = None,
        user_progress: Optional[dict] = None,
    ):
        """流式运行父图，yield 每个节点的输出"""
        from langchain_core.messages import HumanMessage

        tracer = get_tracer(user_id=user_id)
        trace_id = tracer.trace_id

        initial_state: AgentState = {
            "user_id": user_id,
            "messages": [HumanMessage(content=user_query)],
            "courses": courses or {},
            "user_progress": user_progress or {},
            "trace_id": trace_id,
            "privacy_mode": False,
            "interrupt_flag": False,
        }

        for step in self._graph.stream(initial_state):
            yield step

        tracer.end_trace()


_global_graph: Optional[ParentGraph] = None


def get_parent_graph() -> ParentGraph:
    """获取全局 ParentGraph 实例"""
    global _global_graph
    if _global_graph is None:
        _global_graph = ParentGraph()
    return _global_graph
