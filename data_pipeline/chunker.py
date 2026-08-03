"""
chunker.py — 智能分块器（Layout-aware Chunker）

职责:
  - 识别文档结构（标题层级、段落边界）
  - 按语义结构分块，保留标题层级上下文（parent_headings）
  - 支持可配置的 chunk_size / chunk_overlap
  - 对超长段落执行滑动窗口切分
  - 输出 Chunk 列表，与 models.campus_document.Chunk 对齐

使用方式:
  from data_pipeline.chunker import LayoutChunker

  chunker = LayoutChunker(chunk_size=512, chunk_overlap=50)
  chunks = chunker.chunk(cleaned_document)
"""

from __future__ import annotations

import hashlib
import logging
import re
from typing import List, Optional, Tuple

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
#  分块配置
# ─────────────────────────────────────────────

class ChunkerConfig(BaseModel):
    """分块器参数，默认值取自 config.yaml"""
    chunk_size: int = Field(default=512, ge=64, description="每块最大字符数")
    chunk_overlap: int = Field(default=50, ge=0, description="块间重叠字符数")
    min_chunk_size: int = Field(default=20, ge=1, description="最小有效块字符数")


# ─────────────────────────────────────────────
#  标题检测
# ─────────────────────────────────────────────

# 中文文档常见标题模式（按层级排序）
_HEADING_PATTERNS: List[Tuple[re.Pattern, int]] = [
    # "第X章/节/条" → level 1
    (re.compile(r"^第[一二三四五六七八九十百千\d]+[章节条]\s*.+$"), 1),
    # "一、" "二、" … 中文数字编号 → level 1（后续内容可选）
    (re.compile(r"^[一二三四五六七八九十]+[、．.]\s*.*$"), 1),
    # "1." "1.1" "1.1.1" 数字编号 → level 2
    (re.compile(r"^\d+(\.\d+)*[.、．]\s*.*$"), 2),
    # "(一)" "(1)" 带括号编号 → level 2
    (re.compile(r"^[（(][一二三四五六七八九十\d]+[)）]\s*.*$"), 2),
    # "第一部分" "第二部分" → level 1
    (re.compile(r"^第[一二三四五六七八九十\d]+部分\s*.+$"), 1),
    # 短行（< 60 字符）且不含句号/问号/感叹号 → 可能是标题
    # 这个在后续逻辑中处理
]

# 英文标题模式
_EN_HEADING_PATTERNS: List[Tuple[re.Pattern, int]] = [
    (re.compile(r"^(Chapter|Section|Part)\s+\d+[:.]?\s*.+$", re.IGNORECASE), 1),
    (re.compile(r"^\d+(\.\d+)*\s+[A-Z].+$"), 2),
]


def _detect_heading(line: str) -> Optional[int]:
    """
    检测一行是否为标题。
    返回标题层级（1=最高级），非标题返回 None。
    """
    stripped = line.strip()
    if not stripped or len(stripped) > 80:
        return None

    # 中文标题模式
    for pattern, level in _HEADING_PATTERNS:
        if pattern.match(stripped):
            return level

    # 英文标题模式
    for pattern, level in _EN_HEADING_PATTERNS:
        if pattern.match(stripped):
            return level

    # 启发式：短行（< 50字符）、无句末标点、有内容 → 可能是标题
    if (
        len(stripped) < 50
        and not stripped.endswith(("。", ".", "；", ";", "，", ",", "：", ":"))
        and not stripped.endswith(("？", "?", "！", "!"))
        and re.search(r"[\u4e00-\u9fff\w]", stripped)
        and not stripped.startswith(("·", "-", "•", "※"))
    ):
        # 需要排除纯数字行和页码
        if not re.match(r"^[\d\sivxlcdmIVXLCDM第页]+$", stripped):
            return 3  # 最低级标题

    return None


# ─────────────────────────────────────────────
#  分块器
# ─────────────────────────────────────────────

