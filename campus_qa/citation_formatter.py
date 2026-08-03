"""
citation_formatter.py — 来源引用格式化器

职责:
  - 将检索结果格式化为带来源引用的结构化输出
  - 生成引用卡片数据（标题 + 来源 + 日期 + URL）
  - 支持 Markdown / JSON / 纯文本输出格式
  - 为 LLM 生成的回答附加引用标注

使用方式:
  from campus_qa.citation_formatter import CitationFormatter

  formatter = CitationFormatter()
  formatted = formatter.format_results(ranked_results)
  # formatted.citations → [{"index": 1, "title": "...", "source": "...", ...}]
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
#  引用数据结构
# ─────────────────────────────────────────────

class Citation(BaseModel):
    """单条引用"""
    index: int = Field(..., ge=1, description="引用编号（从 1 开始）")
    doc_id: str = Field(default="", description="文档 ID")
    title: str = Field(default="", description="文档标题")
    source_url: Optional[str] = Field(None, description="来源 URL")
    category: str = Field(default="", description="文档分类")
    publish_date: Optional[str] = Field(None, description="发布日期")
    snippet: str = Field(default="", description="内容片段（前 100 字符）")
    relevance_score: float = Field(default=0.0, description="相关度分数")


class FormattedResponse(BaseModel):
    """格式化后的完整响应"""
    answer: str = Field(default="", description="LLM 生成的回答文本（含引用标注）")
    citations: List[Citation] = Field(default_factory=list, description="引用列表")
    intent: str = Field(default="", description="意图分类")
    query: str = Field(default="", description="原始查询")


# ─────────────────────────────────────────────
#  分类显示名映射
# ─────────────────────────────────────────────

_CATEGORY_DISPLAY = {
    "academic": "教务政策",
    "life": "校园生活",
    "course": "课程资料",
    "policy": "教务政策",
    "general": "通用",
}


# ─────────────────────────────────────────────
#  引用格式化器
# ─────────────────────────────────────────────

class CitationFormatter:
    """
    来源引用格式化器。

    功能:
      - 将 RankedResult/FusedResult 列表转换为 Citation 列表
      - 为回答文本添加 [1][2] 引用标注
      - 生成引用卡片数据（供前端渲染）
      - 支持 Markdown 输出

    示例:
        >>> formatter = CitationFormatter()
        >>> response = formatter.format_with_answer(
        ...     answer="保研需要学业成绩排名前30%[1]。",
        ...     results=ranked_results,
        ... )
        >>> response.citations[0].title
        '2026年保研推免通知'
    """

    def __init__(self, max_snippet_chars: int = 100):
        """
        Args:
            max_snippet_chars: 引用片段最大字符数
        """
        self._max_snippet = max_snippet_chars

    # ── 公共接口 ──────────────────────────────

    def format_results(self, results: List[Any]) -> List[Citation]:
        """
        将结果列表转换为 Citation 列表。

        Args:
            results: RankedResult / FusedResult 列表

        Returns:
            Citation 列表
        """
        citations = []
        seen_docs = set()

        for i, item in enumerate(results):
            if hasattr(item, "model_dump"):
                item = item.model_dump()
            elif hasattr(item, "dict"):
                item = item.dict()

            doc_id = item.get("doc_id", "")

            # 同一文档只引用一次（取第一个分块）
            if doc_id in seen_docs:
                continue
            seen_docs.add(doc_id)

            content = item.get("content", "")
            snippet = content[:self._max_snippet] + ("..." if len(content) > self._max_snippet else "")

            citations.append(Citation(
                index=len(citations) + 1,
                doc_id=doc_id,
                title=item.get("doc_title", item.get("title", "未知文档")),
                source_url=item.get("source_url"),
                category=_CATEGORY_DISPLAY.get(
                    item.get("category", ""), item.get("category", "")
                ),
                publish_date=item.get("publish_date"),
                snippet=snippet,
                relevance_score=float(item.get("final_score", item.get("score", 0.0))),
            ))

        return citations

    def format_with_answer(
        self,
        answer: str,
        results: List[Any],
        query: str = "",
        intent: str = "",
    ) -> FormattedResponse:
        """
        格式化完整响应（回答 + 引用）。

        Args:
            answer: LLM 生成的回答文本
            results: 检索结果列表
            query: 原始查询
            intent: 意图分类

        Returns:
            FormattedResponse
        """
        citations = self.format_results(results)
        return FormattedResponse(
            answer=answer,
            citations=citations,
            intent=intent,
            query=query,
        )

    def add_citation_marks(
        self,
        answer: str,
        citations: List[Citation],
    ) -> str:
        """
        在回答文本中插入引用标注 [1][2]。

        简单策略：在每句话末尾按顺序插入引用。

        Args:
            answer: 原始回答文本
            citations: 引用列表

        Returns:
            带引用标注的文本
        """
        if not citations:
            return answer

        # 如果文本中已有 [数字] 引用，不重复添加
        import re
        if re.search(r"\[\d+\]", answer):
            return answer

        # 在末尾添加引用列表
        marks = " ".join(f"[{c.index}]" for c in citations)
        return f"{answer}\n\n参考来源：{marks}"

    # ── Markdown 输出 ─────────────────────────

    def to_markdown(self, response: FormattedResponse) -> str:
        """
        将 FormattedResponse 转为 Markdown 格式。

        Args:
            response: 格式化响应

        Returns:
            Markdown 文本
        """
        lines = []

        # 回答
        if response.answer:
            lines.append(response.answer)
            lines.append("")

        # 引用卡片
        if response.citations:
            lines.append("---")
            lines.append("**参考来源：**")
            lines.append("")

            for c in response.citations:
                date_str = f" ({c.publish_date})" if c.publish_date else ""
                cat_str = f" [{c.category}]" if c.category else ""

                if c.source_url:
                    lines.append(f"[{c.index}] [{c.title}]({c.source_url}){cat_str}{date_str}")
                else:
                    lines.append(f"[{c.index}] {c.title}{cat_str}{date_str}")

                if c.snippet:
                    lines.append(f"    {c.snippet}")
                lines.append("")

        return "\n".join(lines)

    # ── JSON 输出 ─────────────────────────────

    def to_json(self, response: FormattedResponse) -> Dict:
        """
        将 FormattedResponse 转为 JSON 字典。

        Args:
            response: 格式化响应

        Returns:
            JSON 字典
        """
        return {
            "query": response.query,
            "intent": response.intent,
            "answer": response.answer,
            "citations": [
                {
                    "index": c.index,
                    "doc_id": c.doc_id,
                    "title": c.title,
                    "source_url": c.source_url,
                    "category": c.category,
                    "publish_date": c.publish_date,
                    "snippet": c.snippet,
                }
                for c in response.citations
            ],
        }


# ─────────────────────────────────────────────
#  命令行测试
# ─────────────────────────────────────────────

if __name__ == "__main__":
    import json

    logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")

    formatter = CitationFormatter()

    # 模拟结果
    mock_results = [
        {
            "doc_id": "DOC_001",
            "doc_title": "2026年保研推免通知",
            "content": "保研条件：学业成绩排名在本专业前30%，且无不及格科目记录。",
            "category": "academic",
            "publish_date": "2026-08-20",
            "source_url": "https://jwc.example.edu.cn/notice/baoyan.html",
            "final_score": 0.95,
        },
        {
            "doc_id": "DOC_002",
            "doc_title": "推免工作管理办法",
            "content": "各学院应于9月15日前完成初审工作。",
            "category": "academic",
            "publish_date": "2026-08-20",
            "final_score": 0.85,
        },
    ]

    answer = "根据教务处通知，保研需要满足以下条件：\n1. 学业成绩排名在本专业前30%[1]\n2. 无不及格科目记录[1]\n3. 各学院9月15日前完成初审[2]"

    citations = formatter.format_results(mock_results)
    response = formatter.format_with_answer(answer, mock_results, query="保研条件", intent="policy")

    print("=== 引用格式化测试 ===\n")
    print("引用列表:")
    for c in citations:
        print(f"  [{c.index}] {c.title} ({c.category}) | {c.publish_date}")

    print(f"\nMarkdown 输出:")
    print(formatter.to_markdown(response))

    print(f"\nJSON 输出:")
    print(json.dumps(formatter.to_json(response), ensure_ascii=False, indent=2))
