"""
activity_crawler.py — 活动数据爬虫（讲座 / 竞赛 / 科研机会）

职责:
  - 爬取学院官网、公告页面的活动信息
  - 分类识别：讲座（lecture）、竞赛（competition）、科研机会（research）
  - 提取活动详情（标题、时间、地点、组织者、描述）
  - 输出结构化 JSON，与 Event model 对齐
  - 支持预置 JSON 数据导入

使用方式:
  from crawler.activity_crawler import ActivityCrawler

  crawler = ActivityCrawler()
  results = crawler.crawl(list_url="https://cs.example.edu.cn/news/")
  crawler.save_results(results, "data/raw/activities/")
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Literal, Optional

from .utils import (
    CrawlRateLimiter,
    extract_article,
    extract_list_links,
    fetch_page,
    normalize_url,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
#  活动分类关键词
# ─────────────────────────────────────────────

_ACTIVITY_PATTERNS = {
    "lecture": [
        re.compile(r"讲座|报告|学术沙龙|seminar|talk|论坛", re.I),
    ],
    "competition": [
        re.compile(r"竞赛|比赛|大赛|challenge|cup|ACM|ICPC|建模|Hackathon", re.I),
    ],
    "research": [
        re.compile(r"科研|实验室|课题组|导师|研究|大创|SRF|URP|本科生科研", re.I),
    ],
}


def _classify_activity(title: str, content: str = "") -> Optional[str]:
    """
    根据标题和内容判断活动类型。

    Returns:
        "lecture" / "competition" / "research" / None（不匹配）
    """
    text = f"{title} {content[:300]}"
    scores = {"lecture": 0, "competition": 0, "research": 0}

    for cat, patterns in _ACTIVITY_PATTERNS.items():
        for pat in patterns:
            if pat.search(text):
                scores[cat] += 1

    max_score = max(scores.values())
    if max_score == 0:
        return None

    return max(scores, key=scores.get)


# ─────────────────────────────────────────────
#  活动详情提取
# ─────────────────────────────────────────────

def _extract_activity_details(content: str) -> Dict:
    """从正文中提取活动关键信息"""
    details = {}

    # 时间
    time_patterns = [
        re.compile(r"时间[：:]\s*(.+?)(?:\n|$)"),
        re.compile(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日\s*(\d{1,2})[:：](\d{2})"),
        re.compile(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})\s+(\d{1,2})[:：](\d{2})"),
    ]
    for pat in time_patterns:
        match = pat.search(content[:1000])
        if match:
            details["event_time"] = match.group(0).strip()
            break

    # 地点
    location_patterns = [
        re.compile(r"地点[：:]\s*(.+?)(?:\n|$)"),
        re.compile(r"地址[：:]\s*(.+?)(?:\n|$)"),
    ]
    for pat in location_patterns:
        match = pat.search(content[:1000])
        if match:
            details["location"] = match.group(1).strip()
            break

    # 主办方
    org_patterns = [
        re.compile(r"(?:主办|组织|承办)[单位方]?[：:]\s*(.+?)(?:\n|$)"),
    ]
    for pat in org_patterns:
        match = pat.search(content[:1000])
        if match:
            details["organizer"] = match.group(1).strip()
            break

    # 主讲人/嘉宾
    speaker_patterns = [
        re.compile(r"(?:主讲人|报告人|嘉宾|讲者)[：:]\s*(.+?)(?:\n|$)"),
    ]
    for pat in speaker_patterns:
        match = pat.search(content[:1000])
        if match:
            details["speaker"] = match.group(1).strip()
            break

    return details


# ─────────────────────────────────────────────
#  活动爬虫
# ─────────────────────────────────────────────

class ActivityCrawler:
    """
    活动数据爬虫。

    爬取流程:
      1. 访问列表页，提取活动相关链接
      2. 逐页爬取详情页
      3. 分类识别活动类型
      4. 提取活动关键信息
      5. 输出结构化 JSON

    示例:
        >>> crawler = ActivityCrawler(rate_limit=1.0)
        >>> results = crawler.crawl(
        ...     list_url="https://cs.example.edu.cn/news/",
        ...     keywords=["讲座", "竞赛", "科研"],
        ... )
    """

    DEFAULT_KEYWORDS = [
        "讲座", "报告", "学术", "竞赛", "比赛", "大赛",
        "科研", "实验室", "课题组", "大创", "SRF", "论坛",
        "seminar", "challenge", "Hackathon",
    ]

    def __init__(self, rate_limit: float = 1.0):
        self._limiter = CrawlRateLimiter(rate_limit)

    # ── 公共接口 ──────────────────────────────

    def crawl(
        self,
        list_url: str,
        keywords: Optional[List[str]] = None,
        max_pages: int = 3,
        encoding: Optional[str] = None,
    ) -> List[Dict]:
        """
        爬取活动列表。

        Args:
            list_url: 列表页 URL
            keywords: 过滤关键词
            max_pages: 最大页数
            encoding: 强制编码

        Returns:
            结构化活动列表
        """
        keywords = keywords or self.DEFAULT_KEYWORDS

        logger.info(
            "[ActivityCrawler] 开始爬取: %s | 关键词=%s",
            list_url, keywords,
        )

        # 1. 爬取列表页
        all_links = []
        current_url = list_url
        visited = set()

        for page in range(max_pages):
            self._limiter.wait()
            html = fetch_page(current_url, encoding=encoding)
            if not html:
                break

            links = extract_list_links(html, current_url, keyword_filter=keywords)
            all_links.extend(links)

            # 去重 + 翻页
            seen = {normalize_url(l["url"]) for l in all_links}
            next_url = self._find_next_page(html, current_url)
            if not next_url or normalize_url(next_url) in visited:
                break
            visited.add(normalize_url(current_url))
            current_url = next_url

        # 去重
        seen_urls = set()
        unique_links = []
        for link in all_links:
            nu = normalize_url(link["url"])
            if nu not in seen_urls:
                seen_urls.add(nu)
                unique_links.append(link)

        logger.info("[ActivityCrawler] 发现 %d 条相关链接", len(unique_links))

        # 2. 逐页爬取
        results = []
        for link in unique_links:
            result = self._crawl_detail(url=link["url"], title=link["title"], encoding=encoding)
            if result:
                results.append(result)

        logger.info("[ActivityCrawler] 爬取完成: %d/%d 成功", len(results), len(unique_links))
        return results

    def crawl_from_json(self, json_path: str | Path) -> List[Dict]:
        """
        从预置 JSON 文件导入活动数据。

        JSON 格式:
          [{"title": "...", "description": "...", "type": "lecture", ...}, ...]
        """
        path = Path(json_path)
        if not path.exists():
            logger.warning("[ActivityCrawler] 文件不存在: %s", path)
            return []

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        items = data if isinstance(data, list) else data.get("items", [])
        results = []

        for item in items:
            activity_type = item.get("type") or _classify_activity(
                item.get("title", ""), item.get("description", "")
            )
            if not activity_type:
                activity_type = "lecture"  # 默认

            results.append({
                "title": item.get("title", ""),
                "description": item.get("description", ""),
                "type": activity_type,
                "url": item.get("url", ""),
                "event_time": item.get("event_time", item.get("time", "")),
                "location": item.get("location", ""),
                "organizer": item.get("organizer", ""),
                "speaker": item.get("speaker", ""),
                "tags": item.get("tags", []),
                "source": "json_import",
                "crawl_time": datetime.now().isoformat(),
            })

        logger.info("[ActivityCrawler] JSON 导入: %d 条活动", len(results))
        return results

    # ── 结果保存 ──────────────────────────────

    def save_results(self, results: List[Dict], output_dir: str | Path) -> Path:
        """保存活动数据为 JSON"""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = output_dir / f"activities_{timestamp}.json"

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

        logger.info("[ActivityCrawler] 结果已保存: %s (%d 条)", output_path, len(results))
        return output_path

    # ── 示例数据生成 ──────────────────────────

    @staticmethod
    def create_sample_data(output_dir: str | Path, count: int = 15) -> Path:
        """生成示例活动数据"""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        samples = [
            {
                "title": "学术讲座：大语言模型的前沿进展与挑战",
                "description": "本次讲座将介绍大语言模型（LLM）的最新研究进展，包括Transformer架构演进、"
                               "多模态融合、推理能力提升等方向，并探讨当前面临的主要技术挑战。",
                "type": "lecture",
                "url": "https://cs.example.edu.cn/news/llm-talk",
                "event_time": "2026年9月15日 14:00",
                "location": "计算机学院报告厅A301",
                "organizer": "计算机科学与技术学院",
                "speaker": "张教授（清华大学）",
                "tags": ["人工智能", "大模型", "NLP"],
            },
            {
                "title": "第十二届ACM-ICPC程序设计竞赛校内选拔赛",
                "description": "为选拔优秀选手参加ACM-ICPC区域赛，现举办校内选拔赛。"
                               "比赛采用ACM-ICPC标准赛制，3人一组，限时5小时。",
                "type": "competition",
                "url": "https://cs.example.edu.cn/news/acm-icpc",
                "event_time": "2026年10月20日 9:00-14:00",
                "location": "计算机学院机房B202",
                "organizer": "计算机学院竞赛中心",
                "speaker": "",
                "tags": ["算法", "竞赛", "ACM", "编程"],
            },
            {
                "title": "本科生科研训练计划（SRF）项目申报通知",
                "description": "为培养本科生科研能力，现启动2026年度SRF项目申报。"
                               "每位导师最多指导2个项目，项目周期为1年，资助经费5000-10000元。",
                "type": "research",
                "url": "https://jwc.example.edu.cn/srf-2026",
                "event_time": "申报截止：2026年4月30日",
                "location": "",
                "organizer": "教务处",
                "speaker": "",
                "tags": ["科研", "SRF", "本科生", "项目申报"],
            },
            {
                "title": "学术报告：图神经网络在推荐系统中的应用",
                "description": "本报告将分享图神经网络（GNN）在推荐系统中的最新应用成果，"
                               "包括知识图谱增强推荐、社交网络推荐等方向的研究进展。",
                "type": "lecture",
                "url": "https://cs.example.edu.cn/news/gnn-recommendation",
                "event_time": "2026年9月22日 15:00",
                "location": "信息楼C501",
                "organizer": "信息科学与工程学院",
                "speaker": "李教授（中国科学院计算所）",
                "tags": ["图神经网络", "推荐系统", "知识图谱"],
            },
            {
                "title": "全国大学生数学建模竞赛报名通知",
                "description": "2026年全国大学生数学建模竞赛将于10月举行，"
                               "现组织校内选拔和培训工作。参赛队伍由3名学生组成。",
                "type": "competition",
                "url": "https://math.example.edu.cn/mcm-2026",
                "event_time": "2026年10月（具体日期待定）",
                "location": "",
                "organizer": "数学学院",
                "speaker": "",
                "tags": ["数学建模", "竞赛", "建模"],
            },
            {
                "title": "人工智能实验室招收本科生科研助理",
                "description": "人工智能实验室（AI Lab）现面向全校招收本科生科研助理，"
                               "参与计算机视觉、自然语言处理等方向的研究工作。"
                               "要求有Python编程基础，每周至少投入10小时。",
                "type": "research",
                "url": "https://cs.example.edu.cn/ailab-recruit",
                "event_time": "长期招募",
                "location": "人工智能实验室（科技楼D401）",
                "organizer": "人工智能实验室",
                "speaker": "",
                "tags": ["人工智能", "科研助理", "CV", "NLP"],
            },
            {
                "title": "创新创业大赛——互联网+大学生创新创业大赛校赛",
                "description": "第十二届中国'互联网+'大学生创新创业大赛校内选拔赛正式启动。"
                               "大赛设高教主赛道、'青年红色筑梦之旅'赛道和产业赛道。",
                "type": "competition",
                "url": "https://cxcy.example.edu.cn/internet-plus",
                "event_time": "2026年5月-6月",
                "location": "创新创业学院",
                "organizer": "创新创业学院",
                "speaker": "",
                "tags": ["创新创业", "互联网+", "竞赛"],
            },
        ]

        # 填充到指定数量
        while len(samples) < count:
            base = samples[len(samples) % len(samples)]
            item = dict(base)
            item["title"] = f"{item['title']}（第{len(samples) + 1}期）"
            samples.append(item)

        output_path = output_dir / "sample_activities.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(samples[:count], f, ensure_ascii=False, indent=2)

        logger.info("[ActivityCrawler] 示例数据已生成: %s (%d 条)", output_path, count)
        return output_path

    # ── 内部方法 ──────────────────────────────

    def _crawl_detail(
        self,
        url: str,
        title: str,
        encoding: Optional[str] = None,
    ) -> Optional[Dict]:
        """爬取单个活动详情页"""
        self._limiter.wait()

        html = fetch_page(url, encoding=encoding)
        if not html:
            return None

        try:
            article = extract_article(html, base_url=url)
            if not article["title"]:
                article["title"] = title

            content = article["content"]

            # 分类
            activity_type = _classify_activity(article["title"], content)
            if not activity_type:
                return None  # 不是活动类内容，跳过

            # 提取详情
            details = _extract_activity_details(content)

            result = {
                "title": article["title"],
                "description": content[:500],
                "type": activity_type,
                "url": url,
                "event_time": details.get("event_time", ""),
                "location": details.get("location", ""),
                "organizer": details.get("organizer", ""),
                "speaker": details.get("speaker", ""),
                "tags": [],
                "source": "crawl",
                "crawl_time": datetime.now().isoformat(),
            }

            logger.info(
                "[ActivityCrawler] ✓ [%s] %s",
                activity_type, result["title"][:40],
            )
            return result

        except Exception as e:
            logger.warning("[ActivityCrawler] 详情页解析失败 %s: %s", url, e)
            return None

    @staticmethod
    def _find_next_page(html: str, current_url: str) -> Optional[str]:
        """查找下一页链接"""
        from bs4 import BeautifulSoup
        from urllib.parse import urljoin

        soup = BeautifulSoup(html, "html.parser")
        for a in soup.find_all("a", href=True):
            text = a.get_text(strip=True)
            if re.search(r"下一页|next|下页|>", text, re.I):
                href = a["href"]
                next_url = urljoin(current_url, href)
                if next_url.startswith("http"):
                    return next_url
        return None


# ─────────────────────────────────────────────
#  命令行入口
# ─────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")

    if len(sys.argv) >= 2 and sys.argv[1] == "--sample":
        count = int(sys.argv[2]) if len(sys.argv) > 2 else 15
        path = ActivityCrawler.create_sample_data("data/raw/activities", count=count)
        print(f"[OK] 示例数据已生成: {path}")
    elif len(sys.argv) >= 2:
        url = sys.argv[1]
        crawler = ActivityCrawler(rate_limit=1.0)
        results = crawler.crawl(url, max_pages=2)
        output = crawler.save_results(results, "data/raw/activities")
        print(f"[OK] 爬取完成: {len(results)} 条 → {output}")
    else:
        print("用法:")
        print("  python activity_crawler.py --sample [count]   生成示例数据")
        print("  python activity_crawler.py <list_url>         爬取指定列表页")
