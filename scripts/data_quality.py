# -*- coding: utf-8 -*-
"""
data_quality.py — 数据质量评估器

职责:
  - 评估数据完整性（字段缺失率、空值率）
  - 分析内容长度分布
  - 检查分类均衡性
  - 验证分块质量
  - 生成质量报告

使用方式:
  python scripts/data_quality.py --source data/raw/policies
"""

from __future__ import annotations

import argparse
import json
import logging
import statistics
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
#  质量指标
# ─────────────────────────────────────────────

class QualityMetrics:
    """数据质量指标容器"""

    def __init__(self):
        self.total_items = 0
        self.valid_items = 0
        self.completeness = {}  # 字段完整率
        self.content_lengths = []
        self.categories = {}
        self.issues = []
        self.warnings = []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_items": self.total_items,
            "valid_items": self.valid_items,
            "validity_rate": self.valid_items / max(self.total_items, 1),
            "completeness": self.completeness,
            "content_stats": self._content_stats(),
            "category_distribution": self.categories,
            "issues": self.issues,
            "warnings": self.warnings,
        }

    def _content_stats(self) -> Dict[str, Any]:
        if not self.content_lengths:
            return {"avg": 0, "min": 0, "max": 0, "median": 0}
        return {
            "avg": round(statistics.mean(self.content_lengths), 1),
            "min": min(self.content_lengths),
            "max": max(self.content_lengths),
            "median": round(statistics.median(self.content_lengths), 1),
        }


# ─────────────────────────────────────────────
#  数据质量评估器
# ─────────────────────────────────────────────

