# -*- coding: utf-8 -*-
"""
generate_supplementary_data.py — 补充遗漏场景数据生成器

职责:
  - 生成通知公告、失物招领、心理咨询等补充数据
  - 覆盖 Day 24 要求的遗漏场景
  - 输出为 JSON 格式，供数据管道消费

使用方式:
  python scripts/generate_supplementary_data.py
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import sys
from datetime import date, timedelta
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

logger = logging.getLogger(__name__)


def _safe_format(template: str, kwargs: dict) -> str:
    """安全的字符串格式化"""
    class SafeDict(dict):
        def __missing__(self, key):
            return "{" + key + "}"
    return template.format_map(SafeDict(kwargs))


# ─────────────────────────────────────────────
#  补充场景模板
# ─────────────────────────────────────────────

_SUPPLEMENTARY_TEMPLATES = [
    {
        "category": "通知公告",
        "title_tpl": "关于{year}年{month}月{event_type}的通知",
        "content_tpl": (
            "全校师生：\n\n"
            "根据学校工作安排，{year}年{month}月{day}日将举行{event_type}，现将有关事项通知如下：\n\n"
            "一、时间安排\n"
            "{event_type}时间：{year}年{month}月{day}日 {start_time}-{end_time}\n\n"
            "二、地点安排\n"
            "地点：{location}\n\n"
            "三、参与要求\n"
            "请{participants}按时参加，如有特殊情况请提前向{contact_dept}请假。\n\n"
            "四、注意事项\n"
            "1. 请携带校园卡签到\n"
            "2. 活动期间请保持手机静音\n"
            "3. 如需帮助请联系{contact_phone}\n\n"
            "{issuer}\n{year}年{month}月{day}日"
        ),
    },
    {
        "category": "失物招领",
        "title_tpl": "{year}年{month}月失物招领公告（第{batch}期）",
        "content_tpl": (
            "以下物品于近期在校园内拾获，请失主携带有效证件前往认领。\n\n"
            "一、拾获物品清单\n"
            "1. {item_type} - 拾获地点：{location1}\n"
            "2. {item_type2} - 拾获地点：{location2}\n"
            "3. {item_type3} - 拾获地点：{location3}\n\n"
            "二、认领方式\n"
            "请到{office_location}办理认领手续，需出示校园卡并描述物品特征。\n\n"
            "三、认领期限\n"
            "自公告发布之日起{retention_days}天内有效，逾期将按无主物品处理。\n\n"
            "四、联系方式\n"
            "联系电话：{contact_phone}\n"
            "办公时间：工作日 {work_hours}\n\n"
            "保卫处\n{year}年{month}月{day}日"
        ),
    },
    {
        "category": "心理咨询",
        "title_tpl": "心理健康教育中心{semester}学期服务指南",
        "content_tpl": (
            "为帮助同学们更好地应对学习和生活中的压力，心理健康教育中心提供以下服务：\n\n"
            "一、个体咨询\n"
            "预约方式：{booking_method}\n"
            "咨询时间：{consult_hours}\n"
            "咨询地点：{consult_location}\n\n"
            "二、团体辅导\n"
            "本学期开设以下团体辅导小组：\n"
            "1. 考试焦虑缓解小组（{group1_time}）\n"
            "2. 人际关系改善小组（{group2_time}）\n"
            "3. 自我成长探索小组（{group3_time}）\n\n"
            "三、心理测评\n"
            "可通过学校心理健康平台进行在线测评，测评结果保密。\n\n"
            "四、危机干预\n"
            "如遇紧急心理危机，请拨打24小时热线：{crisis_phone}\n\n"
            "心理健康教育中心\n{year}年{month}月{day}日"
        ),
    },
    {
        "category": "就业指导",
        "title_tpl": "{year}届毕业生就业服务指南",
        "content_tpl": (
            "为帮助{year}届毕业生顺利就业，就业指导中心提供以下服务：\n\n"
            "一、就业信息\n"
            "关注学校就业信息网（{job_website}）获取最新招聘信息。\n"
            "本学期已举办{jobfair_count}场校园招聘会，{company_count}家企业参会。\n\n"
            "二、简历指导\n"
            "每周{resume_day}下午提供一对一简历修改服务，需提前预约。\n\n"
            "三、面试技巧\n"
            "定期举办模拟面试工作坊，涵盖结构化面试、无领导小组讨论等形式。\n\n"
            "四、手续办理\n"
            "就业协议书、推荐表等手续办理地点：{office_location}\n"
            "办理时间：{work_hours}\n\n"
            "五、咨询电话\n"
            "就业指导热线：{contact_phone}\n\n"
            "就业指导中心\n{year}年{month}月{day}日"
        ),
    },
    {
        "category": "校园安全",
        "title_tpl": "关于加强{season}期间校园安全管理的通知",
        "content_tpl": (
            "为维护校园安全稳定，保障师生人身财产安全，现就{season}期间安全管理工作通知如下：\n\n"
            "一、防火安全\n"
            "1. 严禁在宿舍使用大功率电器（{power_limit}W以上）\n"
            "2. 严禁私拉乱接电线\n"
            "3. 离开宿舍时请关闭所有电器电源\n\n"
            "二、防盗安全\n"
            "1. 贵重物品请妥善保管\n"
            "2. 宿舍无人时请锁好门窗\n"
            "3. 发现可疑人员请及时报告保卫处\n\n"
            "三、交通安全\n"
            "1. 校内骑行请遵守交通规则，限速{speed_limit}km/h\n"
            "2. 夜间出行建议结伴而行\n\n"
            "四、报警电话\n"
            "校园报警电话：{alarm_phone}\n"
            "24小时值班电话：{duty_phone}\n\n"
            "保卫处\n{year}年{month}月{day}日"
        ),
    },
    {
        "category": "志愿服务",
        "title_tpl": "{year}年{semester}学期志愿服务活动招募",
        "content_tpl": (
            "青年志愿者协会现面向全校学生招募{semester}学期志愿者，具体信息如下：\n\n"
            "一、志愿项目\n"
            "1. 社区服务：{project1_desc}\n"
            "2. 校园导览：{project2_desc}\n"
            "3. 支教帮扶：{project3_desc}\n\n"
            "二、报名条件\n"
            "1. 全日制在校学生\n"
            "2. 热心公益事业，有责任心\n"
            "3. 每周可投入至少{min_hours}小时\n\n"
            "三、报名方式\n"
            "请填写在线报名表：{signup_url}\n"
            "报名截止：{year}年{month}月{deadline}日\n\n"
            "四、激励措施\n"
            "1. 累计志愿服务时长可兑换学分\n"
            "2. 优秀志愿者可获荣誉证书\n"
            "3. 志愿服务经历可写入综合素质评价\n\n"
            "团委 青年志愿者协会\n{year}年{month}月{day}日"
        ),
    },
]


def generate_supplementary_data(count: int = 30, output_dir: str = "data/raw/supplementary") -> Path:
    """生成补充场景数据"""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    results = []
    random.seed(2024)

    for i in range(count):
        tpl = _SUPPLEMENTARY_TEMPLATES[i % len(_SUPPLEMENTARY_TEMPLATES)]
        year = random.randint(2023, 2026)
        month = random.randint(1, 12)
        day = random.randint(1, 28)

        title = _safe_format(tpl["title_tpl"], {
            "year": year, "month": month, "day": day,
            "event_type": random.choice(["开学典礼", "毕业典礼", "校庆活动", "运动会", "文艺汇演"]),
            "batch": random.randint(1, 10),
            "semester": random.choice(["春", "秋"]),
            "season": random.choice(["春", "夏", "秋", "冬"]),
        })

        fmt_kwargs = {
            "year": year, "month": month, "day": day,
            "event_type": random.choice(["开学典礼", "毕业典礼", "校庆活动", "运动会", "文艺汇演"]),
            "start_time": random.choice(["9:00", "10:00", "14:00"]),
            "end_time": random.choice(["11:30", "12:00", "16:30"]),
            "location": random.choice(["大礼堂", "体育馆", "操场", "学术报告厅"]),
            "participants": random.choice(["全体师生", "新生", "毕业生", "学生干部"]),
            "contact_dept": random.choice(["学院办公室", "辅导员", "班主任"]),
            "contact_phone": f"0531-{random.randint(1000000, 9999999)}",
            "issuer": random.choice(["教务处", "学生处", "团委", "研究生院"]),
            "batch": random.randint(1, 10),
            "item_type": random.choice(["钱包", "手机", "钥匙", "学生证"]),
            "item_type2": random.choice(["雨伞", "水杯", "书包", "耳机"]),
            "item_type3": random.choice(["眼镜", "U盘", "充电宝", "外套"]),
            "location1": random.choice(["图书馆", "食堂", "教学楼"]),
            "location2": random.choice(["操场", "宿舍楼下", "校车站"]),
            "location3": random.choice(["实验室", "自习室", "体育馆"]),
            "office_location": random.choice(["保卫处办公室", "学生事务中心"]),
            "retention_days": random.choice([30, 60, 90]),
            "work_hours": random.choice(["9:00-17:00", "8:30-17:30"]),
            "semester": random.choice(["春", "秋"]),
            "booking_method": random.choice(["微信公众号预约", "电话预约", "现场排队"]),
            "consult_hours": random.choice(["周一至周五 14:00-17:00", "周二、四 10:00-12:00"]),
            "consult_location": random.choice(["心理中心", "学生活动中心3楼"]),
            "group1_time": "每周三 19:00",
            "group2_time": "每周五 14:00",
            "group3_time": "每周日 10:00",
            "crisis_phone": "400-161-9995",
            "job_website": "job.example.edu.cn",
            "jobfair_count": random.randint(3, 10),
            "company_count": random.randint(50, 200),
            "resume_day": random.choice(["周一", "周三", "周五"]),
            "season": random.choice(["春", "夏", "秋", "冬"]),
            "power_limit": random.choice([500, 800, 1000]),
            "speed_limit": random.choice([10, 15, 20]),
            "alarm_phone": "110",
            "duty_phone": f"0531-{random.randint(1000000, 9999999)}",
            "project1_desc": "为周边社区老人提供生活帮助",
            "project2_desc": "为新生和家长提供校园导览服务",
            "project3_desc": "为偏远地区学生提供线上辅导",
            "min_hours": random.choice([2, 3, 4]),
            "signup_url": "https://volunteer.example.edu.cn/signup",
            "deadline": random.randint(15, 28),
        }

        content = _safe_format(tpl["content_tpl"], fmt_kwargs)

        pub_date = f"{year}年{month}月{day}日"
        crawl_time = f"{year}-{month:02d}-{day:02d}T10:00:00"

        results.append({
            "url": f"https://notice.example.edu.cn/{year}/{i:04d}.html",
            "title": title,
            "content": content,
            "publish_date": pub_date,
            "crawl_time": crawl_time,
            "attachments": [],
            "category": tpl["category"],
        })

    output_path = output_dir / "supplementary_notices.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    logger.info("[SupplementaryGen] 生成 %d 条补充数据 → %s", len(results), output_path)
    return output_path


# ─────────────────────────────────────────────
#  命令行入口
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="补充场景数据生成器")
    parser.add_argument("--count", type=int, default=30, help="生成数量")
    parser.add_argument("--output", type=str, default="data/raw/supplementary", help="输出目录")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")

    output_path = generate_supplementary_data(args.count, args.output)
    print(f"[OK] 补充数据已生成: {output_path} ({args.count} 条)")


if __name__ == "__main__":
    main()
