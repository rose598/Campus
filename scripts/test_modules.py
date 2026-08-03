# -*- coding: utf-8 -*-
"""快速测试脚本 - 验证 Day3-Day10 所有模块"""
import sys
sys.path.insert(0, ".")

def test_chunker():
    from data_pipeline.chunker import LayoutChunker
    from data_pipeline.text_cleaner import CleanedDocument
    chunker = LayoutChunker(chunk_size=200, chunk_overlap=30)
    doc = CleanedDocument(
        doc_id="DOC_AABBCCDD", title="test",
        content="第一章 总则\n\n一、适用范围\n本条例适用于全校学生。\n\n二、基本原则\n坚持公平公正公开原则。\n\n第二章 条件\n\n一、学业成绩\n成绩排名前百分之三十。",
        source_path="test.txt", file_type="txt",
    )
    chunks = chunker.chunk(doc)
    print(f"[Chunker] 分块数: {len(chunks)}")
    for c in chunks:
        print(f"  [{c['chunk_id']}] {len(c['content'])}字 | headings={c['parent_headings']}")
    assert len(chunks) > 0, "Chunker 产出为空"
    print("  [OK] Chunker test passed\n")

def test_annotator():
    from data_pipeline.metadata_annotator import MetadataAnnotator
    from data_pipeline.text_cleaner import CleanedDocument
    annotator = MetadataAnnotator(use_llm=False)
    doc = CleanedDocument(
        doc_id="DOC_AABBCCDD", title="2026年保研推免通知",
        content="各学院：根据教育部文件精神，学业成绩排名在本专业前30%。申请时间2026年9月1日至9月15日。教务处2026年8月20日",
        source_path="test.txt", file_type="txt",
    )
    result = annotator.annotate(doc)
    print(f"[Annotator] category={result.category}, tags={result.tags}, date={result.publish_date}")
    assert result.category == "academic", f"Expected 'academic', got '{result.category}'"
    print("  [OK] Annotator test passed\n")

def test_intent():
    from campus_qa.intent_classifier import IntentClassifier
    c = IntentClassifier(use_llm=False)
    tests = [
        ("保研需要什么条件？", "policy"),
        ("图书馆几点关门？", "life"),
        ("这门课的课件有吗？", "course"),
    ]
    for q, expected in tests:
        r = c.classify(q)
        print(f"  Q: {q} → {r.intent} (expected: {expected})")
        assert r.intent == expected, f"Expected '{expected}', got '{r.intent}'"
    print("  [OK] IntentClassifier test passed\n")

def test_time_ranker():
    from campus_qa.time_ranker import TimeRanker
    ranker = TimeRanker(decay_lambda=0.01)
    candidates = [
        {"chunk_id": "CHK_01", "doc_id": "DOC_01", "content": "新文档", "publish_date": "2026-07-01", "score": 0.8},
        {"chunk_id": "CHK_02", "doc_id": "DOC_02", "content": "旧文档", "publish_date": "2024-01-01", "score": 0.9},
    ]
    from datetime import date
    ranked = ranker.rank(candidates, top_k=2, reference_date=date(2026, 8, 1))
    print(f"[TimeRanker] #1: {ranked[0]['chunk_id'] if isinstance(ranked[0], dict) else ranked[0].chunk_id}")
    # 新文档应该排第一（虽然检索分低，但时间权重大）
    first_id = ranked[0].chunk_id if hasattr(ranked[0], 'chunk_id') else ranked[0]["chunk_id"]
    assert first_id == "CHK_01", f"Expected CHK_01 first, got {first_id}"
    print("  [OK] TimeRanker test passed\n")

def test_router():
    from campus_qa.category_router import _expand_query
    expanded = _expand_query("保研需要什么条件")
    print(f"[Router] 查询扩展: '保研需要什么条件' → '{expanded}'")
    assert expanded != "保研需要什么条件" or "保研" not in expanded, "扩展逻辑有问题"
    print("  [OK] CategoryRouter test passed\n")

def test_fuser():
    from campus_qa.multi_source_fuser import MultiSourceFuser
    fuser = MultiSourceFuser()
    s1 = [{"chunk_id": "A1", "doc_id": "D1", "content": "c1", "score": 0.9}]
    s2 = [{"chunk_id": "A1", "doc_id": "D1", "content": "c1", "score": 0.8}, {"chunk_id": "B1", "doc_id": "D2", "content": "c2", "score": 0.7}]
    fused = fuser.fuse([s1, s2], top_k=3, source_labels=["a", "b"])
    print(f"[Fuser] 融合结果: {len(fused)} 条")
    assert len(fused) > 0
    print("  [OK] MultiSourceFuser test passed\n")

def test_citation():
    from campus_qa.citation_formatter import CitationFormatter
    fmt = CitationFormatter()
    results = [
        {"doc_id": "DOC_01", "doc_title": "保研通知", "content": "保研条件...", "category": "academic", "publish_date": "2026-08-20", "final_score": 0.95},
    ]
    citations = fmt.format_results(results)
    print(f"[Citation] 引用数: {len(citations)}, 标题: {citations[0].title}")
    assert len(citations) == 1
    print("  [OK] CitationFormatter test passed\n")

if __name__ == "__main__":
    print("=" * 50)
    print("GraphCampus Day3-Day10 模块测试")
    print("=" * 50 + "\n")

    test_chunker()
    test_annotator()
    test_intent()
    test_time_ranker()
    test_router()
    test_fuser()
    test_citation()

    print("=" * 50)
    print("ALL TESTS PASSED!")
    print("=" * 50)
