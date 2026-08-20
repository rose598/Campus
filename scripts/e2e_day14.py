"""Day 14 全链路验证 —— 编译后的 LangGraph 父图端到端跑通

验证 router → Fan-out(intel/knowit/buddy 并行) → aggregator 全流程，
覆盖三类意图路由 + 兜底场景。默认离线模式（LLM 快速失败）。

前置条件：已运行 `python scripts/seed_mock_data.py --reset`

用法：
    python scripts/e2e_day14.py [--online]
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
    from utils import get_llm_client

    llm = get_llm_client()

    def _offline(*args, **kwargs):
        raise RuntimeError("LLM offline（E2E 模拟）")

    llm.call = _offline
    print("  [模拟] LLMClient.call 离线模式")


def main():
    parser = argparse.ArgumentParser(description="Day 14 全链路验证")
    parser.add_argument("--online", action="store_true")
    args = parser.parse_args()

    if not args.online:
        patch_llm_offline()

    section("0. 父图编译")
    from agents.parent_graph import get_parent_graph

    pg = get_parent_graph()
    check("父图编译成功", pg.graph is not None)

    # ── 场景 1: 活动推荐（activity_push 路由） ─────────────────────
    section("1. 场景：活动推荐")
    out1 = pg.run(
        user_query="最近有什么人工智能相关的活动推荐吗？",
        user_id="e2e_user",
        user_progress={"interests": ["人工智能", "深度学习"]},
    )
    check("intent == activity_push", out1["intent"] == "activity_push")
    recs = (out1.get("intel_result") or {}).get("recommendations", [])
    check("情报官返回推荐", len(recs) > 0)
    check("final_response 含推荐板块", "情报官" in out1["final_response"])
    if recs:
        chain = recs[0].get("reasoning_chain", [])
        check("推荐含推理链", len(chain) >= 2)
        print(f"    Top1: {recs[0]['event_title']} | 推理链: {' → '.join(chain)}")

    # ── 场景 2: 校园问答（campus_qa 路由） ─────────────────────────
    section("2. 场景：校园问答")
    out2 = pg.run(
        user_query="保研需要什么条件？",
        user_id="e2e_user",
    )
    check("intent == campus_qa", out2["intent"] == "campus_qa")
    qa = out2.get("qa_result") or {}
    check("百事通返回 answer", bool(qa.get("answer")))
    check("百事通返回 sources", len(qa.get("sources", [])) > 0)
    check("final_response 含问答板块", "百事通" in out2["final_response"])
    print(f"    回答: {qa.get('answer')[:50]}")
    print(f"    来源: {[s.get('title') for s in qa.get('sources', [])][:2]}")

    # ── 场景 3: 课程总结（course_summary 路由） ────────────────────
    section("3. 场景：课程总结（学伴全流程）")
    out3 = pg.run(
        user_query="帮我总结一下数据结构这门课的大纲",
        user_id="e2e_user",
        courses={"CS2101": object()},
    )
    check("intent == course_summary", out3["intent"] == "course_summary")
    buddy = out3.get("buddy_result") or {}
    check("学伴完成检索/总结流程",
          buddy.get("status") in ("full", "retrieved", "placeholder"))
    check("学伴识别到课程", "CS2101" in buddy.get("courses_available", []))
    check("学伴返回总结文本", bool(buddy.get("summary")))
    check("final_response 含学伴板块", "学伴" in out3["final_response"])
    print(f"    总结: {(buddy.get('summary') or '')[:60]}")

    # ── 场景 4: 无法路由（all 兜底） ───────────────────────────────
    section("4. 场景：兜底（无明确意图）")
    out4 = pg.run(
        user_query="你好",
        user_id="e2e_user",
    )
    # router 给出 "all" 后，百事通 LLM 精分类会细化为 general（离线时为降级结果）
    check("intent 为 all 或 QA 分类结果",
          out4["intent"] in ("all", "general", "policy", "life", "course"))
    check("final_response 非空", bool(out4["final_response"]))
    check("兜底回复包含引导或内容板块",
          any(k in out4["final_response"] for k in ("暂无可用信息", "情报官", "百事通", "学伴")))
    check("trace_id 生成", bool(out4.get("trace_id")))

    # ── 场景 5: 多轮改写贯通（rewritten_query 写入 state） ─────────
    section("5. 场景：多轮对话（改写节点在图中生效）")
    from agents.parent_graph import node_knowit

    class Msg:
        def __init__(self, type_, content):
            self.type = type_
            self.content = content

    state = {
        "messages": [
            Msg("human", "图书馆几点开门？"),
            Msg("ai", "周一至周五 8:00-22:00。"),
            Msg("human", "那周末呢？"),
        ],
        "user_id": "e2e_user",
    }
    updates = node_knowit(state)
    check("rewritten_query 已产出", "rewritten_query" in updates)
    check("qa_result 已产出", "qa_result" in updates)
    print(f"    改写结果: {updates.get('rewritten_query')}")

    # ── 汇总 ────────────────────────────────────────────────────────
    section("E2E 结果")
    if FAILED:
        print(f"❌ 共 {len(FAILED)} 项失败:")
        for f in FAILED:
            print(f"   - {f}")
        sys.exit(1)
    print("✅ 全链路跑通：router → 三子图 Fan-out → aggregator")
    sys.exit(0)


if __name__ == "__main__":
    main()
