from datetime import datetime, timezone
from typing import List, Optional, Dict
from pydantic import BaseModel, Field
import networkx as nx

from utils.config_loader import get


class Recommendation(BaseModel):
    event_id: str = Field(..., description="活动节点 ID，格式 event:{title}")
    event_title: str = Field(..., description="活动标题")
    event_type: str = Field(default="", description="活动类型")
    score: float = Field(..., ge=0, le=1, description="PPR 分数")
    reasoning_chain: List[str] = Field(default_factory=list, description="推理链路径，可读名称列表")


class PprRecommender:
    """PPR 推荐引擎 —— Personalized PageRank + 推理链 + 兜底"""

    def __init__(self, graph: nx.DiGraph):
        self._graph = graph
        self._undirected = graph.to_undirected(as_view=True)
        self._alpha = float(get("ppr.alpha", 0.85))
        self._max_iter = int(get("ppr.max_iter", 100))
        self._top_k = int(get("ppr.top_k", 5))
        self._tol = float(get("ppr.tol", 1e-6))
        self._max_hops = int(get("ppr.max_chain_hops", 4))
        self._fallback_count = int(get("ppr.fallback_count", 3))
        # Day 23 调优参数
        self._course_weight = float(get("ppr.course_weight", 1.2))
        self._freshness_weight = float(get("ppr.freshness_weight", 0.3))
        self._freshness_halflife_days = float(get("ppr.freshness_halflife_days", 60))
        self._diversity_penalty = float(get("ppr.diversity_penalty", 0.25))

    # ── public API ─────────────────────────────────────────────────────

    def recommend(
        self,
        user_interests: List[str],
        user_courses: Optional[List[str]] = None,
        top_k: Optional[int] = None,
    ) -> List[Recommendation]:
        try:
            personalization, source_nodes = self._build_personalization(
                user_interests, user_courses or []
            )
        except Exception:
            return self._fallback_recommend(self._fallback_count)

        if personalization is None:
            return self._fallback_recommend(self._fallback_count)

        try:
            scores = self._run_ppr(personalization)
        except Exception:
            return self._fallback_recommend(self._fallback_count)

        k = top_k or self._top_k
        results = self._extract_event_recommendations(scores, k)

        if not results:
            return self._fallback_recommend(self._fallback_count)

        for r in results:
            r.reasoning_chain = self._generate_reasoning_chain(source_nodes, r.event_id)

        return results

    # ── personalization ────────────────────────────────────────────────

    def _build_personalization(
        self, user_interests: List[str], user_courses: List[str]
    ) -> tuple:
        pvec: Dict[str, float] = {}
        source_nodes: List[str] = []

        interest_nodes = [
            n for n, d in self._graph.nodes(data=True)
            if d.get("node_type") == "interest"
        ]
        for user_kw in user_interests:
            for nid in interest_nodes:
                name = self._graph.nodes[nid].get("name", "")
                if user_kw in name or name in user_kw:
                    pvec[nid] = 1.0
                    source_nodes.append(nid)

        for code in user_courses:
            course_nid = f"course:{code}"
            if course_nid in self._graph:
                # 课程信号权重略高于兴趣（课程与活动的关联更确定）
                pvec[course_nid] = pvec.get(course_nid, 0) + self._course_weight
                if course_nid not in source_nodes:
                    source_nodes.append(course_nid)

        if not pvec:
            return None, []

        return pvec, source_nodes

    # ── PPR run ────────────────────────────────────────────────────────

    def _run_ppr(self, personalization: dict) -> dict:
        # networkx ≥ 3.3 要求 personalization 向量求和为 1，先归一化
        total = sum(personalization.values())
        if total <= 0:
            raise ValueError("personalization 向量总和非正")
        normalized = {nid: w / total for nid, w in personalization.items()}

        return nx.pagerank(
            self._undirected,
            alpha=self._alpha,
            personalization=normalized,
            max_iter=self._max_iter,
            tol=self._tol,
        )

    # ── event extraction ───────────────────────────────────────────────

    def _extract_event_recommendations(
        self, scores: dict, top_k: int
    ) -> List[Recommendation]:
        # 初筛：所有 event 节点的 PPR 原始分
        event_scores = []
        for nid, score in scores.items():
            if self._graph.nodes[nid].get("node_type") != "event":
                continue
            event_scores.append((nid, float(score)))

        if not event_scores:
            return []

        # Day 23 调优 1: 时效加权 —— 近期活动按半衰期提权
        event_scores = [
            (nid, s * (1.0 + self._freshness_boost(nid)))
            for nid, s in event_scores
        ]

        # Day 23 调优 2: 类型多样性惩罚 —— 贪心选择，同类型已选越多惩罚越重
        event_scores.sort(key=lambda x: x[1], reverse=True)
        selected: List[tuple] = []
        type_counts: Dict[str, int] = {}
        candidates = list(event_scores)
        while candidates and len(selected) < top_k:
            best_idx, best_val = 0, float("-inf")
            for i, (nid, s) in enumerate(candidates):
                etype = self._graph.nodes[nid].get("event_type", "")
                penalty = self._diversity_penalty * type_counts.get(etype, 0)
                val = s * (1.0 - penalty)
                if val > best_val:
                    best_val, best_idx = val, i
            nid, s = candidates.pop(best_idx)
            selected.append((nid, max(s, 0.0)))
            etype = self._graph.nodes[nid].get("event_type", "")
            type_counts[etype] = type_counts.get(etype, 0) + 1

        # Day 23 调优 3: 分数归一化 —— Top1 归一到 1.0，保持可比性
        max_score = max((s for _, s in selected), default=0.0)
        results = []
        for nid, score in selected:
            nd = self._graph.nodes[nid]
            normalized = (score / max_score) if max_score > 0 else 0.0
            results.append(Recommendation(
                event_id=nid,
                event_title=nd.get("name", ""),
                event_type=nd.get("event_type", ""),
                score=round(min(normalized, 1.0), 6),
            ))
        return results

    def _freshness_boost(self, event_nid: str) -> float:
        """时效提权因子：活动日期越近提权越高（半衰期衰减，无日期不提权）"""
        if self._freshness_weight <= 0:
            return 0.0
        date_str = self._graph.nodes[event_nid].get("event_date", "")
        if not date_str:
            return 0.0
        try:
            ev_dt = datetime.fromisoformat(date_str)
            if ev_dt.tzinfo is not None:
                ev_dt = ev_dt.astimezone(timezone.utc).replace(tzinfo=None)
        except (ValueError, TypeError):
            return 0.0
        days = (ev_dt - datetime.now()).total_seconds() / 86400.0
        if days < 0:  # 已过去的活动不提权
            return 0.0
        # 半衰期衰减：到达半衰期时提权减半
        decay = 0.5 ** (days / self._freshness_halflife_days)
        return self._freshness_weight * decay

    # ── reasoning chain ─────────────────────────────────────────────────

    def _generate_reasoning_chain(
        self, source_nodes: List[str], target_event_id: str
    ) -> List[str]:
        best_path = None
        best_len = self._max_hops + 1
        for src in source_nodes:
            try:
                path = nx.shortest_path(
                    self._undirected, source=src, target=target_event_id
                )
                if len(path) <= self._max_hops + 1 and len(path) < best_len:
                    best_path = path
                    best_len = len(path)
            except (nx.NetworkXNoPath, nx.NodeNotFound):
                continue

        if best_path:
            return [
                self._node_label(nid) for nid in best_path
            ]
        if source_nodes:
            return [
                self._node_label(source_nodes[0]),
                "...",
                self._node_label(target_event_id),
            ]
        return ["热门推荐"]

    def _node_label(self, nid: str) -> str:
        nd = self._graph.nodes.get(nid, {})
        return nd.get("name", nid)

    # ── fallback ───────────────────────────────────────────────────────

    def _fallback_recommend(self, count: int) -> List[Recommendation]:
        event_nodes = [
            nid for nid, d in self._graph.nodes(data=True)
            if d.get("node_type") == "event"
        ]
        in_degrees = [
            (nid, self._graph.in_degree(nid))
            for nid in event_nodes
        ]
        in_degrees.sort(key=lambda x: x[1], reverse=True)
        top = in_degrees[:count]

        results = []
        for i, (nid, deg) in enumerate(top):
            nd = self._graph.nodes[nid]
            results.append(Recommendation(
                event_id=nid,
                event_title=nd.get("name", ""),
                event_type=nd.get("event_type", ""),
                score=round(1.0 / (i + 1), 4),
                reasoning_chain=["热门推荐"],
            ))
        return results


# ── demo ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from knowledge_graph.graph_builder import build_heterogeneous_graph

    G = build_heterogeneous_graph()
    recommender = PprRecommender(G)

    print("=== 推荐结果（兴趣: 人工智能, 算法 | 课程: CS4101, CS3201）===")
    results = recommender.recommend(
        user_interests=["人工智能", "算法"],
        user_courses=["CS4101", "CS3201"],
    )
    for r in results:
        print(f"  [{r.score:.4f}] {r.event_title} ({r.event_type})")
        print(f"         推理链: {' → '.join(r.reasoning_chain)}")

    print()
    print("=== 兜底结果（兴趣: 不存在的兴趣xyz）===")
    results2 = recommender.recommend(user_interests=["不存在的兴趣xyz"])
    for r in results2:
        print(f"  [{r.score:.4f}] {r.event_title} - {r.reasoning_chain}")