class DataQualityEvaluator:
    """
    数据质量评估器。

    评估维度:
      1. 完整性：必需字段是否缺失
      2. 有效性：内容长度、格式是否合规
      3. 一致性：分类标签是否规范
      4. 均衡性：各类别数据量是否合理
    """

    # 必需字段（含别名：活动数据用 description/event_time）
    REQUIRED_FIELDS = ["title", "content", "publish_date"]
    FIELD_ALIASES = {
        "content": ["description"],
        "publish_date": ["event_time"],
    }

    @classmethod
    def _get_field(cls, item: Dict[str, Any], field: str) -> Any:
        """按主字段名或别名取值"""
        value = item.get(field)
        if value:
            return value
        for alias in cls.FIELD_ALIASES.get(field, []):
            value = item.get(alias)
            if value:
                return value
        return value

    # 内容长度阈值
    MIN_CONTENT_LENGTH = 50
    MAX_CONTENT_LENGTH = 10000

    def evaluate_source(self, source_path: str) -> QualityMetrics:
        """评估数据源"""
        path = Path(source_path)
        metrics = QualityMetrics()

        if not path.exists():
            metrics.issues.append(f"路径不存在: {source_path}")
            return metrics

        # 加载数据
        items = self._load_data(path)
        if not items:
            metrics.issues.append("无法加载数据")
            return metrics

        metrics.total_items = len(items)

        # 活动类数据（含 type 字段）的必需字段不含日期（活动通知常无明确日期）
        is_activity_source = any("type" in item and "title" in item for item in items[:5])
        required = ["title", "content"] if is_activity_source else self.REQUIRED_FIELDS

        # 逐条评估
        for item in items:
            self._evaluate_item(item, metrics, required_fields=required)

        # 汇总评估
        self._evaluate_overall(metrics)

        return metrics

    def _load_data(self, path: Path) -> List[Dict[str, Any]]:
        """加载数据"""
        items = []

        if path.is_file() and path.suffix == ".json":
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        items = data
                    elif isinstance(data, dict):
                        items = [data]
            except Exception as e:
                logger.error("加载 JSON 失败: %s", e)

        elif path.is_dir():
            for json_file in path.glob("*.json"):
                try:
                    with open(json_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        if isinstance(data, list):
                            items.extend(data)
                        elif isinstance(data, dict):
                            items.append(data)
                except Exception:
                    pass

        return items

    def _evaluate_item(self, item: Dict[str, Any], metrics: QualityMetrics,
                       required_fields: Optional[List[str]] = None):
        """评估单个数据项"""
        is_valid = True
        required_fields = required_fields or self.REQUIRED_FIELDS

        # 1. 完整性检查（支持字段别名）
        for field in required_fields:
            if not self._get_field(item, field):
                metrics.completeness.setdefault(field, {"total": 0, "missing": 0})
                metrics.completeness[field]["missing"] += 1
                is_valid = False

        # 记录完整性统计
        for field in required_fields:
            metrics.completeness.setdefault(field, {"total": 0, "missing": 0})
            metrics.completeness[field]["total"] += 1

        # 2. 内容长度检查（支持 description 别名）
        content = self._get_field(item, "content") or ""
        content_len = len(content)
        metrics.content_lengths.append(content_len)

        if content_len < self.MIN_CONTENT_LENGTH:
            metrics.warnings.append(f"内容过短 ({content_len} 字符): {item.get('title', 'N/A')[:30]}")
            is_valid = False
        elif content_len > self.MAX_CONTENT_LENGTH:
            metrics.warnings.append(f"内容过长 ({content_len} 字符): {item.get('title', 'N/A')[:30]}")

        # 3. 分类检查（活动数据用 type 字段）
        category = item.get("category") or item.get("type") or "unknown"
        metrics.categories[category] = metrics.categories.get(category, 0) + 1

        # 4. 日期格式检查（活动数据的 event_time 常为自由文本，放宽校验）
        pub_date = self._get_field(item, "publish_date") or ""
        if pub_date and not self._is_valid_date(pub_date) and "event_time" not in item:
            metrics.warnings.append(f"日期格式异常: {pub_date}")

        if is_valid:
            metrics.valid_items += 1

    def _evaluate_overall(self, metrics: QualityMetrics):
        """整体评估"""
        # 有效率检查
        validity_rate = metrics.valid_items / max(metrics.total_items, 1)
        if validity_rate < 0.8:
            metrics.issues.append(f"有效率过低: {validity_rate:.1%}")

        # 分类均衡性检查
        if metrics.categories:
            total = sum(metrics.categories.values())
            for cat, count in metrics.categories.items():
                ratio = count / total
                if ratio < 0.05:
                    metrics.warnings.append(f"分类 '{cat}' 数据量过少: {count} ({ratio:.1%})")

        # 内容长度分布检查
        if metrics.content_lengths:
            std_dev = statistics.stdev(metrics.content_lengths) if len(metrics.content_lengths) > 1 else 0
            mean_len = statistics.mean(metrics.content_lengths)
            if std_dev > mean_len * 2:
                metrics.warnings.append("内容长度方差过大，数据质量不均")

    def _is_valid_date(self, date_str: str) -> bool:
        """检查日期格式"""
        import re
        # 支持 YYYY-MM-DD 或 YYYY年MM月DD日 格式
        if re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
            return True
        if re.match(r"^\d{4}年\d{1,2}月\d{1,2}日$", date_str):
            return True
        return False


# ─────────────────────────────────────────────
#  索引质量评估
# ─────────────────────────────────────────────

class IndexQualityEvaluator:
    """索引质量评估器"""

    def evaluate_index(self, index_dir: str) -> Dict[str, Any]:
        """评估索引质量"""
        from data_pipeline.index_builder import IndexBuilder

        result = {
            "loaded": False,
            "stats": {},
            "test_queries": [],
            "issues": [],
        }

        try:
            builder = IndexBuilder.load(Path(index_dir))
            stats = builder.stats()
            result["loaded"] = True
            result["stats"] = stats

            # 测试查询
            test_queries = [
                ("保研条件", "academic"),
                ("图书馆开放时间", "life"),
                ("课程资料", "course"),
            ]

            for query, expected_cat in test_queries:
                results = builder.search(query, top_k=5, use_dense=False)
                test_result = {
                    "query": query,
                    "expected_category": expected_cat,
                    "result_count": len(results),
                    "top_category": results[0].get("category", "") if results else "",
                    "latency_ms": 0,
                }
                result["test_queries"].append(test_result)

                if not results:
                    result["issues"].append(f"查询 '{query}' 无结果")

        except Exception as e:
            result["issues"].append(f"索引加载失败: {e}")

        return result


# ─────────────────────────────────────────────
#  命令行入口
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="数据质量评估工具")
    parser.add_argument("--source", type=str, help="数据源路径（目录或JSON文件）")
    parser.add_argument("--index", type=str, help="索引目录")
    parser.add_argument("--report", type=str, help="输出报告路径")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")

    if args.source:
        evaluator = DataQualityEvaluator()
        metrics = evaluator.evaluate_source(args.source)
        report = metrics.to_dict()

        print("\n" + "=" * 50)
        print("数据质量评估报告")
        print("=" * 50)
        print(f"总条目: {report['total_items']}")
        print(f"有效条目: {report['valid_items']} ({report['validity_rate']:.1%})")
        print(f"内容长度: avg={report['content_stats']['avg']}, "
              f"min={report['content_stats']['min']}, "
              f"max={report['content_stats']['max']}")
        print(f"分类分布: {json.dumps(report['category_distribution'], ensure_ascii=False)}")
        if report["issues"]:
            print(f"\n问题 ({len(report['issues'])}):")
            for issue in report["issues"][:5]:
                print(f"  [!] {issue}")
        if report["warnings"]:
            print(f"\n警告 ({len(report['warnings'])}):")
            for warn in report["warnings"][:5]:
                print(f"  [?] {warn}")
        print("=" * 50)

        if args.report:
            with open(args.report, "w", encoding="utf-8") as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
            print(f"\n报告已保存: {args.report}")

    if args.index:
        idx_evaluator = IndexQualityEvaluator()
        idx_report = idx_evaluator.evaluate_index(args.index)

        print("\n" + "=" * 50)
        print("索引质量评估报告")
        print("=" * 50)
        print(f"索引状态: {'已加载' if idx_report['loaded'] else '加载失败'}")
        if idx_report["loaded"]:
            print(f"索引统计: {json.dumps(idx_report['stats'], ensure_ascii=False)}")
        for tq in idx_report.get("test_queries", []):
            print(f"  查询 '{tq['query']}': {tq['result_count']} 结果")
        if idx_report["issues"]:
            print("问题:")
            for issue in idx_report["issues"]:
                print(f"  [!] {issue}")
        print("=" * 50)


if __name__ == "__main__":
    main()
