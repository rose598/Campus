"""
百事通子图 —— 学校知识问答（查询改写 + 意图分类 + 分类路由 + 时间排序 + 多源融合 + 引用格式化）

生产链路接入 campus_qa 五模块管道:
  IntentClassifier → CategoryRouter → TimeRanker → MultiSourceFuser → CitationFormatter
  文件索引不可用时兜底走 rag.hybrid_retriever（数据库索引）。
"""
import logging
import re
from typing import Dict, Any, List, Optional

from langchain_core.runnables import RunnableConfig

from models.agent_state import AgentState

from campus_qa.intent_classifier import IntentClassifier
from campus_qa.category_router import CategoryRouter
from campus_qa.time_ranker import TimeRanker
from campus_qa.multi_source_fuser import MultiSourceFuser
from campus_qa.citation_formatter import CitationFormatter
from campus_qa.event_retriever import EventRetriever

from rag.hybrid_retriever import hybrid_search
from rag.query_rewriter import QueryRewriter, history_from_messages
from utils.config_loader import get
from utils import get_llm_client

logger = logging.getLogger(__name__)


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


# 意图 → 数据库分类映射（hybrid_search 兜底检索用）
INTENT_TO_CATEGORY = {
    "policy": "academic",
    "life": "life",
    "course": "course",
    "activity": None,
    "general": None,
}


def _llm_available() -> bool:
    """调用方自检：是否配置了真实 LLM API Key。

    未配置时直接跳过 LLM 调用，避免占位 key 发起真实网络请求（超时+重试）
    导致链路长时间挂起；降级逻辑走各节点自身的离线兜底分支。
    """
    api_key = get("llm.api_key")
    return bool(api_key) and api_key != "sk-placeholder"


# ─────────────────────────────────────────────
#  campus_qa 五模块管道（懒加载单例）
# ─────────────────────────────────────────────

