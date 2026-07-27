import json
import re
from pathlib import Path
from typing import Optional

import networkx as nx


def _root() -> Path:
    return Path(__file__).resolve().parent.parent


def _default_courses_path() -> Path:
    return _root() / "data" / "mock_courses.json"


def _default_events_path() -> Path:
    return _root() / "data" / "mock_events.json"


def _load_json(path: Path) -> list:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _extract_keywords(text: str) -> list[str]:
    """从中文文本中提取关键词（Day 5 简化：按标点和空白分词，过滤单字）"""
    parts = re.split(r'[、，,。；;（）()（\s/]+', text)
    keywords = []
    for p in parts:
        p = p.strip()
        # 保留长度 ≥2 的中文/英文/混合词，过滤纯标点和单字
        if len(p) >= 2 and not re.match(r'^[\-\.，,。；;]+$', p):
            keywords.append(p)
    return keywords


def _make_node_id(node_type: str, name: str) -> str:
    return f"{node_type}:{name}"


def build_heterogeneous_graph(
    courses_path: Optional[Path] = None,
    events_path: Optional[Path] = None,
) -> nx.DiGraph:
    G = nx.DiGraph()

    cp = courses_path or _default_courses_path()
    ep = events_path or _default_events_path()
    courses = _load_json(cp) if cp.exists() else []
    events = _load_json(ep) if ep.exists() else []

    teacher_names: set[str] = set()
    course_keywords: set[str] = set()

    # ── 1. course 节点 ──
    for c in courses:
        nid = _make_node_id("course", c["code"])
        G.add_node(nid, node_type="course", name=c["name"], code=c["code"])
        teacher_names.add(c["teacher"])
        for kw in _extract_keywords(c["name"]):
            course_keywords.add(kw)

    # ── 2. prerequisite 边（先修课 → 后续课） ──
    for c in courses:
        target_nid = _make_node_id("course", c["code"])
        for prereq_code in c.get("prerequisites", []):
            source_nid = _make_node_id("course", prereq_code)
            if source_nid not in G:
                continue
            G.add_edge(source_nid, target_nid, edge_type="prerequisite")

    # ── 3. teacher 节点 + taught_by 边 ──
    for name in teacher_names:
        tid = _make_node_id("teacher", name)
        G.add_node(tid, node_type="teacher", name=name)

    for c in courses:
        course_nid = _make_node_id("course", c["code"])
        teacher_nid = _make_node_id("teacher", c["teacher"])
        G.add_edge(course_nid, teacher_nid, edge_type="taught_by")

    # ── 4. event 节点 ──
    event_interest_keywords: set[str] = set()
    for ev in events:
        eid = _make_node_id("event", ev["title"])
        G.add_node(eid, node_type="event", name=ev["title"], event_type=ev["event_type"])
        for tag in ev.get("tags", []):
            event_interest_keywords.add(tag)

    # ── 5. event → course（targets 边） ──
    for ev in events:
        eid = _make_node_id("event", ev["title"])
        for rc in ev.get("related_courses", []):
            course_nid = _make_node_id("course", rc)
            if course_nid in G:
                G.add_edge(eid, course_nid, edge_type="targets")

    # ── 6. interest 节点 ──
    interest_keywords = course_keywords | event_interest_keywords
    for kw in interest_keywords:
        iid = _make_node_id("interest", kw)
        G.add_node(iid, node_type="interest", name=kw)

    # ── 7. teacher → interest（researches 边） ──
    teacher_courses: dict[str, list[str]] = {}
    for c in courses:
        teacher_courses.setdefault(c["teacher"], []).append(c["code"])
    for teacher_name, course_codes in teacher_courses.items():
        teacher_nid = _make_node_id("teacher", teacher_name)
        # 收集该教师所有课程的关键词
        teacher_kws: set[str] = set()
        for cc in course_codes:
            for c in courses:
                if c["code"] == cc:
                    teacher_kws.update(_extract_keywords(c["name"]))
                    break
        for kw in teacher_kws:
            iid = _make_node_id("interest", kw)
            if iid in G:
                G.add_edge(teacher_nid, iid, edge_type="researches")

    # ── 8. event → interest（tagged 边） ──
    for ev in events:
        eid = _make_node_id("event", ev["title"])
        for tag in ev.get("tags", []):
            iid = _make_node_id("interest", tag)
            if iid in G:
                G.add_edge(eid, iid, edge_type="tagged")

    # ── 9. course → interest（covers 边） ──
    for c in courses:
        course_nid = _make_node_id("course", c["code"])
        for kw in _extract_keywords(c["name"]):
            iid = _make_node_id("interest", kw)
            if iid in G:
                G.add_edge(course_nid, iid, edge_type="covers")

    return G


if __name__ == "__main__":
    G = build_heterogeneous_graph()
    print(f"Nodes: {G.number_of_nodes()}, Edges: {G.number_of_edges()}")
    for ntype in ["course", "event", "teacher", "interest"]:
        count = sum(1 for _, d in G.nodes(data=True) if d.get("node_type") == ntype)
        print(f"  {ntype}: {count}")
