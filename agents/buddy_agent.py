"""
学伴子图 —— 课程资料检索 + LLM 提取 + 结构化总结

流程（Day 15 检索流程设计 → Day 18 完整接入）:
    课程解析（state/用户输入 → 目标课程）
      → 课程资料检索（Hybrid RAG，category=course + 课程关键词过滤）
      → LLM 提取（知识点/重点/考核方式，Day 16）
      → 结构化总结生成（Day 17）
      → buddy_result 写回 AgentState

降级策略：任一环节失败均不阻断，返回可用程度最高的结果，
status 标识当前完成度：full / retrieved / placeholder。
"""
from typing import Dict, Any, Optional, List

from langchain_core.runnables import RunnableConfig

from models.agent_state import AgentState
from rag.hybrid_retriever import hybrid_search
from utils.config_loader import get


def _resolve_course(state: AgentState) -> Dict[str, Any]:
    """课程解析：确定用户想总结的目标课程

    优先级：
    1. state["courses"] 已选课程（单门时直接命中）
    2. state["learning_path"] 学习路径首项
    3. 用户最新输入与数据库课程名/代码模糊匹配

    Returns:
        {"course_code": str|None, "course_name": str|None,
         "matched_by": "selected"|"path"|"query"|"none"}
    """
    courses = state.get("courses", {}) or {}
    if len(courses) == 1:
        code = list(courses.keys())[0]
        return {"course_code": code, "course_name": _course_name(code), "matched_by": "selected"}

    learning_path = state.get("learning_path") or []
    if learning_path:
        code = learning_path[0]
        return {"course_code": code, "course_name": _course_name(code), "matched_by": "path"}

    # 从用户输入中匹配课程
    query = _last_user_message(state)
    if query:
        matched = _match_course_from_db(query)
        if matched:
            return {**matched, "matched_by": "query"}

    return {"course_code": None, "course_name": None, "matched_by": "none"}


def _course_name(code: str) -> str:
    """查课程名，失败返回空串"""
    try:
        from database.crud import CourseCRUD

        row = CourseCRUD.get(code)
        return (row or {}).get("name", "")
    except Exception:
        return ""


def _match_course_from_db(query: str) -> Optional[Dict[str, str]]:
    """用查询文本匹配数据库课程（代码精确 > 名称包含）"""
    try:
        from database.crud import CourseCRUD

        all_courses = CourseCRUD.get_all()
    except Exception:
        return None

    q = query.upper()
    # 代码精确/包含匹配
    for c in all_courses:
        if c["code"].upper() in q:
            return {"course_code": c["code"], "course_name": c["name"]}
    # 名称包含匹配（≥2 字才比较，避免误命中）
    for c in all_courses:
        name = c.get("name", "")
        if len(name) >= 2 and name in query:
            return {"course_code": c["code"], "course_name": name}
    return None


def _last_user_message(state: AgentState) -> str:
    messages = state.get("messages", [])
    for msg in reversed(messages):
        if getattr(msg, "type", "") == "human":
            return getattr(msg, "content", "") or ""
    return ""


def retrieve_course_materials(
    state: AgentState, config: Optional[RunnableConfig] = None
) -> Dict[str, Any]:
    """课程资料检索节点：对 category=course 的文档做 Hybrid RAG 检索

    检索词 = 课程名 + 课程代码 + 用户原始问题，提升召回。
    """
    resolved = state.get("_resolved_course") or _resolve_course(state)
    course_name = resolved.get("course_name") or ""
    course_code = resolved.get("course_code") or ""
    user_query = _last_user_message(state)

    # 组合检索词：课程上下文优先
    parts = [p for p in (course_name, course_code, user_query) if p]
    search_query = " ".join(parts) if parts else user_query

    top_k = int(get("rag.final_top_k", 3))
    try:
        docs = hybrid_search(search_query, top_k=max(top_k, 5), category="course")
    except Exception:
        docs = []

    # 命中课程名/代码的文档排前（简单重排）
    if course_name or course_code:
        def _relevance(d: Dict[str, Any]) -> int:
            text = f"{d.get('title', '')} {d.get('content', '')}"
            score = 0
            if course_name and course_name in text:
                score += 2
            if course_code and course_code in text:
                score += 2
            return score

        docs = sorted(docs, key=_relevance, reverse=True)

    return {"_resolved_course": resolved, "course_docs": docs[:top_k]}


def run_buddy_node(state: AgentState, config: Optional[RunnableConfig] = None) -> Dict[str, Any]:
    """学伴节点入口：课程解析 → 资料检索 → 提取 → 总结

    Day 15 版本实现解析 + 检索；提取/总结在 Day 16/17 模块就绪后接入，
    缺失时优雅降级为 placeholder。
    """
    trace_id = state.get("trace_id", "unknown")

    courses = state.get("courses", {}) or {}
    learning_path = state.get("learning_path") or []
    course_list = list(courses.keys()) if courses else learning_path

    # Step 1: 课程解析 + 资料检索
    retrieve_updates = retrieve_course_materials(state)
    resolved = retrieve_updates["_resolved_course"]
    docs = retrieve_updates["course_docs"]

    if not docs:
        # 无可检索资料 → 保持骨架行为
        return {
            "buddy_result": {
                "trace_id": trace_id,
                "courses_available": course_list[:10],
                "course_code": resolved.get("course_code"),
                "course_name": resolved.get("course_name"),
                "summary": "暂未收录该课程的资料，请先上传课程大纲或课件。",
                "status": "placeholder",
                "sources": [],
            }
        }

    # Step 2/3: 提取 + 总结（Day 16/17 模块，缺失时降级）
    # 课程名未解析到时，用 Top1 文档标题兜底，避免展示"未知课程"
    display_name = (
        resolved.get("course_name")
        or resolved.get("course_code")
        or (docs[0].get("title", "") if docs else "")
        or "未知课程"
    )
    try:
        from rag.course_extractor import CourseExtractor
        from rag.summary_generator import SummaryGenerator

        material_text = "\n\n".join(
            (d.get("content", "") or "")[:1500] for d in docs
        )
        extracted = CourseExtractor().extract(
            course_name=display_name,
            material_text=material_text,
            user_id=state.get("user_id", "default"),
        )
        summary = SummaryGenerator().generate(
            course_name=display_name,
            course_code=resolved.get("course_code") or "",
            extracted=extracted,
            sources=[d.get("title", "") for d in docs],
        )
        status = "full" if extracted.get("source") == "llm" else "retrieved"
    except Exception:
        extracted = {}
        summary = _fallback_summary(docs)
        status = "retrieved"

    return {
        "buddy_result": {
            "trace_id": trace_id,
            "courses_available": course_list[:10],
            "course_code": resolved.get("course_code"),
            "course_name": resolved.get("course_name"),
            "summary": summary,
            "extracted": extracted,
            "status": status,
            "sources": [
                {"title": d.get("title", ""), "chunk_id": d.get("chunk_id", "")}
                for d in docs
            ],
        }
    }


def _fallback_summary(docs: List[Dict[str, Any]]) -> str:
    """无 LLM/提取模块时的降级总结：拼接资料要点"""
    lines = ["已检索到以下课程资料："]
    for i, d in enumerate(docs[:3]):
        title = d.get("title", "未知文档")
        snippet = (d.get("content", "") or "").replace("\n", " ")[:120]
        lines.append(f"{i + 1}. 《{title}》：{snippet}…")
    return "\n".join(lines)
