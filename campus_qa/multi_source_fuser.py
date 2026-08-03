"""
multi_source_fuser.py — 多源融合器

职责:
  - 对来自不同分类索引的检索结果执行跨类别 RRF 融合
  - 合并相同文档的不同分块
  - 去重 + 最终排序

使用方式:
  from campus_qa.multi_source_fuser import MultiSourceFuser

  fuser = MultiSourceFuser()
  fused = fuser.fuse([academic_results, life_results, course_results])
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
#  融合结果
# ─────────────────────────────────────────────

class FusedResult(BaseModel):
    """融合后的单条结果"""
    chunk_id: str = Field(default="", description="分块 ID")
    doc_id: str = Field(default="", description="文档 ID")
    content: str = Field(default="", description="内容")
    doc_title: str = Field(default="", description="文档标题")
    category: str = Field(default="", description="分类")
    publish_date: Optional[str] = Field(None, description="发布日期")
    score: float = Field(default=0.0, description="融合分数")
    sources: List[str] = Field(default_factory=list, description="来源分类列表")


# ─────────────────────────────────────────────
#  多源融合器
# ─────────────────────────────────────────────

class MultiSourceFuser:
    """
    跨类别 RRF 融合器。

    融合策略:
      - Reciprocal Rank Fusion (RRF)：对每个来源列表中的排名取倒数加权求和
      - 同一文档的不同分块合并（取最高分）
      - 去重后输出最终排序

    示例:
        >>> fuser = MultiSourceFuser(rrf_k=60)
        >>> fused = fuser.fuse([results_a, results_b], top_k=5)
    """

    def __init__(self, rrf_k: int = 60):
        """
        Args:
            rrf_k: RRF 融合参数 k（默认 60，标准值）
        """
        self._rrf_k = rrf_k

    @classmethod
    def from_config(cls) -> "MultiSourceFuser":
        """从 config.yaml 读取参数"""
        from utils.config_loader import get
        return cls(rrf_k=get("rag.rrf_k", 60))

    # ── 公共接口 ──────────────────────────────

    def fuse(
        self,
        source_lists: List[List[Any]],
        top_k: int = 5,
        source_labels: Optional[List[str]] = None,
    ) -> List[FusedResult]:
        """
        融合多个来源的检索结果。

        Args:
            source_lists: 多个来源的结果列表
                         [[result_a1, result_a2, ...], [result_b1, ...], ...]
            top_k: 返回条数
            source_labels: 来源标签列表（如 ["academic", "life"]）

        Returns:
            FusedResult 列表（按融合分数降序）
        """
        if not source_lists:
            return []

        # 默认标签
        if source_labels is None:
            source_labels = [f"source_{i}" for i in range(len(source_lists))]

        scores: Dict[str, float] = {}
        doc_map: Dict[str, Dict] = {}
        doc_sources: Dict[str, List[str]] = {}

        for label, results in zip(source_labels, source_lists):
            if not results:
                continue

            for rank, item in enumerate(results):
                # 支持 dict 和 Pydantic model
                if hasattr(item, "model_dump"):
                    item = item.model_dump()
                elif hasattr(item, "dict"):
                    item = item.dict()

                cid = item.get("chunk_id", str(id(item)))
                rrf_score = 1.0 / (self._rrf_k + rank + 1)

                scores[cid] = scores.get(cid, 0) + rrf_score

                if cid not in doc_map:
                    doc_map[cid] = item
                doc_sources.setdefault(cid, [])
                if label not in doc_sources[cid]:
                    doc_sources[cid].append(label)

        # 排序
        sorted_ids = sorted(scores, key=scores.get, reverse=True)

        results = []
        for cid in sorted_ids[:top_k]:
            item = doc_map[cid]
            results.append(FusedResult(
                chunk_id=cid,
                doc_id=item.get("doc_id", ""),
                content=item.get("content", ""),
                doc_title=item.get("doc_title", item.get("title", "")),
                category=item.get("category", ""),
                publish_date=item.get("publish_date"),
                score=round(scores[cid], 6),
                sources=doc_sources.get(cid, []),
            ))

        logger.info(
            "[MultiSourceFuser] 融合 %d 个来源 → %d 结果 (top_k=%d)",
            len(source_lists), len(results), top_k,
        )

        return results

    def fuse_ranked_results(
        self,
        ranked_results: List[Any],
        category: str = "",
        top_k: int = 5,
    ) -> List[FusedResult]:
        """
        融合已经过 TimeRanker 排序的结果。

        直接使用 final_score 而非 RRF 排名融合。
        """
        scored = []
        for item in ranked_results:
            if hasattr(item, "model_dump"):
                item = item.model_dump()
            elif hasattr(item, "dict"):
                item = item.dict()

            scored.append(FusedResult(
                chunk_id=item.get("chunk_id", ""),
                doc_id=item.get("doc_id", ""),
                content=item.get("content", ""),
                doc_title=item.get("doc_title", ""),
                category=item.get("category", category),
                publish_date=item.get("publish_date"),
                score=float(item.get("final_score", item.get("score", 0.0))),
                sources=[category] if category else [],
            ))

        scored.sort(key=lambda x: x.score, reverse=True)
        return scored[:top_k]


# ─────────────────────────────────────────────
#  命令行测试
# ─────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")

    fuser = MultiSourceFuser(rrf_k=60)

    # 模拟两个来源
    source_a = [
        {"chunk_id": "CHK_A1", "doc_id": "DOC_01", "content": "保研条件...", "doc_title": "保研通知", "score": 0.95},
        {"chunk_id": "CHK_A2", "doc_id": "DOC_02", "content": "转专业...", "doc_title": "转专业办法", "score": 0.80},
    ]
    source_b = [
        {"chunk_id": "CHK_B1", "doc_id": "DOC_01", "content": "保研条件...", "doc_title": "保研通知", "score": 0.90},
        {"chunk_id": "CHK_B2", "doc_id": "DOC_03", "content": "选课...", "doc_title": "选课通知", "score": 0.70},
    ]

    fused = fuser.fuse([source_a, source_b], top_k=5, source_labels=["academic", "course"])

    print("=== 多源融合测试 ===\n")
    for i, r in enumerate(fused):
        print(f"  #{i+1} {r.doc_title} | score={r.score} | sources={r.sources}")
