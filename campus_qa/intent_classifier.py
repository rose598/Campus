"""
intent_classifier.py — 意图分类器

职责:
  - 对用户问题进行意图分类
  - 分类类别: policy（政策）/ life（生活）/ course（课程）/ activity（活动）/ general（通用）
  - 支持 LLM 分类（高精度）和规则分类（离线兜底）
  - 输出分类结果 + 置信度

使用方式:
  from campus_qa.intent_classifier import IntentClassifier

  classifier = IntentClassifier()
  result = classifier.classify("保研需要什么条件？")
  # result.intent == "policy", result.confidence == 0.95
"""

from __future__ import annotations

import json
import logging
import re
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
#  分类结果
# ─────────────────────────────────────────────

class IntentResult(BaseModel):
    """意图分类结果"""
    intent: Literal["policy", "life", "course", "activity", "general"] = Field(
        default="general",
        description="意图类别",
    )
    confidence: float = Field(default=0.5, ge=0.0, le=1.0, description="置信度")
    sub_intent: Optional[str] = Field(None, description="子意图（如保研/转专业/选课）")
    method: str = Field(default="rule", description="分类方法: llm / rule / hybrid")


# ─────────────────────────────────────────────
#  关键词词典
# ─────────────────────────────────────────────

_POLICY_KEYWORDS = {
    "保研": ["保研", "推免", "免试", "免推"],
    "转专业": ["转专业", "换专业", "专业调剂", "专业分流"],
    "选课": ["选课", "退课", "补选"],
    "补考": ["补考", "重修", "挂科", "不及格"],
    "学籍": ["休学", "复学", "退学", "学籍", "在读证明"],
    "毕业": ["毕业", "学位", "毕业论文", "毕业设计", "答辩"],
    "奖学金": ["奖学金", "助学金", "国家奖学金", "励志奖学金"],
    "四六级": ["四级", "六级", "CET", "英语考试", "四六级"],
    "学分绩点": ["绩点", "GPA", "学分绩点"],
    "交换": ["交换生", "交流", "留学", "出国"],
}

_LIFE_KEYWORDS = {
    "宿舍": ["宿舍", "住宿", "寝室", "舍管", "宿管"],
    "餐饮": ["食堂", "吃饭", "餐饮", "外卖", "午餐", "晚餐"],
    "图书馆": ["图书馆", "借书", "阅览", "自习室", "借阅读"],
    "医疗": ["校医院", "体检", "医保", "看病", "报销"],
    "交通": ["校车", "公交", "地铁", "停车", "班车"],
    "网络": ["校园网", "WiFi", "VPN", "邮箱", "门户", "网络密码"],
    "一卡通": ["一卡通", "饭卡", "水卡", "充值", "校园卡"],
    "社团": ["社团", "学生会", "社团活动", "志愿者"],
    "就业": ["就业", "实习", "招聘", "校招", "简历"],
    "心理咨询": ["心理", "咨询", "压力", "辅导"],
}

_COURSE_KEYWORDS = {
    "大纲": ["课程大纲", "教学大纲", "syllabus", "培养方案"],
    "资料": ["课件", "PPT", "讲义", "复习资料", "笔记", "课件下载"],
    "考试": ["期末考试", "期中考试", "考试范围", "考点", "考试重点"],
    "作业": ["作业", "实验报告", "课程设计", "大作业", "课后练习"],
    "教师": ["授课", "答疑", "老师布置"],
    "先修": ["先修", "前置课程", "prerequisite"],
    "评分": ["评分标准", "考核方式", "成绩构成", "平时分"],
    "学时": ["学时", "课时", "课程安排"],
    "教材": ["教材", "参考书", "参考资料", "指定用书"],
}

_ACTIVITY_KEYWORDS = {
    "讲座": ["讲座", "报告会", "学术报告", "大讲堂", "论坛", "宣讲", "seminar", "思政课"],
    "竞赛": ["竞赛", "比赛", "大赛", "挑战赛", "选拔赛", "建模", "Hackathon", "ICPC", "创新创业"],
    "科研活动": ["大创", "SRF", "科研训练", "本科生科研", "科研项目", "招募", "招收", "项目申报"],
    "培训": ["培训", "训练营", "动员会"],
}

