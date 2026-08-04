"""
import_data.py — 数据导入脚本（全流程管道）

职责:
  - 读取原始数据（JSON / PDF / HTML）
  - 执行完整管道：解析 → 清洗 → 分块 → 标注 → 索引构建
  - 数据入库（写入 SQLite）
  - 生成索引统计报告

使用方式:
  python scripts/import_data.py --source data/raw/policies/ --type policy
  python scripts/import_data.py --source data/raw/activities/ --type activity
  python scripts/import_data.py --all   # 导入所有数据
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Dict, List

# 确保项目根目录在 sys.path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from data_pipeline.doc_parser import DocParser, ParsedDocument
from data_pipeline.text_cleaner import TextCleaner, CleanedDocument
from data_pipeline.chunker import LayoutChunker
from data_pipeline.metadata_annotator import MetadataAnnotator, AnnotatedDocument
from data_pipeline.index_builder import IndexBuilder

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
#  数据导入管道
# ─────────────────────────────────────────────

class DataImporter:
    """
    完整数据导入管道。

    流程: 原始文件 → DocParser → TextCleaner → LayoutChunker → MetadataAnnotator → IndexBuilder → DB
    """

    def __init__(self, use_llm: bool = False, chunk_size: int = 512, chunk_overlap: int = 50):
        self._parser = DocParser()
        self._cleaner = TextCleaner()
        self._chunker = LayoutChunker(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        self._annotator = MetadataAnnotator(use_llm=use_llm)
        self._use_llm = use_llm

    def import_from_files(
        self,
        source_dir: str | Path,
        file_exts: tuple = (".pdf", ".docx", ".html", ".htm"),
    ) -> Dict:
        """
        从文件目录导入数据。

        Args:
            source_dir: 源文件目录
            file_exts: 支持的文件扩展名

        Returns:
            {"annotated": [...], "chunks": {...}, "stats": {...}}
        """
        source_dir = Path(source_dir)
        if not source_dir.exists():
            logger.error("目录不存在: %s", source_dir)
            return {"annotated": [], "chunks": {}, "stats": {}}

        # 1. 发现文件
        files = []
        for ext in file_exts:
            files.extend(source_dir.rglob(f"*{ext}"))
        logger.info("[Import] 发现 %d 个文件 in %s", len(files), source_dir)

        if not files:
            return {"annotated": [], "chunks": {}, "stats": {}}

        # 2. 解析
        parsed_docs = self._parser.parse_batch([str(f) for f in files])
        logger.info("[Import] 解析: %d/%d 成功", len(parsed_docs), len(files))

        # 3. 清洗
        cleaned_docs = self._cleaner.clean_batch(parsed_docs)
        logger.info("[Import] 清洗: %d 有效文档", len(cleaned_docs))

        # 4. 分块
        chunks_map = self._chunker.chunk_batch(cleaned_docs)
        total_chunks = sum(len(v) for v in chunks_map.values())
        logger.info("[Import] 分块: %d 文档, %d 块", len(chunks_map), total_chunks)

        # 5. 标注
        annotated = self._annotator.annotate_batch(cleaned_docs)
        logger.info("[Import] 标注: %d 文档", len(annotated))

        # 统计
        cat_counts = {}
        for doc in annotated:
            cat_counts[doc.category] = cat_counts.get(doc.category, 0) + 1

        stats = {
            "files_found": len(files),
            "parsed": len(parsed_docs),
            "cleaned": len(cleaned_docs),
            "chunked_docs": len(chunks_map),
            "total_chunks": total_chunks,
            "annotated": len(annotated),
            "categories": cat_counts,
        }

        return {
            "annotated": annotated,
            "chunks": chunks_map,
            "stats": stats,
        }

    def import_from_json(
        self,
        json_path: str | Path,
        content_field: str = "content",
        title_field: str = "title",
    ) -> Dict:
        """
        从 JSON 文件导入数据（爬虫输出格式）。

        Args:
            json_path: JSON 文件路径
            content_field: 内容字段名
            title_field: 标题字段名

        Returns:
            {"annotated": [...], "chunks": {...}, "stats": {...}}
        """
        path = Path(json_path)
        if not path.exists():
            logger.error("文件不存在: %s", path)
            return {"annotated": [], "chunks": {}, "stats": {}}

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        items = data if isinstance(data, list) else data.get("items", [])
        logger.info("[Import] JSON 加载: %d 条", len(items))

        # 转换为 ParsedDocument
        import hashlib
        parsed_docs = []
        for item in items:
            content = item.get(content_field, "")
            if not content or not content.strip():
                continue

            title = item.get(title_field, "")
            doc_id = f"DOC_{hashlib.md5(str(item.get('url', title)).encode()).hexdigest()[:8].upper()}"

            parsed_docs.append(ParsedDocument(
                doc_id=doc_id,
                title=title,
                content=content,
                source_path=str(json_path),
                source_url=item.get("url"),
                file_type="json",
                metadata={
                    k: v for k, v in item.items()
                    if k not in (content_field, title_field, "url") and isinstance(v, (str, int, float))
                },
            ))

        # 清洗
        cleaned_docs = self._cleaner.clean_batch(parsed_docs)

        # 分块
        chunks_map = self._chunker.chunk_batch(cleaned_docs)
        total_chunks = sum(len(v) for v in chunks_map.values())

        # 标注
        annotated = self._annotator.annotate_batch(cleaned_docs)

        cat_counts = {}
        for doc in annotated:
            cat_counts[doc.category] = cat_counts.get(doc.category, 0) + 1

        stats = {
            "json_items": len(items),
            "parsed": len(parsed_docs),
            "cleaned": len(cleaned_docs),
            "chunked_docs": len(chunks_map),
            "total_chunks": total_chunks,
            "annotated": len(annotated),
            "categories": cat_counts,
        }

        return {
            "annotated": annotated,
            "chunks": chunks_map,
            "stats": stats,
        }

    # ── 索引构建 ──────────────────────────────

    def build_indexes(
        self,
        annotated: List[AnnotatedDocument],
        chunks_map: Dict[str, List[Dict]],
        output_dir: str | Path = "data/processed/indexes",
        use_dense: bool = True,
    ) -> IndexBuilder:
        """
        构建索引。

        Args:
            annotated: 标注后的文档列表
            chunks_map: 分块映射
            output_dir: 索引输出目录
            use_dense: 是否构建 Dense 索引

        Returns:
            IndexBuilder 实例
        """
        builder = IndexBuilder()

        embedding_client = None
        if use_dense:
            try:
                from utils.embedding_client import EmbeddingClient
                embedding_client = EmbeddingClient.get_instance()
            except Exception as e:
                logger.warning("[Import] Embedding 不可用，跳过 Dense 索引: %s", e)

        builder.build_from_documents(annotated, chunks_map, embedding_client)
        builder.save(output_dir)

        stats = builder.stats()
        logger.info("[Import] 索引构建完成: %s", json.dumps(stats, ensure_ascii=False))

        return builder


# ─────────────────────────────────────────────
#  验证脚本
# ─────────────────────────────────────────────

def verify_indexes(index_dir: str | Path = "data/processed/indexes") -> Dict:
    """
    验证索引完整性。

    Returns:
        {"valid": bool, "stats": {...}, "issues": [...]}
    """
    index_dir = Path(index_dir)
    issues = []

    if not index_dir.exists():
        return {"valid": False, "stats": {}, "issues": ["索引目录不存在"]}

    try:
        builder = IndexBuilder.load(index_dir)
        stats = builder.stats()

        if stats["global_bm25"] == 0:
            issues.append("全局 BM25 索引为空")
        if stats["global_dense"] == 0:
            issues.append("全局 Dense 索引为空（可能 Embedding 不可用）")

        # 测试检索
        test_queries = ["保研条件", "选课时间", "宿舍"]
        for query in test_queries:
            results = builder.search(query, top_k=3, use_dense=False)
            if not results:
                issues.append(f"测试查询 '{query}' 无结果")

        return {
            "valid": len(issues) == 0,
            "stats": stats,
            "issues": issues,
        }
    except Exception as e:
        return {"valid": False, "stats": {}, "issues": [f"索引加载失败: {e}"]}


# ─────────────────────────────────────────────
#  命令行入口
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="GraphCampus 数据导入工具")
    parser.add_argument("--source", type=str, help="数据源目录或文件路径")
    parser.add_argument("--type", type=str, choices=["policy", "activity", "auto"],
                        default="auto", help="数据类型")
    parser.add_argument("--all", action="store_true", help="导入所有默认目录的数据")
    parser.add_argument("--no-dense", action="store_true", help="跳过 Dense 索引构建")
    parser.add_argument("--verify", action="store_true", help="验证已有索引")
    parser.add_argument("--output", type=str, default="data/processed/indexes",
                        help="索引输出目录")
    parser.add_argument("--chunk-size", type=int, default=512, help="分块大小")
    parser.add_argument("--chunk-overlap", type=int, default=50, help="分块重叠")

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")

    if args.verify:
        print("=== 索引验证 ===")
        result = verify_indexes(args.output)
        print(f"有效: {result['valid']}")
        print(f"统计: {json.dumps(result['stats'], indent=2, ensure_ascii=False)}")
        if result["issues"]:
            print("问题:")
            for issue in result["issues"]:
                print(f"  [!] {issue}")
        return

    importer = DataImporter(
        use_llm=False,
        chunk_size=args.chunk_size,
        chunk_overlap=args.chunk_overlap,
    )

    all_annotated = []
    all_chunks_map = {}

    if args.all:
        # 导入所有默认目录
        dirs = [
            ("data/raw/policies", "policy"),
            ("data/raw/activities", "activity"),
            ("data/raw/life", "policy"),  # life guides also treated as policy-type
        ]
        for source_dir, dtype in dirs:
            path = Path(source_dir)
            if not path.exists():
                logger.info("跳过不存在的目录: %s", path)
                continue
            _import_dir(importer, path, dtype, all_annotated, all_chunks_map)
    elif args.source:
        source = Path(args.source)
        if source.is_file() and source.suffix == ".json":
            result = importer.import_from_json(source)
            all_annotated.extend(result["annotated"])
            all_chunks_map.update(result["chunks"])
            print(f"\n=== 导入统计 ===")
            print(json.dumps(result["stats"], indent=2, ensure_ascii=False))
        elif source.is_dir():
            _import_dir(importer, source, args.type, all_annotated, all_chunks_map)
        else:
            print(f"错误: {source} 不存在")
            return
    else:
        parser.print_help()
        return

    # 构建索引
    if all_annotated:
        print(f"\n=== 构建索引 ===")
        builder = importer.build_indexes(
            all_annotated, all_chunks_map,
            output_dir=args.output,
            use_dense=not args.no_dense,
        )
        print(f"索引统计: {json.dumps(builder.stats(), indent=2, ensure_ascii=False)}")

        # 验证
        print(f"\n=== 索引验证 ===")
        result = verify_indexes(args.output)
        print(f"有效: {result['valid']}")
        if result["issues"]:
            for issue in result["issues"]:
                print(f"  [!] {issue}")
    else:
        print("没有导入任何数据")


def _import_dir(importer, source_dir, dtype, all_annotated, all_chunks_map):
    """导入一个目录的数据"""
    print(f"\n=== 导入: {source_dir} ({dtype}) ===")

    # 尝试 JSON 文件
    json_files = list(Path(source_dir).glob("*.json"))
    file_data = list(Path(source_dir).glob("*.pdf")) + \
                list(Path(source_dir).glob("*.docx")) + \
                list(Path(source_dir).glob("*.html"))

    if json_files:
        for jf in json_files:
            result = importer.import_from_json(jf)
            all_annotated.extend(result["annotated"])
            all_chunks_map.update(result["chunks"])
            print(f"  JSON {jf.name}: {json.dumps(result['stats'], ensure_ascii=False)}")

    if file_data:
        result = importer.import_from_files(source_dir)
        all_annotated.extend(result["annotated"])
        all_chunks_map.update(result["chunks"])
        print(f"  文件: {json.dumps(result['stats'], ensure_ascii=False)}")


if __name__ == "__main__":
    main()
