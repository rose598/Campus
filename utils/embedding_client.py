from typing import List, Optional
from sentence_transformers import SentenceTransformer
import numpy as np
from .config_loader import get


class EmbeddingClient:
    """Embedding 服务封装 —— 本地运行，零 API 成本"""

    _instance: Optional["EmbeddingClient"] = None

    def __init__(self, model_name: Optional[str] = None):
        self._model_name = model_name or get("embedding.model", "sentence-transformers/all-MiniLM-L6-v2")
        self._model: Optional[SentenceTransformer] = None

    @classmethod
    def get_instance(cls) -> "EmbeddingClient":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @property
    def model(self) -> SentenceTransformer:
        if self._model is None:
            device = get("embedding.device", "cpu")
            self._model = SentenceTransformer(self._model_name, device=device)
        return self._model

    def embed(self, text: str) -> List[float]:
        if not text or not text.strip():
            return [0.0] * self.model.get_sentence_embedding_dimension()
        embedding = self.model.encode(text, normalize_embeddings=True)
        return embedding.tolist()

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        non_empty = [t for t in texts if t and t.strip()]
        if not non_empty:
            dim = self.model.get_sentence_embedding_dimension()
            return [[0.0] * dim for _ in texts]

        embeddings = self.model.encode(non_empty, normalize_embeddings=True)
        results = embeddings.tolist()

        dim = self.model.get_sentence_embedding_dimension()
        final = []
        idx = 0
        for t in texts:
            if t and t.strip():
                final.append(results[idx])
                idx += 1
            else:
                final.append([0.0] * dim)
        return final

    def cosine_similarity(self, a: List[float], b: List[float]) -> float:
        a_arr = np.array(a)
        b_arr = np.array(b)
        norm_a = np.linalg.norm(a_arr)
        norm_b = np.linalg.norm(b_arr)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(np.dot(a_arr, b_arr) / (norm_a * norm_b))
