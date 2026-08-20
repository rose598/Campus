"""
百事通子图 —— 学校知识问答（查询改写 + 意图分类 + 分类路由 + Hybrid RAG 检索 + LLM 生成）
"""
from typing import Dict, Any, Optional

from langchain_core.runnables import RunnableConfig

from models.agent_state import AgentState

from rag.hybrid_retriever import hybrid_search
from rag.query_rewriter import QueryRewriter, history_from_messages
from utils.config_loader import get
from utils import get_llm_client


INTENT_PROMPT = """你是一个校园问答意图分类器。根据用户问题，判断意图类型。

意图类型：
- policy: 政策通知类（保研、转专业、选课、补考、毕业要求等）
- life: 校园生活类（食堂、住宿、图书馆、体育馆、后勤等）
- course: 课程信息类（课程大纲、考核方式、先修课、学分等）
- general: 其他通用问题

输出格式：只输出意图类型，不要其他内容。"""

QA_SYSTEM_PROMPT = """你是校园助手"百事通"。基于提供的参考资料回答用户问题。

要求：
1. 答案须基于参考资料，不可编造
2. 如果参考资料不包含答案，诚实告知"暂未收录该问题"
3. 回答简洁，标注来源文档和发布日期"""


# 意图 → 数据库分类映射
INTENT_TO_CATEGORY = {
    "policy": "academic",
    "life": "life",
    "course": "course",
    "general": None,
}


def rewrite_query(state: AgentState, config: Optional[RunnableConfig] = None) -> Dict[str, Any]:
    """查询改写节点：结合对话历史将最新问题改写为自包含的独立查询

    LLM 不可用或无历史时透传原始查询，不阻断主流程。
    """
    messages = state.get("messages", [])
    query = ""
    for msg in reversed(messages):
        if getattr(msg, "type", "") == "human":
            query = getattr(msg, "content", "") or ""
            break

    if not query.strip():
        return {"rewritten_query": query}

    history = history_from_messages(messages)
    rewriter = QueryRewriter()
    result = rewriter.rewrite(
        query,
        chat_history=history,
        user_id=state.get("user_id", "default"),
    )

    return {"rewritten_query": result["rewritten"]}


def classify_intent(state: AgentState, config: Optional[RunnableConfig] = None) -> Dict[str, Any]:
    """意图分类节点：对用户最新问题做 QA 细分类（policy/life/course/general）

    注意：父图 router 产出的是功能路由（activity_push/campus_qa/
    course_summary/all），与本节点的 QA 分类是两个命名空间。
    仅当 router 未给出有效功能路由（"all" 或空）时才调用 LLM 精分类，
    避免覆盖父图路由结果导致聚合器降级。
    分类基于改写后的查询（如有），提升多轮场景下的准确率。
    """
    router_intent = state.get("intent", "all")

    if router_intent and router_intent != "all":
        # 父图路由已确定功能方向，保留不覆盖
        return {}

    messages = state.get("messages", [])
    if not messages:
        return {"intent": "general"}

    last_user_msg = ""
    for msg in reversed(messages):
        role = getattr(msg, "type", "")
        if role == "human":
            last_user_msg = getattr(msg, "content", "") or ""
            break

    # 意图分类优先使用改写后的查询（自包含，分类更准）
    last_user_msg = state.get("rewritten_query") or last_user_msg

    if not last_user_msg.strip():
        return {"intent": "general"}

    try:
        llm = get_llm_client()
        result = llm.call(
            system_prompt=INTENT_PROMPT,
            user_message=last_user_msg,
            user_id=state.get("user_id", "default"),
        )
        intent = result.strip().lower()
        if intent not in ("policy", "life", "course", "general"):
            intent = "general"
    except Exception:
        intent = "general"

    return {"intent": intent}


def retrieve_knowit(state: AgentState, config: Optional[RunnableConfig] = None) -> Dict[str, Any]:
    """检索节点：Hybrid RAG 检索（BM25 + Dense + RRF 融合，支持按类别过滤）

    优先使用改写后的查询检索，提升多轮对话召回率。
    """
    intent = state.get("intent", "general")

    messages = state.get("messages", [])
    query = ""
    for msg in reversed(messages):
        if getattr(msg, "type", "") == "human":
            query = getattr(msg, "content", "") or ""
            break

    # 优先使用改写后的自包含查询
    query = state.get("rewritten_query") or query

    if not query:
        return {"retrieved_docs": []}

    db_category = INTENT_TO_CATEGORY.get(intent, None)
    top_k = int(get("rag.final_top_k", 3))

    try:
        results = hybrid_search(query, top_k=top_k, category=db_category)
    except Exception:
        results = []

    return {"retrieved_docs": results}


def generate_knowit(state: AgentState, config: Optional[RunnableConfig] = None) -> Dict[str, Any]:
    """生成节点：LLM 基于检索结果生成带引用的回答"""
    messages = state.get("messages", [])
    query = ""
    for msg in reversed(messages):
        if getattr(msg, "type", "") == "human":
            query = getattr(msg, "content", "") or ""
            break

    # 生成时使用改写后的查询（检索与生成的语义对齐）
    query = state.get("rewritten_query") or query

    retrieved = state.get("retrieved_docs", []) or []
    if not retrieved:
        fallback = "暂未收录该问题的相关信息，请换个问法试试。"
        return {"qa_result": {"answer": fallback, "sources": []}}

    context_parts = []
    for i, doc in enumerate(retrieved):
        title = doc.get("title", "未知文档")
        category = doc.get("category", "")
        content = (doc.get("content", "") or "")[:800]
        context_parts.append(f"[{i + 1}] 来源: {title}（{category}）\n{content}")

    context_text = "\n\n".join(context_parts)

    user_message = f"参考资料：\n{context_text}\n\n用户问题：{query}"

    try:
        llm = get_llm_client()
        answer = llm.call(
            system_prompt=QA_SYSTEM_PROMPT,
            user_message=user_message,
            user_id=state.get("user_id", "default"),
        )
    except Exception:
        answer = "AI 服务暂时不可用，请稍后再试。"

    sources = []
    for doc in retrieved[:3]:
        sources.append({
            "title": doc.get("title", ""),
            "category": doc.get("category", ""),
            "chunk_id": doc.get("chunk_id", ""),
        })

    return {"qa_result": {"answer": answer, "sources": sources, "intent": state.get("intent", "general")}}
