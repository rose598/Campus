"""
数据库连接管理模块
提供 SQLite WAL 模式连接和数据库初始化功能
"""

import sqlite3
import os
from pathlib import Path

# 数据库文件路径
DB_PATH = Path(__file__).parent.parent / "data" / "graphcampus.db"


def get_connection(db_path: str = None) -> sqlite3.Connection:
    """
    获取数据库连接，启用 WAL 模式和外键约束
    
    Args:
        db_path: 数据库文件路径，默认为 data/graphcampus.db
        
    Returns:
        sqlite3.Connection: 配置好的数据库连接
    """
    path = db_path or str(DB_PATH)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: str = None) -> None:
    """
    初始化数据库，创建所有表
    
    Args:
        db_path: 数据库文件路径，默认为 data/graphcampus.db
    """
    from .schema import SCHEMA_SQL
    
    conn = get_connection(db_path)
    try:
        conn.executescript(SCHEMA_SQL)
        conn.commit()
        print(f"数据库初始化完成: {db_path or DB_PATH}")
    finally:
        conn.close()


def get_db_path() -> Path:
    """获取数据库文件路径"""
    return DB_PATH


if __name__ == "__main__":
    init_db()
