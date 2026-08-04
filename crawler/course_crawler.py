# -*- coding: utf-8 -*-
"""
course_crawler.py — 课程资料爬虫 & 数据生成器

职责:
  - 模拟从教务系统抓取课程大纲/课件
  - 生成 20 门课程的完整样例数据
  - 输出 JSON 格式供 course_processor 消费

使用方式:
  python -m crawler.course_crawler --sample 20
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
#  课程数据模板
# ─────────────────────────────────────────────

_COURSE_TEMPLATES = [
    {
        "course_name": "C语言程序设计",
        "department": "计算机学院",
        "credits": 4,
        "syllabus_tpl": (
            "一、课程概述\n"
            "本课程是计算机类专业的核心基础课程，通过系统学习C语言的基本语法、数据结构和程序设计方法，"
            "培养学生的编程能力和计算思维。\n\n"
            "二、教学目标\n"
            "1. 掌握C语言的基本语法和语义\n"
            "2. 理解指针、数组、结构体等核心概念\n"
            "3. 掌握函数、文件操作等编程技巧\n"
            "4. 能够独立完成中等规模程序的设计与实现\n\n"
            "三、先修课程\n"
            "先修课程：无\n\n"
            "四、教学内容\n"
            "第一章 C语言概述\n"
            "第二章 数据类型与运算符\n"
            "第三章 控制结构\n"
            "第四章 函数\n"
            "第五章 数组\n"
            "第六章 指针\n"
            "第七章 结构体与共用体\n"
            "第八章 文件操作\n\n"
            "五、考核方式\n"
            "平时成绩占30%，期末考试占70%（闭卷）\n\n"
            "六、教材及参考资料\n"
            "《C程序设计语言》(K&R)\n"
            "《C Primer Plus》"
        ),
        "slides_tpl": (
            "第{week}周 课件\n\n"
            "本讲内容：{topic}\n\n"
            "重点：{key_point}\n\n"
            "示例代码：\n"
            "#include <stdio.h>\n"
            "int main() {{\n"
            "    printf(\"Hello, {topic}!\\n\");\n"
            "    return 0;\n"
            "}}\n\n"
            "课后作业：完成教材第{week}章习题1-5"
        ),
    },
    {
        "course_name": "数据结构与算法",
        "department": "计算机学院",
        "credits": 4,
        "syllabus_tpl": (
            "一、课程概述\n"
            "数据结构是计算机专业的核心课程，研究数据的逻辑结构、存储结构及其上的算法操作。\n\n"
            "二、教学目标\n"
            "1. 掌握线性表、栈、队列、树、图等基本数据结构\n"
            "2. 理解排序、查找等经典算法\n"
            "3. 能够分析算法的时间和空间复杂度\n"
            "4. 能够根据实际问题选择合适的数据结构\n\n"
            "三、先修课程\n"
            "先修课程：C语言程序设计、离散数学\n\n"
            "四、教学内容\n"
            "第一章 绪论\n"
            "第二章 线性表\n"
            "第三章 栈和队列\n"
            "第四章 串\n"
            "第五章 树与二叉树\n"
            "第六章 图\n"
            "第七章 查找\n"
            "第八章 排序\n\n"
            "五、考核方式\n"
            "平时成绩占20%，实验成绩占20%，期末考试占60%\n\n"
            "六、教材\n"
            "《数据结构（C语言版）》严蔚敏"
        ),
        "slides_tpl": (
            "第{week}周 课件\n\n"
            "主题：{topic}\n\n"
            "核心概念：{key_point}\n\n"
            "时间复杂度分析：\n"
            "- 最好情况: O(1)\n"
            "- 最坏情况: O(n)\n"
            "- 平均情况: O(log n)\n\n"
            "代码实现要点：\n"
            "1. 边界条件处理\n"
            "2. 内存管理\n"
            "3. 异常处理"
        ),
    },
    {
        "course_name": "操作系统原理",
        "department": "计算机学院",
        "credits": 3,
        "syllabus_tpl": (
            "一、课程概述\n"
            "操作系统是管理计算机硬件与软件资源的核心系统软件，本课程讲解操作系统的基本原理和实现技术。\n\n"
            "二、教学目标\n"
            "1. 理解进程、线程、调度等核心概念\n"
            "2. 掌握内存管理、文件系统的工作原理\n"
            "3. 了解I/O管理和设备驱动\n"
            "4. 能够分析操作系统的性能问题\n\n"
            "三、先修课程\n"
            "先修课程：C语言程序设计、计算机组成原理\n\n"
            "四、教学内容\n"
            "第一章 操作系统概述\n"
            "第二章 进程管理\n"
            "第三章 线程与并发\n"
            "第四章 内存管理\n"
            "第五章 文件系统\n"
            "第六章 I/O管理\n"
            "第七章 死锁\n"
            "第八章 安全与保护\n\n"
            "五、考核方式\n"
            "平时成绩占30%，实验占20%，期末考试占50%\n\n"
            "六、教材\n"
            "《现代操作系统》Tanenbaum"
        ),
        "slides_tpl": (
            "第{week}周 课件\n\n"
            "主题：{topic}\n\n"
            "关键概念：{key_point}\n\n"
            "核心机制：\n"
            "1. 系统调用\n"
            "2. 中断处理\n"
            "3. 上下文切换\n\n"
            "实例分析：\n"
            "Linux 进程调度策略\n"
            "- CFS (Completely Fair Scheduler)\n"
            "- 实时调度\n"
            "- 优先级调度"
        ),
    },
    {
        "course_name": "计算机网络",
        "department": "计算机学院",
        "credits": 3,
        "syllabus_tpl": (
            "一、课程概述\n"
            "本课程系统介绍计算机网络的基本原理、协议和技术，涵盖从物理层到应用层的完整知识体系。\n\n"
            "二、教学目标\n"
            "1. 掌握TCP/IP协议栈的分层模型\n"
            "2. 理解路由、交换、拥塞控制等核心机制\n"
            "3. 掌握HTTP、DNS等应用层协议\n"
            "4. 了解网络安全基础\n\n"
            "三、先修课程\n"
            "先修课程：操作系统原理\n\n"
            "四、教学内容\n"
            "第一章 概述\n"
            "第二章 物理层\n"
            "第三章 数据链路层\n"
            "第四章 网络层\n"
            "第五章 传输层\n"
            "第六章 应用层\n"
            "第七章 网络安全\n\n"
            "五、考核方式\n"
            "平时成绩占30%，实验占20%，期末考试占50%\n\n"
            "六、教材\n"
            "《计算机网络：自顶向下方法》Kurose"
        ),
        "slides_tpl": (
            "第{week}周 课件\n\n"
            "主题：{topic}\n\n"
            "核心协议：{key_point}\n\n"
            "报文格式：\n"
            "+------------------+\n"
            "|     Header       |\n"
            "+------------------+\n"
            "|     Payload      |\n"
            "+------------------+\n\n"
            "关键参数：\n"
            "- TTL: 生存时间\n"
            "- Window Size: 窗口大小\n"
            "- Checksum: 校验和"
        ),
    },
    {
        "course_name": "数据库系统原理",
        "department": "计算机学院",
        "credits": 3,
        "syllabus_tpl": (
            "一、课程概述\n"
            "数据库系统是信息化社会的核心技术基础设施，本课程讲解关系数据库的理论、设计和实现。\n\n"
            "二、教学目标\n"
            "1. 掌握关系模型和关系代数\n"
            "2. 熟练使用SQL进行数据操作\n"
            "3. 理解事务、并发控制、恢复机制\n"
            "4. 能够进行数据库设计（ER模型→关系模式）\n\n"
            "三、先修课程\n"
            "先修课程：数据结构与算法\n\n"
            "四、教学内容\n"
            "第一章 数据库系统概述\n"
            "第二章 关系模型\n"
            "第三章 SQL语言\n"
            "第四章 数据库设计\n"
            "第五章 查询优化\n"
            "第六章 事务管理\n"
            "第七章 并发控制\n"
            "第八章 数据库恢复\n\n"
            "五、考核方式\n"
            "平时成绩占20%，实验占30%，期末考试占50%\n\n"
            "六、教材\n"
            "《数据库系统概论》王珊"
        ),
        "slides_tpl": (
            "第{week}周 课件\n\n"
            "主题：{topic}\n\n"
            "核心知识点：{key_point}\n\n"
            "SQL 示例：\n"
            "SELECT * FROM students\n"
            "WHERE gpa > 3.5\n"
            "ORDER BY gpa DESC;\n\n"
            "范式理论：\n"
            "1NF → 2NF → 3NF → BCNF\n\n"
            "设计原则：\n"
            "- 消除冗余\n"
            "- 避免异常"
        ),
    },
]


# ─────────────────────────────────────────────
#  课程数据生成
# ─────────────────────────────────────────────

_TOPICS = [
    "基本概念与定义", "核心算法分析", "实例讲解",
    "编程实践", "性能优化", "案例分析",
    "复习与总结", "实验指导", "习题讲解",
]

_KEY_POINTS = [
    "理解基本定义", "掌握核心算法", "熟悉编程技巧",
    "能够分析复杂度", "理解应用场景", "掌握调试方法",
]


def _safe_format(template: str, kwargs: dict) -> str:
    """安全的字符串格式化"""
    class SafeDict(dict):
        def __missing__(self, key):
            return "{" + key + "}"
    return template.format_map(SafeDict(kwargs))


def generate_courses(count: int = 20, output_dir: str = "data/raw/course_materials") -> Path:
    """生成课程样例数据"""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    random.seed(42)
    courses = []

    for i in range(count):
        tpl = _COURSE_TEMPLATES[i % len(_COURSE_TEMPLATES)]
        course_id = f"CS{100 + i}"
        year = random.randint(2023, 2026)
        semester = random.choice(["春季", "秋季"])

        # 生成大纲
        syllabus = {
            "material_id": f"{course_id}_syllabus",
            "type": "syllabus",
            "title": f"{tpl['course_name']}教学大纲",
            "content": tpl["syllabus_tpl"],
        }

        # 生成课件（随机 8-12 周）
        materials = [syllabus]
        num_slides = random.randint(8, 12)
        for week in range(1, num_slides + 1):
            topic = random.choice(_TOPICS)
            key_point = random.choice(_KEY_POINTS)
            slide_content = _safe_format(tpl["slides_tpl"], {
                "week": week,
                "topic": topic,
                "key_point": key_point,
            })
            materials.append({
                "material_id": f"{course_id}_slide_{week}",
                "type": "slides",
                "title": f"第{week}周课件",
                "content": slide_content,
            })

        # 生成模拟试卷（50%概率）
        if random.random() > 0.5:
            exam_content = (
                f"{tpl['course_name']}期末考试试卷\n\n"
                "一、选择题（每题2分，共20分）\n"
                "1. 以下关于本课程的说法，正确的是：\n"
                "A. 选项A\n B. 选项B\n C. 选项C\n D. 选项D\n\n"
                "二、简答题（每题10分，共30分）\n"
                "1. 请简述本课程的核心概念。\n\n"
                "三、编程题（每题15分，共50分）\n"
                "1. 实现一个函数，完成指定功能。"
            )
            materials.append({
                "material_id": f"{course_id}_exam",
                "type": "exam",
                "title": "期末试卷",
                "content": exam_content,
            })

        courses.append({
            "course_id": course_id,
            "course_name": tpl["course_name"],
            "teacher": f"教授{random.choice(['王', '李', '张', '刘', '陈'])}",
            "department": tpl["department"],
            "semester": f"{year}年{semester}学期",
            "credits": tpl["credits"],
            "materials": materials,
        })

    output_path = output_dir / "courses.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(courses, f, ensure_ascii=False, indent=2)

    total_materials = sum(len(c["materials"]) for c in courses)
    logger.info("[CourseCrawler] 生成 %d 门课程, %d 个资料 → %s", len(courses), total_materials, output_path)
    return output_path


# ─────────────────────────────────────────────
#  命令行入口
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="课程资料数据生成器")
    parser.add_argument("--sample", type=int, default=20, help="生成课程数量")
    parser.add_argument("--output", type=str, default="data/raw/course_materials", help="输出目录")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")

    output_path = generate_courses(args.sample, args.output)
    print(f"[OK] 课程数据已生成: {output_path} ({args.sample} 门课程)")


if __name__ == "__main__":
    main()
