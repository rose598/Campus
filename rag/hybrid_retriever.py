from typing import List, Optional, Dict, Any

from utils.config_loader import get


def rrf_merge(
    bm25_results: List[Dict[str, Any]],
    dense_results: List[Dict[str, Any]],
    k: Optional[int] = None,
    final_top_k: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """RRF (Reciprocal Rank Fusion) —— 融合 BM25 和 Dense 检索结果

    Args:
        bm25_results: BM25 检索结果列表，每项含 chunk_id/score/content 等
        dense_results: Dense 检索结果列表，格式同上
        k: RRF 平滑参数（默认从 config.yaml 的 rag.rrf_k 读取）
        final_top_k: 最终返回条数（默认从 config.yaml 的 rag.final_top_k 读取）

    Returns:
        融合后按 RRF 分数降序排列的结果列表
    """
    rrf_k = k or int(get("rag.rrf_k", 60))
    top_k = final_top_k or int(get("rag.final_top_k", 3))

    scores: Dict[str, float] = {}
    result_map: Dict[str, Dict[str, Any]] = {}

    for rank, item in enumerate(bm25_results):
        cid = item.get("chunk_id", "")
        scores[cid] = scores.get(cid, 0.0) + 1.0 / (rrf_k + rank + 1)
        result_map[cid] = item

    for rank, item in enumerate(dense_results):
        cid = item.get("chunk_id", "")
        scores[cid] = scores.get(cid, 0.0) + 1.0 / (rrf_k + rank + 1)
        if cid not in result_map:
            result_map[cid] = item

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    top = ranked[:top_k]

    results = []
    for cid, rrf_score in top:
        item = dict(result_map.get(cid, {}))
        item["rrf_score"] = round(rrf_score, 6)
        results.append(item)

    return results


def hybrid_search(
    query: str,
    top_k: Optional[int] = None,
    category: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """混合检索：BM25 + Dense → RRF 融合

    自动从数据库加载数据构建索引执行检索。

    Args:
        query: 用户查询文本
        top_k: 最终返回条数（默认从 config.yaml 的 rag.final_top_k 读取）
        category: 文档分类过滤（academic/life/course），None 表示全量检索

    Returns:
        融合后的 Top-K 结果列表
    """
    from rag.bm25_index import BM25Index
    from rag.dense_index import DenseIndex

    k = top_k or int(get("rag.final_top_k", 3))

    try:
        bm25 = BM25Index.from_database(category=category)
        bm25_results = bm25.search_with_meta(query, top_k=None)
    except Exception:
        bm25_results = []

    try:
        dense = DenseIndex.from_database(category=category)
        dense_results = dense.search(query, top_k=None)
    except Exception:
        dense_results = []

    if not bm25_results and not dense_results:
        return []

    bm25_top_k = int(get("rag.bm25_top_k", 5))
    dense_top_k = int(get("rag.dense_top_k", 5))

    return rrf_merge(
        bm25_results[:bm25_top_k],
        dense_results[:dense_top_k],
        final_top_k=k,
    )


GENERATION_PROMPT = """你是校园助手"百事通"。基于以下参考资料回答问题。

要求：
1. 答案须基于参考资料，不可编造
2. 如参考资料不包含答案，请诚实告知
3. 标注来源文档名称
4. 回答简洁专业"""


def generate_answer(
    query: str,
    retrieved_docs: List[Dict[str, Any]],
    system_prompt: Optional[str] = None,
    user_id: str = "default",
) -> Dict[str, Any]:
    """基于检索结果生成 LLM 回答

    Args:
        query: 用户原始问题
        retrieved_docs: 检索结果列表
        system_prompt: 可选的系统提示词
        user_id: 用户 ID（用于限速）

    Returns:
        {
            "answer": str,
            "sources": [{"title": str, "category": str, "chunk_id": str}]
        }
    """
    if not retrieved_docs:
        return {
            "answer": "暂未收录该问题的相关信息，请换个问法试试。",
            "sources": [],
        }

    context_parts = []
    for i, doc in enumerate(retrieved_docs):
        title = doc.get("title", "未知文档")
        category = doc.get("category", "")
        content = (doc.get("content", "") or "")[:800]
        context_parts.append(f"[{i + 1}] 来源: {title}（{category}）\n{content}")

    context_text = "\n\n".join(context_parts)
    user_message = f"参考资料：\n{context_text}\n\n用户问题：{query}"

    try:
        from utils import get_llm_client

        llm = get_llm_client()
        answer = llm.call(
            system_prompt=system_prompt or GENERATION_PROMPT,
            user_message=user_message,
            user_id=user_id,
        )
    except Exception:
        answer = "AI 服务暂时不可用，请稍后再试。"

    sources = []
    for doc in retrieved_docs[:3]:
        sources.append({
            "title": doc.get("title", ""),
            "category": doc.get("category", ""),
            "chunk_id": doc.get("chunk_id", ""),
        })

    return {"answer": answer, "sources": sources}


def hybrid_qa(
    query: str,
    user_id: str = "default",
    top_k: Optional[int] = None,
    category: Optional[str] = None,
) -> Dict[str, Any]:
    """端到端混合检索问答：Hybrid RAG → LLM 生成

    Args:
        query: 用户问题
        user_id: 用户标识
        top_k: 最终返回条数
        category: 文档分类过滤（academic/life/course），None 表示全量

    Returns:
        {
            "answer": str,
            "sources": [...],
            "retrieved_docs": [...],
        }
    """
    docs = hybrid_search(query, top_k=top_k, category=category)
    result = generate_answer(query, docs, user_id=user_id)
    result["retrieved_docs"] = docs
    return result
