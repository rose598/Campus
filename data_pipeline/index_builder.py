"""
index_builder.py — 索引构建器（BM25 + Dense Embedding）

职责:
  - 从标注后的文档（AnnotatedDocument）和分块（Chunk）构建检索索引
  - BM25 倒排索引（rank_bm25）
  - Dense Embedding 索引（sentence-transformers + numpy）
  - 分类索引构建（academic / life / course 各自独立索引）
  - 索引持久化（保存为 JSON + numpy .npy）
  - 索引加载与查询接口

使用方式:
  from data_pipeline.index_builder import IndexBuilder

  builder = IndexBuilder()
  builder.build_from_documents(annotated_docs, chunks_map)
  builder.save("data/processed/indexes/")

  # 加载已构建的索引
  builder = IndexBuilder.load("data/processed/indexes/")
  results = builder.search("保研条件", category="academic", top_k=5)
"""

from __future__ import annotations

import json
import logging
import os
import pickle
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
#  BM25 索引封装
# ─────────────────────────────────────────────

class BM25Index:
    """BM25 倒排索引封装"""

    def __init__(self):
        self._index = None  # rank_bm25.BM25Okapi 实例
        self._docs: List[Dict] = []  # [{"chunk_id": str, "doc_id": str, "content": str}, ...]
        self._tokenized: List[List[str]] = []

    @property
    def size(self) -> int:
        return len(self._docs)

    def build(self, chunks: List[Dict]) -> None:
        """
        从 chunk 列表构建 BM25 索引。

        Args:
            chunks: [{"chunk_id": str, "doc_id": str, "content": str, ...}, ...]
        """
        from rank_bm25 import BM25Okapi

        self._docs = chunks
        # 简单中文分词：按字符 + 2-gram
        self._tokenized = [self._tokenize(c["content"]) for c in chunks]

        if self._tokenized:
            self._index = BM25Okapi(self._tokenized)
        else:
            self._index = None

        logger.info("[BM25Index] 构建完成: %d 块", len(chunks))

    def search(self, query: str, top_k: int = 5) -> List[Dict]:
        """
        BM25 检索。

        Returns:
            [{"chunk_id": str, "doc_id": str, "content": str, "score": float}, ...]
        """
        if self._index is None or not self._docs:
            return []

        tokens = self._tokenize(query)
        scores = self._index.get_scores(tokens)

        # 排序取 top_k
        indexed_scores = list(enumerate(scores))
        indexed_scores.sort(key=lambda x: x[1], reverse=True)

        results = []
        for idx, score in indexed_scores[:top_k]:
            doc = dict(self._docs[idx])
            doc["score"] = float(score)
            results.append(doc)

        return results

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        """
        简易中文分词：单字符 + 2-gram。
        对于校园文档场景足够使用（BM25 对分词质量容忍度较高）。
        """
        text = text.strip().lower()
        tokens = []

        # 单字符
        for ch in text:
            if ch.isalnum() or '\u4e00' <= ch <= '\u9fff':
                tokens.append(ch)

        # 2-gram
        for i in range(len(text) - 1):
            bigram = text[i:i + 2]
            if all(c.isalnum() or '\u4e00' <= c <= '\u9fff' for c in bigram):
                tokens.append(bigram)

        # 3-gram（增强短语匹配）
        for i in range(len(text) - 2):
            trigram = text[i:i + 3]
            if all(c.isalnum() or '\u4e00' <= c <= '\u9fff' for c in trigram):
                tokens.append(trigram)

        return tokens

    def save(self, path: Path) -> None:
        """保存索引到磁盘"""
        path.mkdir(parents=True, exist_ok=True)
        with open(path / "bm25_docs.json", "w", encoding="utf-8") as f:
            json.dump(self._docs, f, ensure_ascii=False, indent=2)
        if self._index:
            with open(path / "bm25_index.pkl", "wb") as f:
                pickle.dump(self._index, f)
        logger.info("[BM25Index] 已保存到 %s", path)

    def load(self, path: Path) -> None:
        """从磁盘加载索引"""
        docs_path = path / "bm25_docs.json"
        index_path = path / "bm25_index.pkl"

        if docs_path.exists():
            with open(docs_path, "r", encoding="utf-8") as f:
                self._docs = json.load(f)
            self._tokenized = [self._tokenize(c["content"]) for c in self._docs]

        if index_path.exists():
            with open(index_path, "rb") as f:
                self._index = pickle.load(f)

        logger.info("[BM25Index] 已加载 %d 块", len(self._docs))


