"""种子数据导入脚本 —— 将 data/ 下的 mock JSON 导入 SQLite

与 import_data.py（原始文件全流程管道）不同，本脚本只负责
结构化 mock 数据的快速入库，用于联调与演示：

- mock_courses.json   → courses 表
- mock_events.json    → events 表
- mock_documents.json → documents + chunks 表（简单分块）

用法：
    python scripts/seed_mock_data.py [--reset]

--reset 会先清空上述表再导入（默认增量跳过已存在记录）。
"""
import argparse
import json
import sys
from pathlib import Path

# 保证从项目根目录可导入各包
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from utils.config_loader import get
from database.connection import get_connection, init_db


def _load_json(path: Path) -> list:
    if not path.exists():
        print(f"  [skip] {path.name} 不存在")
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _chunk_text(text: str, chunk_size: int, overlap: int) -> list:
    """按段落优先、长度兜底的策略分块"""
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]

    chunks = []
    buf = ""
    for p in paragraphs:
        if len(buf) + len(p) + 1 <= chunk_size:
            buf = f"{buf}\n{p}" if buf else p
        else:
            if buf:
                chunks.append(buf)
            # 单段超长时硬切
            while len(p) > chunk_size:
                chunks.append(p[:chunk_size])
                p = p[chunk_size - overlap:]
            buf = p
    if buf:
        chunks.append(buf)
    return chunks


def reset_tables() -> None:
    conn = get_connection()
    try:
        for t in ("courses", "events", "documents", "chunks"):
            conn.execute(f"DELETE FROM {t}")
        conn.commit()
        print("[reset] 已清空 courses / events / documents / chunks")
    finally:
        conn.close()


def import_courses(data_dir: Path) -> int:
    from database.crud import CourseCRUD

    courses = _load_json(data_dir / "mock_courses.json")
    count = 0
    for c in courses:
        ok = CourseCRUD.create(
            code=c["code"],
            name=c["name"],
            credits=c["credits"],
            semester=c["semester"],
            teacher=c["teacher"],
            description=c.get("description"),
            prerequisites=c.get("prerequisites", []),
        )
        count += 1 if ok else 0
    print(f"[courses] 导入 {count}/{len(courses)} 条")
    return count


def import_events(data_dir: Path) -> int:
    events = _load_json(data_dir / "mock_events.json")
    conn = get_connection()
    count = 0
    try:
        for ev in events:
            cur = conn.execute(
                "SELECT COUNT(*) FROM events WHERE title = ?", (ev["title"],)
            )
            if cur.fetchone()[0] > 0:
                continue
            conn.execute(
                """INSERT INTO events (title, event_type, date, location, organizer, url)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    ev["title"],
                    ev["event_type"],
                    ev.get("date"),
                    ev.get("location"),
                    ev.get("organizer"),
                    ev.get("url"),
                ),
            )
            count += 1
        conn.commit()
    finally:
        conn.close()
    print(f"[events] 导入 {count}/{len(events)} 条")
    return count


def import_documents(data_dir: Path) -> int:
    from database.crud import DocumentCRUD, ChunkCRUD

    documents = _load_json(data_dir / "mock_documents.json")
    chunk_size = int(get("rag.chunk_size", 512))
    overlap = int(get("rag.chunk_overlap", 50))

    doc_count = 0
    chunk_count = 0
    for doc in documents:
        ok = DocumentCRUD.create(
            doc_id=doc["doc_id"],
            category=doc["category"],
            title=doc["title"],
            content=doc["content"],
            source_url=doc.get("source_url"),
            publish_date=doc.get("publish_date"),
            tags=doc.get("tags", []),
        )
        if not ok:
            continue
        doc_count += 1

        chunks = _chunk_text(doc["content"], chunk_size, overlap)
        for i, text in enumerate(chunks):
            chunk_id = f"{doc['doc_id']}#c{i}"
            if ChunkCRUD.create(
                chunk_id=chunk_id,
                doc_id=doc["doc_id"],
                content=text,
                position=i,
            ):
                chunk_count += 1

    print(f"[documents] 导入 {doc_count}/{len(documents)} 篇，共 {chunk_count} 个分块")
    return doc_count


def main():
    parser = argparse.ArgumentParser(description="GraphCampus 种子数据导入")
    parser.add_argument("--reset", action="store_true", help="先清空相关表再导入")
    args = parser.parse_args()

    data_dir = ROOT / "data"

    # 确保数据库表存在（增量模式同样适用全新环境）
    init_db()

    if args.reset:
        reset_tables()

    print("== 开始导入 ==")
    import_courses(data_dir)
    import_events(data_dir)
    import_documents(data_dir)
    print("== 导入完成 ==")


if __name__ == "__main__":
    main()
