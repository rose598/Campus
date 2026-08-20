from typing import List, Tuple, Optional, Dict, Any, Union
from dataclasses import dataclass

from rank_bm25 import BM25Okapi

from utils.config_loader import get


def _tokenize(text: str) -> List[str]:
    """中文分词：优先 jieba；缺失时用正则词 + 字符二元组降级

    降级策略说明：中文无空格分隔，纯正则会把整句当单个 token
    导致 BM25 无法命中；字符二元组保证基本匹配能力（Day 24）。
    """
    try:
        import jieba

        tokens = [t for t in jieba.cut(text) if t.strip()]
        return tokens
    except ImportError:
        pass
    import re

    tokens = re.findall(r"[\u4e00-\u9fff]+|[a-zA-Z]+|\d+", text)
    # 对连续中文段补充字符二元组，提升词面重合概率
    expanded: List[str] = []
    for t in tokens:
        expanded.append(t)
        if re.match(r"^[\u4e00-\u9fff]+$", t) and len(t) >= 2:
            expanded.extend(t[i:i + 2] for i in range(len(t) - 1))
    return [t.strip() for t in expanded if t.strip()]


@dataclass
class ChunkRecord:
    chunk_id: str
    content: str
    doc_id: str = ""
    category: str = ""
    title: str = ""


class BM25Index:
    """BM25 倒排索引 —— 构建、检索、序列化"""

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        cfg_k1 = get("rag.bm25_k1", None)
        cfg_b = get("rag.bm25_b", None)
        self._k1 = float(cfg_k1) if cfg_k1 is not None else k1
        self._b = float(cfg_b) if cfg_b is not None else b
        self._index: Optional[BM25Okapi] = None
        self._chunks: List[ChunkRecord] = []
        self._tokenized: List[List[str]] = []

    @property
    def chunk_count(self) -> int:
        return len(self._chunks)

    def build(self, chunks: List[Union[dict, ChunkRecord]]) -> "BM25Index":
        if not chunks:
            return self

        self._chunks = []
        self._tokenized = []

        for c in chunks:
            if isinstance(c, ChunkRecord):
                record = c
            else:
                record = ChunkRecord(
                    chunk_id=c.get("chunk_id", ""),
                    content=c.get("content", ""),
                    doc_id=c.get("doc_id", ""),
                    category=c.get("category", ""),
                    title=c.get("title", ""),
                )
            self._chunks.append(record)
            # Day 24 调优：索引文本 = 标题 + 正文。关键词常只出现在标题
            # （如"保研"），仅索引正文会导致相关文档无法命中。
            self._tokenized.append(_tokenize(record.title + "\n" + record.content))

        if self._tokenized:
            self._index = BM25Okapi(self._tokenized, k1=self._k1, b=self._b)

        return self

    def search(
        self,
        query: str,
        top_k: Optional[int] = None,
    ) -> List[Tuple[str, float, str]]:
        if self._index is None:
            return []

        k = top_k or int(get("rag.bm25_top_k", 5))
        query_tokens = _tokenize(query)
        if not query_tokens:
            return []

        scores = self._index.get_scores(query_tokens)
        indexed = list(enumerate(scores))
        indexed.sort(key=lambda x: x[1], reverse=True)
        top = indexed[:k]

        results: List[Tuple[str, float, str]] = []
        for idx, score in top:
            # Day 24 调优：无任何词面重合的结果直接过滤。
            # 不用 score>0 判断：小语料下 IDF 可为 0（词出现在半数文档），
            # 分数为 0 不代表不相关。
            if not set(query_tokens) & set(self._tokenized[idx]):
                continue
            record = self._chunks[idx]
            results.append((record.chunk_id, float(score), record.content))

        return results

    def search_with_meta(
        self,
        query: str,
        top_k: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        if self._index is None:
            return []

        k = top_k or int(get("rag.bm25_top_k", 5))
        query_tokens = _tokenize(query)
        if not query_tokens:
            return []

        scores = self._index.get_scores(query_tokens)
        indexed = list(enumerate(scores))
        indexed.sort(key=lambda x: x[1], reverse=True)
        top = indexed[:k]

        results = []
        for idx, score in top:
            # Day 24 调优：无任何词面重合的结果直接过滤（同上，不用分数判断）
            if not set(query_tokens) & set(self._tokenized[idx]):
                continue
            record = self._chunks[idx]
            results.append({
                "chunk_id": record.chunk_id,
                "score": float(score),
                "content": record.content,
                "doc_id": record.doc_id,
                "category": record.category,
                "title": record.title,
            })
        return results

    def to_state(self) -> dict:
        return {
            "k1": self._k1,
            "b": self._b,
            "chunks": [
                {
                    "chunk_id": c.chunk_id,
                    "content": c.content,
                    "doc_id": c.doc_id,
                    "category": c.category,
                    "title": c.title,
                }
                for c in self._chunks
            ],
        }

    @classmethod
    def from_state(cls, data: dict) -> "BM25Index":
        index = cls(k1=data.get("k1", 1.5), b=data.get("b", 0.75))
        chunks = data.get("chunks", [])
        if chunks:
            index.build(chunks)
        return index

    @classmethod
    def from_database(cls, category: Optional[str] = None) -> "BM25Index":
        from database.crud import DocumentCRUD

        chunks_data: List[Dict[str, Any]] = []

        if category:
            docs = DocumentCRUD.get_by_category(category)
        else:
            docs = DocumentCRUD.get_all()

        for doc in docs:
            doc_chunks = DocumentCRUD.get_chunks(doc["doc_id"])
            for chunk in doc_chunks:
                chunks_data.append({
                    "chunk_id": chunk["chunk_id"],
                    "content": chunk["content"],
                    "doc_id": doc["doc_id"],
                    "category": doc.get("category", ""),
                    "title": doc.get("title", ""),
                })

        index = cls()
        if chunks_data:
            index.build(chunks_data)
        return index

    @classmethod
    def from_documents(cls, documents: List[Any]) -> "BM25Index":
        chunks_data: List[Dict[str, Any]] = []
        for doc in documents:
            content = getattr(doc, "content", "") or doc.get("content", "") if isinstance(doc, dict) else str(doc)
            doc_id = getattr(doc, "doc_id", "") or doc.get("doc_id", "") if isinstance(doc, dict) else ""
            category = getattr(doc, "category", "") or doc.get("category", "") if isinstance(doc, dict) else ""
            title = getattr(doc, "title", "") or doc.get("title", "") if isinstance(doc, dict) else ""
            chunks_data.append({
                "chunk_id": doc_id,
                "content": content,
                "doc_id": doc_id,
                "category": category,
                "title": title,
            })

        index = cls()
        if chunks_data:
            index.build(chunks_data)
        return index


def build_bm25_index(
    chunks: List[dict],
    k1: float = 1.5,
    b: float = 0.75,
) -> BM25Index:
    index = BM25Index(k1=k1, b=b)
    return index.build(chunks)