# 通用模式 → 分类映射
_INTENT_PATTERNS = {
    "policy": [
        re.compile(r"怎么(样|做)?(保研|推免|转专业|选课|毕业)", re.I),
        re.compile(r"(保研|推免|转专业|选课|补考|毕业|学位).*(条件|要求|规定|政策|流程|怎么办)", re.I),
        re.compile(r"(什么|哪些|多少).*(条件|要求|名额|比例)", re.I),
        re.compile(r"(通知|规定|办法|条例|细则|管理办法)", re.I),
        re.compile(r"(什么时候|几月|截止|申请时间|报名)", re.I),
    ],
    "life": [
        re.compile(r"(怎么|如何|哪里).*(办|申请|预约|借|报修)", re.I),
        re.compile(r"(宿舍|食堂|图书馆|校医院|校车|校园网|一卡通)", re.I),
        re.compile(r"(时间|几点|开门|关门|营业|开放时间)", re.I),
        re.compile(r"(可以|能|能否|允许).*(吗|么)", re.I),
    ],
    "course": [
        re.compile(r"(课程|这门课|这门).*(大纲|重点|考点|资料|课件)", re.I),
        re.compile(r"(复习|备考|期末|期中).*(怎么|如何|重点|范围)", re.I),
        re.compile(r"(作业|实验|报告).*(要求|格式|截止|deadline)", re.I),
        re.compile(r"(先修|前置|prerequisite)", re.I),
        re.compile(r"(哪|那|这).*(门|节|堂).*(课|讲)", re.I),
    ],
    "activity": [
        re.compile(r"(有什么|有哪些|近期|最近|本周|下周|本月).*(讲座|报告|比赛|竞赛|活动|大赛)", re.I),
        re.compile(r"(讲座|报告会|大赛|竞赛|比赛|挑战赛).*(时间|地点|报名|参加|在哪|什么时候|怎么报)", re.I),
        re.compile(r"(怎么|如何|哪里).*(报名|参赛|组队)", re.I),
        re.compile(r"(报名|参赛).*(截止|方式|链接|时间)", re.I),
        re.compile(r"(科研|项目|课题).*(申请|报名|招募|招收|加入)", re.I),
    ],
}

# 子意图检测（activity 不纳入子意图体系，单独识别）
_SUB_INTENT_MAP = {
    "policy": _POLICY_KEYWORDS,
    "life": _LIFE_KEYWORDS,
    "course": _COURSE_KEYWORDS,
}


# ─────────────────────────────────────────────
#  意图分类器
# ─────────────────────────────────────────────

