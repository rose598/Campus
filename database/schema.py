import sqlite3
import os
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "graphcampus.db"

SCHEMA_SQL = """
-- 课程表
CREATE TABLE IF NOT EXISTS courses (
    code TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    credits REAL NOT NULL,
    semester TEXT NOT NULL,
    teacher TEXT NOT NULL,
    description TEXT,
    prerequisites TEXT,  -- JSON 数组字符串，如 '["CS1101","MATH2001"]'
    created_at REAL DEFAULT (strftime('%s','now')),
    updated_at REAL DEFAULT (strftime('%s','now'))
);

-- 教师表
CREATE TABLE IF NOT EXISTS teachers (
    name TEXT PRIMARY KEY,
    department TEXT NOT NULL,
    title TEXT,
    email TEXT,
    research_interests TEXT,  -- JSON 数组字符串
    created_at REAL DEFAULT (strftime('%s','now')),
    updated_at REAL DEFAULT (strftime('%s','now'))
);

-- 实验室表
CREATE TABLE IF NOT EXISTS labs (
    name TEXT PRIMARY KEY,
    director TEXT NOT NULL,
    description TEXT,
    keywords TEXT,             -- JSON 数组字符串
    created_at REAL DEFAULT (strftime('%s','now')),
    updated_at REAL DEFAULT (strftime('%s','now'))
);

-- 活动（讲座/竞赛）表
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    event_type TEXT NOT NULL,
    date TEXT,
    location TEXT,
    organizer TEXT,
    url TEXT,
    created_at REAL DEFAULT (strftime('%s','now'))
);

-- 校园非结构化文档主表
CREATE TABLE IF NOT EXISTS documents (
    doc_id TEXT PRIMARY KEY,
    category TEXT NOT NULL,       -- academic / life / course
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    source_url TEXT,
    publish_date TEXT,
    expiry_date TEXT,
    tags TEXT,                    -- JSON 数组字符串
    confidence REAL DEFAULT 1.0
);

-- 文档分块表
CREATE TABLE IF NOT EXISTS chunks (
    chunk_id TEXT PRIMARY KEY,
    doc_id TEXT NOT NULL,
    content TEXT NOT NULL,
    parent_headings TEXT,         -- JSON 数组，如 '["教务处通知","选课通知"]'
    position INTEGER NOT NULL,
    FOREIGN KEY (doc_id) REFERENCES documents(doc_id)
);

-- 文档索引
CREATE INDEX IF NOT EXISTS idx_documents_category ON documents(category);
CREATE INDEX IF NOT EXISTS idx_documents_publish_date ON documents(publish_date);

-- 向量索引表（存储序列化后的 Embedding）
CREATE TABLE IF NOT EXISTS embeddings (
    chunk_id TEXT PRIMARY KEY,
    embedding BLOB NOT NULL,      -- 使用 pickle 或 numpy 序列化
    FOREIGN KEY (chunk_id) REFERENCES chunks(chunk_id)
);

-- 语义缓存表
CREATE TABLE IF NOT EXISTS cache (
    key_hash TEXT PRIMARY KEY,    -- query embedding 的哈希
    value TEXT NOT NULL,          -- 缓存的回答 JSON
    created_at REAL NOT NULL      -- Unix timestamp
);

-- 结构化日志表
CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trace_id TEXT NOT NULL,
    user_id TEXT,
    node TEXT,                    -- LangGraph 节点名称
    level TEXT,
    message TEXT,
    detail TEXT,                  -- JSON 额外信息
    timestamp REAL NOT NULL
);

-- 日志索引
CREATE INDEX IF NOT EXISTS idx_logs_trace_id ON logs(trace_id);
CREATE INDEX IF NOT EXISTS idx_logs_timestamp ON logs(timestamp);
"""


def get_connection(db_path: str = None) -> sqlite3.Connection:
    """获取数据库连接，启用 WAL 模式"""
    path = db_path or str(DB_PATH)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: str = None) -> None:
    """初始化数据库，创建所有表"""
    conn = get_connection(db_path)
    try:
        conn.executescript(SCHEMA_SQL)
        conn.commit()
        print(f"数据库初始化完成: {db_path or DB_PATH}")
    finally:
        conn.close()


if __name__ == "__main__":
    init_db()
