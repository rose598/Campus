"""课程资料结构化提取 —— LLM 提取知识点/重点/考核方式

从课程资料文本中提取三类结构化信息：
- knowledge_points: 知识点列表
- key_points:       重点章节/核心考点
- assessment:       考核方式

LLM 可用时输出 JSON；不可用时回退为规则提取（按章节标记切分），
保证学伴流程不因 LLM 故障中断。
"""
import json
import re
from typing import Dict, Any, List


EXTRACT_SYSTEM_PROMPT = """你是高校课程资料分析专家。

任务：从给定的课程资料文本中提取结构化信息。

输出严格的 JSON（不要 markdown 代码块、不要解释）：
{
  "knowledge_points": ["知识点1", "知识点2"],
  "key_points": ["重点1", "重点2"],
  "assessment": "考核方式描述"
}

规则：
1. 每个列表项不超过 30 字
2. 列表最多 8 项，按重要性排序
3. 资料中未提及的字段用空列表/空字符串，不得编造"""


class CourseExtractor:
    """课程资料结构化提取器"""

    def extract(
        self,
        course_name: str,
        material_text: str,
        user_id: str = "default",
    ) -> Dict[str, Any]:
        """提取课程结构化信息

        Returns:
            {
                "course_name": str,
                "knowledge_points": List[str],
                "key_points": List[str],
                "assessment": str,
                "source": "llm" | "rules",   # 提取方式
            }
        """
        material_text = (material_text or "").strip()
        if not material_text:
            return self._empty_result(course_name, "rules")

        try:
            from utils import get_llm_client

            llm = get_llm_client()
            user_message = (
                f"课程名称：{course_name}\n\n"
                f"课程资料：\n{material_text[:4000]}"
            )
            raw = llm.call(
                system_prompt=EXTRACT_SYSTEM_PROMPT,
                user_message=user_message,
                user_id=user_id,
            )
            parsed = self._parse_json(raw)
            if parsed is not None:
                return {
                    "course_name": course_name,
                    "knowledge_points": parsed.get("knowledge_points", [])[:8],
                    "key_points": parsed.get("key_points", [])[:8],
                    "assessment": parsed.get("assessment", ""),
                    "source": "llm",
                }
        except Exception:
            pass

        # LLM 不可用或输出非法 → 规则提取
        return self._rule_based_extract(course_name, material_text)

    # ── internal ───────────────────────────────────────────────────────

    @staticmethod
    def _parse_json(text: str) -> Dict[str, Any] | None:
        """宽容解析 LLM JSON 输出（容忍代码块包裹/前后缀）"""
        if not text:
            return None
        t = text.strip()
        # 去除 markdown 代码块
        m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", t, re.DOTALL)
        if m:
            t = m.group(1)
        # 截取首个 {...} 片段
        start, end = t.find("{"), t.rfind("}")
        if start == -1 or end <= start:
            return None
        try:
            data = json.loads(t[start:end + 1])
        except (json.JSONDecodeError, ValueError):
            return None
        if not isinstance(data, dict):
            return None
        # 字段类型兜底
        for key in ("knowledge_points", "key_points"):
            if not isinstance(data.get(key), list):
                data[key] = []
            data[key] = [str(x) for x in data[key] if str(x).strip()]
        if not isinstance(data.get("assessment"), str):
            data["assessment"] = ""
        return data

    @staticmethod
    def _rule_based_extract(course_name: str, text: str) -> Dict[str, Any]:
        """规则提取：按中文序号/标题切分章节要点"""
        knowledge_points: List[str] = []
        key_points: List[str] = []
        assessment = ""

        # 按"一、二、…"或"1. 2."切分条目
        segments = re.split(r"\n+", text)
        for seg in segments:
            seg = seg.strip()
            if not seg:
                continue
            # 考核方式关键词
            if re.search(r"考核|考试|闭卷|开卷|成绩.*[占计]|平时.*\d+%|期末.*\d+%", seg):
                if not assessment:
                    assessment = seg[:100]
                continue
            # 重点关键词
            if re.search(r"重点|核心|必考|掌握", seg):
                key_points.append(seg[:60])
                continue
            # 其余视为知识点（带序号的条目优先）
            if re.match(r"^[一二三四五六七八九十\d][、.．]", seg):
                knowledge_points.append(seg[:60])

        return {
            "course_name": course_name,
            "knowledge_points": knowledge_points[:8],
            "key_points": key_points[:8],
            "assessment": assessment,
            "source": "rules",
        }

    @staticmethod
    def _empty_result(course_name: str, source: str) -> Dict[str, Any]:
        return {
            "course_name": course_name,
            "knowledge_points": [],
            "key_points": [],
            "assessment": "",
            "source": source,
        }
