from typing import List, Optional, Dict, Any
import numpy as np

from utils.config_loader import get


class DenseIndex:
    """稠密向量索引 —— 基于 sentence-transformers 的语义检索"""

    def __init__(self):
        self._chunks: List[Dict[str, Any]] = []
        self._embeddings: Optional[np.ndarray] = None

    @property
    def chunk_count(self) -> int:
        return len(self._chunks)

    def build(self, chunks: List[Dict[str, Any]]) -> "DenseIndex":
        if not chunks:
            return self

        from utils.embedding_client import EmbeddingClient

        self._chunks = chunks

        texts = [c.get("content", "") or "" for c in chunks]
        non_empty_indices = [i for i, t in enumerate(texts) if t.strip()]
        if not non_empty_indices:
            return self

        client = EmbeddingClient.get_instance()

        embeddings_map = {}
        batch_size = min(32, len(non_empty_indices))
        for start in range(0, len(non_empty_indices), batch_size):
            batch_indices = non_empty_indices[start:start + batch_size]
            batch_texts = [texts[i] for i in batch_indices]
            batch_embs = client.embed_batch(batch_texts)
            for idx, emb in zip(batch_indices, batch_embs):
                embeddings_map[idx] = emb

        dim = client.model.get_sentence_embedding_dimension()
        self._embeddings = np.zeros((len(chunks), dim), dtype=np.float32)
        for idx, emb in embeddings_map.items():
            self._embeddings[idx] = np.array(emb, dtype=np.float32)

        return self

    def search(self, query: str, top_k: Optional[int] = None) -> List[Dict[str, Any]]:
        if self._embeddings is None or self._embeddings.shape[0] == 0:
            return []

        k = top_k or int(get("rag.dense_top_k", 5))

        from utils.embedding_client import EmbeddingClient
        client = EmbeddingClient.get_instance()
        query_emb = np.array(client.embed(query), dtype=np.float32)

        query_norm = np.linalg.norm(query_emb)
        if query_norm == 0:
            return []

        query_emb_norm = query_emb / query_norm

        norms = np.linalg.norm(self._embeddings, axis=1)
        norms[norms == 0] = 1.0
        normalized = self._embeddings / norms[:, np.newaxis]

        scores = np.dot(normalized, query_emb_norm)

        top_indices = np.argsort(scores)[::-1][:k]

        results = []
        for idx in top_indices:
            score = float(scores[idx])
            if score <= 0:
                continue
            chunk = self._chunks[idx]
            results.append({
                "chunk_id": chunk.get("chunk_id", ""),
                "score": score,
                "content": chunk.get("content", ""),
                "doc_id": chunk.get("doc_id", ""),
                "category": chunk.get("category", ""),
                "title": chunk.get("title", ""),
            })

        return results

    def to_state(self) -> dict:
        return {
            "chunks": [
                {
                    "chunk_id": c.get("chunk_id", ""),
                    "content": c.get("content", ""),
                    "doc_id": c.get("doc_id", ""),
                    "category": c.get("category", ""),
                    "title": c.get("title", ""),
                }
                for c in self._chunks
            ],
            "embeddings": self._embeddings.tolist() if self._embeddings is not None else [],
        }

    @classmethod
    def from_state(cls, data: dict) -> "DenseIndex":
        index = cls()
        chunks = data.get("chunks", [])
        emb_list = data.get("embeddings", [])

        if not chunks:
            return index

        index._chunks = chunks
        if emb_list:
            index._embeddings = np.array(emb_list, dtype=np.float32)

        return index

    @classmethod
    def from_database(cls, category: Optional[str] = None) -> "DenseIndex":
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
    def from_documents(cls, documents: List[Any]) -> "DenseIndex":
        chunks_data: List[Dict[str, Any]] = []
        for doc in documents:
            content = doc.get("content", "") if isinstance(doc, dict) else str(doc)
            doc_id = doc.get("doc_id", "") if isinstance(doc, dict) else ""
            category = doc.get("category", "") if isinstance(doc, dict) else ""
            title = doc.get("title", "") if isinstance(doc, dict) else ""
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


def build_dense_index(chunks: List[Dict[str, Any]]) -> DenseIndex:
    index = DenseIndex()
    return index.build(chunks)