# ─────────────────────────────────────────────
#  Dense 索引封装
# ─────────────────────────────────────────────

class DenseIndex:
    """Dense Embedding 索引封装"""

    def __init__(self):
        self._embeddings: Optional[np.ndarray] = None  # (N, dim)
        self._docs: List[Dict] = []

    @property
    def size(self) -> int:
        return len(self._docs)

    def build(self, chunks: List[Dict], embedding_client=None) -> None:
        """
        从 chunk 列表构建 Dense 索引。

        Args:
            chunks: [{"chunk_id": str, "doc_id": str, "content": str, ...}, ...]
            embedding_client: EmbeddingClient 实例（为 None 时使用默认实例）
        """
        if embedding_client is None:
            from utils.embedding_client import EmbeddingClient
            embedding_client = EmbeddingClient.get_instance()

        self._docs = chunks
        texts = [c["content"] for c in chunks]

        if texts:
            embeddings = embedding_client.embed_batch(texts)
            self._embeddings = np.array(embeddings, dtype=np.float32)
            # L2 归一化
            norms = np.linalg.norm(self._embeddings, axis=1, keepdims=True)
            norms = np.where(norms == 0, 1, norms)
            self._embeddings = self._embeddings / norms
        else:
            self._embeddings = None

        logger.info("[DenseIndex] 构建完成: %d 块, dim=%s",
                     len(chunks), self._embeddings.shape if self._embeddings is not None else "N/A")

    def search(self, query: str, top_k: int = 5, embedding_client=None) -> List[Dict]:
        """
        Dense 余弦相似度检索。

        Returns:
            [{"chunk_id": str, "doc_id": str, "content": str, "score": float}, ...]
        """
        if self._embeddings is None or not self._docs:
            return []

        if embedding_client is None:
            from utils.embedding_client import EmbeddingClient
            embedding_client = EmbeddingClient.get_instance()

        query_emb = np.array(embedding_client.embed(query), dtype=np.float32)
        query_norm = np.linalg.norm(query_emb)
        if query_norm == 0:
            return []
        query_emb = query_emb / query_norm

        # 余弦相似度（已归一化，直接点积）
        scores = self._embeddings @ query_emb

        # 排序取 top_k
        top_indices = np.argsort(scores)[::-1][:top_k]

        results = []
        for idx in top_indices:
            if scores[idx] <= 0:
                break
            doc = dict(self._docs[idx])
            doc["score"] = float(scores[idx])
            results.append(doc)

        return results

    def save(self, path: Path) -> None:
        """保存索引到磁盘"""
        path.mkdir(parents=True, exist_ok=True)
        with open(path / "dense_docs.json", "w", encoding="utf-8") as f:
            json.dump(self._docs, f, ensure_ascii=False, indent=2)
        if self._embeddings is not None:
            np.save(path / "dense_embeddings.npy", self._embeddings)
        logger.info("[DenseIndex] 已保存到 %s", path)

    def load(self, path: Path) -> None:
        """从磁盘加载索引"""
        docs_path = path / "dense_docs.json"
        emb_path = path / "dense_embeddings.npy"

        if docs_path.exists():
            with open(docs_path, "r", encoding="utf-8") as f:
                self._docs = json.load(f)

        if emb_path.exists():
            self._embeddings = np.load(emb_path)

        logger.info("[DenseIndex] 已加载 %d 块", len(self._docs))


# ─────────────────────────────────────────────
#  索引构建器（统一入口）
# ─────────────────────────────────────────────

