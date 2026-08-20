"""语义缓存 —— 余弦相似度匹配 + TTL 过期 + LRU 淘汰

相似问题（embedding 余弦相似度 > 阈值，默认 0.92）直接返回缓存答案，
避免重复调用 LLM，降低成本与延迟。

设计要点：
- 线程安全：所有读写在 threading.Lock 内进行（Streamlit 多线程环境）
- TTL 过期：条目写入超过 ttl_seconds 后，在下次查询时清理
- LRU 淘汰：超过 max_size 时，一次性淘汰最久未访问的 25%
- 命中率统计：hit / miss 计数，便于健康检查与调参
"""
import time
import threading
from typing import List, Optional, Tuple


class SemanticCache:
    """语义缓存 —— 余弦相似度匹配 + TTL 过期 + LRU 淘汰"""

    def __init__(
        self,
        similarity_threshold: float = 0.92,
        ttl_seconds: int = 3600,
        max_size: int = 1000,
    ):
        self._threshold = similarity_threshold
        self._ttl = ttl_seconds
        self._max_size = max_size
        # 存储: [(embedding, response, timestamp, last_access)]
        self._store: List[Tuple[List[float], str, float, float]] = []
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    def query(self, embedding: List[float]) -> Optional[str]:
        """查询缓存，返回相似度超过阈值的缓存结果，否则返回 None"""
        import numpy as np

        now = time.time()
        best_score = -1.0
        best_idx = -1

        with self._lock:
            # 清理过期条目
            self._store = [
                entry for entry in self._store
                if now - entry[2] < self._ttl
            ]

            if not self._store:
                self._misses += 1
                return None

            query_arr = np.array(embedding)
            query_norm = np.linalg.norm(query_arr)
            if query_norm == 0:
                self._misses += 1
                return None

            for i, (cached_emb, _, _, _) in enumerate(self._store):
                cached_arr = np.array(cached_emb)
                cached_norm = np.linalg.norm(cached_arr)
                if cached_norm == 0:
                    continue
                score = float(np.dot(query_arr, cached_arr) / (query_norm * cached_norm))
                if score > best_score:
                    best_score = score
                    best_idx = i

            if best_score >= self._threshold and best_idx >= 0:
                # 更新 LRU 访问时间
                entry = self._store[best_idx]
                self._store[best_idx] = (entry[0], entry[1], entry[2], now)
                self._hits += 1
                return entry[1]

            self._misses += 1
        return None

    def put(self, embedding: List[float], response: str) -> None:
        """存入缓存"""
        now = time.time()
        with self._lock:
            # LRU 淘汰：超过 max_size 时删除最久未访问的
            if len(self._store) >= self._max_size:
                self._store.sort(key=lambda x: x[3])
                self._store = self._store[self._max_size // 4:]  # 淘汰 25%
            self._store.append((embedding, response, now, now))

    def clear(self) -> None:
        """清空缓存"""
        with self._lock:
            self._store.clear()
            self._hits = 0
            self._misses = 0

    def stats(self) -> dict:
        """缓存统计信息（供健康检查 / 调试使用）"""
        with self._lock:
            total = self._hits + self._misses
            return {
                "size": len(self._store),
                "max_size": self._max_size,
                "threshold": self._threshold,
                "ttl_seconds": self._ttl,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": round(self._hits / total, 4) if total else 0.0,
            }