class LayoutChunker:
    """
    Layout-aware 文档分块器。

    分块策略:
      1. 按双换行分割段落
      2. 检测每个段落的标题层级
      3. 按标题边界切分为语义段（section）
      4. 超长段使用滑动窗口切分（chunk_size + chunk_overlap）
      5. 每块附带 parent_headings（标题面包屑）

    示例:
        >>> chunker = LayoutChunker(chunk_size=512, chunk_overlap=50)
        >>> chunks = chunker.chunk(cleaned_doc)
        >>> chunks[0].parent_headings
        ['第一章 总则', '一、适用范围']
    """

    # 全局 chunk 计数器（用于生成唯一 chunk_id）
    _chunk_counter: int = 0

    def __init__(self, chunk_size: int = 512, chunk_overlap: int = 50, min_chunk_size: int = 20):
        self._config = ChunkerConfig(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            min_chunk_size=min_chunk_size,
        )

    @classmethod
    def from_config(cls) -> "LayoutChunker":
        """从 config.yaml 读取参数构建"""
        from utils.config_loader import get
        return cls(
            chunk_size=get("rag.chunk_size", 512),
            chunk_overlap=get("rag.chunk_overlap", 50),
        )

    # ── 公共接口 ──────────────────────────────

    def chunk(self, doc) -> List[dict]:
        """
        对 CleanedDocument 执行智能分块。

        Args:
            doc: data_pipeline.text_cleaner.CleanedDocument 实例

        Returns:
            Chunk 字典列表（与 models.campus_document.Chunk 对齐）
        """
        text = doc.content
        doc_id = doc.doc_id

        if not text or not text.strip():
            logger.warning("[Chunker] 文档内容为空: %s", doc_id)
            return []

        # 1. 分割段落并检测标题
        paragraphs = self._split_into_paragraphs(text)
        annotated = self._annotate_paragraphs(paragraphs)

        # 2. 按标题边界切分为语义段
        sections = self._build_sections(annotated)

        # 3. 对超长段执行滑动窗口切分
        raw_chunks = self._split_sections(sections)

        # 4. 生成 Chunk 对象
        chunks = []
        for i, (content, headings) in enumerate(raw_chunks):
            content = content.strip()
            if len(content) < self._config.min_chunk_size:
                continue
            chunk_id = self._generate_chunk_id(doc_id, i)
            chunks.append({
                "chunk_id": chunk_id,
                "doc_id": doc_id,
                "content": content,
                "parent_headings": headings,
                "position": i,
            })

        logger.info(
            "[Chunker] %s: %d 段落 → %d 块 (size=%d, overlap=%d)",
            doc_id, len(paragraphs), len(chunks),
            self._config.chunk_size, self._config.chunk_overlap,
        )
        return chunks

    def chunk_batch(self, docs: list) -> dict:
        """
        批量分块。

        Returns:
            {doc_id: [chunk_dict, ...], ...}
        """
        results = {}
        for doc in docs:
            chunks = self.chunk(doc)
            if chunks:
                results[doc.doc_id] = chunks
        logger.info("[Chunker] 批量分块完成: %d 文档, 共 %d 块",
                     len(results), sum(len(v) for v in results.values()))
        return results

    # ── 内部步骤 ──────────────────────────────

    @staticmethod
    def _split_into_paragraphs(text: str) -> List[str]:
        """按双换行或单换行分割文本为段落列表"""
        # 先按双换行分
        parts = re.split(r"\n{2,}", text)
        paragraphs = []
        for part in parts:
            p = part.strip()
            if p:
                paragraphs.append(p)
        return paragraphs

    @staticmethod
    def _annotate_paragraphs(paragraphs: List[str]) -> List[dict]:
        """
        为每个段落标注标题信息。

        Returns:
            [{"text": str, "heading_level": Optional[int], "is_heading": bool}, ...]
        """
        annotated = []
        for p in paragraphs:
            level = _detect_heading(p)
            annotated.append({
                "text": p,
                "heading_level": level,
                "is_heading": level is not None,
            })
        return annotated

    def _build_sections(self, annotated: List[dict]) -> List[dict]:
        """
        按标题边界将段落组织为语义段。

        Returns:
            [{"content": str, "headings": [str, ...]}, ...]
        """
        sections = []
        current_headings: List[str] = []  # 标题面包屑栈
        current_paragraphs: List[str] = []

        for item in annotated:
            if item["is_heading"]:
                # 先把当前积累的段落收成一个 section
                if current_paragraphs:
                    sections.append({
                        "content": "\n\n".join(current_paragraphs),
                        "headings": list(current_headings),
                    })
                    current_paragraphs = []

                # 更新标题栈
                level = item["heading_level"]
                heading_text = item["text"].strip()

                # 层级 ≤ 当前栈深度时弹出
                while len(current_headings) >= level:
                    current_headings.pop()
                current_headings.append(heading_text)
            else:
                current_paragraphs.append(item["text"])

        # 收尾
        if current_paragraphs:
            sections.append({
                "content": "\n\n".join(current_paragraphs),
                "headings": list(current_headings),
            })

        # 如果没有任何标题，整个文档作为一个 section
        if not sections and annotated:
            sections.append({
                "content": "\n\n".join(item["text"] for item in annotated),
                "headings": [],
            })

        return sections

    def _split_sections(self, sections: List[dict]) -> List[Tuple[str, List[str]]]:
        """
        对每个 section 执行切分：
          - 短 section（≤ chunk_size）直接输出
          - 长 section 使用滑动窗口切分

        Returns:
            [(content, headings), ...]
        """
        result = []
        chunk_size = self._config.chunk_size
        overlap = self._config.chunk_overlap

        for section in sections:
            content = section["content"]
            headings = section["headings"]

            if len(content) <= chunk_size:
                result.append((content, headings))
            else:
                # 滑动窗口切分
                windows = self._sliding_window(content, chunk_size, overlap)
                for window in windows:
                    result.append((window, headings))

        return result

    @staticmethod
    def _sliding_window(text: str, window_size: int, overlap: int) -> List[str]:
        """
        滑动窗口切分文本。

        尽量在句号/换行处断开，避免切断句子。
        """
        if len(text) <= window_size:
            return [text]

        chunks = []
        start = 0
        while start < len(text):
            end = start + window_size

            if end >= len(text):
                chunks.append(text[start:])
                break

            # 在 [end - overlap, end] 范围内寻找最佳断句点
            search_start = max(start + 1, end - overlap)
            best_break = end  # 默认硬切

            # 优先找句号/换行
            for sep in ["。\n", "。\n\n", "。\n", "。", ".\n", ".\n\n", ".", "\n\n", "\n"]:
                idx = text.rfind(sep, search_start, end)
                if idx > start:
                    best_break = idx + len(sep)
                    break

            chunk_text = text[start:best_break].strip()
            if chunk_text:
                chunks.append(chunk_text)

            start = best_break
            # 避免死循环
            if start <= (end - window_size):
                start = end

        return chunks

    # ── 工具方法 ──────────────────────────────

    @staticmethod
    def _generate_chunk_id(doc_id: str, position: int) -> str:
        """
        生成稳定的 chunk_id（格式: CHK_XXXXXX，6 位大写十六进制）。
        基于 doc_id + position 的哈希。
        """
        raw = f"{doc_id}:{position}"
        digest = hashlib.md5(raw.encode("utf-8")).hexdigest()[:6].upper()
        return f"CHK_{digest}"


