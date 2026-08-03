"""
metadata_annotator.py — 元数据标注器（LLM 辅助 + 规则兜底）

职责:
  - 自动分类文档类别（academic / life / course）
  - 提取关键词标签（tags）
  - 推断发布日期与失效日期
  - 使用 LLM 辅助标注（离线/隐私模式下回退到纯规则）
  - 输出 CampusDocument 兼容结构

使用方式:
  from data_pipeline.metadata_annotator import MetadataAnnotator

  annotator = MetadataAnnotator()
  annotated = annotator.annotate(cleaned_document)
  # annotated 是一个 CampusDocument 实例
"""

from __future__ import annotations

import json
import logging
import re
from datetime import date, timedelta
from typing import List, Literal, Optional, Tuple

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
#  标注结果结构
# ─────────────────────────────────────────────

class AnnotatedDocument(BaseModel):
    """标注后的文档，与 CampusDocument 结构对齐"""
    doc_id: str
    category: Literal["academic", "life", "course"]
    title: str
    content: str
    source_url: Optional[str] = None
    publish_date: Optional[date] = None
    expiry_date: Optional[date] = None
    tags: List[str] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    annotation_source: str = Field(default="rule", description="标注来源: llm / rule / hybrid")


# ─────────────────────────────────────────────
#  分类关键词词典
# ─────────────────────────────────────────────

_ACADEMIC_KEYWORDS = [
    "保研", "推免", "转专业", "选课", "补考", "学分", "绩点", "GPA",
    "毕业论文", "毕业设计", "学位", "毕业", "肄业", "休学", "复学",
    "退学", "学籍", "成绩单", "教务", "考试", "四六级", "考研",
    "奖学金", "助学金", "贷款", "学费", "培养方案", "教学计划",
    "教学大纲", "课程安排", "排课", "选课系统", "重修", "免修",
    "交换生", "留学", "双学位", "辅修", "招生", "录取",
]

_LIFE_KEYWORDS = [
    "宿舍", "食堂", "图书馆", "校医院", "体检", "医保",
    "快递", "公交", "校车", "停车", "网络", "VPN", "校园网",
    "一卡通", "饭卡", "水卡", "社团", "学生会", "志愿者",
    "心理咨询", "就业指导", "实习", "兼职", "失物招领",
    "安全", "消防", "门禁", "报修", "后勤",
]

_COURSE_KEYWORDS = [
    "课程大纲", "课件", "PPT", "讲义", "期末", "期中考试",
    "作业", "实验", "上机", "课程设计", "知识点", "重点",
    "复习资料", "习题", "答案", "参考书", "教材", "先修",
    "考核方式", "评分标准", "学时", "授课", "教师",
]

# 分类 → 关键词映射
_CATEGORY_KEYWORDS = {
    "academic": _ACADEMIC_KEYWORDS,
    "life": _LIFE_KEYWORDS,
    "course": _COURSE_KEYWORDS,
}

# URL 路径模式 → 分类映射
_URL_PATTERNS = {
    r"jwc|教务|academic|teach": "academic",
    r"life|后勤|宿舍|library|图书": "life",
    r"course|课|teach|lesson": "course",
}


# ─────────────────────────────────────────────
#  日期提取正则
# ─────────────────────────────────────────────

_DATE_PATTERNS = [
    # 2026年9月1日 / 2026年09月01日
    re.compile(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日"),
    # 2026-09-01 / 2026/09/01
    re.compile(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})"),
    # 2026.09.01
    re.compile(r"(\d{4})\.(\d{1,2})\.(\d{1,2})"),
]


# ─────────────────────────────────────────────
#  元数据标注器
# ─────────────────────────────────────────────

