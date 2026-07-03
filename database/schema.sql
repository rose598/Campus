-- 课程表
CREATE TABLE IF NOT EXISTS courses (
    code TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    credits REAL NOT NULL,
    semester TEXT NOT NULL,
    teacher TEXT NOT NULL,
    description TEXT,
    prerequisites TEXT   -- JSON 数组字符串，如 '["CS1101","MATH2001"]'
);

-- 教师表
CREATE TABLE IF NOT EXISTS teachers (
    name TEXT PRIMARY KEY,
    department TEXT NOT NULL,
    title TEXT,
    email TEXT,
    research_interests TEXT  -- JSON 数组字符串
);

-- 实验室表
CREATE TABLE IF NOT EXISTS labs (
    name TEXT PRIMARY KEY,
    director TEXT NOT NULL,
    description TEXT,
    keywords TEXT             -- JSON 数组字符串
);

-- 活动（讲座/竞赛）表
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    event_type TEXT NOT NULL,
    date TEXT,
    location TEXT,
    organizer TEXT,
    url TEXT
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
    FOREIGN KEY (doc_id) REFERENCES documents(doc_id) ON DELETE CASCADE
);

-- 向量索引表（存储序列化后的 Embedding）
CREATE TABLE IF NOT EXISTS embeddings (
    chunk_id TEXT PRIMARY KEY,
    embedding BLOB NOT NULL,      -- 使用 pickle 或 numpy 序列化
    FOREIGN KEY (chunk_id) REFERENCES chunks(chunk_id) ON DELETE CASCADE
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