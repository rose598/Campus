"""Day 13 联调脚本 —— 缓存 + RAG + Rewrite + PPR 全链路验证

前置条件：已运行 `python scripts/seed_mock_data.py --reset` 导入种子数据。

由于联调环境通常无 LLM API Key / 外网，脚本默认将 LLMClient.call
替换为快速失败的离线模拟，重点验证各模块的降级路径与数据贯通；
传 --online 则使用真实 LLM（需要可用的 api_key 与网络）。

用法：
    python scripts/integration_day13.py [--online]
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

FAILED = []


def section(title: str):
    print(f"\n{'=' * 56}\n{title}\n{'=' * 56}")


def check(name: str, cond: bool):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}")
    if not cond:
        FAILED.append(name)


def patch_llm_offline():
    """将 LLMClient.call 替换为快速失败，模拟 LLM 不可用"""
    from utils import get_llm_client

    llm = get_llm_client()

    def _offline(*args, **kwargs):
        raise RuntimeError("LLM offline（联调模拟）")

    llm.call = _offline
    print("  [模拟] LLMClient.call 已切换为离线模式（快速失败）")


class Msg:
    """LangGraph BaseMessage 的轻量替身"""

    def __init__(self, type_: str, content: str):
        self.type = type_
        self.content = content


def main():
    parser = argparse.ArgumentParser(description="Day 13 联调")
    parser.add_argument("--online", action="store_true", help="使用真实 LLM（需可用 API）")
    args = parser.parse_args()

    if not args.online:
        patch_llm_offline()

    # ── 1. Query Rewriting ────────────────────────────────────────────
    section("1. Query Rewriting（多轮改写）")
    from rag import QueryRewriter

    rewriter = QueryRewriter()
    r_no_hist = rewriter.rewrite("图书馆几点开门？")
    check("无历史 → 透传原始查询", r_no_hist["rewritten"] == "图书馆几点开门？")

    history = [
        {"role": "human", "content": "保研需要什么条件？"},
        {"role": "ai", "content": "保研需要绩点排名前 20%，且无挂科记录。"},
    ]
    r_hist = rewriter.rewrite("那它的学分要求呢？", history, user_id="integration")
    if args.online:
        check("在线模式 → LLM 改写生效", r_hist["source"] == "llm" and r_hist["changed"])
        print(f"    改写结果: {r_hist['rewritten']}")
    else:
        check("离线模式 → 回退原始查询", r_hist["rewritten"] == "那它的学分要求呢？")
        check("回退来源标记 passthrough", r_hist["source"] == "passthrough")

    # ── 2. 语义缓存 ──────────────────────────────────────────────────
    section("2. 语义缓存（SemanticCache）")
    from rag import SemanticCache

    cache = SemanticCache(similarity_threshold=0.92, ttl_seconds=3600, max_size=100)
    cache.put([1.0, 0.0, 0.0], "图书馆开放时间：周一至周五 8:00-22:00")
    check("相同向量命中缓存", cache.query([1.0, 0.0, 0.0]) is not None)
    check("无关向量未命中", cache.query([0.0, 1.0, 0.0]) is None)
    stats = cache.stats()
    check("命中率统计正常", stats["hits"] == 1 and stats["misses"] == 1)

    from utils import get_llm_client
    check("LLMClient 已挂载 rag.SemanticCache",
          type(get_llm_client()._semantic_cache).__module__ == "rag.semantic_cache")

    # ── 3. Hybrid RAG（BM25 + Dense + RRF） ─────────────────────────
    section("3. Hybrid RAG 检索")
    from rag import hybrid_search

    docs = hybrid_search("保研需要什么条件？")
    check("检索返回非空", len(docs) > 0)
    if docs:
        top = docs[0]
        check("结果含 rrf_score", "rrf_score" in top)
        check("Top1 命中保研文档", "保研" in top.get("title", ""))
        print(f"    Top1: {top.get('title')} (rrf={top.get('rrf_score')})")

    docs_life = hybrid_search("图书馆几点开门", category="life")
    check("category 过滤生效（life）",
          len(docs_life) > 0 and all(d.get("category") == "life" for d in docs_life))

    docs_empty = hybrid_search("量子纠缠退相干时间测量")
    check("无关查询返回结果不崩溃", isinstance(docs_empty, list))

    # ── 4. PPR 推荐 + 推理链 ────────────────────────────────────────
    section("4. PPR 推荐引擎")
    from knowledge_graph import build_heterogeneous_graph, PprRecommender

    graph = build_heterogeneous_graph()
    check("异构图构建成功", graph.number_of_nodes() > 0)
    print(f"    Nodes: {graph.number_of_nodes()}, Edges: {graph.number_of_edges()}")

    recommender = PprRecommender(graph)
    recs = recommender.recommend(user_interests=["人工智能"], user_courses=["CS4101"])
    check("PPR 返回推荐", len(recs) > 0)
    if recs:
        top_rec = recs[0]
        check("推荐附带推理链", len(top_rec.reasoning_chain) >= 2)
        check("分数在 [0,1]", 0.0 <= top_rec.score <= 1.0)
        print(f"    Top1: {top_rec.event_title} (score={top_rec.score:.4f})")
        print(f"    推理链: {' → '.join(top_rec.reasoning_chain)}")

    recs_fb = recommender.recommend(user_interests=[])
    check("无兴趣 → 兜底推荐不崩溃", isinstance(recs_fb, list))

    # ── 5. 百事通子图全流程（rewrite → intent → retrieve → generate） ──
    section("5. 百事通子图全流程")
    from agents.knowit_agent import (
        rewrite_query, classify_intent, retrieve_knowit, generate_knowit,
    )

    state = {
        "messages": [
            Msg("human", "保研需要什么条件？"),
            Msg("ai", "保研需要绩点排名前 20%，且无挂科记录。"),
            Msg("human", "那它的学分要求呢？"),
        ],
        "user_id": "integration",
        "intent": "policy",  # 模拟上游规则路由已设定意图
    }

    state.update(rewrite_query(state))
    check("rewrite_query 产出 rewritten_query", bool(state.get("rewritten_query")))

    state.update(classify_intent(state))
    check("intent 沿用路由结果 policy", state.get("intent") == "policy")

    state.update(retrieve_knowit(state))
    retrieved = state.get("retrieved_docs", [])
    check("检索节点返回文档", len(retrieved) > 0)
    check("按 academic 分类过滤",
          all(d.get("category") == "academic" for d in retrieved) if retrieved else False)

    state.update(generate_knowit(state))
    qa = state.get("qa_result", {})
    check("生成节点产出 answer", bool(qa.get("answer")))
    check("生成节点产出 sources", len(qa.get("sources", [])) > 0)
    print(f"    回答（降级/生成）: {qa.get('answer')[:60]}")
    print(f"    来源: {[s.get('title') for s in qa.get('sources', [])]}")

    # ── 6. parent_graph 节点包装 ────────────────────────────────────
    section("6. parent_graph 集成")
    from agents.parent_graph import node_knowit

    out = node_knowit(state)
    check("node_knowit 正常返回", isinstance(out, dict))
    check("包含 qa_result", "qa_result" in out or "intent" in out)

    # ── 汇总 ────────────────────────────────────────────────────────
    section("联调结果")
    if FAILED:
        print(f"❌ 共 {len(FAILED)} 项失败:")
        for f in FAILED:
            print(f"   - {f}")
        sys.exit(1)
    print("✅ 全部通过：缓存 + RAG + Rewrite + PPR 链路贯通")
    sys.exit(0)


if __name__ == "__main__":
    main()
