# -*- coding: utf-8 -*-
"""
import_course_data.py — 课程数据完整入库脚本

职责:
  - 读取课程资料 JSON
  - 调用 CourseProcessor 处理
  - 构建课程专用索引
  - 验证入库结果

使用方式:
  python scripts/import_course_data.py --source data/raw/course_materials/courses.json
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from data_pipeline.course_processor import CourseProcessor

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
#  课程数据导入器
# ─────────────────────────────────────────────

class CourseDataImporter:
    """课程数据导入器"""

    def __init__(self, output_dir: str = "data/processed/course_indexes"):
        self._output_dir = Path(output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._processor = CourseProcessor()

    def import_from_file(self, file_path: str) -> Dict[str, Any]:
        """从 JSON 文件导入课程数据"""
        path = Path(file_path)
        if not path.exists():
            logger.error("文件不存在: %s", file_path)
            return {"success": False, "error": "文件不存在"}

        try:
            with open(path, "r", encoding="utf-8") as f:
                courses = json.load(f)
        except Exception as e:
            logger.error("读取 JSON 失败: %s", e)
            return {"success": False, "error": str(e)}

        results = []
        total_chunks = 0
        total_knowledge_points = 0

        for course_data in courses:
            try:
                result = self._processor.process_course(course_data)
                results.append(result)
                total_chunks += result["stats"]["chunks_count"]
                total_knowledge_points += result["stats"]["knowledge_points"]
            except Exception as e:
                logger.error("处理课程 '%s' 失败: %s", course_data.get("course_name", "?"), e)

        # 保存处理结果
        output = {
            "courses": results,
            "summary": {
                "total_courses": len(results),
                "total_chunks": total_chunks,
                "total_knowledge_points": total_knowledge_points,
            },
        }

        output_path = self._output_dir / "course_processed.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)

        # 构建课程索引
        self._build_course_index(results)

        stats = {
            "success": True,
            "courses_processed": len(results),
            "total_chunks": total_chunks,
            "total_knowledge_points": total_knowledge_points,
            "output_path": str(output_path),
        }

        logger.info(
            "[CourseImport] 完成: %d 课程, %d 分块, %d 知识点",
            stats["courses_processed"],
            stats["total_chunks"],
            stats["total_knowledge_points"],
        )

        return stats

    def _build_course_index(self, results: List[Dict[str, Any]]):
        """构建课程专用索引"""
        # 收集所有分块
        all_chunks = []
        course_metadata = {}

        for result in results:
            course_info = result["course_info"]
            course_id = course_info["course_id"]
            course_metadata[course_id] = course_info

            for chunk in result["chunks"]:
                chunk_data = {
                    "chunk_id": chunk.get("chunk_id", ""),
                    "course_id": course_id,
                    "course_name": course_info["course_name"],
                    "content": chunk.get("content", ""),
                    "material_type": chunk.get("material_type", "unknown"),
                    "parent_headings": chunk.get("parent_headings", []),
                }
                all_chunks.append(chunk_data)

        # 保存索引数据
        index_data = {
            "chunks": all_chunks,
            "courses": course_metadata,
            "chunk_count": len(all_chunks),
        }

        index_path = self._output_dir / "course_index.json"
        with open(index_path, "w", encoding="utf-8") as f:
            json.dump(index_data, f, ensure_ascii=False, indent=2)

        logger.info("[CourseImport] 课程索引已保存: %d 分块 → %s", len(all_chunks), index_path)

    def verify(self) -> Dict[str, Any]:
        """验证入库结果"""
        output_path = self._output_dir / "course_processed.json"
        index_path = self._output_dir / "course_index.json"

        result = {
            "valid": False,
            "issues": [],
            "stats": {},
        }

        if not output_path.exists():
            result["issues"].append("处理结果文件不存在")
            return result

        if not index_path.exists():
            result["issues"].append("索引文件不存在")
            return result

        try:
            with open(output_path, "r", encoding="utf-8") as f:
                processed = json.load(f)
            with open(index_path, "r", encoding="utf-8") as f:
                index = json.load(f)

            result["valid"] = True
            result["stats"] = {
                "courses": len(processed.get("courses", [])),
                "chunks": index.get("chunk_count", 0),
            }
        except Exception as e:
            result["issues"].append(f"验证失败: {e}")

        return result


# ─────────────────────────────────────────────
#  命令行入口
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="课程数据入库工具")
    parser.add_argument("--source", type=str, required=True, help="课程数据 JSON 文件路径")
    parser.add_argument("--output", type=str, default="data/processed/course_indexes", help="输出目录")
    parser.add_argument("--verify", action="store_true", help="验证入库结果")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")

    importer = CourseDataImporter(output_dir=args.output)

    if args.source:
        print(f"\n=== 课程数据入库 ===")
        print(f"数据源: {args.source}")

        stats = importer.import_from_file(args.source)

        print(f"\n=== 入库统计 ===")
        print(json.dumps(stats, indent=2, ensure_ascii=False))

    if args.verify or not args.source:
        print(f"\n=== 入库验证 ===")
        result = importer.verify()
        print(f"有效: {result['valid']}")
        if result["issues"]:
            for issue in result["issues"]:
                print(f"  [!] {issue}")
        if result.get("stats"):
            print(f"统计: {json.dumps(result['stats'], ensure_ascii=False)}")


if __name__ == "__main__":
    main()
