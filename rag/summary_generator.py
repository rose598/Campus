"""课程结构化总结生成 —— 基于提取结果生成课程概览

输入 CourseExtractor 的提取结果，生成结构化总结：
{课程名, 大纲/知识点, 重点, 考核, 参考资料}

两种生成模式：
- LLM 模式：将提取结果润色为连贯的课程概览文本
- 模板模式：LLM 不可用时按固定模板组装（保证始终有输出）
"""
from typing import Dict, Any, List, Optional


SUMMARY_SYSTEM_PROMPT = """你是高校课程顾问。基于提供的课程结构化信息，写一段简洁的课程总结。

要求：
1. 150 字以内，分要点陈述
2. 只使用提供的信息，不得编造
3. 依次覆盖：课程主要内容、学习重点、考核方式
4. 直接输出总结文本，不要标题或前缀"""


class SummaryGenerator:
    """课程总结生成器"""

    def generate(
        self,
        course_name: str,
        course_code: str,
        extracted: Dict[str, Any],
        sources: Optional[List[str]] = None,
        user_id: str = "default",
    ) -> str:
        """生成课程总结文本

        Args:
            course_name: 课程名称
            course_code: 课程代码（可为空）
            extracted: CourseExtractor.extract 的输出
            sources: 参考资料标题列表
            user_id: 用户标识（用于限速）

        Returns:
            结构化总结文本（markdown 友好）
        """
        extracted = extracted or {}
        knowledge_points = extracted.get("knowledge_points", [])
        key_points = extracted.get("key_points", [])
        assessment = extracted.get("assessment", "")

        # 无任何提取内容 → 模板兜底
        if not knowledge_points and not key_points and not assessment:
            return self._template_summary(
                course_name, course_code, [], [], "", sources
            )

        # 优先 LLM 润色
        try:
            from utils import get_llm_client

            llm = get_llm_client()
            user_message = (
                f"课程：{course_name}（{course_code}）\n"
                f"知识点：{'; '.join(knowledge_points[:6])}\n"
                f"重点：{'; '.join(key_points[:6])}\n"
                f"考核方式：{assessment}"
            )
            polished = llm.call(
                system_prompt=SUMMARY_SYSTEM_PROMPT,
                user_message=user_message,
                user_id=user_id,
            )
            polished = (polished or "").strip()
            if polished:
                return self._with_sources(polished, sources)
        except Exception:
            pass

        # LLM 不可用 → 模板组装
        return self._template_summary(
            course_name, course_code, knowledge_points, key_points, assessment, sources
        )

    # ── internal ───────────────────────────────────────────────────────

    @staticmethod
    def _template_summary(
        course_name: str,
        course_code: str,
        knowledge_points: List[str],
        key_points: List[str],
        assessment: str,
        sources: Optional[List[str]],
    ) -> str:
        lines = []
        title = f"《{course_name}》" + (f"（{course_code}）" if course_code else "")
        lines.append(f"课程总结：{title}")

        if knowledge_points:
            lines.append("📖 主要内容：" + "；".join(knowledge_points[:5]))
        if key_points:
            lines.append("🎯 学习重点：" + "；".join(key_points[:5]))
        if assessment:
            lines.append(f"📝 考核方式：{assessment}")
        if not knowledge_points and not key_points and not assessment:
            lines.append("暂无足够的资料生成总结，请补充课程大纲或课件。")

        return SummaryGenerator._with_sources("\n".join(lines), sources)

    @staticmethod
    def _with_sources(text: str, sources: Optional[List[str]]) -> str:
        titles = [s for s in (sources or []) if s][:3]
        if not titles:
            return text
        refs = "、".join(f"《{t}》" for t in titles)
        return f"{text}\n\n📎 参考资料：{refs}"
