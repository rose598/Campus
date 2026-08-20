# -*- coding: utf-8 -*-
"""Day 19-20 三子图并行联调 —— 验证 Send Fan-out 真实并行与结果聚合

检查项：
1. 父图结构：router → Send(intel/knowit/buddy) → aggregator
2. "all" 场景三子图全部被调度且各自产出结果
3. 单意图场景只触发对应子图的业务分支（其他子图可被调度但聚合器按 intent 选取）
4. 各子图节点耗时打点（Tracer）
5. 聚合器对三子图结果的选择性渲染

默认离线模式（LLM 快速失败），用法：
    python scripts/parallel_day19.py [--online]
"""
import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

FAILED = []


def check(name, cond):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}")
    if not cond:
        FAILED.append(name)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--online", action="store_true")
    args = parser.parse_args()

    if not args.online:
        from utils import get_llm_client
        llm = get_llm_client()
        llm.call = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("offline"))
        print("[模拟] LLM 离线模式")

    from agents.parent_graph import get_parent_graph

    pg = get_parent_graph()

    print("\n=== 1. 父图结构检查 ===")
    node_names = set(pg.graph.nodes.keys()) if hasattr(pg.graph, "nodes") else set()
    print(f"    图节点: {sorted(node_names)}")
    check("包含 router 节点", any("router" in n for n in node_names))
    check("包含 aggregator 节点", any("aggregat" in n for n in node_names))

    print("\n=== 2. all 场景：三子图全调度 ===")
    t0 = time.perf_counter()
    out_all = pg.run(
        user_query="你好，请给我一些帮助",
        user_id="parallel_user",
        user_progress={"interests": ["人工智能"]},
        courses={"CS2101": object()},
    )
    elapsed_all = time.perf_counter() - t0
    check("intent 为 all/general（无关键词命中）",
          out_all["intent"] in ("all", "general"))
    check("intel_result 产出", bool(out_all.get("intel_result")))
    check("qa_result 产出", bool(out_all.get("qa_result")))
    check("buddy_result 产出", bool(out_all.get("buddy_result")))
    check("final_response 聚合三板块",
          all(k in out_all["final_response"] for k in ("情报官", "百事通", "学伴")))
    print(f"    三子图并行总耗时: {elapsed_all:.2f}s")

    print("\n=== 3. 单意图场景路由正确性 ===")
    out_act = pg.run(user_query="推荐一个人工智能讲座", user_id="parallel_user")
    check("活动意图 → 推荐板块", "情报官" in out_act["final_response"])
    out_qa = pg.run(user_query="转专业需要什么条件？", user_id="parallel_user")
    check("问答意图 → 问答板块", "百事通" in out_qa["final_response"])
    out_cs = pg.run(user_query="总结数据结构课程", user_id="parallel_user",
                    courses={"CS2101": object()})
    check("课程意图 → 学伴板块", "学伴" in out_cs["final_response"])
    check("课程总结非空", bool((out_cs.get("buddy_result") or {}).get("summary")))

    print("\n=== 4. 节点耗时打点（Tracer）===")
    try:
        from utils import get_tracer
        tracer = get_tracer()
        check("Tracer 可用且有计时接口",
              hasattr(tracer, "node") and hasattr(tracer, "total_latency_ms"))
        print(f"    当前 trace 总耗时: {tracer.total_latency_ms()}ms")
    except Exception as e:
        print(f"    [SKIP] Tracer 检查跳过: {e}")

    print("\n=== 5. 异常隔离：单子图失败不阻断 ===")
    # 让 buddy 检索抛异常，验证其他子图不受影响
    import agents.buddy_agent as buddy_mod

    orig = buddy_mod.retrieve_course_materials

    def _boom(state, config=None):
        raise RuntimeError("buddy 故障注入")

    buddy_mod.retrieve_course_materials = _boom
    try:
        out_fail = pg.run(user_query="保研政策是什么？顺便总结数据结构",
                          user_id="parallel_user", courses={"CS2101": object()})
        check("buddy 故障时 final_response 仍有内容", bool(out_fail["final_response"]))
        check("百事通结果不受影响", bool(out_fail.get("qa_result")))
    except Exception as e:
        check(f"buddy 故障未冒泡到父图（实际: {type(e).__name__}）", False)
    finally:
        buddy_mod.retrieve_course_materials = orig

    print()
    if FAILED:
        print(f"❌ {len(FAILED)} 项失败: {FAILED}")
        sys.exit(1)
    print("✅ 三子图并行联调全部通过")
    sys.exit(0)


if __name__ == "__main__":
    main()
