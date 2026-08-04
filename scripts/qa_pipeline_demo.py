# -*- coding: utf-8 -*-
"""
qa_pipeline_demo.py — 百事通（校园问答）全流程联调脚本

完整管道:
  1. 意图分类 (IntentClassifier)
  2. 分类路由 (CategoryRouter)
  3. 时间排序 (TimeRanker)
  4. 多源融合 (MultiSourceFuser)
  5. 引用格式化 (CitationFormatter)

使用方式:
  python scripts/qa_pipeline_demo.py --query "保研需要什么条件？"
  python scripts/qa_pipeline_demo.py --query "图书馆几点关门？"
  python scripts/qa_pipeline_demo.py --batch   # 批量测试
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from campus_qa.intent_classifier import IntentClassifier
from campus_qa.category_router import CategoryRouter
from campus_qa.time_ranker import TimeRanker
from campus_qa.multi_source_fuser import MultiSourceFuser
from campus_qa.citation_formatter import CitationFormatter

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
#  问答管道
# ─────────────────────────────────────────────

class QAPipeline:
    """
    校园问答全流程管道。

    流程: query → 意图分类 → 分类路由 → 时间排序 → 多源融合 → 引用格式化
    """

    def __init__(self, index_dir: str = "data/processed/indexes", use_llm: bool = False):
        self._classifier = IntentClassifier(use_llm=use_llm)
        self._router = CategoryRouter(expand_query=True, expand_routes=True)
        self._ranker = TimeRanker.from_config()
        self._fuser = MultiSourceFuser.from_config()
        self._formatter = CitationFormatter()
        self._index_dir = index_dir
        self._loaded = False

    def load_indexes(self) -> bool:
        """加载索引"""
        index_path = Path(self._index_dir)
        if not index_path.exists():
            logger.warning("[QAPipeline] 索引目录不存在: %s，请先运行 import_data.py", self._index_dir)
            return False

        try:
            from data_pipeline.index_builder import IndexBuilder
            builder = IndexBuilder.load(index_path)
            self._router.set_index_builder(builder)
            self._loaded = True
            logger.info("[QAPipeline] 索引加载成功")
            return True
        except Exception as e:
            logger.error("[QAPipeline] 索引加载失败: %s", e)
            return False

    def answer(self, query: str, verbose: bool = False) -> dict:
        """
        对用户问题执行完整 QA 管道。

        Args:
            query: 用户问题
            verbose: 是否输出中间步骤

        Returns:
            包含所有中间结果的字典
        """
        start_time = time.time()
        trace = {}

        # 1. 意图分类
        t0 = time.time()
        intent_result = self._classifier.classify(query)
        trace["intent"] = {
            "intent": intent_result.intent,
            "sub_intent": intent_result.sub_intent,
            "confidence": intent_result.confidence,
            "method": intent_result.method,
            "latency_ms": int((time.time() - t0) * 1000),
        }
        if verbose:
            print(f"  [1] 意图分类: {intent_result.intent} ({intent_result.confidence:.2f})")

        # 2. 分类路由 + 检索
        t0 = time.time()
        if self._loaded:
            route_result = self._router.route_with_fallback(
                query, intent=intent_result.intent, use_dense=False
            )
        else:
            # 无索引时使用模拟数据
            route_result = self._mock_route(query, intent_result.intent)
        trace["route"] = {
            "route_to": route_result.route_to,
            "candidates_count": len(route_result.candidates),
            "strategy": route_result.strategy,
            "latency_ms": int((time.time() - t0) * 1000),
        }
        if verbose:
            print(f"  [2] 路由: {route_result.route_to} | 候选={len(route_result.candidates)}")

        # 3. 时间排序
        t0 = time.time()
        if route_result.candidates:
            ranked = self._ranker.rank(route_result.candidates, top_k=10)
        else:
            ranked = []
        trace["rank"] = {
            "input_count": len(route_result.candidates),
            "output_count": len(ranked),
            "latency_ms": int((time.time() - t0) * 1000),
        }
        if verbose:
            print(f"  [3] 时间排序: {len(ranked)} 结果")

        # 4. 多源融合
        t0 = time.time()
        fused = self._fuser.fuse_ranked_results(ranked, top_k=5)
        trace["fuse"] = {
            "fused_count": len(fused),
            "latency_ms": int((time.time() - t0) * 1000),
        }
        if verbose:
            print(f"  [4] 多源融合: {len(fused)} 结果")

        # 5. 引用格式化
        t0 = time.time()
        # 模拟 LLM 生成回答
        answer = self._generate_answer(query, fused, intent_result)
        response = self._formatter.format_with_answer(
            answer=answer,
            results=fused,
            query=query,
            intent=intent_result.intent,
        )
        trace["format"] = {
            "citations_count": len(response.citations),
            "latency_ms": int((time.time() - t0) * 1000),
        }
        if verbose:
            print(f"  [5] 引用格式化: {len(response.citations)} 条引用")

        # 总耗时
        trace["total_latency_ms"] = int((time.time() - start_time) * 1000)
        trace["query"] = query
        trace["answer"] = answer
        trace["citations"] = [c.model_dump() for c in response.citations]

        return trace

    def _generate_answer(self, query: str, fused_results, intent_result) -> str:
        """
        生成回答（模拟 LLM，实际项目中调用 LLMClient）。
        """
        if not fused_results:
            return "暂未收录该问题，换个问法试试。"

        # 简单模板回答
        top_result = fused_results[0]
        content_preview = top_result.content[:200] if hasattr(top_result, "content") else top_result.get("content", "")[:200]
        doc_title = top_result.doc_title if hasattr(top_result, "doc_title") else top_result.get("doc_title", "未知来源")

        return (
            f"根据《{doc_title}》的相关信息：\n\n"
            f"{content_preview}\n\n"
            f"[1]"
        )

    @staticmethod
    def _mock_route(query: str, intent: str):
        """无索引时的模拟路由"""
        from campus_qa.category_router import RouteResult
        mock_candidates = [
            {
                "chunk_id": f"CHK_MOCK_{i}",
                "doc_id": f"DOC_MOCK_{i:04d}",
                "content": f"模拟内容 {i}: 关于 {query} 的相关信息...",
                "doc_title": f"模拟文档 {i}",
                "category": intent,
                "publish_date": "2026-07-01",
                "score": 0.9 - i * 0.1,
            }
            for i in range(5)
        ]
        return RouteResult(
            query=query,
            intent=intent,
            route_to=[intent],
            candidates=mock_candidates,
            strategy="mock",
        )


# ─────────────────────────────────────────────
#  批量测试
# ─────────────────────────────────────────────

_BATCH_QUERIES = [
    ("保研需要什么条件？", "policy"),
    ("转专业的流程是怎样的？", "policy"),
    ("选课系统什么时候开放？", "policy"),
    ("奖学金怎么申请？", "policy"),
    ("图书馆几点关门？", "life"),
    ("宿舍可以换吗？", "life"),
    ("校园网密码忘了怎么办？", "life"),
    ("食堂午餐时间？", "life"),
    ("高数期末复习资料有吗？", "course"),
    ("这门课的先修要求是什么？", "course"),
    ("C语言课件在哪里下载？", "course"),
]


def run_batch_test(pipeline: QAPipeline):
    """批量测试"""
    print("=" * 60)
    print("百事通全流程批量测试")
    print("=" * 60)

    results = []
    for query, expected_intent in _BATCH_QUERIES:
        print(f"\nQ: {query}")
        result = pipeline.answer(query, verbose=True)
        actual_intent = result["intent"]["intent"]
        status = "OK" if actual_intent == expected_intent else "MISMATCH"
        results.append({
            "query": query,
            "expected": expected_intent,
            "actual": actual_intent,
            "status": status,
            "total_ms": result["total_latency_ms"],
        })
        print(f"  [{status}] intent={actual_intent} (expected={expected_intent}) | {result['total_latency_ms']}ms")

    print("\n" + "=" * 60)
    print("测试汇总:")
    ok_count = sum(1 for r in results if r["status"] == "OK")
    total_ms = sum(r["total_ms"] for r in results)
    print(f"  通过: {ok_count}/{len(results)}")
    print(f"  平均延迟: {total_ms / len(results):.1f}ms")
    print("=" * 60)

    return results


# ─────────────────────────────────────────────
#  命令行入口
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="校园问答全流程联调")
    parser.add_argument("--query", type=str, help="单个查询")
    parser.add_argument("--batch", action="store_true", help="批量测试")
    parser.add_argument("--index-dir", type=str, default="data/processed/indexes", help="索引目录")
    parser.add_argument("--verbose", action="store_true", help="显示详细输出")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")

    pipeline = QAPipeline(index_dir=args.index_dir, use_llm=False)
    pipeline.load_indexes()

    if args.batch:
        run_batch_test(pipeline)
    elif args.query:
        result = pipeline.answer(args.query, verbose=True)
        print("\n" + "=" * 60)
        print(f"Q: {result['query']}")
        print(f"A: {result['answer']}")
        print(f"\n引用:")
        for c in result["citations"]:
            print(f"  [{c['index']}] {c['title']} ({c.get('category', '')})")
        print(f"\n总延迟: {result['total_latency_ms']}ms")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