class IndexBuilder:
    """
    统一索引构建器。

    支持:
      - 全局索引（所有文档）
      - 分类索引（academic / life / course）
      - BM25 + Dense 双索引

    示例:
        >>> builder = IndexBuilder()
        >>> builder.build_from_documents(annotated_docs, chunks_map)
        >>> builder.save("data/processed/indexes/")
        >>> results = builder.search("保研条件", category="academic", top_k=5)
    """

    CATEGORIES = ("academic", "life", "course")

    def __init__(self):
        # 全局索引
        self._global_bm25 = BM25Index()
        self._global_dense = DenseIndex()
        # 分类索引
        self._category_bm25: Dict[str, BM25Index] = {cat: BM25Index() for cat in self.CATEGORIES}
        self._category_dense: Dict[str, DenseIndex] = {cat: DenseIndex() for cat in self.CATEGORIES}
        # 文档元数据
        self._doc_meta: Dict[str, Dict] = {}

    # ── 构建 ──────────────────────────────────

    def build_from_documents(
        self,
        annotated_docs: List[Any],
        chunks_map: Dict[str, List[Dict]],
        embedding_client=None,
    ) -> None:
        """
        从标注文档和分块构建索引。

        Args:
            annotated_docs: AnnotatedDocument 列表
            chunks_map: {doc_id: [chunk_dict, ...], ...}
            embedding_client: EmbeddingClient 实例
        """
        # 1. 收集所有分块，按分类分组
        all_chunks = []
        category_chunks = {cat: [] for cat in self.CATEGORIES}

        for doc in annotated_docs:
            doc_id = doc.doc_id
            category = doc.category

            # 保存文档元数据
            self._doc_meta[doc_id] = {
                "doc_id": doc_id,
                "category": category,
                "title": doc.title,
                "publish_date": str(doc.publish_date) if doc.publish_date else None,
                "expiry_date": str(doc.expiry_date) if doc.expiry_date else None,
                "tags": doc.tags,
                "source_url": doc.source_url,
                "confidence": doc.confidence,
            }

            # 收集分块
            doc_chunks = chunks_map.get(doc_id, [])
            for chunk in doc_chunks:
                # 附加文档元数据到每个 chunk
                enriched = dict(chunk)
                enriched["category"] = category
                enriched["doc_title"] = doc.title
                enriched["publish_date"] = str(doc.publish_date) if doc.publish_date else None

                all_chunks.append(enriched)
                if category in category_chunks:
                    category_chunks[category].append(enriched)

        logger.info(
            "[IndexBuilder] 总块数: %d | academic=%d life=%d course=%d",
            len(all_chunks),
            len(category_chunks["academic"]),
            len(category_chunks["life"]),
            len(category_chunks["course"]),
        )

        # 2. 构建全局索引
        self._global_bm25.build(all_chunks)
        try:
            self._global_dense.build(all_chunks, embedding_client)
        except Exception as e:
            logger.warning("[IndexBuilder] Dense 索引构建失败（将仅使用 BM25）: %s", e)

        # 3. 构建分类索引
        for cat in self.CATEGORIES:
            chunks = category_chunks[cat]
            if chunks:
                self._category_bm25[cat].build(chunks)
                try:
                    self._category_dense[cat].build(chunks, embedding_client)
                except Exception as e:
                    logger.warning("[IndexBuilder] %s Dense 索引构建失败: %s", cat, e)

    def build_from_chunks(self, chunks: List[Dict], embedding_client=None) -> None:
        """
        直接从 chunk 列表构建全局索引（不分类）。

        Args:
            chunks: chunk 字典列表
        """
        self._global_bm25.build(chunks)
        try:
            self._global_dense.build(chunks, embedding_client)
        except Exception as e:
            logger.warning("[IndexBuilder] Dense 索引构建失败: %s", e)

    # ── 查询 ──────────────────────────────────

    def search(
        self,
        query: str,
        category: Optional[str] = None,
        top_k: int = 5,
        use_dense: bool = True,
        rrf_k: int = 60,
    ) -> List[Dict]:
        """
        检索。

        Args:
            query: 查询文本
            category: 限定分类（None 表示全局检索）
            top_k: 返回条数
            use_dense: 是否使用 Dense 索引
            rrf_k: RRF 融合参数

        Returns:
            融合后的检索结果
        """
        # 选择索引
        if category and category in self._category_bm25:
            bm25_idx = self._category_bm25[category]
            dense_idx = self._category_dense[category]
        else:
            bm25_idx = self._global_bm25
            dense_idx = self._global_dense

        # BM25 检索
        bm25_results = bm25_idx.search(query, top_k=top_k * 2)

        # Dense 检索
        dense_results = []
        if use_dense:
            try:
                dense_results = dense_idx.search(query, top_k=top_k * 2)
            except Exception as e:
                logger.warning("[IndexBuilder] Dense 检索失败: %s", e)

        # RRF 融合
        if bm25_results and dense_results:
            return self._rrf_fuse(bm25_results, dense_results, k=rrf_k, top_k=top_k)
        elif bm25_results:
            return bm25_results[:top_k]
        elif dense_results:
            return dense_results[:top_k]
        else:
            return []

    @staticmethod
    def _rrf_fuse(
        bm25_results: List[Dict],
        dense_results: List[Dict],
        k: int = 60,
        top_k: int = 5,
    ) -> List[Dict]:
        """
        Reciprocal Rank Fusion (RRF) 融合两路检索结果。

        RRF(d) = Σ 1 / (k + rank_i(d))
        """
        scores: Dict[str, float] = {}
        doc_map: Dict[str, Dict] = {}

        # BM25 排名
        for rank, doc in enumerate(bm25_results):
            cid = doc.get("chunk_id", str(rank))
            scores[cid] = scores.get(cid, 0) + 1.0 / (k + rank + 1)
            doc_map[cid] = doc

        # Dense 排名
        for rank, doc in enumerate(dense_results):
            cid = doc.get("chunk_id", str(rank))
            scores[cid] = scores.get(cid, 0) + 1.0 / (k + rank + 1)
            if cid not in doc_map:
                doc_map[cid] = doc

        # 排序
        sorted_ids = sorted(scores, key=scores.get, reverse=True)

        results = []
        for cid in sorted_ids[:top_k]:
            doc = dict(doc_map[cid])
            doc["rrf_score"] = scores[cid]
            results.append(doc)

        return results

    # ── 持久化 ────────────────────────────────

    def save(self, output_dir: str | Path) -> None:
        """保存所有索引到磁盘"""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # 全局索引
        global_dir = output_dir / "global"
        self._global_bm25.save(global_dir / "bm25")
        self._global_dense.save(global_dir / "dense")

        # 分类索引
        for cat in self.CATEGORIES:
            cat_dir = output_dir / cat
            if self._category_bm25[cat].size > 0:
                self._category_bm25[cat].save(cat_dir / "bm25")
            if self._category_dense[cat].size > 0:
                self._category_dense[cat].save(cat_dir / "dense")

        # 文档元数据
        with open(output_dir / "doc_meta.json", "w", encoding="utf-8") as f:
            json.dump(self._doc_meta, f, ensure_ascii=False, indent=2)

        logger.info("[IndexBuilder] 所有索引已保存到 %s", output_dir)

    @classmethod
    def load(cls, index_dir: str | Path) -> "IndexBuilder":
        """从磁盘加载已构建的索引"""
        index_dir = Path(index_dir)
        builder = cls()

        # 全局索引
        global_dir = index_dir / "global"
        if (global_dir / "bm25").exists():
            builder._global_bm25.load(global_dir / "bm25")
        if (global_dir / "dense").exists():
            builder._global_dense.load(global_dir / "dense")

        # 分类索引
        for cat in cls.CATEGORIES:
            cat_dir = index_dir / cat
            if (cat_dir / "bm25").exists():
                builder._category_bm25[cat].load(cat_dir / "bm25")
            if (cat_dir / "dense").exists():
                builder._category_dense[cat].load(cat_dir / "dense")

        # 文档元数据
        meta_path = index_dir / "doc_meta.json"
        if meta_path.exists():
            with open(meta_path, "r", encoding="utf-8") as f:
                builder._doc_meta = json.load(f)

        logger.info("[IndexBuilder] 索引加载完成")
        return builder

    # ── 统计 ──────────────────────────────────

    def stats(self) -> Dict:
        """返回索引统计信息"""
        return {
            "global_bm25": self._global_bm25.size,
            "global_dense": self._global_dense.size,
            "categories": {
                cat: {
                    "bm25": self._category_bm25[cat].size,
                    "dense": self._category_dense[cat].size,
                }
                for cat in self.CATEGORIES
            },
            "doc_count": len(self._doc_meta),
        }


# ─────────────────────────────────────────────
#  命令行入口
# ─────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")

    if len(sys.argv) >= 2 and sys.argv[1] == "--stats":
        index_dir = sys.argv[2] if len(sys.argv) > 2 else "data/processed/indexes"
        builder = IndexBuilder.load(index_dir)
        stats = builder.stats()
        print(json.dumps(stats, indent=2, ensure_ascii=False))
    else:
        print("用法:")
        print("  python index_builder.py --stats [index_dir]   查看索引统计")
        print()
        print("在代码中使用:")
        print("  builder = IndexBuilder()")
        print("  builder.build_from_documents(annotated_docs, chunks_map)")
        print("  builder.save('data/processed/indexes/')")
