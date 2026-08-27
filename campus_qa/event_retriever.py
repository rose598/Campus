"""
event_retriever.py — 校园活动检索器

职责:
  - 针对 activity 意图（讲座/竞赛/科研/培训）检索校园活动
  - 主链路：SQLite events 表结构化查询（关键词 LIKE 匹配 + 类型过滤）
  - 兜底链路：活动原始数据文件（data/raw/activities/*.json）全文匹配
  - 输出与文档检索统一的 dict 格式，供 generate 节点组装回答

使用方式:
  from campus_qa.event_retriever import EventRetriever

  retriever = EventRetriever()
  events = retriever.search("最近有什么讲座", top_k=5)
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# 活动类型中英文显示名
_EVENT_TYPE_NAMES = {
    "lecture": "讲座报告",
    "competition": "竞赛",
    "research": "科研机会",
    "training": "培训",
    "other": "活动",
}

# 查询词 → 活动类型（用于类型过滤）
_TYPE_HINT_KEYWORDS = {
    "lecture": ["讲座", "报告", "宣讲", "论坛", "大讲堂", "思政课", "学术报告"],
    "competition": ["竞赛", "比赛", "大赛", "挑战赛", "选拔赛", "建模", "ICPC", "程序设计"],
    "research": ["科研", "大创", "SRF", "科研训练", "项目申报", "招募", "招收"],
    "training": ["培训", "训练营", "动员会"],
}

# 通用停用词（不作为实体关键词参与匹配）
_STOP_WORDS = {
    "什么", "哪些", "怎么", "如何", "多少", "哪里", "哪个", "最近", "近期",
    "本周", "下周", "本月", "今天", "明天", "请问", "有没有", "有什么",
    "有哪些", "可以", "参加", "报名", "时间", "地点", "时候", "活动",
}


class EventRetriever:
    """校园活动检索器（events 表结构化查询 + 原始数据兜底）。"""

    def __init__(self, db_path: str = "data/graphcampus.db",
                 raw_dir: str = "data/raw/activities"):
        self._db_path = db_path
        self._raw_dir = Path(raw_dir)
        self._raw_cache: Optional[List[Dict]] = None

    # ── 公共接口 ──────────────────────────────

    def search(self, query: str, top_k: int = 5,
               event_type: Optional[str] = None) -> List[Dict]:
        """检索与查询相关的校园活动。

        Returns:
            [{"chunk_id", "doc_id", "title", "doc_title", "category",
              "content", "publish_date", "score", "event_type",
              "event_time", "location", "organizer"}, ...]
        """
        if event_type is None:
            event_type = self._infer_event_type(query)

        results = self._search_db(query, top_k, event_type)

        # 兜底：数据库无结果时查原始数据文件
        if not results:
            results = self._search_raw(query, top_k, event_type)

        return results[:top_k]

    # ── 查询解析 ──────────────────────────────

    @staticmethod
    def _infer_event_type(query: str) -> Optional[str]:
        """从查询推断活动类型（无明确类型词时返回 None 不过滤）。"""
        best_type, best_hits = None, 0
        for etype, keywords in _TYPE_HINT_KEYWORDS.items():
            hits = sum(1 for kw in keywords if kw.lower() in query.lower())
            if hits > best_hits:
                best_type, best_hits = etype, hits
        return best_type

    @staticmethod
    def _extract_keywords(query: str) -> List[str]:
        """提取查询中的实体关键词（过滤通用疑问词/时间词）。"""
        words = re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z]{2,}", query)
        return [w for w in words if w not in _STOP_WORDS and w.lower() not in _STOP_WORDS]

    # ── 数据库检索 ────────────────────────────

    def _search_db(self, query: str, top_k: int,
                   event_type: Optional[str]) -> List[Dict]:
        """events 表 LIKE 匹配：标题/主办方命中计分，类型过滤优先。"""
        try:
            import sqlite3
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
        except Exception as e:  # noqa: BLE001
            logger.warning("[EventRetriever] 数据库连接失败: %s", e)
            return []

        try:
            rows = conn.execute(
                "SELECT title, event_type, date, location, organizer, url FROM events"
            ).fetchall()
        except Exception as e:  # noqa: BLE001
            logger.warning("[EventRetriever] events 表查询失败: %s", e)
            return []
        finally:
            conn.close()

        keywords = self._extract_keywords(query)
        scored = []
        for row in rows:
            title = row["title"] or ""
            organizer = row["organizer"] or ""
            etype = row["event_type"] or ""

            score = 0.0
            for kw in keywords:
                if kw in title:
                    score += 3.0
                if kw in organizer:
                    score += 1.0

            # 类型过滤匹配加分；查询指定类型但事件不匹配则跳过
            if event_type:
                if etype == event_type:
                    score += 1.0
                elif score == 0:
                    continue
            elif score == 0:
                # 无关键词命中且无类型过滤 → 仅对“最近有什么活动”类泛查询保留
                if not any(w in query for w in ("活动", "讲座", "比赛", "竞赛")):
                    continue
                score = 0.1  # 泛查询按新鲜度兜底

            if score > 0:
                scored.append((score, dict(row)))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [self._to_doc(s, row) for s, row in scored[:top_k * 2]]

    # ── 原始数据兜底 ──────────────────────────

    def _load_raw(self) -> List[Dict]:
        """加载 data/raw/activities/ 下所有 JSON（缓存）。"""
        if self._raw_cache is not None:
            return self._raw_cache
        items: List[Dict] = []
        if self._raw_dir.exists():
            for fp in sorted(self._raw_dir.glob("*.json")):
                try:
                    data = json.loads(fp.read_text(encoding="utf-8"))
                    if isinstance(data, list):
                        items.extend(data)
                except Exception as e:  # noqa: BLE001
                    logger.warning("[EventRetriever] 读取 %s 失败: %s", fp, e)
        self._raw_cache = items
        return items

    def _search_raw(self, query: str, top_k: int,
                    event_type: Optional[str]) -> List[Dict]:
        """原始数据全文匹配（标题权重高于正文）。"""
        keywords = self._extract_keywords(query)
        scored = []
        for item in self._load_raw():
            title = item.get("title", "") or ""
            desc = item.get("description", "") or ""
            etype = item.get("type", "") or ""

            score = 0.0
            for kw in keywords:
                if kw in title:
                    score += 3.0
                if kw in desc:
                    score += 1.0

            if event_type:
                if etype == event_type:
                    score += 1.0
                elif score == 0:
                    continue
            elif score == 0:
                continue

            scored.append((score, item))

        scored.sort(key=lambda x: x[0], reverse=True)
        results = []
        for s, item in scored[:top_k * 2]:
            row = {
                "title": item.get("title", ""),
                "event_type": item.get("type", ""),
                "date": item.get("event_time", ""),
                "location": item.get("location", ""),
                "organizer": item.get("organizer", ""),
                "url": item.get("url", ""),
                "_description": item.get("description", ""),
            }
            results.append(self._to_doc(s, row))
        return results

    # ── 格式统一 ──────────────────────────────

    @staticmethod
    def _to_doc(score: float, row: Dict) -> Dict:
        """转为与文档检索一致的 dict 格式 + 活动摘要正文。"""
        title = row.get("title", "")
        etype = row.get("event_type", "")
        date = row.get("date", "") or ""
        location = row.get("location", "") or ""
        organizer = row.get("organizer", "") or ""
        description = row.get("_description", "") or ""

        # 结构化摘要作为正文（generate 节点直接可用）
        parts = []
        if date:
            parts.append(f"时间：{date}")
        if location:
            parts.append(f"地点：{location}")
        if organizer:
            parts.append(f"主办方：{organizer}")
        summary = "；".join(parts)
        content = f"【{title}】{summary}" if summary else f"【{title}】"
        if description:
            content += "\n" + description[:300]

        return {
            "chunk_id": f"event:{title[:20]}",
            "doc_id": f"event:{title}",
            "title": title,
            "doc_title": title,
            "category": "activity",
            "content": content,
            "publish_date": date,
            "score": score,
            "event_type": etype,
            "event_time": date,
            "location": location,
            "organizer": organizer,
        }

    # ── 回答组装 ──────────────────────────────

    @staticmethod
    def format_answer(events: List[Dict], query: str) -> str:
        """将活动检索结果组装为结构化文本回答（离线可用，不依赖 LLM）。"""
        if not events:
            return "暂未找到相关活动信息，可关注教务处与学校官网的最新通知。"

        # 按类型统计
        type_counts: Dict[str, int] = {}
        for e in events:
            t = e.get("event_type", "") or "other"
            type_counts[t] = type_counts.get(t, 0) + 1

        lines = [f"为你找到 {len(events)} 个相关活动：", ""]
        for i, e in enumerate(events, 1):
            type_name = _EVENT_TYPE_NAMES.get(e.get("event_type", ""), "活动")
            line = f"{i}. [{type_name}] {e.get('title', '')}"
            detail = []
            if e.get("event_time"):
                detail.append(f"时间：{e['event_time']}")
            if e.get("location"):
                detail.append(f"地点：{e['location']}")
            if e.get("organizer"):
                detail.append(f"主办：{e['organizer']}")
            if detail:
                line += "\n   " + "，".join(detail)
            lines.append(line)
        return "\n".join(lines)
