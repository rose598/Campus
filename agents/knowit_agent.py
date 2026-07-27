"""
百事通子图 —— 学校知识问答（意图分类 + 分类路由 + Hybrid RAG 检索 + LLM 生成）
"""
from typing import Dict, Any, Optional

from langchain_core.runnables import RunnableConfig

from models.agent_state import AgentState

from rag.hybrid_retriever import hybrid_search
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


def classify_intent(state: AgentState, config: Optional[RunnableConfig] = None) -> Dict[str, Any]:
    """意图分类节点：对用户最新问题分类

    优先使用 router 已设定的 intent（规则路由），
    仅当 intent 为 "all" 或未设置时才调用 LLM 精分类。
    """
    router_intent = state.get("intent", "all")

    if router_intent and router_intent != "all":
        return {"intent": router_intent}

    messages = state.get("messages", [])
    if not messages:
        return {"intent": "general"}

    last_user_msg = ""
    for msg in reversed(messages):
        role = getattr(msg, "type", "")
        if role == "human":
            last_user_msg = getattr(msg, "content", "") or ""
            break

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
    """检索节点：Hybrid RAG 检索（BM25 + Dense + RRF 融合，支持按类别过滤）"""
    intent = state.get("intent", "general")

    messages = state.get("messages", [])
    query = ""
    for msg in reversed(messages):
        if getattr(msg, "type", "") == "human":
            query = getattr(msg, "content", "") or ""
            break

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
