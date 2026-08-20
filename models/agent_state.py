"""AgentState – LangGraph 全局状态定义"""
from typing import TypedDict, List, Dict, Optional, Any
from langchain_core.messages import BaseMessage

from .course import Course
from .campus_document import CampusDocument


class AgentState(TypedDict, total=False):
    """Agent 共享状态，所有字段均为可选（total=False）"""
    user_id: str
    messages: List[BaseMessage]               # 滑动窗口（最多20轮）
    chat_summary: str                         # LLM 生成的对话摘要
    courses: Dict[str, Course]                # 课程字典，key=课程代码
    course_graph: Any                         # NetworkX 图对象
    node2vec_model: Optional[Any]             # Node2Vec 模型
    bm25_index: Any                           # BM25 索引对象
    dense_index: Any                          # DenseIndex 对象
    cache_pool: Dict[str, str]                # 语义缓存（query_hash -> answer）
    user_progress: Dict[str, Any]             # 用户学习进度
    learning_path: Optional[List[str]]        # 推荐学习路径（课程代码列表）
    alt_paths: List[List[str]]                # 备用路径列表
    ppr_scores: Optional[Dict[str, float]]    # PPR 分数（节点 → 分数）
    current_notes: Optional[Dict[str, Any]]   # 当前笔记分析结果
    campus_docs: Dict[str, List[CampusDocument]]   # 校园文档分类（按类别）
    campus_indexes: Dict[str, Any]            # 分类索引 {教务/生活/课程}
    intent: Optional[str]                     # 意图分类结果
    rewritten_query: Optional[str]            # 多轮对话改写后的查询
    privacy_mode: bool                         # 隐私模式
    interrupt_flag: bool                      # 中断标志
    extraction_confidence: float              # 抽取结果置信度
    trace_id: str                             # 链路追踪 ID
    # ── 子图输出字段（Day 7 父图 Fan-out/聚合）──
    intel_result: Optional[Dict[str, Any]]    # 情报官输出 {recommendations, ...}
    retrieved_docs: List[Dict[str, Any]]      # 百事通检索结果
    qa_result: Optional[Dict[str, Any]]       # 百事通问答输出 {answer, sources, ...}
    buddy_result: Optional[Dict[str, Any]]    # 学伴输出 {summary, ...}
    aggregated_result: Optional[Dict[str, Any]]  # 聚合后的完整结果
    final_response: str                       # 最终用户可读回复文本
