"""
policy_crawler.py — 教务处政策通知爬虫

职责:
  - 爬取教务处政策通知列表页
  - 提取详情页正文 + 附件下载
  - 支持关键词过滤（保研/转专业/选课/补考/四六级等）
  - 输出结构化 JSON，供 data_pipeline 后续处理
  - 尊重 robots.txt，限速请求

使用方式:
  from crawler.policy_crawler import PolicyCrawler

  crawler = PolicyCrawler()
  results = crawler.crawl(
      list_url="https://jwc.example.edu.cn/notice/",
      keywords=["保研", "转专业", "选课"],
  )
  crawler.save_results(results, "data/raw/policies/")
"""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from .utils import (
    CrawlRateLimiter,
    deduplicate_urls,
    download_pdf,
    extract_article,
    extract_list_links,
    fetch_page,
    is_same_domain,
    normalize_url,
    url_to_filename,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
#  政策通知爬虫
# ─────────────────────────────────────────────

class PolicyCrawler:
    """
    教务处政策通知爬虫。

    爬取流程:
      1. 访问列表页，提取文章链接
      2. 逐页访问详情页，提取正文 + 附件
      3. 下载 PDF 附件到本地
      4. 输出结构化 JSON

    限速策略:
      - 默认 1 请求/秒
      - 同域名请求
      - 失败自动跳过

    示例:
        >>> crawler = PolicyCrawler(rate_limit=1.0)
        >>> results = crawler.crawl(
        ...     list_url="https://jwc.example.edu.cn/tzgg/",
        ...     keywords=["保研", "推免", "转专业"],
        ...     max_pages=3,
        ... )
        >>> len(results)
        15
    """

    # 政策关键词（默认过滤集）
    DEFAULT_KEYWORDS = [
        "保研", "推免", "转专业", "选课", "补考", "四六级",
        "学籍", "休学", "复学", "退学", "毕业", "学位",
        "学分", "绩点", "奖学金", "助学金", "培养方案",
        "教学计划", "考试", "重修", "免修", "交换生",
    ]

    def __init__(
        self,
        rate_limit: float = 1.0,
        max_depth: int = 2,
        download_attachments: bool = True,
    ):
        """
        Args:
            rate_limit: 每秒请求数
            max_depth: 最大翻页深度
            download_attachments: 是否下载 PDF 附件
        """
        self._limiter = CrawlRateLimiter(rate_limit)
        self._max_depth = max_depth
        self._download_attachments = download_attachments
        self._visited_urls: set = set()

    # ── 公共接口 ──────────────────────────────

    def crawl(
        self,
        list_url: str,
        keywords: Optional[List[str]] = None,
        max_pages: int = 3,
        save_dir: Optional[str | Path] = None,
        encoding: Optional[str] = None,
    ) -> List[Dict]:
        """
        爬取政策通知。

        Args:
            list_url: 列表页 URL
            keywords: 过滤关键词列表（默认使用 DEFAULT_KEYWORDS）
            max_pages: 最大爬取页数
            save_dir: PDF 附件保存目录
            encoding: 强制页面编码

        Returns:
            结构化的政策通知列表
        """
        keywords = keywords or self.DEFAULT_KEYWORDS
        save_dir = Path(save_dir) if save_dir else Path("data/raw/policies")
        save_dir.mkdir(parents=True, exist_ok=True)

        logger.info(
            "[PolicyCrawler] 开始爬取: %s | 关键词=%s | 最大页数=%d",
            list_url, keywords, max_pages,
        )

        all_links = []
        current_url = list_url

        # 1. 爬取列表页（支持翻页）
        for page in range(max_pages):
            logger.info("[PolicyCrawler] 爬取列表页 %d: %s", page + 1, current_url)
            self._limiter.wait()

            html = fetch_page(current_url, encoding=encoding)
            if not html:
                logger.warning("[PolicyCrawler] 列表页获取失败: %s", current_url)
                break

            # 提取链接
            links = extract_list_links(html, current_url, keyword_filter=keywords)
            all_links.extend(links)

            # 尝试找下一页链接
            next_url = self._find_next_page(html, current_url)
            if not next_url or next_url in self._visited_urls:
                break
            self._visited_urls.add(current_url)
            current_url = next_url

        # 去重
        seen_urls = set()
        unique_links = []
        for link in all_links:
            normalized = normalize_url(link["url"])
            if normalized not in seen_urls:
                seen_urls.add(normalized)
                unique_links.append(link)

        logger.info("[PolicyCrawler] 发现 %d 条相关链接", len(unique_links))

        # 2. 逐页爬取详情
        results = []
        for link in unique_links:
            result = self._crawl_detail(
                url=link["url"],
                title=link["title"],
                save_dir=save_dir,
                encoding=encoding,
            )
            if result:
                results.append(result)

        logger.info("[PolicyCrawler] 爬取完成: %d/%d 成功", len(results), len(unique_links))
        return results

    def crawl_urls(
        self,
        urls: List[Dict[str, str]],
        save_dir: Optional[str | Path] = None,
        encoding: Optional[str] = None,
    ) -> List[Dict]:
        """
        直接爬取指定的 URL 列表。

        Args:
            urls: [{"url": str, "title": str}, ...]
            save_dir: 附件保存目录
            encoding: 编码
        """
        save_dir = Path(save_dir) if save_dir else Path("data/raw/policies")
        save_dir.mkdir(parents=True, exist_ok=True)

        results = []
        for item in urls:
            result = self._crawl_detail(
                url=item["url"],
                title=item.get("title", ""),
                save_dir=save_dir,
                encoding=encoding,
            )
            if result:
                results.append(result)

        return results

    # ── 结果保存 ──────────────────────────────

    def save_results(self, results: List[Dict], output_dir: str | Path) -> Path:
        """
        将爬取结果保存为 JSON 文件。

        Args:
            results: 爬取结果列表
            output_dir: 输出目录

        Returns:
            保存的文件路径
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = output_dir / f"policies_{timestamp}.json"

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

        logger.info("[PolicyCrawler] 结果已保存: %s (%d 条)", output_path, len(results))
        return output_path

    # ── 内部方法 ──────────────────────────────

    def _crawl_detail(
        self,
        url: str,
        title: str,
        save_dir: Path,
        encoding: Optional[str] = None,
    ) -> Optional[Dict]:
        """爬取单个详情页"""
        self._limiter.wait()

        html = fetch_page(url, encoding=encoding)
        if not html:
            return None

        try:
            article = extract_article(html, base_url=url)

            # 如果标题为空，使用传入的标题
            if not article["title"]:
                article["title"] = title

            result = {
                "url": url,
                "title": article["title"],
                "content": article["content"],
                "publish_date": article["publish_date"],
                "crawl_time": datetime.now().isoformat(),
                "attachments": [],
            }

            # 下载 PDF 附件
            if self._download_attachments and article["attachments"]:
                for att in article["attachments"]:
                    self._limiter.wait()
                    saved = download_pdf(
                        url=att["url"],
                        save_dir=save_dir,
                    )
                    if saved:
                        result["attachments"].append({
                            "url": att["url"],
                            "name": att["name"],
                            "local_path": str(saved),
                        })

            logger.info(
                "[PolicyCrawler] ✓ %s | %d字 | %d附件",
                result["title"][:40],
                len(result["content"]),
                len(result["attachments"]),
            )
            return result

        except Exception as e:
            logger.warning("[PolicyCrawler] 详情页解析失败 %s: %s", url, e)
            return None

    @staticmethod
    def _find_next_page(html: str, current_url: str) -> Optional[str]:
        """从列表页 HTML 中提取下一页链接"""
        from bs4 import BeautifulSoup
        from urllib.parse import urljoin

        soup = BeautifulSoup(html, "html.parser")

        # 常见的下一页链接模式
        next_patterns = [
            re.compile(r"下一页|next|下页|>", re.I),
        ]

        for a in soup.find_all("a", href=True):
            text = a.get_text(strip=True)
            for pattern in next_patterns:
                if pattern.search(text):
                    href = a["href"]
                    next_url = urljoin(current_url, href)
                    if next_url.startswith("http"):
                        return next_url

        # 尝试数字翻页（如 ?page=2, &p=2）
        page_pattern = re.compile(r"([?&])(page|p|pageNum|currentPage)=(\d+)")
        match = page_pattern.search(current_url)
        if match:
            sep, key, page_num = match.groups()
            next_page = int(page_num) + 1
            next_url = page_pattern.sub(f"{sep}{key}={next_page}", current_url)
            return next_url

        return None


# ─────────────────────────────────────────────
#  离线模式：从预置 JSON 加载
# ─────────────────────────────────────────────

class OfflinePolicyLoader:
    """
    离线策略数据加载器。

    当无法爬取或需要开发测试时，从预置 JSON 文件加载数据。
    """

    @staticmethod
    def load(json_path: str | Path) -> List[Dict]:
        """加载预置的政策数据 JSON"""
        path = Path(json_path)
        if not path.exists():
            logger.warning("[OfflinePolicyLoader] 文件不存在: %s", path)
            return []

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, list):
            return data
        elif isinstance(data, dict) and "items" in data:
            return data["items"]
        return []

    @staticmethod
    def create_sample_data(output_dir: str | Path, count: int = 10) -> Path:
        """
        创建示例政策数据（用于开发和测试）。

        Args:
            output_dir: 输出目录
            count: 生成条数

        Returns:
            生成的文件路径
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        samples = [
            {
                "url": "https://jwc.example.edu.cn/notice/2026/baoyan.html",
                "title": "关于2026年推荐优秀应届本科毕业生免试攻读硕士学位研究生工作的通知",
                "content": "各学院：根据教育部相关文件精神，结合我校实际情况，现将2026年推免工作有关事项通知如下：\n\n"
                           "一、申请条件\n1. 全日制普通本科应届毕业生；\n2. 学业成绩排名在本专业前30%；\n3. 无违纪处分记录。\n\n"
                           "二、工作安排\n各学院应于9月15日前完成初审工作，9月30日前完成复审。\n\n"
                           "三、材料提交\n请各学院统一提交申请表、成绩单及综合素质评价表。",
                "publish_date": "2026年8月20日",
                "crawl_time": "2026-08-21T10:00:00",
                "attachments": [],
            },
            {
                "url": "https://jwc.example.edu.cn/notice/2026/zhuanzhuanye.html",
                "title": "2026年本科生转专业工作实施办法",
                "content": "为尊重学生个性发展，充分调动学生学习积极性，根据《普通高等学校学生管理规定》和我校实际情况，"
                           "特制定本办法。\n\n"
                           "一、转专业条件\n1. 在校全日制本科一年级学生；\n2. 入学后未受过纪律处分；\n3. 高考招生时未跨批次。\n\n"
                           "二、名额分配\n各专业接收转专业学生比例不超过该专业当年招生人数的10%。\n\n"
                           "三、考核方式\n转专业考核由接收学院组织，包括笔试和面试两个环节。",
                "publish_date": "2026年3月15日",
                "crawl_time": "2026-03-16T09:00:00",
                "attachments": [],
            },
            {
                "url": "https://jwc.example.edu.cn/notice/2026/xuanke.html",
                "title": "2026-2027学年第一学期选课通知",
                "content": "各学院、各位同学：\n\n"
                           "2026-2027学年第一学期选课工作即将开始，现将有关事项通知如下：\n\n"
                           "一、选课时间\n第一轮选课：2026年6月20日-6月27日\n"
                           "第二轮选课（补退选）：2026年9月1日-9月7日\n\n"
                           "二、选课方式\n登录教务系统（http://jwxt.example.edu.cn）进行选课操作。\n\n"
                           "三、注意事项\n1. 每位学生每学期选课学分上限为30学分；\n2. 必修课无需选课，系统自动分配。",
                "publish_date": "2026年6月10日",
                "crawl_time": "2026-06-11T08:00:00",
                "attachments": [],
            },
            {
                "url": "https://jwc.example.edu.cn/notice/2026/bukao.html",
                "title": "关于2026年春季学期补考安排的通知",
                "content": "各学院：\n\n"
                           "根据教学安排，2026年春季学期补考安排如下：\n\n"
                           "一、补考时间\n2026年3月1日至3月10日\n\n"
                           "二、补考范围\n上学期期末考试不及格的必修课程。\n\n"
                           "三、注意事项\n1. 每位学生最多可参加2门课程的补考；\n2. 补考成绩最高记为60分。",
                "publish_date": "2026年2月15日",
                "crawl_time": "2026-02-16T09:00:00",
                "attachments": [],
            },
            {
                "url": "https://jwc.example.edu.cn/notice/2026/cet.html",
                "title": "2026年上半年大学英语四六级考试报名通知",
                "content": "各位同学：\n\n"
                           "2026年上半年全国大学英语四、六级考试报名工作即将开始，现将有关事项通知如下：\n\n"
                           "一、报名时间\n2026年3月20日至3月31日\n\n"
                           "二、考试时间\n英语四级：2026年6月14日上午\n英语六级：2026年6月14日下午\n\n"
                           "三、报名方式\n登录全国大学英语四六级考试报名网站进行报名。",
                "publish_date": "2026年3月10日",
                "crawl_time": "2026-03-11T08:00:00",
                "attachments": [],
            },
        ]

        # 重复填充到指定数量
        while len(samples) < count:
            base = samples[len(samples) % 5]
            sample = dict(base)
            sample["title"] = f"{sample['title']}（第{len(samples) + 1}批）"
            samples.append(sample)

        output_path = output_dir / "sample_policies.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(samples[:count], f, ensure_ascii=False, indent=2)

        logger.info("[OfflinePolicyLoader] 示例数据已生成: %s (%d 条)", output_path, count)
        return output_path


# ─────────────────────────────────────────────
#  命令行入口
# ─────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")

    if len(sys.argv) >= 2 and sys.argv[1] == "--sample":
        # 生成示例数据
        count = int(sys.argv[2]) if len(sys.argv) > 2 else 10
        path = OfflinePolicyLoader.create_sample_data("data/raw/policies", count=count)
        print(f"[OK] 示例数据已生成: {path}")
    elif len(sys.argv) >= 2:
        # 爬取指定 URL
        url = sys.argv[1]
        crawler = PolicyCrawler(rate_limit=1.0)
        results = crawler.crawl(url, max_pages=2)
        output = crawler.save_results(results, "data/raw/policies")
        print(f"[OK] 爬取完成: {len(results)} 条 → {output}")
    else:
        print("用法:")
        print("  python policy_crawler.py --sample [count]    生成示例数据")
        print("  python policy_crawler.py <list_url>          爬取指定列表页")
