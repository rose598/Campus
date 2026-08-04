# -*- coding: utf-8 -*-
"""
course_processor.py — 课程资料处理器

职责:
  - 课程大纲/课件/试卷的结构化解析
  - LLM 辅助知识点提取
  - 课程专用分块策略
  - 课程资料索引构建

使用方式:
  from data_pipeline.course_processor import CourseProcessor

  processor = CourseProcessor()
  result = processor.process_course(course_data)
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
#  课程数据结构
# ─────────────────────────────────────────────

class CourseInfo:
    """课程基本信息"""

    def __init__(self, data: Dict[str, Any]):
        self.course_id = data.get("course_id", "")
        self.course_name = data.get("course_name", "")
        self.teacher = data.get("teacher", "")
        self.department = data.get("department", "")
        self.semester = data.get("semester", "")
        self.credits = data.get("credits", 0)
        self.materials = data.get("materials", [])

    def to_dict(self) -> Dict[str, Any]:
        return {
            "course_id": self.course_id,
            "course_name": self.course_name,
            "teacher": self.teacher,
            "department": self.department,
            "semester": self.semester,
            "credits": self.credits,
        }


class CourseMaterial:
    """单个课程资料"""

    def __init__(self, data: Dict[str, Any]):
        self.material_id = data.get("material_id", "")
        self.material_type = data.get("type", "syllabus")  # syllabus/slides/exam/notes
        self.title = data.get("title", "")
        self.content = data.get("content", "")
        self.file_path = data.get("file_path", "")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "material_id": self.material_id,
            "material_type": self.material_type,
            "title": self.title,
            "content": self.content,
        }


# ─────────────────────────────────────────────
#  课程知识点提取
# ─────────────────────────────────────────────

class KnowledgeExtractor:
    """
    课程知识点提取器。

    从课程资料中提取:
      - 知识点列表
      - 重点/难点
      - 先修课程
      - 考核方式
    """

    # 知识点识别模式
    _KNOWLEDGE_PATTERNS = [
        # 章节标题
        re.compile(r"^(?:第[一二三四五六七八九十\d]+[章节]|Chapter\s+\d+)"),
        # 知识点列表
        re.compile(r"^\d+[\.、]\s*(?:掌握|理解|了解|熟悉)"),
        # 关键词
        re.compile(r"(?:知识点|重点|难点|考点)[：:]"),
    ]

    # 考核方式关键词
    _ASSESSMENT_KEYWORDS = [
        "平时成绩", "期末", "期中", "作业", "实验", "考勤",
        "闭卷", "开卷", "论文", "答辩", "项目",
    ]

    def extract(self, content: str, material_type: str = "syllabus") -> Dict[str, Any]:
        """
        从课程内容中提取结构化知识点。

        Returns:
            {
                "knowledge_points": [...],
                "key_points": [...],
                "prerequisites": [...],
                "assessment": {...},
                "sections": [...]
            }
        """
        result = {
            "knowledge_points": [],
            "key_points": [],
            "prerequisites": [],
            "assessment": {},
            "sections": [],
        }

        # 提取章节结构
        result["sections"] = self._extract_sections(content)

        # 提取知识点
        result["knowledge_points"] = self._extract_knowledge_points(content)

        # 提取重点
        result["key_points"] = self._extract_key_points(content)

        # 提取先修课程
        result["prerequisites"] = self._extract_prerequisites(content)

        # 提取考核方式
        result["assessment"] = self._extract_assessment(content)

        return result

    def _extract_sections(self, content: str) -> List[Dict[str, Any]]:
        """提取章节结构"""
        sections = []
        current_section = None
        current_content = []

        for line in content.split("\n"):
            line = line.strip()
            if not line:
                continue

            # 检测章节标题
            if self._is_section_heading(line):
                if current_section:
                    current_section["content"] = "\n".join(current_content)
                    sections.append(current_section)
                current_section = {"heading": line, "level": self._heading_level(line)}
                current_content = []
            elif current_section:
                current_content.append(line)

        # 最后一个 section
        if current_section:
            current_section["content"] = "\n".join(current_content)
            sections.append(current_section)

        return sections

    def _is_section_heading(self, line: str) -> bool:
        """判断是否为章节标题"""
        if len(line) > 50:
            return False
        for pattern in self._KNOWLEDGE_PATTERNS:
            if pattern.match(line):
                return True
        # 数字开头且较短
        if re.match(r"^\d+[\.、]\s*\S+", line) and len(line) < 30:
            return True
        return False

    def _heading_level(self, line: str) -> int:
        """获取标题层级"""
        if re.match(r"^第[一二三四五六七八九十\d]+[章节]", line):
            return 1
        if re.match(r"^\d+[\.、]", line):
            return 2
        if re.match(r"^[一二三四五六七八九十]+[、．.]", line):
            return 2
        return 3

    def _extract_knowledge_points(self, content: str) -> List[str]:
        """提取知识点列表"""
        points = []
        for line in content.split("\n"):
            line = line.strip()
            # 匹配 "掌握/理解/了解 XXX" 模式
            match = re.search(r"(?:掌握|理解|了解|熟悉)\s*(.{2,50})", line)
            if match:
                points.append(match.group(1).strip())
        return points[:50]  # 限制数量

    def _extract_key_points(self, content: str) -> List[str]:
        """提取重点/难点"""
        points = []
        for line in content.split("\n"):
            if "重点" in line or "难点" in line or "考点" in line:
                # 提取冒号后的内容
                match = re.search(r"[：:]\s*(.+)", line)
                if match:
                    points.append(match.group(1).strip())
        return points[:20]

    def _extract_prerequisites(self, content: str) -> List[str]:
        """提取先修课程"""
        prereqs = []
        for line in content.split("\n"):
            if "先修" in line or "前置" in line:
                # 提取课程名（通常在冒号后）
                match = re.search(r"[：:]\s*(.+)", line)
                if match:
                    # 分割多个课程
                    courses = re.split(r"[、,，;；]", match.group(1))
                    prereqs.extend([c.strip() for c in courses if c.strip()])
        return prereqs[:10]

    def _extract_assessment(self, content: str) -> Dict[str, Any]:
        """提取考核方式"""
        assessment = {}
        for line in content.split("\n"):
            for keyword in self._ASSESSMENT_KEYWORDS:
                if keyword in line:
                    # 尝试提取百分比
                    match = re.search(r"(\d+)%", line)
                    if match:
                        assessment[keyword] = f"{match.group(1)}%"
                    elif "考核" in line or "成绩" in line:
                        assessment[keyword] = True
        return assessment


# ─────────────────────────────────────────────
#  课程分块器
# ─────────────────────────────────────────────

class CourseChunker:
    """
    课程资料专用分块器。

    特点:
      - 保留课程章节结构
      - 知识点级别的细粒度分块
      - 课件/试卷特殊处理
    """

    def __init__(self, chunk_size: int = 512, chunk_overlap: int = 50):
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap
        self._extractor = KnowledgeExtractor()

    def chunk_course_material(
        self, material: CourseMaterial, course_info: CourseInfo
    ) -> List[Dict[str, Any]]:
        """
        对课程资料进行分块。

        Args:
            material: 课程资料
            course_info: 课程信息

        Returns:
            分块列表，每块包含 content, metadata, parent_headings
        """
        chunks = []

        if material.material_type == "syllabus":
            chunks = self._chunk_syllabus(material.content, course_info)
        elif material.material_type == "slides":
            chunks = self._chunk_slides(material.content, course_info)
        elif material.material_type == "exam":
            chunks = self._chunk_exam(material.content, course_info)
        else:
            # 默认处理
            chunks = self._chunk_generic(material.content, course_info)

        # 为每个 chunk 添加课程元数据
        for i, chunk in enumerate(chunks):
            chunk["chunk_id"] = self._gen_chunk_id(course_info.course_id, i)
            chunk["course_id"] = course_info.course_id
            chunk["course_name"] = course_info.course_name
            chunk["material_type"] = material.material_type
            chunk["position"] = i

        return chunks

    def _chunk_syllabus(self, content: str, course: CourseInfo) -> List[Dict]:
        """大纲分块：按章节划分"""
        sections = self._extractor._extract_sections(content)
        chunks = []

        if not sections:
            # 无章节结构，按大小分
            return self._chunk_generic(content, course)

        for section in sections:
            heading = section["heading"]
            section_content = section["content"]

            # 如果章节内容太长，进一步分
            if len(section_content) > self._chunk_size:
                sub_chunks = self._split_long_section(section_content)
                for i, sub in enumerate(sub_chunks):
                    chunks.append({
                        "content": sub,
                        "parent_headings": [heading],
                        "metadata": {
                            "section": heading,
                            "sub_section": i + 1,
                        },
                    })
            else:
                chunks.append({
                    "content": f"{heading}\n{section_content}",
                    "parent_headings": [heading],
                    "metadata": {"section": heading},
                })

        return chunks

    def _chunk_slides(self, content: str, course: CourseInfo) -> List[Dict]:
        """课件分块：按页面/幻灯片划分"""
        # 课件通常以 --- 或 空行分隔
        pages = re.split(r"\n\s*-{3,}\s*\n|\n\s*\n\s*\n", content)
        chunks = []

        for page in pages:
            page = page.strip()
            if len(page) < 10:
                continue
            chunks.append({
                "content": page,
                "parent_headings": [],
                "metadata": {"page": True},
            })

        return chunks if chunks else self._chunk_generic(content, course)

    def _chunk_exam(self, content: str, course: CourseInfo) -> List[Dict]:
        """试卷分块：按题目划分"""
        chunks = []
        current_question = []
        question_num = 0

        for line in content.split("\n"):
            line = line.strip()
            # 检测题号
            if re.match(r"^\d+[\.、]\s*", line) or re.match(r"^[一二三四五六七八九十]+[、．]", line):
                if current_question:
                    chunks.append({
                        "content": "\n".join(current_question),
                        "parent_headings": [],
                        "metadata": {"question_num": question_num},
                    })
                    question_num += 1
                    current_question = []
            current_question.append(line)

        if current_question:
            chunks.append({
                "content": "\n".join(current_question),
                "parent_headings": [],
                "metadata": {"question_num": question_num},
            })

        return chunks if chunks else self._chunk_generic(content, course)

    def _chunk_generic(self, content: str, course: CourseInfo) -> List[Dict]:
        """通用分块"""
        from data_pipeline.chunker import LayoutChunker

        # 使用通用 chunker
        chunker = LayoutChunker(
            chunk_size=self._chunk_size,
            chunk_overlap=self._chunk_overlap,
        )
        # 模拟文档对象
        class FakeDoc:
            doc_id = f"COURSE_{course.course_id}"
            content = content

        raw_chunks = chunker.chunk(FakeDoc())
        return [
            {
                "content": c.content,
                "parent_headings": c.parent_headings,
                "metadata": {},
            }
            for c in raw_chunks
        ]

    def _split_long_section(self, content: str) -> List[str]:
        """将过长的章节内容按大小切分"""
        parts = []
        current = ""
        for line in content.split("\n"):
            if len(current) + len(line) + 1 > self._chunk_size:
                if current:
                    parts.append(current)
                current = line
            else:
                current = current + "\n" + line if current else line
        if current:
            parts.append(current)
        return parts

    @staticmethod
    def _gen_chunk_id(course_id: str, position: int) -> str:
        """生成分块 ID"""
        h = hashlib.md5(f"{course_id}_{position}".encode()).hexdigest()
        return f"CHK_{h[:6].upper()}"


# ─────────────────────────────────────────────
#  课程处理器主入口
# ─────────────────────────────────────────────

class CourseProcessor:
    """
    课程资料处理器主入口。

    流程: 原始数据 → 课程解析 → 知识提取 → 分块 → 元数据标注
    """

    def __init__(
        self,
        chunk_size: int = 512,
        chunk_overlap: int = 50,
        use_llm: bool = False,
    ):
        self._chunker = CourseChunker(chunk_size, chunk_overlap)
        self._extractor = KnowledgeExtractor()
        self._use_llm = use_llm

    def process_course(self, course_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理单个课程的全部资料。

        Args:
            course_data: 课程原始数据
                {
                    "course_id": "CS101",
                    "course_name": "C语言程序设计",
                    "teacher": "张三",
                    "materials": [
                        {"type": "syllabus", "title": "教学大纲", "content": "..."},
                        ...
                    ]
                }

        Returns:
            {
                "course_info": {...},
                "knowledge": {...},
                "chunks": [...],
                "stats": {...}
            }
        """
        course_info = CourseInfo(course_data)
        all_chunks = []
        all_knowledge = {
            "knowledge_points": [],
            "key_points": [],
            "prerequisites": [],
            "assessment": {},
        }

        for material_data in course_data.get("materials", []):
            material = CourseMaterial(material_data)

            # 知识提取
            knowledge = self._extractor.extract(material.content, material.material_type)
            all_knowledge["knowledge_points"].extend(knowledge["knowledge_points"])
            all_knowledge["key_points"].extend(knowledge["key_points"])
            all_knowledge["prerequisites"].extend(knowledge["prerequisites"])
            all_knowledge["assessment"].update(knowledge["assessment"])

            # 分块
            chunks = self._chunker.chunk_course_material(material, course_info)
            all_chunks.extend(chunks)

        # 去重
        all_knowledge["knowledge_points"] = list(set(all_knowledge["knowledge_points"]))
        all_knowledge["key_points"] = list(set(all_knowledge["key_points"]))
        all_knowledge["prerequisites"] = list(set(all_knowledge["prerequisites"]))

        stats = {
            "materials_count": len(course_data.get("materials", [])),
            "chunks_count": len(all_chunks),
            "knowledge_points": len(all_knowledge["knowledge_points"]),
            "key_points": len(all_knowledge["key_points"]),
        }

        logger.info(
            "[CourseProcessor] %s: %d 资料 → %d 分块, %d 知识点",
            course_info.course_name,
            stats["materials_count"],
            stats["chunks_count"],
            stats["knowledge_points"],
        )

        return {
            "course_info": course_info.to_dict(),
            "knowledge": all_knowledge,
            "chunks": all_chunks,
            "stats": stats,
        }

    def process_courses_from_file(self, file_path: str) -> List[Dict[str, Any]]:
        """从 JSON 文件批量处理课程"""
        path = Path(file_path)
        if not path.exists():
            logger.error("[CourseProcessor] 文件不存在: %s", file_path)
            return []

        try:
            with open(path, "r", encoding="utf-8") as f:
                courses = json.load(f)
        except Exception as e:
            logger.error("[CourseProcessor] 读取失败: %s", e)
            return []

        results = []
        for course_data in courses:
            try:
                result = self.process_course(course_data)
                results.append(result)
            except Exception as e:
                logger.error("[CourseProcessor] 处理课程失败: %s", e)

        logger.info("[CourseProcessor] 批量处理完成: %d/%d 课程", len(results), len(courses))
        return results
