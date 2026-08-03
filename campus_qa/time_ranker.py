"""
time_ranker.py — 时间感知排序器

职责:
  - 对检索候选文档应用时间衰减加权
  - 过滤已过期文档（超过 expiry_date）
  - 时间越近的文档权重越高
  - 融合检索分数和时间权重，输出最终排序

使用方式:
  from campus_qa.time_ranker import TimeRanker

  ranker = TimeRanker(decay_lambda=0.01)
  ranked = ranker.rank(candidates, top_k=5)
"""

from __future__ import annotations

import logging
import math
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
#  排序结果
# ─────────────────────────────────────────────

class RankedResult(BaseModel):
    """时间排序后的单条结果"""
    chunk_id: str = Field(default="", description="分块 ID")
    doc_id: str = Field(default="", description="文档 ID")
    content: str = Field(default="", description="内容")
    doc_title: str = Field(default="", description="文档标题")
    category: str = Field(default="", description="分类")
    publish_date: Optional[str] = Field(None, description="发布日期")
    retrieval_score: float = Field(default=0.0, description="原始检索分数")
    time_weight: float = Field(default=1.0, description="时间权重")
    final_score: float = Field(default=0.0, description="最终分数")
    is_expired: bool = Field(default=False, description="是否已过期")
    days_since_publish: Optional[int] = Field(None, description="发布距今天数")


# ─────────────────────────────────────────────
#  日期解析工具
# ─────────────────────────────────────────────

def _parse_date(date_str: Optional[str]) -> Optional[date]:
    """解析日期字符串"""
    if not date_str:
        return None

    date_str = str(date_str).strip()

    # ISO 格式
    try:
        return date.fromisoformat(date_str[:10])
    except (ValueError, IndexError):
        pass

    # "2026年9月1日" 格式
    import re
    patterns = [
        re.compile(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日?"),
        re.compile(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})"),
        re.compile(r"(\d{4})\.(\d{1,2})\.(\d{1,2})"),
    ]
    for pat in patterns:
        match = pat.search(date_str)
        if match:
            try:
                return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
            except (ValueError, IndexError):
                continue

    return None


# ─────────────────────────────────────────────
#  时间感知排序器
# ─────────────────────────────────────────────

