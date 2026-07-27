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
                pvec[course_nid] = pvec.get(course_nid, 0) + 1.0
                if course_nid not in source_nodes:
                    source_nodes.append(course_nid)

        if not pvec:
            return None, []

        return pvec, source_nodes

    # ── PPR run ────────────────────────────────────────────────────────

    def _run_ppr(self, personalization: dict) -> dict:
        return nx.pagerank(
            self._undirected,
            alpha=self._alpha,
            personalization=personalization,
            max_iter=self._max_iter,
            tol=self._tol,
        )

    # ── event extraction ───────────────────────────────────────────────

    def _extract_event_recommendations(
        self, scores: dict, top_k: int
    ) -> List[Recommendation]:
        event_scores = []
        for nid, score in scores.items():
            if self._graph.nodes[nid].get("node_type") != "event":
                continue
            event_scores.append((nid, score))

        event_scores.sort(key=lambda x: x[1], reverse=True)
        event_scores = event_scores[:top_k]

        results = []
        for nid, score in event_scores:
            nd = self._graph.nodes[nid]
            results.append(Recommendation(
                event_id=nid,
                event_title=nd.get("name", ""),
                event_type=nd.get("event_type", ""),
                score=round(float(score), 6),
            ))
        return results

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
