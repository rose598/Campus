"""
text_cleaner.py — 文本清洗器（去噪 / 标准化 / 去重）

职责:
  - 去噪: 移除控制字符、多余空白、OCR 残留、无意义符号
  - 标准化: 全角→半角转换、标点统一、日期格式归一化
  - 去重: 段落级精确去重 + 近似去重（Jaccard 相似度）
  - 空文档兜底: 检测并标记空内容

使用方式:
  from data_pipeline.doc_parser import DocParser
  from data_pipeline.text_cleaner import TextCleaner

  parser = DocParser()
  raw_doc = parser.parse("policy.pdf")

  cleaner = TextCleaner()
  clean_doc = cleaner.clean(raw_doc)
  print(clean_doc.content)
"""

from __future__ import annotations

import logging
import re
import unicodedata
from difflib import SequenceMatcher
from typing import List, Optional, Set

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
#  清洗后数据结构
# ─────────────────────────────────────────────

class CleanedDocument(BaseModel):
    """清洗后的文档，可直接传递给 Chunker 或写入数据库"""
    doc_id: str = Field(..., description="文档 ID（继承自 ParsedDocument）")
    title: str = Field(default="", description="文档标题")
    content: str = Field(..., description="清洗后的文本")
    source_path: str = Field(..., description="原始文件路径")
    source_url: Optional[str] = Field(None, description="来源 URL")
    file_type: str = Field(..., description="文件类型")
    page_count: int = Field(default=0, description="页数")
    metadata: dict = Field(default_factory=dict, description="附加元数据")
    is_empty: bool = Field(default=False, description="内容是否为空（兜底标记）")
    cleaning_stats: dict = Field(default_factory=dict, description="清洗统计信息")


# ─────────────────────────────────────────────
#  文本清洗器
# ─────────────────────────────────────────────

