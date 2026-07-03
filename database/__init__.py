"""
数据库模块
提供 SQLite 数据库连接、表结构定义和 CRUD 操作
"""

from .connection import get_connection, init_db, DB_PATH
from .schema import SCHEMA_SQL
from .crud import (
    CourseCRUD, 
    DocumentCRUD, 
    ChunkCRUD, 
    EmbeddingCRUD, 
    CacheCRUD, 
    LogCRUD
)

__all__ = [
    'get_connection',
    'init_db',
    'DB_PATH',
    'SCHEMA_SQL',
    'CourseCRUD',
    'DocumentCRUD',
    'ChunkCRUD',
    'EmbeddingCRUD',
    'CacheCRUD',
    'LogCRUD'
]
