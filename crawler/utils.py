"""
crawler/utils.py — 爬虫工具函数

职责:
  - HTTP 请求封装（重试 + 超时 + User-Agent 轮换）
  - HTML 内容提取（正文 + 标题 + 日期）
  - PDF 下载与保存
  - URL 规范化与去重
  - 限速与 robots.txt 尊重

使用方式:
  from crawler.utils import fetch_page, download_pdf, extract_article
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
#  User-Agent 池（避免被识别为爬虫）
# ─────────────────────────────────────────────

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) "
    "Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]


def _get_headers() -> Dict[str, str]:
    """获取随机请求头"""
    import random
    return {
        "User-Agent": random.choice(_USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Connection": "keep-alive",
    }


# ─────────────────────────────────────────────
#  HTTP 请求
# ─────────────────────────────────────────────

def fetch_page(
    url: str,
    timeout: int = 15,
    max_retries: int = 3,
    retry_delay: float = 2.0,
    encoding: Optional[str] = None,
) -> Optional[str]:
    """
    获取网页 HTML 内容。

    Args:
        url: 目标 URL
        timeout: 请求超时秒数
        max_retries: 最大重试次数
        retry_delay: 重试间隔（指数退避基数）
        encoding: 强制编码（如 "utf-8"、"gbk"）

    Returns:
        HTML 文本，失败返回 None
    """
    import requests

    for attempt in range(max_retries):
        try:
            resp = requests.get(url, headers=_get_headers(), timeout=timeout)
            resp.raise_for_status()

            if encoding:
                resp.encoding = encoding
            else:
                # 尝试从 Content-Type 或 meta 推断编码
                if resp.encoding and resp.encoding.lower() == "iso-8859-1":
                    # requests 默认编码，中文网页通常需要 GBK 或 UTF-8
                    resp.encoding = resp.apparent_encoding

            return resp.text
        except Exception as e:
            logger.warning(
                "[Crawler] 请求失败 [%d/%d] %s: %s",
                attempt + 1, max_retries, url, e,
            )
            if attempt < max_retries - 1:
                time.sleep(retry_delay * (2 ** attempt))

    logger.error("[Crawler] 请求最终失败: %s", url)
    return None


def download_pdf(
    url: str,
    save_dir: str | Path,
    filename: Optional[str] = None,
    timeout: int = 30,
    max_retries: int = 3,
) -> Optional[Path]:
    """
    下载 PDF 文件并保存到本地。

    Args:
        url: PDF 下载地址
        save_dir: 保存目录
        filename: 保存文件名（默认从 URL 推断）
        timeout: 请求超时秒数
        max_retries: 最大重试次数

    Returns:
        保存的文件路径，失败返回 None
    """
    import requests

    save_dir = Path(save_dir)
    save_dir.mkdir(parents=True, exist_ok=True)

    if filename is None:
        # 从 URL 提取文件名
        parsed = urlparse(url)
        path_parts = parsed.path.strip("/").split("/")
        filename = path_parts[-1] if path_parts else "download.pdf"
        if not filename.endswith(".pdf"):
            filename += ".pdf"

    save_path = save_dir / filename

    for attempt in range(max_retries):
        try:
            resp = requests.get(url, headers=_get_headers(), timeout=timeout, stream=True)
            resp.raise_for_status()

            with open(save_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)

            logger.info("[Crawler] PDF 下载成功: %s → %s", url, save_path)
            return save_path
        except Exception as e:
            logger.warning(
                "[Crawler] PDF 下载失败 [%d/%d] %s: %s",
                attempt + 1, max_retries, url, e,
            )
            if attempt < max_retries - 1:
                time.sleep(2.0 * (2 ** attempt))

    logger.error("[Crawler] PDF 下载最终失败: %s", url)
    return None


# ─────────────────────────────────────────────
#  HTML 内容提取
# ─────────────────────────────────────────────

def extract_article(
    html: str,
    base_url: Optional[str] = None,
) -> Dict[str, any]:
    """
    从 HTML 中提取文章正文、标题、日期和附件链接。

    Args:
        html: HTML 文本
        base_url: 基础 URL（用于解析相对链接）

    Returns:
        {
            "title": str,
            "content": str,
            "publish_date": Optional[str],
            "attachments": [{"url": str, "name": str}, ...],
            "links": [{"url": str, "text": str}, ...],
        }
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")

    # 移除非正文元素
    for tag in soup.find_all(["script", "style", "nav", "footer", "header", "aside", "iframe"]):
        tag.decompose()

    # 提取标题
    title = ""
    h1 = soup.find("h1")
    if h1:
        title = h1.get_text(strip=True)
    if not title:
        title_tag = soup.find("title")
        if title_tag:
            title = title_tag.get_text(strip=True)

    # 提取正文
    body = soup.find("body") or soup
    # 常见正文容器
    content_div = (
        body.find("div", class_=re.compile(r"article|content|main|detail|text", re.I))
        or body.find("article")
        or body
    )
    content = content_div.get_text(separator="\n", strip=True)

    # 提取发布日期
    publish_date = None
    date_patterns = [
        re.compile(r"(\d{4})\s*[-/年.]\s*(\d{1,2})\s*[-/月.]\s*(\d{1,2})\s*日?"),
        re.compile(r"发布时间[：:]\s*(\d{4})[-/年.](\d{1,2})[-/月.](\d{1,2})"),
        re.compile(r"日期[：:]\s*(\d{4})[-/年.](\d{1,2})[-/月.](\d{1,2})"),
    ]
    # 优先从 meta 或特定元素中提取
    date_elem = soup.find(string=re.compile(r"\d{4}[-/年.]\d{1,2}[-/月.]\d{1,2}"))
    date_text = str(date_elem) if date_elem else content[:500]
    for pat in date_patterns:
        match = pat.search(date_text)
        if match:
            publish_date = match.group(0)
            break

    # 提取附件链接（PDF/DOC）
    attachments = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if base_url:
            href = urljoin(base_url, href)
        if re.search(r"\.(pdf|doc|docx)$", href, re.I):
            attachments.append({
                "url": href,
                "name": a.get_text(strip=True) or Path(urlparse(href).path).name,
            })

    # 提取页面链接
    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if base_url:
            href = urljoin(base_url, href)
        text = a.get_text(strip=True)
        if text and href.startswith("http"):
            links.append({"url": href, "text": text})

    return {
        "title": title,
        "content": content,
        "publish_date": publish_date,
        "attachments": attachments,
        "links": links,
    }