class TextCleaner:
    """
    文档文本清洗器，提供可配置的清洗流水线。

    默认清洗步骤:
      1. 移除控制字符与不可见字符
      2. 全角 → 半角转换（ASCII 范围）
      3. 合并连续空白
      4. 移除无意义行（纯符号行、超短行）
      5. 段落级精确去重
      6. 段落级近似去重（Jaccard ≥ 0.8）
      7. 标准化标点符号
      8. 移除页眉/页脚重复文本

    示例:
        >>> cleaner = TextCleaner()
        >>> cleaned = cleaner.clean(parsed_doc)
        >>> cleaned.is_empty
        False
    """

    # 近似去重 Jaccard 阈值（≥ 该值视为重复）
    NEAR_DUP_THRESHOLD = 0.8

    # 段落最少字符数（低于该值的短行视为噪声）
    MIN_PARAGRAPH_CHARS = 4

    # ── 公共接口 ──────────────────────────────

    def clean(self, doc) -> CleanedDocument:
        """
        对 ParsedDocument 执行完整清洗流水线。

        Args:
            doc: data_pipeline.doc_parser.ParsedDocument 实例

        Returns:
            CleanedDocument（清洗后文本 + 统计信息）
        """
        raw_text: str = doc.content
        original_len = len(raw_text)

        stats = {
            "original_chars": original_len,
            "control_chars_removed": 0,
            "blank_lines_removed": 0,
            "exact_dups_removed": 0,
            "near_dups_removed": 0,
            "final_chars": 0,
        }

        if not raw_text or not raw_text.strip():
            logger.warning("[TextCleaner] 文档内容为空: %s", doc.doc_id)
            return CleanedDocument(
                doc_id=doc.doc_id,
                title=doc.title,
                content="",
                source_path=doc.source_path,
                source_url=getattr(doc, "source_url", None),
                file_type=doc.file_type,
                page_count=doc.page_count,
                metadata=getattr(doc, "metadata", {}),
                is_empty=True,
                cleaning_stats=stats,
            )

        # 流水线执行
        text, ctrl_count = self._remove_control_chars(raw_text)
        stats["control_chars_removed"] = ctrl_count

        text = self._normalize_fullwidth(text)
        text = self._collapse_whitespace(text)

        paragraphs = self._split_paragraphs(text)
        paragraphs, blank_rm = self._remove_noise_lines(paragraphs)
        stats["blank_lines_removed"] = blank_rm

        paragraphs, exact_rm = self._remove_exact_duplicates(paragraphs)
        stats["exact_dups_removed"] = exact_rm

        paragraphs, near_rm = self._remove_near_duplicates(paragraphs)
        stats["near_dups_removed"] = near_rm

        paragraphs = self._remove_header_footer_repeats(paragraphs)

        text = self._normalize_punctuation("\n\n".join(paragraphs))
        text = self._strip_trailing_whitespace(text)

        stats["final_chars"] = len(text)
        is_empty = len(text.strip()) == 0

        if is_empty:
            logger.warning("[TextCleaner] 清洗后内容为空: %s", doc.doc_id)

        logger.info(
            "[TextCleaner] %s: %d → %d 字符 | 控制字符-%d 空行-%d 精确重复-%d 近似重复-%d",
            doc.doc_id,
            original_len, stats["final_chars"],
            ctrl_count, blank_rm, exact_rm, near_rm,
        )

        return CleanedDocument(
            doc_id=doc.doc_id,
            title=doc.title,
            content=text,
            source_path=doc.source_path,
            source_url=getattr(doc, "source_url", None),
            file_type=doc.file_type,
            page_count=doc.page_count,
            metadata=getattr(doc, "metadata", {}),
            is_empty=is_empty,
            cleaning_stats=stats,
        )

    def clean_batch(self, docs: list) -> List[CleanedDocument]:
        """批量清洗，跳过空文档。"""
        results = []
        for doc in docs:
            cleaned = self.clean(doc)
            if not cleaned.is_empty:
                results.append(cleaned)
            else:
                logger.warning("[TextCleaner] 跳过空文档: %s (%s)", doc.doc_id, doc.title)
        logger.info("[TextCleaner] 批量清洗完成: %d/%d 有效", len(results), len(docs))
        return results

    # ── 清洗步骤 ──────────────────────────────

    @staticmethod
    def _remove_control_chars(text: str) -> tuple:
        """移除控制字符（保留换行 \\n 和制表符 \\t）"""
        count = 0
        result = []
        for ch in text:
            cat = unicodedata.category(ch)
            # Cc = 控制字符，但保留 \n \r \t
            if cat == "Cc" and ch not in ("\n", "\r", "\t"):
                count += 1
                continue
            result.append(ch)
        return "".join(result), count

    @staticmethod
    def _normalize_fullwidth(text: str) -> str:
        """
        全角 ASCII 字符 → 半角。
        全角空格 (\\u3000) → 普通空格。
        全角数字/字母/标点 → 半角（保留中文标点不转换）。
        """
        result = []
        for ch in text:
            code = ord(ch)
            # 全角 ASCII 范围（！到～，即 0xFF01~0xFF5E）→ 减去 0xFEE0 得到半角
            if 0xFF01 <= code <= 0xFF5E:
                result.append(chr(code - 0xFEE0))
            elif code == 0x3000:
                result.append(" ")
            else:
                result.append(ch)
        return "".join(result)

    @staticmethod
    def _collapse_whitespace(text: str) -> str:
        """合并连续空格（不含换行）为单个空格"""
        # 行内多个空格合并
        text = re.sub(r"[^\S\n]+", " ", text)
        # 连续 3 个以上换行合并为 2 个
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    @staticmethod
    def _split_paragraphs(text: str) -> List[str]:
        """按双换行或单换行分段，过滤空段"""
        # 优先按双换行分
        parts = re.split(r"\n{2,}", text)
        paragraphs = []
        for part in parts:
            p = part.strip()
            if p:
                paragraphs.append(p)
        return paragraphs

    def _remove_noise_lines(self, paragraphs: List[str]) -> tuple:
        """
        移除噪声行:
          - 纯符号行（无字母/数字/中文）
          - 超短行（< MIN_PARAGRAPH_CHARS 字符）
          - 纯数字行（如页码 "1", "2"）
        """
        cleaned = []
        removed = 0
        # 纯页码模式
        page_num_re = re.compile(r"^(第?\s*\d+\s*页?|[ivxlcdmIVXLCDM]+)$")

        for p in paragraphs:
            # 纯页码
            if page_num_re.match(p.strip()):
                removed += 1
                continue
            # 超短行
            if len(p.strip()) < self.MIN_PARAGRAPH_CHARS:
                removed += 1
                continue
            # 纯符号行（不含任何文字字符）
            if not re.search(r"[\u4e00-\u9fff\w]", p):
                removed += 1
                continue
            cleaned.append(p)

        return cleaned, removed

    @staticmethod
    def _remove_exact_duplicates(paragraphs: List[str]) -> tuple:
        """段落精确去重（保留首次出现）"""
        seen: Set[str] = set()
        result = []
        removed = 0
        for p in paragraphs:
            normalized = p.strip()
            if normalized in seen:
                removed += 1
                continue
            seen.add(normalized)
            result.append(p)
        return result, removed

    def _remove_near_duplicates(self, paragraphs: List[str]) -> tuple:
        """
        段落近似去重（基于 Jaccard 相似度，按 4-gram 集合）。
        O(n²) 但对校园文档（通常 < 200 段）足够快。
        """
        if len(paragraphs) < 2:
            return paragraphs, 0

        # 预计算每个段落的 4-gram 集合
        ngram_sets = [self._char_ngrams(p, n=4) for p in paragraphs]
        keep = [True] * len(paragraphs)
        removed = 0

        for i in range(len(paragraphs)):
            if not keep[i]:
                continue
            for j in range(i + 1, len(paragraphs)):
                if not keep[j]:
                    continue
                sim = self._jaccard(ngram_sets[i], ngram_sets[j])
                if sim >= self.NEAR_DUP_THRESHOLD:
                    keep[j] = False
                    removed += 1

        result = [p for p, k in zip(paragraphs, keep) if k]
        return result, removed

    def _remove_header_footer_repeats(self, paragraphs: List[str]) -> List[str]:
        """
        检测并移除在文档中出现 ≥ 3 次的完全相同的短段落
        （通常是页眉/页脚，如 "教务处通知"、"XXX大学"等）。
        """
        if len(paragraphs) < 6:
            return paragraphs

        # 统计短段落（< 40 字符）出现频率
        short_para_counts: dict = {}
        for p in paragraphs:
            if len(p) < 40:
                key = p.strip()
                short_para_counts[key] = short_para_counts.get(key, 0) + 1

        # 出现 ≥ 3 次的视为页眉/页脚
        hf_set = {k for k, v in short_para_counts.items() if v >= 3}
        if not hf_set:
            return paragraphs

        result = [p for p in paragraphs if p.strip() not in hf_set]
        removed_count = len(paragraphs) - len(result)
        if removed_count > 0:
            logger.debug("[TextCleaner] 移除页眉/页脚重复: %d 段", removed_count)
        return result

    @staticmethod
    def _normalize_punctuation(text: str) -> str:
        """
        标点符号标准化（仅处理常见混乱情况，不改变中文标点风格）:
          - 多个连续句号 → 单个
          - "。." → "。"
          - 多余空格清理
        """
        # 连续中英文句号混用
        text = re.sub(r"[。.]{2,}", "。", text)
        # 中文后紧跟英文标点
        text = re.sub(r"([\u4e00-\u9fff])\s*([,;:!?])", r"\1，" if r"\2" == "," else r"\1\2", text)
        return text

    @staticmethod
    def _strip_trailing_whitespace(text: str) -> str:
        """移除每行尾部空白"""
        return "\n".join(line.rstrip() for line in text.split("\n"))

    # ── 工具方法 ──────────────────────────────

    @staticmethod
    def _char_ngrams(text: str, n: int = 4) -> Set[str]:
        """提取字符级 n-gram 集合"""
        text = text.strip()
        if len(text) < n:
            return {text}
        return {text[i:i + n] for i in range(len(text) - n + 1)}

    @staticmethod
    def _jaccard(set_a: set, set_b: set) -> float:
        """计算两个集合的 Jaccard 相似度"""
        if not set_a and not set_b:
            return 1.0
        if not set_a or not set_b:
            return 0.0
        intersection = len(set_a & set_b)
        union = len(set_a | set_b)
        return intersection / union if union > 0 else 0.0