class MetadataAnnotator:
    """
    文档元数据标注器。

    标注流程:
      1. 规则分类（关键词匹配 + URL 模式）
      2. [可选] LLM 辅助分类（提升准确率）
      3. 日期提取（正则匹配）
      4. 关键词标签提取（TF 高频词 + 预定义标签）

    示例:
        >>> annotator = MetadataAnnotator(use_llm=False)
        >>> doc = annotator.annotate(cleaned_doc)
        >>> doc.category
        'academic'
    """

    def __init__(self, use_llm: bool = True, llm_client=None):
        """
        Args:
            use_llm: 是否使用 LLM 辅助标注
            llm_client: LLMClient 实例（use_llm=True 时必需）
        """
        self._use_llm = use_llm
        self._llm_client = llm_client

    # ── 公共接口 ──────────────────────────────

    def annotate(self, doc) -> AnnotatedDocument:
        """
        对 CleanedDocument 执行元数据标注。

        Args:
            doc: CleanedDocument 实例

        Returns:
            AnnotatedDocument
        """
        title = doc.title
        content = doc.content
        source_url = getattr(doc, "source_url", None) or None
        doc_id = doc.doc_id

        # 1. 分类
        category, cat_confidence = self._classify(title, content, source_url)

        # 2. LLM 辅助分类（可选）
        annotation_source = "rule"
        if self._use_llm and self._llm_client:
            try:
                llm_cat, llm_tags = self._llm_classify(title, content[:500])
                if llm_cat:
                    category = llm_cat
                    cat_confidence = min(cat_confidence + 0.1, 1.0)
                    annotation_source = "hybrid"
            except Exception as e:
                logger.warning("[Annotator] LLM 分类失败，回退规则: %s", e)

        if annotation_source == "rule":
            annotation_source = "rule"

        # 3. 日期提取
        publish_date, expiry_date = self._extract_dates(content, doc.metadata if hasattr(doc, "metadata") else {})

        # 4. 标签提取
        tags = self._extract_tags(title, content, category)

        logger.info(
            "[Annotator] %s: category=%s (%.2f) | tags=%d | date=%s | source=%s",
            doc_id, category, cat_confidence, len(tags), publish_date, annotation_source,
        )

        return AnnotatedDocument(
            doc_id=doc_id,
            category=category,
            title=title,
            content=content,
            source_url=source_url,
            publish_date=publish_date,
            expiry_date=expiry_date,
            tags=tags,
            confidence=cat_confidence,
            annotation_source=annotation_source,
        )

    def annotate_batch(self, docs: list) -> List[AnnotatedDocument]:
        """批量标注"""
        results = []
        for doc in docs:
            try:
                results.append(self.annotate(doc))
            except Exception as e:
                logger.warning("[Annotator] 跳过文档 %s: %s", getattr(doc, "doc_id", "?"), e)
        logger.info("[Annotator] 批量标注完成: %d/%d", len(results), len(docs))
        return results

    # ── 分类 ──────────────────────────────────

    def _classify(
        self, title: str, content: str, source_url: Optional[str]
    ) -> Tuple[Literal["academic", "life", "course"], float]:
        """
        规则分类：关键词匹配 + URL 模式。

        Returns:
            (category, confidence)
        """
        scores = {"academic": 0, "life": 0, "course": 0}
        text = f"{title} {content[:1000]}".lower()

        # 关键词匹配
        for cat, keywords in _CATEGORY_KEYWORDS.items():
            for kw in keywords:
                if kw.lower() in text:
                    scores[cat] += 1

        # URL 模式加分
        if source_url:
            for pattern, cat in _URL_PATTERNS.items():
                if re.search(pattern, source_url, re.IGNORECASE):
                    scores[cat] += 3

        # 标题关键词加权（标题命中权重 x3）
        title_lower = title.lower()
        for cat, keywords in _CATEGORY_KEYWORDS.items():
            for kw in keywords:
                if kw.lower() in title_lower:
                    scores[cat] += 3

        # 选出得分最高的
        max_score = max(scores.values())
        if max_score == 0:
            # 无匹配，默认 academic
            return "academic", 0.3

        best_cat = max(scores, key=scores.get)
        # 置信度：得分归一化
        total = sum(scores.values())
        confidence = min(scores[best_cat] / max(total, 1), 1.0)

        return best_cat, round(confidence, 2)

    def _llm_classify(self, title: str, content_snippet: str) -> Tuple[Optional[str], List[str]]:
        """
        LLM 辅助分类。

        Returns:
            (category, tags) — category 为 None 表示 LLM 未返回有效结果
        """
        system_prompt = """你是一个校园文档分类助手。请将文档分类为以下三类之一：
- academic（教务/政策/学业相关）
- life（校园生活/后勤/服务）
- course（课程资料/教学相关）

同时提取 3-5 个关键词标签。

请以 JSON 格式返回，格式如下：
{"category": "academic", "tags": ["保研", "推免", "2026"]}

只返回 JSON，不要其他内容。"""

        user_msg = f"标题：{title}\n内容摘要：{content_snippet[:300]}"

        response = self._llm_client.call(system_prompt, user_msg)

        # 解析 JSON
        try:
            # 清理可能的 markdown 代码块标记
            clean = response.strip()
            if clean.startswith("```"):
                clean = re.sub(r"^```(?:json)?\s*", "", clean)
                clean = re.sub(r"\s*```$", "", clean)
            data = json.loads(clean)
            cat = data.get("category")
            tags = data.get("tags", [])
            if cat in ("academic", "life", "course"):
                return cat, [str(t) for t in tags[:5]]
            return None, []
        except (json.JSONDecodeError, KeyError, TypeError):
            logger.debug("[Annotator] LLM 返回无法解析: %s", response[:100])
            return None, []

    # ── 日期提取 ──────────────────────────────

    def _extract_dates(
        self, content: str, metadata: dict
    ) -> Tuple[Optional[date], Optional[date]]:
        """
        从内容和元数据中提取发布日期和失效日期。
        """
        publish_date = None
        expiry_date = None

        # 1. 从 metadata 中获取
        for key in ("publish_date", "created", "date", "publishDate"):
            val = metadata.get(key)
            if val:
                parsed = self._parse_date_str(str(val))
                if parsed:
                    publish_date = parsed
                    break

        # 2. 从内容中提取（取第一个匹配日期作为发布日期）
        if publish_date is None:
            for pattern in _DATE_PATTERNS:
                match = pattern.search(content[:2000])
                if match:
                    try:
                        y, m, d = int(match.group(1)), int(match.group(2)), int(match.group(3))
                        publish_date = date(y, m, d)
                        break
                    except (ValueError, IndexError):
                        continue

        # 3. 推断失效日期（默认 1 年后）
        if publish_date:
            default_days = 365
            try:
                from utils.config_loader import get as _cfg_get
                default_days = _cfg_get("campus_qa.default_expiry_days", 365)
            except Exception:
                pass
            expiry_date = publish_date + timedelta(days=default_days)

            # 从内容中检测失效日期关键词
            expiry_patterns = [
                re.compile(r"(?:失效|作废|废止|截止|截至|到期).{0,10}?(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日"),
                re.compile(r"(?:失效|作废|废止|截止|截至|到期).{0,10}?(\d{4})[-/](\d{1,2})[-/](\d{1,2})"),
            ]
            for pat in expiry_patterns:
                match = pat.search(content[:3000])
                if match:
                    try:
                        y, m, d = int(match.group(1)), int(match.group(2)), int(match.group(3))
                        expiry_date = date(y, m, d)
                        break
                    except (ValueError, IndexError):
                        continue

        return publish_date, expiry_date

    @staticmethod
    def _parse_date_str(s: str) -> Optional[date]:
        """尝试解析日期字符串"""
        for pattern in _DATE_PATTERNS:
            match = pattern.match(s.strip())
            if match:
                try:
                    return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
                except (ValueError, IndexError):
                    continue
        # 尝试 ISO 格式
        try:
            return date.fromisoformat(s.strip()[:10])
        except (ValueError, IndexError):
            return None

    # ── 标签提取 ──────────────────────────────

    def _extract_tags(self, title: str, content: str, category: str) -> List[str]:
        """
        提取关键词标签（3-5 个）。

        策略：
          1. 从预定义关键词中匹配
          2. 统计高频中文词组（2-4 字）
          3. 去重并排序
        """
        tags = set()
        text = f"{title} {content[:1500]}"

        # 1. 预定义关键词匹配
        all_keywords = _CATEGORY_KEYWORDS.get(category, [])
        for kw in all_keywords:
            if kw in text:
                tags.add(kw)
                if len(tags) >= 5:
                    break

        # 2. 如果标签不够，提取高频 2-4 字词组
        if len(tags) < 3:
            # 简单提取连续中文词组
            chinese_phrases = re.findall(r"[\u4e00-\u9fff]{2,4}", title)
            for phrase in chinese_phrases:
                if phrase not in tags and len(phrase) >= 2:
                    tags.add(phrase)
                    if len(tags) >= 5:
                        break

        return list(tags)[:5]