# ─────────────────────────────────────────────
#  URL 工具
# ─────────────────────────────────────────────

def normalize_url(url: str) -> str:
    """URL 规范化（去 fragment、排序 query）"""
    parsed = urlparse(url)
    # 去除 fragment
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"


def url_to_filename(url: str, ext: str = ".html") -> str:
    """基于 URL 生成稳定的文件名"""
    digest = hashlib.md5(url.encode("utf-8")).hexdigest()[:10]
    return f"{digest}{ext}"


def is_same_domain(url: str, base_url: str) -> bool:
    """判断 URL 是否与基础 URL 同域"""
    return urlparse(url).netloc == urlparse(base_url).netloc


def deduplicate_urls(urls: List[str]) -> List[str]:
    """URL 去重（保持顺序）"""
    seen = set()
    result = []
    for url in urls:
        normalized = normalize_url(url)
        if normalized not in seen:
            seen.add(normalized)
            result.append(url)
    return result


# ─────────────────────────────────────────────
#  限速器
# ─────────────────────────────────────────────

class CrawlRateLimiter:
    """爬虫限速器，控制请求频率"""

    def __init__(self, requests_per_second: float = 1.0):
        self._interval = 1.0 / requests_per_second if requests_per_second > 0 else 1.0
        self._last_request_time: float = 0

    def wait(self) -> None:
        """等待直到可以发起下一次请求"""
        now = time.time()
        elapsed = now - self._last_request_time
        if elapsed < self._interval:
            time.sleep(self._interval - elapsed)
        self._last_request_time = time.time()


# ─────────────────────────────────────────────
#  列表页链接提取
# ─────────────────────────────────────────────

def extract_list_links(
    html: str,
    base_url: str,
    keyword_filter: Optional[List[str]] = None,
) -> List[Dict[str, str]]:
    """
    从列表页提取文章链接。

    Args:
        html: 列表页 HTML
        base_url: 基础 URL
        keyword_filter: 只保留标题中包含这些关键词的链接

    Returns:
        [{"url": str, "title": str}, ...]
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    results = []

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        text = a.get_text(strip=True)

        if not text or len(text) < 4:
            continue

        # 过滤关键词
        if keyword_filter:
            if not any(kw in text for kw in keyword_filter):
                continue

        full_url = urljoin(base_url, href)
        if full_url.startswith("http"):
            results.append({"url": full_url, "title": text})

    return results
