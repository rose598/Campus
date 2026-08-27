# -*- coding: utf-8 -*-
"""
crawl_ustc_activities.py — 真实站点活动数据爬取（成员C / P0-3）

目标站点（经可达性验证）:
  - 学校官网公告通知:  https://www.ustc.edu.cn/tzgg.htm
  - 学校官网教学类通知: https://www.ustc.edu.cn/tzgg/jxltz.htm（带翻页）
  - （教务处 teach.ustc.edu.cn 全站 403 反爬，已确认可达性失败，跳过）

技术要点:
  - 官网详情页链接格式为 tzggcontent.jsp?urltype=news.NewsContentUrl&wbnewsid=...
  - 页面为 UTF-8 但 Content-Type 未声明，需强制 utf-8 解码
  - 正文容器: div.v_news_content；标题: table.nr（官网 CMS 定制结构）

流程: 列表页收集链接 → 详情页正文提取 → 活动分类(讲座/竞赛/科研/其他) →
      与现有 data/raw/activities/sample_activities.json 合并去重 → 写回。

使用方式:
  python scripts/crawl_ustc_activities.py [--pages 4]
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import requests
from bs4 import BeautifulSoup

from crawler.activity_crawler import _classify_activity, _extract_activity_details

logger = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

BASE = "https://www.ustc.edu.cn/"

# 非三类但具活动性质的补充分类关键词 → 映射类型
_EXTRA_TYPE_KEYWORDS = {
    "lecture": ["培训", "报告会", "演出", "典礼", "展览", "观影", "研讨课", "大讲堂"],
    "competition": ["选拔", "大赛", "挑战赛"],
    "research": ["申报", "项目", "课题", "征集", "基金", "招生", "招募", "招收"],
}


def _fetch(url: str, referer: str | None = None) -> str | None:
    """带浏览器头抓取，强制 utf-8 解码"""
    headers = dict(_HEADERS)
    if referer:
        headers["Referer"] = referer
    for attempt in range(2):
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            resp.raise_for_status()
            resp.encoding = "utf-8"
            return resp.text
        except Exception as e:
            logger.warning("[UstcCrawl] 请求失败 [%d/2] %s: %s", attempt + 1, url, e)
            if attempt == 0:
                time.sleep(1.5)
    return None


def _collect_list_links(html: str, page_url: str) -> list:
    """从列表页提取详情链接（tzggcontent.jsp 动态链接 + /info/ 静态链接）"""
    soup = BeautifulSoup(html, "html.parser")
    links, seen = [], set()
    for a in soup.find_all("a", href=True):
        title = a.get_text(strip=True)
        href = a["href"]
        if not title or len(title) < 8:
            continue
        if "tzggcontent.jsp" not in href and "/info/" not in href:
            continue
        url = urljoin(page_url, href)
        if url in seen:
            continue
        seen.add(url)
        links.append({"title": title, "url": url})
    return links


def _parse_detail(html: str) -> tuple:
    """官网 CMS 详情页解析：返回 (title, content)"""
    soup = BeautifulSoup(html, "html.parser")

    # 标题：v_news_content 前的文本节点（table.nr 的首个文本是导航，不可用）
    title = ""
    content_div = soup.find("div", class_="v_news_content")
    if content_div:
        prev_texts = []
        for elem in content_div.find_all_previous(text=True):
            t = elem.strip()
            if t:
                prev_texts.append(t)
        # 过滤导航文本，取紧邻正文的最长候选（标题通常 >8 字）
        nav_words = ("首页", "首页", "上一页", "下一页", "发布时间", "点击", "关闭", "打印")
        candidates = [
            t for t in prev_texts[:15]
            if len(t) > 6 and not any(w in t for w in nav_words) and "|" not in t
        ]
        if candidates:
            title = candidates[0]
    if not title:
        h1 = soup.find("h1")
        if h1:
            title = h1.get_text(strip=True)
    if not title:
        title_tag = soup.find("title")
        if title_tag:
            title = title_tag.get_text(strip=True)

    # 正文：v_news_content 容器优先（注意：上面已提取标题，此处重新取文本）
    content = ""
    if content_div:
        content = content_div.get_text(separator="\n", strip=True)
    if len(content) < 30:
        # 兜底：meta description
        meta = soup.find("meta", attrs={"name": "description"})
        if meta and meta.get("content"):
            content = content or meta["content"].strip()

    return title, content


def _classify_with_extra(title: str, content: str) -> str:
    """活动分类：三类优先，其次按补充关键词，否则返回空串"""
    cat = _classify_activity(title, content)
    if cat:
        return cat
    for cat_type, keywords in _EXTRA_TYPE_KEYWORDS.items():
        if any(k in title for k in keywords):
            return cat_type
    return ""


def _extract_organizer_from_content(content: str) -> str:
    """从正文兜底提取发布单位（官网公告一般末尾有落款）"""
    m = re.search(r"(教务处|研究生院|学生工作处|教务处|图书馆|体育教学部|创新创业学院|[\u4e00-\u9fa5]{2,10}学院|[\u4e00-\u9fa5]{2,8}办公室)\s*$", content, re.M)
    return m.group(1) if m else ""


def _enhance_details(details: dict, content: str) -> dict:
    """增强时间/地点提取：官网正文日期常被换行拆散（如“2026\n年\n6\n月”），
    压缩空白后重跑提取，并补充宽松的时间/地点正则。"""
    flat = re.sub(r"\s+", "", content[:1500])

    # 残缺/含换行的时间值（如“时间：”）视为无效，触发重提取
    et = details.get("event_time") or ""
    et_clean = et.replace("\n", "").replace("时间：", "").replace("时间:", "").strip()
    if len(et_clean) < 6:
        details["event_time"] = ""
    elif "\n" in et:
        details["event_time"] = et_clean

    if not details.get("event_time"):
        time_patterns = [
            re.compile(r"时间[：:]?\d{4}年\d{1,2}月\d{1,2}日[^，。；]{0,20}"),
            re.compile(r"\d{4}年\d{1,2}月\d{1,2}日(?:\d{1,2}[:：]\d{2})?"),
            re.compile(r"\d{1,2}月\d{1,2}日(?:\d{1,2}[:：]\d{2})?"),
            re.compile(r"截止[时日][间期][：:]?[^，。；]{0,20}"),
        ]
        for pat in time_patterns:
            m = pat.search(flat)
            if m:
                details["event_time"] = m.group(0)[:60]
                break

    if not details.get("location"):
        loc_patterns = [
            re.compile(r"地点[：:]?([\u4e00-\u9fa5A-Za-z0-9（）()]{2,30})"),
            re.compile(r"在([\u4e00-\u9fa5]{2,6}(?:大礼堂|报告厅|会议室|教室|礼堂|场馆|楼)[\u4e00-\u9fa5A-Za-z0-9]{0,8})"),
        ]
        for pat in loc_patterns:
            m = pat.search(flat)
            if m:
                details["location"] = m.group(1)[:40]
                break

    return details


def _crawl_detail(url: str, title_hint: str) -> dict | None:
    """爬取单个详情页并转为活动记录"""
    html = _fetch(url, referer=BASE + "tzgg.htm")
    if not html:
        return None

    title, content = _parse_detail(html)
    # 列表页标题更可靠，优先使用；解析标题仅作兜底（需过滤导航残留）
    if title_hint and len(title_hint) > 6 and "|" not in title_hint and "首" not in title_hint[:3]:
        title = title_hint
    title = title or title_hint
    if not title or len(content) < 30:
        return None

    activity_type = _classify_with_extra(title, content)
    if not activity_type:
        return None  # 非活动类通知（如停电/施工/班车），跳过

    details = _extract_activity_details(content)
    details = _enhance_details(details, content)
    if not details.get("organizer"):
        details["organizer"] = _extract_organizer_from_content(content)

    return {
        "title": title,
        "description": content[:500],
        "type": activity_type,
        "url": url,
        "event_time": details.get("event_time", ""),
        "location": details.get("location", ""),
        "organizer": details.get("organizer", ""),
        "speaker": details.get("speaker", ""),
        "tags": [],
        "source": "ustc_crawl",
    }


def main():
    parser = argparse.ArgumentParser(description="USTC 真实站点活动数据爬取")
    parser.add_argument("--pages", type=int, default=4, help="教学类通知翻页数")
    parser.add_argument("--output", type=str,
                        default="data/raw/activities/sample_activities.json",
                        help="合并后输出的活动数据文件")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")

    # 1. 收集列表链接
    all_links = []

    # 公告通知（单页）
    html = _fetch(BASE + "tzgg.htm")
    if html:
        all_links.extend(_collect_list_links(html, BASE + "tzgg.htm"))
    time.sleep(1.0)

    # 教学类通知（带翻页：tzgg/jxltz.htm → tzgg/jxltz/{N}.htm）
    jxl_urls = [BASE + "tzgg/jxltz.htm"] + [
        BASE + f"tzgg/jxltz/{i}.htm" for i in range(args.pages, 0, -1)
    ]
    for u in jxl_urls:
        html = _fetch(u, referer=BASE + "tzgg.htm")
        if not html:
            continue
        links = _collect_list_links(html, u)
        if links:
            all_links.extend(links)
        time.sleep(1.0)

    # URL 去重
    seen, unique_links = set(), []
    for link in all_links:
        if link["url"] not in seen:
            seen.add(link["url"])
            unique_links.append(link)

    logger.info("[UstcCrawl] 共发现 %d 条候选链接", len(unique_links))

    # 2. 逐条爬取详情
    crawled = []
    for i, link in enumerate(unique_links):
        result = _crawl_detail(link["url"], link["title"])
        if result:
            crawled.append(result)
            logger.info("[UstcCrawl] ✓ [%s] %s", result["type"], result["title"][:40])
        time.sleep(0.5)
        if (i + 1) % 20 == 0:
            logger.info("[UstcCrawl] 进度 %d/%d，已命中 %d 条活动",
                        i + 1, len(unique_links), len(crawled))

    logger.info("[UstcCrawl] 爬取完成: %d/%d 命中活动", len(crawled), len(unique_links))

    # 3. 与现有数据合并去重（按 URL）
    output_path = Path(args.output)
    existing = []
    if output_path.exists():
        try:
            with open(output_path, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except Exception:
            existing = []

    seen_urls = {item.get("url", "") for item in existing}
    merged = list(existing)
    for item in crawled:
        if item["url"] not in seen_urls:
            seen_urls.add(item["url"])
            merged.append(item)

    # 4. 写回
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)

    # 5. 统计
    type_stats = {}
    for item in merged:
        t = item.get("type", "unknown")
        type_stats[t] = type_stats.get(t, 0) + 1

    print(f"\n=== 活动数据爬取完成 ===")
    print(f"本次新增: {len(merged) - len(existing)} 条")
    print(f"总活动数: {len(merged)} 条 → {output_path}")
    print(f"类型分布: {json.dumps(type_stats, ensure_ascii=False)}")


if __name__ == "__main__":
    main()