# ─────────────────────────────────────────────
#  命令行快速测试入口
# ─────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    import json

    logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")

    # 用示例文本演示
    sample_text = """第一章 总则

一、适用范围
本条例适用于全校全日制本科在校学生。

二、基本原则
坚持公平、公正、公开的原则，促进学生全面发展。

第二章 保研条件

一、学业成绩
学业成绩排名在本专业前30%，且无不及格科目记录。

二、综合素质
参加科研竞赛、社会实践等活动，获得相应学分认定。
综合素质评价由学院综合评定，包括科研能力、创新能力、团队协作等方面。
各学院应根据本院实际情况制定具体的评价标准和实施细则。

三、特殊条件
对于在学科竞赛中获得国家级奖项的学生，可适当放宽成绩要求。
具体放宽标准由教务处根据实际情况确定。

第三章 申请流程

一、时间安排
每年9月1日至9月15日为申请期。
9月16日至9月30日为审核期。

二、申请材料
1. 保研申请表；
2. 成绩单（教务处盖章）；
3. 综合素质评价表；
4. 获奖证书复印件。"""

    from data_pipeline.doc_parser import ParsedDocument
    from data_pipeline.text_cleaner import TextCleaner, CleanedDocument

    doc = ParsedDocument(
        doc_id="DOC_00000001",
        title="保研政策示例",
        content=sample_text,
        source_path="example.txt",
        file_type="txt",
    )

    cleaner = TextCleaner()
    cleaned = cleaner.clean(doc)

    chunker = LayoutChunker(chunk_size=200, chunk_overlap=30)
    chunks = chunker.chunk(cleaned)

    print(f"=== 分块结果: {len(chunks)} 块 ===\n")
    for c in chunks:
        print(f"[{c['chunk_id']}] pos={c['position']} headings={c['parent_headings']}")
        print(f"  内容({len(c['content'])}字): {c['content'][:80]}...")
        print()
