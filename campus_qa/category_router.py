"""
category_router.py — 分类路由器

职责:
  - 根据意图分类结果路由到对应的索引
  - 支持多路由策略（精确路由 / 扩展路由 / 全局回退）
  - 查询改写（简单同义词扩展）
  - 输出检索候选文档，供下游 TimeRanker 排序

使用方式:
  from campus_qa.category_router import CategoryRouter

  router = CategoryRouter(index_builder)
  results = router.route("保研需要什么条件？", intent="policy")
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
#  路由结果
# ─────────────────────────────────────────────

class RouteResult(BaseModel):
    """路由检索结果"""
    query: str = Field(..., description="原始查询")
    intent: str = Field(default="general", description="意图分类")
    route_to: List[str] = Field(default_factory=list, description="路由目标分类列表")
    candidates: List[Dict] = Field(default_factory=list, description="检索候选文档")
    strategy: str = Field(default="exact", description="路由策略: exact / expanded / global")


# ─────────────────────────────────────────────
#  查询扩展（同义词）
# ─────────────────────────────────────────────

_SYNONYMS = {
    "保研": ["推免", "免试研究生", "推荐免试"],
    "推免": ["保研", "免试"],
    "转专业": ["换专业", "专业调剂"],
    "选课": ["选课程", "课程选择"],
    "补考": ["重修", "重考"],
    "绩点": ["GPA", "学分绩点"],
    "宿舍": ["住宿", "寝室"],
    "食堂": ["餐厅", "吃饭"],
    "图书馆": ["图书室", "阅览室"],
    "校园网": ["WiFi", "无线网络"],
    "一卡通": ["饭卡", "校园卡"],
    "期末考试": ["期末考", "期末"],
    "课件": ["PPT", "讲义", "幻灯片"],
    "奖学金": ["奖学", "国奖"],
    "四六级": ["CET4", "CET6", "英语四级", "英语六级"],
}


def _expand_query(query: str, max_expansions: int = 3) -> str:
    """
    简单同义词扩展查询。

    将匹配到的同义词追加到查询末尾，增强召回率。
    """
    expansions = []
    query_lower = query.lower()

    for word, synonyms in _SYNONYMS.items():
        if word.lower() in query_lower:
            for syn in synonyms:
                if syn.lower() not in query_lower and syn not in expansions:
                    expansions.append(syn)
                    if len(expansions) >= max_expansions:
                        break
        if len(expansions) >= max_expansions:
            break

    if expansions:
        expanded = f"{query} {' '.join(expansions)}"
        logger.debug("[CategoryRouter] 查询扩展: '%s' → '%s'", query, expanded)
        return expanded

    return query


# ─────────────────────────────────────────────
#  分类路由器
# ─────────────────────────────────────────────

class CategoryRouter:
    """
    分类路由器：根据意图分类将查询路由到对应索引。

    路由策略:
      - exact: 精确路由到意图对应的分类索引
      - expanded: 扩展路由，同时查询相关分类
      - global: 全局索引回退（意图不明确时）

    意图 → 索引映射:
      - policy → academic 索引
      - life   → life 索引
      - course → course 索引
      - general → global 索引

    示例:
        >>> router = CategoryRouter(index_builder)
        >>> result = router.route("保研条件", intent="policy")
        >>> len(result.candidates)
        5
    """

    # 意图 → 索引分类映射
    INTENT_TO_CATEGORY = {
        "policy": "academic",
        "life": "life",
        "course": "course",
        "general": None,  # 使用全局索引
    }

    # 扩展路由：意图 → 额外查询的分类
    EXPANDED_ROUTES = {
        "policy": ["course"],       # 政策问题也可能涉及课程
        "life": [],                  # 生活问题一般不需要扩展
        "course": ["academic"],      # 课程问题可能涉及政策
        "general": ["academic", "life", "course"],
    }

    def __init__(
        self,
        index_builder=None,
        expand_query: bool = True,
        expand_routes: bool = True,
        top_k: int = 10,
    ):
        """
        Args:
            index_builder: IndexBuilder 实例
            expand_query: 是否启用查询同义词扩展
            expand_routes: 是否启用扩展路由
            top_k: 每个路由返回的候选数
        """
        self._builder = index_builder
        self._expand_query = expand_query
        self._expand_routes = expand_routes
        self._top_k = top_k

    def set_index_builder(self, builder) -> None:
        """设置/更新 IndexBuilder"""
        self._builder = builder

    # ── 公共接口 ──────────────────────────────

    def route(
        self,
        query: str,
        intent: str = "general",
        sub_intent: Optional[str] = None,
        use_dense: bool = True,
    ) -> RouteResult:
        """
        路由查询到对应索引并检索。

        Args:
            query: 用户查询
            intent: 意图分类结果
            sub_intent: 子意图
            use_dense: 是否使用 Dense 索引

        Returns:
            RouteResult
        """
        if not self._builder:
            logger.warning("[CategoryRouter] IndexBuilder 未设置")
            return RouteResult(query=query, intent=intent, strategy="none")

        # 查询扩展
        search_query = query
        if self._expand_query:
            search_query = _expand_query(query)

        # 确定路由目标
        primary_cat = self.INTENT_TO_CATEGORY.get(intent)
        route_targets = []
        candidates = []

        if primary_cat:
            # 精确路由
            route_targets.append(primary_cat)
            primary_results = self._builder.search(
                search_query,
                category=primary_cat,
                top_k=self._top_k,
                use_dense=use_dense,
            )
            candidates.extend(primary_results)

            # 扩展路由
            if self._expand_routes and intent in self.EXPANDED_ROUTES:
                for extra_cat in self.EXPANDED_ROUTES[intent]:
                    route_targets.append(extra_cat)
                    extra_results = self._builder.search(
                        search_query,
                        category=extra_cat,
                        top_k=max(3, self._top_k // 2),
                        use_dense=use_dense,
                    )
                    candidates.extend(extra_results)

            strategy = "expanded" if len(route_targets) > 1 else "exact"
        else:
            # 全局回退
            route_targets = ["global"]
            candidates = self._builder.search(
                search_query,
                category=None,
                top_k=self._top_k,
                use_dense=use_dense,
            )
            strategy = "global"

        # 去重（按 chunk_id）
        seen = set()
        unique_candidates = []
        for c in candidates:
            cid = c.get("chunk_id", id(c))
            if cid not in seen:
                seen.add(cid)
                unique_candidates.append(c)

        logger.info(
            "[CategoryRouter] query='%s' | intent=%s | route=%s | candidates=%d | strategy=%s",
            query[:30], intent, route_targets, len(unique_candidates), strategy,
        )

        return RouteResult(
            query=query,
            intent=intent,
            route_to=route_targets,
            candidates=unique_candidates,
            strategy=strategy,
        )

    def route_with_fallback(
        self,
        query: str,
        intent: str = "general",
        use_dense: bool = True,
        min_candidates: int = 3,
    ) -> RouteResult:
        """
        带兜底的路由。

        如果精确路由返回的候选不足 min_candidates 个，
        自动回退到全局索引检索。

        Args:
            query: 用户查询
            intent: 意图分类
            use_dense: 是否使用 Dense
            min_candidates: 最少候选数

        Returns:
            RouteResult
        """
        result = self.route(query, intent=intent, use_dense=use_dense)

        if len(result.candidates) < min_candidates and self._builder:
            logger.info(
                "[CategoryRouter] 候选不足(%d < %d)，回退全局检索",
                len(result.candidates), min_candidates,
            )
            global_results = self._builder.search(
                query,
                category=None,
                top_k=self._top_k,
                use_dense=use_dense,
            )
            # 合并去重
            seen = {c.get("chunk_id") for c in result.candidates}
            for c in global_results:
                cid = c.get("chunk_id")
                if cid not in seen:
                    seen.add(cid)
                    result.candidates.append(c)

            result.route_to.append("global_fallback")
            result.strategy = "fallback"

        return result

    # ── 统计 ──────────────────────────────────

    def get_available_categories(self) -> Dict[str, int]:
        """返回可用的分类索引及其文档数"""
        if not self._builder:
            return {}

        stats = self._builder.stats()
        return {
            cat: stats["categories"].get(cat, {}).get("bm25", 0)
            for cat in ("academic", "life", "course")
        }


# ─────────────────────────────────────────────
#  命令行测试
# ─────────────────────────────────────────────

if __name__ == "__main__":
    import json

    logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")

    print("=== 分类路由器测试 ===\n")

    # 测试查询扩展
    test_queries = [
        "保研需要什么条件",
        "绩点怎么算",
        "宿舍可以换吗",
        "期末考试范围",
    ]

    print("查询扩展测试:")
    for q in test_queries:
        expanded = _expand_query(q)
        if expanded != q:
            print(f"  '{q}' → '{expanded}'")
        else:
            print(f"  '{q}' → (无扩展)")