# ─────────────────────────────────────────────
#  命令行快速测试入口
# ─────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    from pathlib import Path

    logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")

    if len(sys.argv) < 2:
        # 用示例文本演示
        sample = (
            "   教务处通知   \n\n"
            "  关于2026年推荐优秀应届本科毕业生\n"
            "  免试攻读硕士学位研究生工作的通知  \n\n"
            "根据教育部相关文件精神，结合我校实际情况，\n"
            "现将2026年推免工作有关事项通知如下：\n\n"
            "一、申请条件\n"
            "1. 全日制普通本科应届毕业生；\n"
            "2. 学业成绩排名在本专业前30％；\n"
            "3. 无违纪处分记录。\n\n"
            "  教务处通知  \n\n"  # 页眉重复
            "二、工作安排\n"
            "各学院应于9月15日前完成初审工作。\n\n"
            "教务处\n"
            "2026年9月1日\n\n"
            "1\n"  # 页码噪声
        )

        # 构造一个简易 ParsedDocument
        from data_pipeline.doc_parser import ParsedDocument
        doc = ParsedDocument(
            doc_id="DOC_00000001",
            title="保研政策通知示例",
            content=sample,
            source_path="example.txt",
            file_type="txt",
        )

        cleaner = TextCleaner()
        result = cleaner.clean(doc)
        print("=== 清洗后文本 ===")
        print(result.content)
        print(f"\n=== 统计 === {result.cleaning_stats}")
        sys.exit(0)

    # 从文件解析后清洗
    from data_pipeline.doc_parser import DocParser

    parser = DocParser()
    cleaner = TextCleaner()

    for fp in sys.argv[1:]:
        try:
            raw = parser.parse(fp)
            cleaned = cleaner.clean(raw)
            print(f"✓ [{cleaned.file_type}] {cleaned.title}")
            print(f"  字符: {cleaned.cleaning_stats['original_chars']} → {cleaned.cleaning_stats['final_chars']}")
            print(f"  预览: {cleaned.content[:300]}...")
            print()
        except Exception as e:
            print(f"✗ {fp}: {e}")
