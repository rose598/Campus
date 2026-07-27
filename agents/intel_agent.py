"""
情报官子图 —— PPR 活动智能推送 + 推理链溯源
"""
from typing import Dict, Any, Optional, List

from langchain_core.runnables import RunnableConfig

from models.agent_state import AgentState
from knowledge_graph.graph_builder import build_heterogeneous_graph
from knowledge_graph.ppr_recommender import PprRecommender, Recommendation

from utils.config_loader import get


def run_intel_node(state: AgentState, config: Optional[RunnableConfig] = None) -> Dict[str, Any]:
    """情报官节点：运行 PPR 推荐，返回活动推荐列表

    Args:
        state: 全局 AgentState
        config: LangGraph 运行时配置（含 tracer 等）

    Returns:
        dict: 映射到 AgentState 键的更新值
    """
    trace_id = state.get("trace_id", "unknown")

    graph = build_heterogeneous_graph()
    recommender = PprRecommender(graph)

    user_interests = _extract_user_interests(state)
    user_courses = _extract_user_courses(state)

    try:
        results: List[Recommendation] = recommender.recommend(
            user_interests=user_interests,
            user_courses=user_courses,
        )
    except Exception:
        results = recommender._fallback_recommend(
            int(get("ppr.fallback_count", 3))
        )

    return {
        "ppr_scores": {r.event_id: r.score for r in results},
        "intel_result": {
            "trace_id": trace_id,
            "recommendations": [r.model_dump() for r in results],
            "source": "ppr_with_fallback",
        },
    }


def _extract_user_interests(state: AgentState) -> List[str]:
    """从对话历史或用户进度中提取兴趣标签"""
    progress = state.get("user_progress", {}) or {}
    interests = progress.get("interests", [])
    if interests:
        return interests

    messages = state.get("messages", [])
    keywords = []
    interest_set = {"人工智能", "算法", "机器学习", "深度学习", "大数据",
                     "数据挖掘", "编程", "计算机视觉", "自然语言处理",
                     "网络安全", "软件工程", "数据库", "操作系统",
                     "计算机网络", "数学建模"}
    for msg in messages:
        content = getattr(msg, "content", "") or ""
        for kw in interest_set:
            if kw in content and kw not in keywords:
                keywords.append(kw)
    return keywords if keywords else ["人工智能", "算法"]


def _extract_user_courses(state: AgentState) -> List[str]:
    """从 state 中提取用户已选课程代码"""
    courses = state.get("courses", {}) or {}
    if courses:
        return list(courses.keys())

    learning_path = state.get("learning_path") or []
    if learning_path:
        return learning_path

    return []