class TimeRanker:
    """
    时间感知排序器。

    排序公式:
      final_score = retrieval_score × time_weight

    时间权重计算（指数衰减）:
      time_weight = exp(-λ × days_ago)

    其中:
      - λ: 衰减系数（默认 0.01，即 100 天后权重约为 37%）
      - days_ago: 文档发布距今天数

    过期过滤:
      - 如果文档有 expiry_date 且已过期，默认过滤掉
      - 可通过 include_expired=True 保留但标记

    示例:
        >>> ranker = TimeRanker(decay_lambda=0.01)
        >>> ranked = ranker.rank(candidates, top_k=5)
        >>> ranked[0].doc_title
        '2026年保研推免通知'
    """

    def __init__(
        self,
        decay_lambda: float = 0.01,
        default_expiry_days: int = 365,
        filter_expired: bool = True,
        min_time_weight: float = 0.1,
    ):
        """
        Args:
            decay_lambda: 时间衰减系数（越大衰减越快）
            default_expiry_days: 默认有效期天数（文档无 expiry_date 时使用）
            filter_expired: 是否过滤已过期文档
            min_time_weight: 最小时间权重下限（防止旧文档权重过低）
        """
        self._lambda = decay_lambda
        self._default_expiry_days = default_expiry_days
        self._filter_expired = filter_expired
        self._min_weight = min_time_weight

    @classmethod
    def from_config(cls) -> "TimeRanker":
        """从 config.yaml 读取参数"""
        from utils.config_loader import get
        return cls(
            decay_lambda=get("campus_qa.time_decay_lambda", 0.01),
            default_expiry_days=get("campus_qa.default_expiry_days", 365),
        )

    # ── 公共接口 ──────────────────────────────

    def rank(
        self,
        candidates: List[Dict],
        top_k: int = 5,
        include_expired: bool = False,
        reference_date: Optional[date] = None,
    ) -> List[RankedResult]:
        """
        对候选文档执行时间感知排序。

        Args:
            candidates: 检索候选列表（包含 chunk_id, doc_id, content, score, publish_date 等）
            top_k: 返回条数
            include_expired: 是否包含已过期文档
            reference_date: 参考日期（默认为今天）

        Returns:
            RankedResult 列表（按 final_score 降序）
        """
        today = reference_date or date.today()
        results = []
        expired_count = 0

        for cand in candidates:
            # 解析日期
            pub_date = _parse_date(cand.get("publish_date"))
            exp_date = _parse_date(cand.get("expiry_date"))

            # 计算距今天数
            days_ago = None
            if pub_date:
                days_ago = (today - pub_date).days
                if days_ago < 0:
                    days_ago = 0

            # 过期检测
            is_expired = False
            if exp_date and today > exp_date:
                is_expired = True
            elif pub_date and not exp_date:
                # 无显式过期日期，使用默认有效期
                default_expiry = pub_date.replace(
                    year=pub_date.year + (self._default_expiry_days // 365),
                )
                if today > default_expiry:
                    is_expired = True

            # 过滤过期文档
            if is_expired and self._filter_expired and not include_expired:
                expired_count += 1
                continue

            # 计算时间权重
            time_weight = self._compute_time_weight(days_ago)

            # 原始检索分数
            retrieval_score = float(
                cand.get("rrf_score", cand.get("score", 0.0))
            )

            # 最终分数
            final_score = retrieval_score * time_weight

            results.append(RankedResult(
                chunk_id=cand.get("chunk_id", ""),
                doc_id=cand.get("doc_id", ""),
                content=cand.get("content", ""),
                doc_title=cand.get("doc_title", ""),
                category=cand.get("category", ""),
                publish_date=str(pub_date) if pub_date else None,
                retrieval_score=round(retrieval_score, 4),
                time_weight=round(time_weight, 4),
                final_score=round(final_score, 4),
                is_expired=is_expired,
                days_since_publish=days_ago,
            ))

        # 按 final_score 降序排列
        results.sort(key=lambda x: x.final_score, reverse=True)

        if expired_count > 0:
            logger.info("[TimeRanker] 过滤 %d 条过期文档", expired_count)

        logger.info(
            "[TimeRanker] 排序完成: %d → %d 候选 (top_k=%d)",
            len(candidates), len(results[:top_k]), top_k,
        )

        return results[:top_k]

    def rank_with_boost(
        self,
        candidates: List[Dict],
        top_k: int = 5,
        recent_boost: float = 1.5,
        recent_days: int = 30,
        reference_date: Optional[date] = None,
    ) -> List[RankedResult]:
        """
        带近期加权的排序。

        最近 N 天发布的文档获得额外加权。

        Args:
            candidates: 候选列表
            top_k: 返回条数
            recent_boost: 近期加权倍数
            recent_days: 近期天数阈值
            reference_date: 参考日期

        Returns:
            RankedResult 列表
        """
        results = self.rank(candidates, top_k=top_k * 2, reference_date=reference_date)

        for r in results:
            if r.days_since_publish is not None and r.days_since_publish <= recent_days:
                r.final_score = round(r.final_score * recent_boost, 4)

        results.sort(key=lambda x: x.final_score, reverse=True)
        return results[:top_k]

    # ── 时间权重计算 ──────────────────────────

    def _compute_time_weight(self, days_ago: Optional[int]) -> float:
        """
        计算时间权重（指数衰减）。

        weight = max(min_weight, exp(-λ × days_ago))

        Args:
            days_ago: 距今天数（None 表示未知日期）

        Returns:
            时间权重 [min_weight, 1.0]
        """
        if days_ago is None:
            # 无日期信息，给予中等权重
            return 0.5

        weight = math.exp(-self._lambda * days_ago)
        return max(self._min_weight, weight)

    # ── 配置调整 ──────────────────────────────

    def set_decay_lambda(self, new_lambda: float) -> None:
        """动态调整衰减系数"""
        self._lambda = new_lambda
        logger.info("[TimeRanker] 衰减系数更新: λ = %f", new_lambda)

    def get_decay_profile(self, max_days: int = 365, step: int = 30) -> Dict[int, float]:
        """
        获取衰减曲线（用于调试和可视化）。

        Returns:
            {天数: 权重, ...}
        """
        profile = {}
        for d in range(0, max_days + 1, step):
            profile[d] = round(self._compute_time_weight(d), 4)
        return profile


# ─────────────────────────────────────────────
#  命令行测试
# ─────────────────────────────────────────────

if __name__ == "__main__":
    import json

    logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")

    ranker = TimeRanker(decay_lambda=0.01)

    # 模拟候选文档
    mock_candidates = [
        {
            "chunk_id": "CHK_000001",
            "doc_id": "DOC_00000001",
            "content": "保研条件：学业成绩排名在本专业前30%",
            "doc_title": "2026年保研推免通知",
            "category": "academic",
            "publish_date": "2026-08-20",
            "score": 0.95,
        },
        {
            "chunk_id": "CHK_000002",
            "doc_id": "DOC_00000002",
            "content": "保研条件：全日制本科应届毕业生",
            "doc_title": "2025年保研推免通知",
            "category": "academic",
            "publish_date": "2025-08-15",
            "score": 0.90,
        },
        {
            "chunk_id": "CHK_000003",
            "doc_id": "DOC_00000003",
            "content": "保研申请条件：无违纪处分记录",
            "doc_title": "2024年保研推免通知",
            "category": "academic",
            "publish_date": "2024-08-10",
            "score": 0.88,
        },
        {
            "chunk_id": "CHK_000004",
            "doc_id": "DOC_00000004",
            "content": "选课系统开放时间通知",
            "doc_title": "2026年选课通知",
            "category": "academic",
            "publish_date": "2026-06-10",
            "score": 0.70,
        },
        {
            "chunk_id": "CHK_000005",
            "doc_id": "DOC_00000005",
            "content": "图书馆开放时间调整通知",
            "doc_title": "图书馆通知",
            "category": "life",
            "publish_date": None,
            "score": 0.60,
        },
    ]

    print("=== 时间感知排序测试 ===\n")
    print(f"衰减曲线:")
    profile = ranker.get_decay_profile(max_days=365, step=60)
    for days, weight in profile.items():
        bar = "█" * int(weight * 20)
        print(f"  {days:>4}天: {weight:.4f} {bar}")

    print(f"\n排序结果:")
    ranked = ranker.rank(mock_candidates, top_k=5)
    for i, r in enumerate(ranked):
        expired_mark = " [已过期]" if r.is_expired else ""
        print(
            f"  #{i+1} {r.doc_title}{expired_mark}\n"
            f"      检索分={r.retrieval_score} × 时间权={r.time_weight} = {r.final_score}\n"
            f"      发布于 {r.publish_date or '未知'} ({r.days_since_publish or '?'} 天前)"
        )

    print(f"\n近期加权排序 (30天内 x1.5):")
    ranked_boost = ranker.rank_with_boost(mock_candidates, top_k=5, recent_boost=1.5, recent_days=90)
    for i, r in enumerate(ranked_boost):
        print(f"  #{i+1} {r.doc_title} | final={r.final_score}")