class _KnowitPipeline:
    """封装 campus_qa 五模块，供子图节点复用。"""

    def __init__(self):
        self.ready = False
        # 无 API Key 时使用纯规则分类；配置 campus_qa.classifier_use_llm 可开启 LLM 增强
        use_llm = bool(get("campus_qa.classifier_use_llm", False))
        self.classifier = IntentClassifier(use_llm=use_llm)
        self.router = CategoryRouter(expand_query=True, expand_routes=True)
        self.ranker = TimeRanker.from_config()
        self.fuser = MultiSourceFuser.from_config()
        self.formatter = CitationFormatter()
        self.event_retriever = EventRetriever()

        try:
            from data_pipeline.index_builder import IndexBuilder
            builder = IndexBuilder.load("data/processed/indexes")
            self.router.set_index_builder(builder)
            self.ready = True
            logger.info("[KnowitPipeline] campus_qa 管道就绪")
        except Exception as e:  # noqa: BLE001
            logger.warning("[KnowitPipeline] 文件索引加载失败，将降级为数据库检索: %s", e)

    def classify(self, query: str) -> str:
        """规则优先的意图分类。"""
        try:
            return self.classifier.classify(query).intent
        except Exception:  # noqa: BLE001
            return "general"

    @staticmethod
    def _extract_query_keywords(query: str) -> List[str]:
        """提取查询关键词：英文词原样保留；中文段按 2-gram 滑窗切分后过滤停用词。
        用于分块级重排序（BM25 单字分词对长问句区分度不足）。
        注：正则 [\\u4e00-\\u9fff]{2,} 会贪婪匹配整个中文问句，
        因此改用滑窗分词，确保“保研需要什么条件”能拆出“保研/条件”。
        """
        stop_words = {
            "什么", "哪些", "怎么", "如何", "多少", "哪里", "哪个", "为什么",
            "请问", "需要", "可以", "进行", "使用", "关于", "应该", "时候",
            "一下", "告诉", "知道", "帮我", "有没有", "有没有", "哪些是",
            "the", "what", "how", "where", "when",
        }
        keywords: List[str] = []
        for seg in re.findall(r"[A-Za-z]{2,}|[\u4e00-\u9fff]+", query):
            if seg.isascii():
                if seg.lower() not in stop_words:
                    keywords.append(seg)
            else:
                # 2-gram 滑窗：保研需要什么条件 → 保研/研需/需要/要什/什么/么条/条件 → 过滤停用词
                grams = [seg[i:i + 2] for i in range(len(seg) - 1)]
                keywords.extend(g for g in grams if g not in stop_words)
        # 去重保序
        return list(dict.fromkeys(keywords))

    @staticmethod
    def _chunk_field(item: Any, name: str, default: Any = "") -> Any:
        """兼容 dict 与 Pydantic 对象（RankedResult）的字段读取。"""
        if isinstance(item, dict):
            return item.get(name, default)
        return getattr(item, name, default)

    @classmethod
    def _chunk_relevance(cls, chunk: Any, keywords: List[str]) -> float:
        """分块与查询关键词的命中得分：文档标题命中权重高于正文。"""
        if not keywords:
            return 0.0
        title = str(cls._chunk_field(chunk, "doc_title", "") or "")
        content = str(cls._chunk_field(chunk, "content", "") or "")
        headings = cls._chunk_field(chunk, "parent_headings", None)
        if headings:
            title += " " + " ".join(str(h) for h in headings)
        score = 0.0
        for kw in keywords:
            if kw in title:
                score += 3.0
            if kw in content:
                score += 1.0
        return score

    def retrieve(self, query: str, intent: str, top_k: int = 5) -> list:
        """路由检索 → 时间排序 → 融合，返回统一格式的文档 dict 列表。"""
        if not self.ready:
            return []
        try:
            route_result = self.router.route_with_fallback(
                query, intent=intent, use_dense=False
            )
            if not route_result.candidates:
                return []
            ranked = self.ranker.rank(route_result.candidates, top_k=top_k * 2)
            # 分块级重排序：关键词命中（标题/标题层级 > 正文）叠加原融合分，
            # 修正 BM25 单字分词对长问句的排序偏差（如“教材”问句被试卷分块抢占）。
            # 注：融合器会按 final_score 重排，因此将 kw 得分直接注入 final_score
            #（归一化后叠加，保留原分区分度）。
            keywords = self._extract_query_keywords(query)
            if keywords:
                max_final = max(
                    (float(self._chunk_field(d, "final_score", 0.0) or 0) for d in ranked),
                    default=1.0,
                ) or 1.0
                for doc in ranked:
                    kw = self._chunk_relevance(doc, keywords)
                    final = float(self._chunk_field(doc, "final_score", 0.0) or 0)
                    new_score = final + kw * max_final * 0.5
                    if isinstance(doc, dict):
                        doc["final_score"] = new_score
                    else:
                        try:
                            doc.final_score = new_score
                        except Exception:  # noqa: BLE001  Pydantic 冻结时跳过
                            pass
            fused = self.fuser.fuse_ranked_results(ranked, top_k=top_k)
            # 内容级去重：相同内容的分块只保留一条，避免前端展示重复引用
            seen, docs = set(), []
            for f in fused:
                key = (f.content or "").strip()
                if not key or key in seen:
                    continue
                seen.add(key)
                docs.append(
                    {
                        "chunk_id": f.chunk_id,
                        "doc_id": f.doc_id,
                        "title": f.doc_title,
                        "doc_title": f.doc_title,
                        "category": f.category,
                        "content": f.content,
                        "publish_date": f.publish_date,
                        "score": f.score,
                    }
                )
            return docs
        except Exception as e:  # noqa: BLE001
            logger.warning("[KnowitPipeline] 管道检索异常: %s", e)
            return []


_PIPELINE: Optional[_KnowitPipeline] = None


def _get_pipeline() -> _KnowitPipeline:
    """懒加载管道单例。"""
    global _PIPELINE
    if _PIPELINE is None:
        _PIPELINE = _KnowitPipeline()
    return _PIPELINE


