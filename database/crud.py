"""
数据库 CRUD 操作封装
提供课程和文档的增删改查功能
"""

import json
import sqlite3
from typing import List, Optional, Dict, Any
from datetime import datetime

from .connection import get_connection


class CourseCRUD:
    """课程表 CRUD 操作"""
    
    @staticmethod
    def create(code: str, name: str, credits: float, semester: str, 
               teacher: str, description: str = None, 
               prerequisites: List[str] = None) -> bool:
        """
        创建课程记录
        
        Args:
            code: 课程代码
            name: 课程名称
            credits: 学分
            semester: 开课学期
            teacher: 授课教师
            description: 课程简介
            prerequisites: 先修课程代码列表
            
        Returns:
            bool: 是否创建成功
        """
        conn = get_connection()
        try:
            conn.execute("""
                INSERT INTO courses (code, name, credits, semester, teacher, description, prerequisites)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (code, name, credits, semester, teacher, description, 
                  json.dumps(prerequisites or [], ensure_ascii=False)))
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
        finally:
            conn.close()
    
    @staticmethod
    def get(code: str) -> Optional[Dict[str, Any]]:
        """
        获取课程信息
        
        Args:
            code: 课程代码
            
        Returns:
            课程信息字典，不存在返回 None
        """
        conn = get_connection()
        try:
            cursor = conn.execute("SELECT * FROM courses WHERE code = ?", (code,))
            row = cursor.fetchone()
            if row:
                result = dict(row)
                # 解析 JSON 字段
                if result.get('prerequisites'):
                    try:
                        result['prerequisites'] = json.loads(result['prerequisites'])
                    except (json.JSONDecodeError, TypeError):
                        result['prerequisites'] = []
                return result
            return None
        finally:
            conn.close()
    
    @staticmethod
    def get_all() -> List[Dict[str, Any]]:
        """获取所有课程"""
        conn = get_connection()
        try:
            cursor = conn.execute("SELECT * FROM courses ORDER BY code")
            results = []
            for row in cursor.fetchall():
                result = dict(row)
                # 解析 JSON 字段
                if result.get('prerequisites'):
                    try:
                        result['prerequisites'] = json.loads(result['prerequisites'])
                    except (json.JSONDecodeError, TypeError):
                        result['prerequisites'] = []
                results.append(result)
            return results
        finally:
            conn.close()
    
    @staticmethod
    def update(code: str, **kwargs) -> bool:
        """
        更新课程信息
        
        Args:
            code: 课程代码
            **kwargs: 要更新的字段
            
        Returns:
            bool: 是否更新成功
        """
        if not kwargs:
            return False
        
        conn = get_connection()
        try:
            # 处理 prerequisites 字段
            if 'prerequisites' in kwargs:
                kwargs['prerequisites'] = json.dumps(kwargs['prerequisites'], ensure_ascii=False)
            
            # 添加更新时间
            kwargs['updated_at'] = datetime.now().timestamp()
            
            set_clause = ", ".join(f"{k} = ?" for k in kwargs.keys())
            values = list(kwargs.values()) + [code]
            
            cursor = conn.execute(f"UPDATE courses SET {set_clause} WHERE code = ?", values)
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()
    
    @staticmethod
    def delete(code: str) -> bool:
        """
        删除课程
        
        Args:
            code: 课程代码
            
        Returns:
            bool: 是否删除成功
        """
        conn = get_connection()
        try:
            cursor = conn.execute("DELETE FROM courses WHERE code = ?", (code,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()
    
    @staticmethod
    def search_by_teacher(teacher: str) -> List[Dict[str, Any]]:
        """按教师搜索课程"""
        conn = get_connection()
        try:
            cursor = conn.execute("SELECT * FROM courses WHERE teacher LIKE ?", (f"%{teacher}%",))
            results = []
            for row in cursor.fetchall():
                result = dict(row)
                # 解析 JSON 字段
                if result.get('prerequisites'):
                    try:
                        result['prerequisites'] = json.loads(result['prerequisites'])
                    except (json.JSONDecodeError, TypeError):
                        result['prerequisites'] = []
                results.append(result)
            return results
        finally:
            conn.close()
    
    @staticmethod
    def search_by_semester(semester: str) -> List[Dict[str, Any]]:
        """按学期搜索课程"""
        conn = get_connection()
        try:
            cursor = conn.execute("SELECT * FROM courses WHERE semester = ?", (semester,))
            results = []
            for row in cursor.fetchall():
                result = dict(row)
                # 解析 JSON 字段
                if result.get('prerequisites'):
                    try:
                        result['prerequisites'] = json.loads(result['prerequisites'])
                    except (json.JSONDecodeError, TypeError):
                        result['prerequisites'] = []
                results.append(result)
            return results
        finally:
            conn.close()


class DocumentCRUD:
    """文档表 CRUD 操作"""
    
    @staticmethod
    def create(doc_id: str, category: str, title: str, content: str,
               source_url: str = None, publish_date: str = None,
               expiry_date: str = None, tags: List[str] = None,
               confidence: float = 1.0) -> bool:
        """
        创建文档记录
        
        Args:
            doc_id: 文档ID
            category: 分类 (academic/life/course)
            title: 标题
            content: 内容
            source_url: 来源URL
            publish_date: 发布日期
            expiry_date: 过期日期
            tags: 标签列表
            confidence: 置信度
            
        Returns:
            bool: 是否创建成功
        """
        conn = get_connection()
        try:
            conn.execute("""
                INSERT INTO documents (doc_id, category, title, content, source_url, 
                                     publish_date, expiry_date, tags, confidence)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (doc_id, category, title, content, source_url, publish_date,
                  expiry_date, json.dumps(tags or [], ensure_ascii=False), confidence))
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
        finally:
            conn.close()
    
    @staticmethod
    def get(doc_id: str) -> Optional[Dict[str, Any]]:
        """
        获取文档信息
        
        Args:
            doc_id: 文档ID
            
        Returns:
            文档信息字典，不存在返回 None
        """
        conn = get_connection()
        try:
            cursor = conn.execute("SELECT * FROM documents WHERE doc_id = ?", (doc_id,))
            row = cursor.fetchone()
            if row:
                result = dict(row)
                # 解析 JSON 字段
                if result.get('tags'):
                    try:
                        result['tags'] = json.loads(result['tags'])
                    except (json.JSONDecodeError, TypeError):
                        result['tags'] = []
                return result
            return None
        finally:
            conn.close()
    
    @staticmethod
    def get_all() -> List[Dict[str, Any]]:
        """获取所有文档"""
        conn = get_connection()
        try:
            cursor = conn.execute("SELECT * FROM documents ORDER BY publish_date DESC")
            results = []
            for row in cursor.fetchall():
                result = dict(row)
                # 解析 JSON 字段
                if result.get('tags'):
                    try:
                        result['tags'] = json.loads(result['tags'])
                    except (json.JSONDecodeError, TypeError):
                        result['tags'] = []
                results.append(result)
            return results
        finally:
            conn.close()
    
    @staticmethod
    def get_by_category(category: str) -> List[Dict[str, Any]]:
        """按分类获取文档"""
        conn = get_connection()
        try:
            cursor = conn.execute(
                "SELECT * FROM documents WHERE category = ? ORDER BY publish_date DESC", 
                (category,))
            results = []
            for row in cursor.fetchall():
                result = dict(row)
                # 解析 JSON 字段
                if result.get('tags'):
                    try:
                        result['tags'] = json.loads(result['tags'])
                    except (json.JSONDecodeError, TypeError):
                        result['tags'] = []
                results.append(result)
            return results
        finally:
            conn.close()
    
    @staticmethod
    def search_by_title(title: str) -> List[Dict[str, Any]]:
        """按标题搜索文档"""
        conn = get_connection()
        try:
            cursor = conn.execute(
                "SELECT * FROM documents WHERE title LIKE ?", 
                (f"%{title}%",))
            results = []
            for row in cursor.fetchall():
                result = dict(row)
                # 解析 JSON 字段
                if result.get('tags'):
                    try:
                        result['tags'] = json.loads(result['tags'])
                    except (json.JSONDecodeError, TypeError):
                        result['tags'] = []
                results.append(result)
            return results
        finally:
            conn.close()
    
    @staticmethod
    def update(doc_id: str, **kwargs) -> bool:
        """
        更新文档信息
        
        Args:
            doc_id: 文档ID
            **kwargs: 要更新的字段
            
        Returns:
            bool: 是否更新成功
        """
        if not kwargs:
            return False
        
        conn = get_connection()
        try:
            # 处理 tags 字段
            if 'tags' in kwargs:
                kwargs['tags'] = json.dumps(kwargs['tags'], ensure_ascii=False)
            
            set_clause = ", ".join(f"{k} = ?" for k in kwargs.keys())
            values = list(kwargs.values()) + [doc_id]
            
            cursor = conn.execute(f"UPDATE documents SET {set_clause} WHERE doc_id = ?", values)
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()
    
    @staticmethod
    def delete(doc_id: str) -> bool:
        """
        删除文档
        
        Args:
            doc_id: 文档ID
            
        Returns:
            bool: 是否删除成功
        """
        conn = get_connection()
        try:
            # 先删除关联的 chunks
            conn.execute("DELETE FROM chunks WHERE doc_id = ?", (doc_id,))
            # 删除文档
            cursor = conn.execute("DELETE FROM documents WHERE doc_id = ?", (doc_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()
    
    @staticmethod
    def get_chunks(doc_id: str) -> List[Dict[str, Any]]:
        """获取文档的所有分块"""
        conn = get_connection()
        try:
            cursor = conn.execute(
                "SELECT * FROM chunks WHERE doc_id = ? ORDER BY position", 
                (doc_id,))
            results = []
            for row in cursor.fetchall():
                result = dict(row)
                # 解析 JSON 字段
                if result.get('parent_headings'):
                    try:
                        result['parent_headings'] = json.loads(result['parent_headings'])
                    except (json.JSONDecodeError, TypeError):
                        result['parent_headings'] = []
                results.append(result)
            return results
        finally:
            conn.close()


class ChunkCRUD:
    """分块表 CRUD 操作"""
    
    @staticmethod
    def create(chunk_id: str, doc_id: str, content: str, 
               parent_headings: List[str] = None, position: int = 0) -> bool:
        """创建分块记录"""
        conn = get_connection()
        try:
            conn.execute("""
                INSERT INTO chunks (chunk_id, doc_id, content, parent_headings, position)
                VALUES (?, ?, ?, ?, ?)
            """, (chunk_id, doc_id, content, 
                  json.dumps(parent_headings or [], ensure_ascii=False), position))
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
        finally:
            conn.close()
    
    @staticmethod
    def get(chunk_id: str) -> Optional[Dict[str, Any]]:
        """获取分块信息"""
        conn = get_connection()
        try:
            cursor = conn.execute("SELECT * FROM chunks WHERE chunk_id = ?", (chunk_id,))
            row = cursor.fetchone()
            if row:
                result = dict(row)
                # 解析 JSON 字段
                if result.get('parent_headings'):
                    try:
                        result['parent_headings'] = json.loads(result['parent_headings'])
                    except (json.JSONDecodeError, TypeError):
                        result['parent_headings'] = []
                return result
            return None
        finally:
            conn.close()
    
    @staticmethod
    def delete_by_doc(doc_id: str) -> bool:
        """删除文档的所有分块"""
        conn = get_connection()
        try:
            cursor = conn.execute("DELETE FROM chunks WHERE doc_id = ?", (doc_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()


class EmbeddingCRUD:
    """向量索引表 CRUD 操作"""
    
    @staticmethod
    def create(chunk_id: str, embedding: bytes) -> bool:
        """创建向量记录"""
        conn = get_connection()
        try:
            conn.execute("""
                INSERT OR REPLACE INTO embeddings (chunk_id, embedding)
                VALUES (?, ?)
            """, (chunk_id, embedding))
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
        finally:
            conn.close()
    
    @staticmethod
    def get(chunk_id: str) -> Optional[bytes]:
        """获取向量数据"""
        conn = get_connection()
        try:
            cursor = conn.execute("SELECT embedding FROM embeddings WHERE chunk_id = ?", (chunk_id,))
            row = cursor.fetchone()
            if row:
                return row['embedding']
            return None
        finally:
            conn.close()


class CacheCRUD:
    """语义缓存表 CRUD 操作"""
    
    @staticmethod
    def get(key_hash: str) -> Optional[Dict[str, Any]]:
        """获取缓存"""
        conn = get_connection()
        try:
            cursor = conn.execute("SELECT * FROM cache WHERE key_hash = ?", (key_hash,))
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None
        finally:
            conn.close()
    
    @staticmethod
    def set(key_hash: str, value: str, ttl_seconds: int = 3600) -> bool:
        """设置缓存"""
        conn = get_connection()
        try:
            created_at = datetime.now().timestamp()
            conn.execute("""
                INSERT OR REPLACE INTO cache (key_hash, value, created_at)
                VALUES (?, ?, ?)
            """, (key_hash, value, created_at))
            conn.commit()
            return True
        finally:
            conn.close()
    
    @staticmethod
    def delete(key_hash: str) -> bool:
        """删除缓存"""
        conn = get_connection()
        try:
            cursor = conn.execute("DELETE FROM cache WHERE key_hash = ?", (key_hash,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()
    
    @staticmethod
    def cleanup_expired(ttl_seconds: int = 3600) -> int:
        """清理过期缓存"""
        conn = get_connection()
        try:
            threshold = datetime.now().timestamp() - ttl_seconds
            conn.execute("DELETE FROM cache WHERE created_at < ?", (threshold,))
            conn.commit()
            return conn.total_changes
        finally:
            conn.close()


class LogCRUD:
    """日志表 CRUD 操作"""
    
    @staticmethod
    def create(trace_id: str, user_id: str = None, node: str = None,
               level: str = "INFO", message: str = None, 
               detail: Dict = None) -> bool:
        """创建日志记录"""
        conn = get_connection()
        try:
            timestamp = datetime.now().timestamp()
            conn.execute("""
                INSERT INTO logs (trace_id, user_id, node, level, message, detail, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (trace_id, user_id, node, level, message, 
                  json.dumps(detail or {}, ensure_ascii=False), timestamp))
            conn.commit()
            return True
        finally:
            conn.close()
    
    @staticmethod
    def get_by_trace(trace_id: str) -> List[Dict[str, Any]]:
        """按 trace_id 获取日志"""
        conn = get_connection()
        try:
            cursor = conn.execute(
                "SELECT * FROM logs WHERE trace_id = ? ORDER BY timestamp", 
                (trace_id,))
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()
    
    @staticmethod
    def get_recent(limit: int = 100) -> List[Dict[str, Any]]:
        """获取最近的日志"""
        conn = get_connection()
        try:
            cursor = conn.execute(
                "SELECT * FROM logs ORDER BY timestamp DESC LIMIT ?", 
                (limit,))
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()