# ─────────────────────────────────────────────
#  命令行快速测试入口
# ─────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")

    from data_pipeline.doc_parser import ParsedDocument
    from data_pipeline.text_cleaner import TextCleaner

    sample_text = """关于2026年推荐优秀应届本科毕业生免试攻读硕士学位研究生工作的通知

各学院：

根据教育部相关文件精神，结合我校实际情况，现将2026年推免工作有关事项通知如下：

一、申请条件
1. 全日制普通本科应届毕业生；
2. 学业成绩排名在本专业前30%；
3. 无违纪处分记录。

二、时间安排
申请时间：2026年9月1日至9月15日
审核时间：2026年9月16日至9月30日

三、申请材料
1. 保研申请表
2. 成绩单（教务处盖章）
3. 综合素质评价表

教务处
2026年8月20日"""

    doc = ParsedDocument(
        doc_id="DOC_00000001",
        title="2026年保研推免通知",
        content=sample_text,
        source_path="example.txt",
        file_type="txt",
    )

    cleaner = TextCleaner()
    cleaned = cleaner.clean(doc)

    annotator = MetadataAnnotator(use_llm=False)
    result = annotator.annotate(cleaned)

    print("=== 标注结果 ===")
    print(f"  doc_id:    {result.doc_id}")
    print(f"  category:  {result.category}")
    print(f"  confidence: {result.confidence}")
    print(f"  tags:      {result.tags}")
    print(f"  publish:   {result.publish_date}")
    print(f"  expiry:    {result.expiry_date}")
    print(f"  source:    {result.annotation_source}")
