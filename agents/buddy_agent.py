"""
学伴子图 —— 课程资料检索 + LLM 总结（骨架）
"""
from typing import Dict, Any, Optional

from langchain_core.runnables import RunnableConfig

from models.agent_state import AgentState


def run_buddy_node(state: AgentState, config: Optional[RunnableConfig] = None) -> Dict[str, Any]:
    """学伴节点：课程资料检索 + 结构化总结生成

    当前为 Day 7 骨架版本，完整实现见 Week 3。
    """
    courses = state.get("courses", {}) or {}
    learning_path = state.get("learning_path") or []

    course_list = list(courses.keys()) if courses else learning_path

    return {
        "buddy_result": {
            "trace_id": state.get("trace_id", "unknown"),
            "courses_available": course_list[:10],
            "summary": "课程资料收集与总结功能正在开发中（Week 3）",
            "status": "placeholder",
        },
    }