def _extract_last_user_query(state: AgentState) -> str:
    """从 state 中提取用户最新问题。"""
    for msg in reversed(state.get("messages", []) or []):
        if getattr(msg, "type", "") == "human":
            return getattr(msg, "content", "") or ""
    return ""


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

    # LLM 离线时跳过改写（改写依赖 LLM），直接透传原始查询，不阻断主流程
    if not _llm_available():
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
    """意图分类节点：使用 campus_qa.IntentClassifier 对最新问题做 QA 细分类
    （policy/life/course/general，规则优先，可配置 LLM 增强）

    注意：父图 router 产出的是功能路由（activity_push/campus_qa/
    course_summary/all），与本节点的 QA 分类是两个命名空间。
    仅当 router 未给出有效功能路由（"all" 或空）时才执行分类，
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

    return {"intent": _get_pipeline().classify(last_user_msg)}


def retrieve_knowit(state: AgentState, config: Optional[RunnableConfig] = None) -> Dict[str, Any]:
    """检索节点：分类路由 + 时间排序 + 多源融合（campus_qa 管道）

    主链路：CategoryRouter.route_with_fallback → TimeRanker.rank → MultiSourceFuser。
    文件索引不可用或无结果时兜底走数据库混合检索（BM25+Dense+RRF）。
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

    top_k = int(get("rag.final_top_k", 3))

    # activity 意图：走活动检索器（events 表结构化查询 + 原始数据兜底）
    if intent == "activity":
        try:
            results = _get_pipeline().event_retriever.search(query, top_k=max(top_k, 5))
        except Exception as e:  # noqa: BLE001
            logger.warning("[KnowitPipeline] 活动检索异常: %s", e)
            results = []
        if results:
            return {"retrieved_docs": results}

    # 主链路：campus_qa 管道（路由 → 时间排序 → 融合）
    results = _get_pipeline().retrieve(query, intent, top_k=max(top_k, 3))

    # 兜底：文件索引不可用或无结果时，走数据库混合检索（按类别过滤）
    if not results:
        db_category = INTENT_TO_CATEGORY.get(intent, None)
        try:
            results = hybrid_search(query, top_k=top_k, category=db_category)
        except Exception:  # noqa: BLE001
            results = []

    return {"retrieved_docs": results}


def generate_knowit(state: AgentState, config: Optional[RunnableConfig] = None) -> Dict[str, Any]:
    """生成节点：LLM 基于检索结果生成回答 + CitationFormatter 结构化引用"""
    messages = state.get("messages", [])
    query = ""
    for msg in reversed(messages):
        if getattr(msg, "type", "") == "human":
            query = getattr(msg, "content", "") or ""
            break

    # 生成时使用改写后的查询（检索与生成的语义对齐）
    query = state.get("rewritten_query") or query

    intent = state.get("intent", "general")
    retrieved = state.get("retrieved_docs", []) or []
    if not retrieved:
        fallback = "暂未收录该问题的相关信息，请换个问法试试。"
        return {"qa_result": {"answer": fallback, "sources": [], "intent": intent}}

    # activity 意图：结构化活动列表回答（离线可用，不依赖 LLM）
    is_activity_answer = intent == "activity" and all(
        d.get("category") == "activity" for d in retrieved
    )
    answer = None
    if is_activity_answer:
        answer = EventRetriever.format_answer(retrieved, query)
    else:
        context_parts = []
        for i, doc in enumerate(retrieved):
            title = doc.get("doc_title") or doc.get("title", "未知文档")
            category = doc.get("category", "")
            pub = doc.get("publish_date") or ""
            content = (doc.get("content", "") or "")[:800]
            date_part = f"，发布于 {pub}" if pub else ""
            context_parts.append(f"[{i + 1}] 来源: {title}（{category}{date_part}）\n{content}")

        context_text = "\n\n".join(context_parts)

        user_message = f"参考资料：\n{context_text}\n\n用户问题：{query}"

        try:
            if not _llm_available():
                raise RuntimeError("LLM 离线（未配置 API Key）")
            llm = get_llm_client()
            answer = llm.call(
                system_prompt=QA_SYSTEM_PROMPT,
                user_message=user_message,
                user_id=state.get("user_id", "default"),
            )
        except Exception:
            # LLM 不可用（无 API Key / 服务异常）时的离线兜底：摘录检索原文
            top = retrieved[0]
            preview = (top.get("content", "") or "")[:150]
            answer = (
                f"根据《{top.get('doc_title') or top.get('title', '相关文档')}》：\n{preview}...\n"
                f"（AI 生成服务暂不可用，以上为检索原文摘录）"
            )

    # 结构化引用（CitationFormatter）：标题/分类/日期/片段/相关度，供前端渲染引用卡片
    formatter = _get_pipeline().formatter
    citations = formatter.format_results(retrieved)
    sources = [
        {
            "index": c.index,
            "title": c.title,
            "category": c.category,
            "date": c.publish_date,
            "snippet": c.snippet,
            "relevance": c.relevance_score,
            "chunk_id": next(
                (d.get("chunk_id", "") for d in retrieved
                 if (d.get("doc_title") or d.get("title")) == c.title),
                "",
            ),
        }
        for c in citations
    ]

    return {"qa_result": {"answer": answer, "sources": sources, "intent": intent}}