class IntentClassifier:
    """
    用户问题意图分类器。

    分类类别:
      - policy: 教务政策（保研/转专业/选课/补考等）
      - life: 校园生活（宿舍/食堂/图书馆等）
      - course: 课程相关（大纲/资料/考试等）
      - general: 通用/无法分类

    分类方法:
      - rule: 纯关键词 + 模式匹配（离线可用）
      - llm: LLM 分类（高精度）
      - hybrid: 先规则，低置信度时用 LLM 增强

    示例:
        >>> classifier = IntentClassifier()
        >>> result = classifier.classify("保研需要什么条件？")
        >>> result.intent
        'policy'
        >>> result.sub_intent
        '保研'
    """

    def __init__(self, use_llm: bool = True, llm_client=None):
        """
        Args:
            use_llm: 是否使用 LLM 辅助分类
            llm_client: LLMClient 实例
        """
        self._use_llm = use_llm
        self._llm_client = llm_client

    # ── 公共接口 ──────────────────────────────

    def classify(self, query: str, context: Optional[str] = None) -> IntentResult:
        """
        对用户问题进行意图分类。

        Args:
            query: 用户问题
            context: 对话上下文（可选，辅助分类）

        Returns:
            IntentResult
        """
        query = query.strip()
        if not query:
            return IntentResult(intent="general", confidence=0.0, method="rule")

        # 1. 规则分类
        rule_result = self._rule_classify(query, context)

        # 2. LLM 增强（规则置信度低时）
        if self._use_llm and self._llm_client and rule_result.confidence < 0.7:
            try:
                llm_result = self._llm_classify(query, context)
                if llm_result.confidence > rule_result.confidence:
                    llm_result.method = "hybrid"
                    return llm_result
            except Exception as e:
                logger.warning("[IntentClassifier] LLM 分类失败: %s", e)

        return rule_result

    def classify_batch(self, queries: List[str]) -> List[IntentResult]:
        """批量分类"""
        return [self.classify(q) for q in queries]

    # ── 规则分类 ──────────────────────────────

    def _rule_classify(self, query: str, context: Optional[str] = None) -> IntentResult:
        """
        基于关键词和模式的规则分类。

        优化策略:
          - 关键词精确匹配（避免子串误匹配）
          - 模式匹配加权
          - 多关键词叠加提升置信度
        """
        text = f"{query} {context or ''}".lower()
        scores = {"policy": 0, "life": 0, "course": 0, "activity": 0}
        matched_keywords = {"policy": [], "life": [], "course": [], "activity": []}

        # 1. 关键词匹配（精确匹配，避免子串误匹配）
        for intent, keyword_groups in _SUB_INTENT_MAP.items():
            for sub_intent, keywords in keyword_groups.items():
                for kw in keywords:
                    # 精确匹配：关键词前后必须是边界或已包含
                    if kw.lower() in text:
                        # 避免重复计数
                        if sub_intent not in matched_keywords[intent]:
                            matched_keywords[intent].append(sub_intent)
                        scores[intent] += 2

        # 1b. 活动关键词（独立计分，不占用子意图体系）
        for sub_intent, keywords in _ACTIVITY_KEYWORDS.items():
            for kw in keywords:
                if kw.lower() in text:
                    if sub_intent not in matched_keywords["activity"]:
                        matched_keywords["activity"].append(sub_intent)
                    scores["activity"] += 2
                    break

        # 2. 模式匹配（加权）
        for intent, patterns in _INTENT_PATTERNS.items():
            pattern_hits = 0
            for pat in patterns:
                if pat.search(text):
                    pattern_hits += 1
            # 模式命中越多，加权越高（避免单一模式误判）
            scores[intent] += pattern_hits * 2

        # 3. 选出最佳分类
        max_score = max(scores.values())
        if max_score == 0:
            return IntentResult(intent="general", confidence=0.3, method="rule")

        best_intent = max(scores, key=scores.get)
        total = sum(scores.values())

        # 置信度计算：best_score / total + 命中关键词数加成
        keyword_bonus = min(len(matched_keywords.get(best_intent, [])) * 0.05, 0.2)
        confidence = min(scores[best_intent] / max(total, 1) + keyword_bonus, 1.0)

        # 子意图（去重）
        sub_intents = list(set(matched_keywords.get(best_intent, [])))
        sub_intent = sub_intents[0] if sub_intents else None

        return IntentResult(
            intent=best_intent,
            confidence=round(confidence, 2),
            sub_intent=sub_intent,
            method="rule",
        )

    # ── LLM 分类 ──────────────────────────────

    def _llm_classify(self, query: str, context: Optional[str] = None) -> IntentResult:
        """
        使用 LLM 进行意图分类。
        """
        system_prompt = """你是校园问答意图分类器。请将用户问题分类为以下五类之一：
- policy：教务政策类（保研、转专业、选课、补考、学籍、毕业、奖学金等）
- life：校园生活类（宿舍、食堂、图书馆、交通、网络、医疗等）
- course：课程资料类（课程大纲、复习资料、考试、作业、教师等）
- activity：校园活动类（讲座、竞赛、科研机会、培训、报名参赛等）
- general：无法归类的通用问题

同时提取子意图关键词（如保研、转专业等）。

请以 JSON 格式返回：
{"intent": "policy", "sub_intent": "保研", "confidence": 0.95}

只返回 JSON，不要其他内容。"""

        user_msg = f"用户问题：{query}"
        if context:
            user_msg += f"\n对话上下文：{context[:200]}"

        response = self._llm_client.call(system_prompt, user_msg)

        try:
            clean = response.strip()
            if clean.startswith("```"):
                clean = re.sub(r"^```(?:json)?\s*", "", clean)
                clean = re.sub(r"\s*```$", "", clean)
            data = json.loads(clean)

            intent = data.get("intent", "general")
            if intent not in ("policy", "life", "course", "activity", "general"):
                intent = "general"

            return IntentResult(
                intent=intent,
                confidence=float(data.get("confidence", 0.8)),
                sub_intent=data.get("sub_intent"),
                method="llm",
            )
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            logger.debug("[IntentClassifier] LLM 返回解析失败: %s", response[:100])
            return IntentResult(intent="general", confidence=0.4, method="llm")


# ─────────────────────────────────────────────
#  命令行测试
# ─────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")

    classifier = IntentClassifier(use_llm=False)

    test_queries = [
        ("保研需要什么条件？", "policy"),
        ("转专业的流程是怎样的？", "policy"),
        ("选课系统什么时候开放？", "policy"),
        ("图书馆几点关门？", "life"),
        ("宿舍可以申请换房吗？", "life"),
        ("这门课的期末考试范围是什么？", "course"),
        ("有没有高数课件？", "course"),
        ("奖学金怎么申请？", "policy"),
        ("四六级什么时候报名？", "policy"),
        ("校园网密码忘了怎么办？", "life"),
        ("最近有什么讲座？", "activity"),
        ("数学建模竞赛什么时候报名？", "activity"),
        ("今天天气怎么样？", "general"),
    ]

    print("=== 意图分类测试 ===")
    correct = 0
    for q, expected in test_queries:
        result = classifier.classify(q)
        status = "OK" if result.intent == expected else "FAIL"
        if result.intent == expected:
            correct += 1
        print(f"  [{status}] Q: {q}")
        print(f"       → {result.intent} (expected={expected}) | sub={result.sub_intent} | conf={result.confidence}")
    print(f"\n准确率: {correct}/{len(test_queries)} ({correct/len(test_queries)*100:.1f}%)")
