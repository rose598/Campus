# -*- coding: utf-8 -*-
"""
generate_bulk_data.py — 批量生成校园通知/政策/生活指南数据

职责:
  - 生成 100+ 篇教务政策通知
  - 生成 50+ 篇校园生活指南
  - 输出为 JSON 格式，供 data_pipeline 消费

使用方式:
  python scripts/generate_bulk_data.py --policies 100 --life 50
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
    """安全的字符串格式化，忽略缺失的 key"""
    class SafeDict(dict):
        def __missing__(self, key):
            return "{" + key + "}"
    return template.format_map(SafeDict(kwargs))



# ─────────────────────────────────────────────
#  教务政策通知模板
# ─────────────────────────────────────────────

_POLICY_TEMPLATES = [
    {
        "category": "保研",
        "title_tpl": "关于{year}年推荐优秀应届本科毕业生免试攻读硕士学位研究生工作的通知",
        "content_tpl": (
            "各学院：\n\n"
            "根据教育部相关文件精神，结合我校实际情况，现将{year}年推免工作有关事项通知如下：\n\n"
            "一、申请条件\n"
            "1. 全日制普通本科应届毕业生；\n"
            "2. 学业成绩排名在本专业前{top_pct}%；\n"
            "3. 无违纪处分记录；\n"
            "4. 外语成绩达到学校规定标准。\n\n"
            "二、时间安排\n"
            "申请时间：{year}年9月1日至9月15日\n"
            "审核时间：{year}年9月16日至9月30日\n\n"
            "三、申请材料\n"
            "1. 保研申请表\n"
            "2. 成绩单（教务处盖章）\n"
            "3. 综合素质评价表\n"
            "4. 获奖证书复印件\n\n"
            "四、其他事项\n"
            "各学院应严格按照公开、公平、公正的原则组织推免工作。\n\n"
            "教务处\n{year}年{month}月{day}日"
        ),
    },
    {
        "category": "转专业",
        "title_tpl": "{year}年本科生转专业工作实施办法",
        "content_tpl": (
            "为尊重学生个性发展，充分调动学生学习积极性，根据《普通高等学校学生管理规定》和我校实际情况，"
            "特制定本办法。\n\n"
            "一、转专业条件\n"
            "1. 在校全日制本科{grade}年级学生；\n"
            "2. 入学后未受过纪律处分；\n"
            "3. 高考招生时未跨批次录取。\n\n"
            "二、名额分配\n"
            "各专业接收转专业学生比例不超过该专业当年招生人数的{quota}%。\n\n"
            "三、考核方式\n"
            "转专业考核由接收学院组织，包括笔试和面试两个环节。\n"
            "笔试占{written_pct}%，面试占{oral_pct}%。\n\n"
            "四、时间安排\n"
            "报名时间：{year}年{month}月1日至{month}月15日\n"
            "考核时间：{year}年{month}月20日至{month}月25日\n\n"
            "教务处\n{year}年{month}月{day}日"
        ),
    },
    {
        "category": "选课",
        "title_tpl": "{year}-{year2}学年第{semester}学期选课通知",
        "content_tpl": (
            "各学院、各位同学：\n\n"
            "{year}-{year2}学年第{semester}学期选课工作即将开始，现将有关事项通知如下：\n\n"
            "一、选课时间\n"
            "第一轮选课：{year}年{sel_month}月{sel_day}日至{sel_month2}月{sel_day2}日\n"
            "第二轮选课（补退选）：{year}年9月1日至9月7日\n\n"
            "二、选课方式\n"
            "登录教务系统（http://jwxt.example.edu.cn）进行选课操作。\n\n"
            "三、注意事项\n"
            "1. 每位学生每学期选课学分上限为{max_credits}学分；\n"
            "2. 必修课无需选课，系统自动分配；\n"
            "3. 选修课先到先得，额满即止。\n\n"
            "教务处\n{year}年{month}月{day}日"
        ),
    },
    {
        "category": "补考",
        "title_tpl": "关于{year}年{semester_name}学期补考安排的通知",
        "content_tpl": (
            "各学院：\n\n"
            "根据教学安排，{year}年{semester_name}学期补考安排如下：\n\n"
            "一、补考时间\n"
            "{year}年{month}月1日至{month}月10日\n\n"
            "二、补考范围\n"
            "上学期期末考试不及格的必修课程。\n\n"
            "三、注意事项\n"
            "1. 每位学生最多可参加{max_retry}门课程的补考；\n"
            "2. 补考成绩最高记为60分；\n"
            "3. 无故缺考者按旷考处理。\n\n"
            "教务处\n{year}年{month}月{day}日"
        ),
    },
    {
        "category": "四六级",
        "title_tpl": "{year}年{half}全国大学英语四六级考试报名通知",
        "content_tpl": (
            "各位同学：\n\n"
            "{year}年{half}全国大学英语四、六级考试报名工作即将开始，现将有关事项通知如下：\n\n"
            "一、报名时间\n"
            "{year}年{month}月{reg_day}日至{month}月{reg_day2}日\n\n"
            "二、考试时间\n"
            "英语四级：{year}年{exam_month}月{exam_day}日上午\n"
            "英语六级：{year}年{exam_month}月{exam_day}日下午\n\n"
            "三、报名方式\n"
            "登录全国大学英语四六级考试报名网站（http://cet-bm.neea.edu.cn）进行报名。\n\n"
            "四、收费标准\n"
            "四级：{cet4_fee}元\n六级：{cet6_fee}元\n\n"
            "教务处\n{year}年{month}月{day}日"
        ),
    },
    {
        "category": "奖学金",
        "title_tpl": "关于{year}年{semester_name}奖学金评定工作的通知",
        "content_tpl": (
            "各学院：\n\n"
            "{year}年{semester_name}奖学金评定工作现启动，有关事项通知如下：\n\n"
            "一、奖学金种类及比例\n"
            "1. 国家奖学金：每专业{nat_count}名，每人{n_amount}元；\n"
            "2. 学校一等奖学金：前{first_pct}%，每人{f_amount}元；\n"
            "3. 学校二等奖学金：前{second_pct}%，每人{s_amount}元。\n\n"
            "二、评定条件\n"
            "1. 学业成绩排名在本专业前列；\n"
            "2. 无违纪处分记录；\n"
            "3. 积极参与课外活动和社会实践。\n\n"
            "三、申请时间\n"
            "{year}年{month}月1日至{month}月20日\n\n"
            "学生处\n{year}年{month}月{day}日"
        ),
    },
    {
        "category": "学籍",
        "title_tpl": "关于{year}年办理休学、复学手续的通知",
        "content_tpl": (
            "各位同学：\n\n"
            "因个人原因需要办理休学或复学手续的同学，请按照以下流程办理：\n\n"
            "一、休学办理\n"
            "1. 填写《学生休学申请表》；\n"
            "2. 由所在学院审核并签署意见；\n"
            "3. 提交至教务处学籍管理科审批；\n"
            "4. 办理离校手续。\n\n"
            "二、复学办理\n"
            "1. 休学期满前{days_before}个月向学院提出复学申请；\n"
            "2. 提交《学生复学申请表》及相关证明材料；\n"
            "3. 经教务处审批后，办理复学手续。\n\n"
            "三、注意事项\n"
            "休学时间最长不超过{max_leave}年，超过期限将按自动退学处理。\n\n"
            "教务处\n{year}年{month}月{day}日"
        ),
    },
    {
        "category": "毕业",
        "title_tpl": "关于{year}届本科毕业生学位授予工作的通知",
        "content_tpl": (
            "各学院：\n\n"
            "{year}届本科毕业生学位授予工作即将开始，现将有关事项通知如下：\n\n"
            "一、学位授予条件\n"
            "1. 完成培养方案规定的全部课程和环节，成绩合格；\n"
            "2. 平均学分绩点达到{gpa_req}以上；\n"
            "3. 外语成绩达到学校规定标准；\n"
            "4. 毕业论文（设计）答辩通过。\n\n"
            "二、时间安排\n"
            "资格审核：{year}年6月1日至6月15日\n"
            "学位评定：{year}年6月20日\n\n"
            "三、申请材料\n"
            "1. 学位申请表\n"
            "2. 成绩单\n"
            "3. 外语成绩证明\n"
            "4. 毕业论文终稿\n\n"
            "教务处\n{year}年{month}月{day}日"
        ),
    },
]


# ─────────────────────────────────────────────
#  校园生活指南模板
# ─────────────────────────────────────────────

_LIFE_TEMPLATES = [
    {
        "category": "图书馆",
        "title_tpl": "图书馆{year}年开放时间调整通知",
        "content_tpl": (
            "各位师生：\n\n"
            "根据学校安排，图书馆自{year}年{month}月{day}日起调整开放时间：\n\n"
            "一、开放时间\n"
            "工作日：{open_time} - {close_time}\n"
            "周末：{weekend_open} - {weekend_close}\n"
            "法定节假日另行通知。\n\n"
            "二、借阅规则\n"
            "1. 本科生每人最多借阅{borrow_count}本；\n"
            "2. 借阅期限为{borrow_days}天，可续借一次；\n"
            "3. 逾期归还需缴纳滞纳金。\n\n"
            "三、自习室\n"
            "图书馆{floor}楼为自习专区，无需预约，先到先得。\n\n"
            "图书馆\n{year}年{month}月{day}日"
        ),
    },
    {
        "category": "食堂",
        "title_tpl": "关于食堂就餐时间及菜品调整的通知",
        "content_tpl": (
            "各位同学：\n\n"
            "为改善就餐体验，食堂自{year}年{month}月起调整如下：\n\n"
            "一、就餐时间\n"
            "早餐：{breakfast_start} - {breakfast_end}\n"
            "午餐：{lunch_start} - {lunch_end}\n"
            "晚餐：{dinner_start} - {dinner_end}\n\n"
            "二、新增窗口\n"
            "{canteen}食堂新增{new_windows}个特色窗口，提供各地风味菜品。\n\n"
            "三、支付方式\n"
            "支持校园卡、微信、支付宝支付。\n\n"
            "后勤管理处\n{year}年{month}月{day}日"
        ),
    },
    {
        "category": "宿舍",
        "title_tpl": "学生宿舍管理条例（{year}年修订版）",
        "content_tpl": (
            "为维护宿舍正常秩序，保障学生住宿安全，特制定本条例。\n\n"
            "一、住宿管理\n"
            "1. 学生须按学校安排入住指定宿舍；\n"
            "2. 不得私自调换宿舍或转租床位；\n"
            "3. 宿舍实行{curfew_time}门禁管理。\n\n"
            "二、安全管理\n"
            "1. 严禁使用大功率电器（{power_limit}W以上）；\n"
            "2. 严禁私拉电线、使用明火；\n"
            "3. 发现安全隐患应及时向宿管报告。\n\n"
            "三、卫生管理\n"
            "宿舍实行每周{check_day}卫生检查制度，检查不合格的宿舍将通报批评。\n\n"
            "学生公寓管理中心\n{year}年{month}月{day}日"
        ),
    },
    {
        "category": "网络",
        "title_tpl": "校园网使用指南及常见故障处理",
        "content_tpl": (
            "为帮助同学们更好地使用校园网络资源，现将相关事项说明如下：\n\n"
            "一、网络接入\n"
            "1. 有线网络：将网线插入宿舍网口，使用校园卡账号登录；\n"
            "2. 无线网络：连接 \"CampusWiFi\"，使用统一认证账号登录。\n\n"
            "二、账号管理\n"
            "初始密码为学号后6位，首次登录请及时修改。\n"
            "账号密码问题请联系网络中心（电话：{net_phone}）。\n\n"
            "三、常见故障\n"
            "1. 无法连接：检查网线是否插好，重启路由器；\n"
            "2. 速度慢：避开高峰时段，或切换到5G频段；\n"
            "3. 账号锁定：连续输错密码{max_attempts}次将锁定，需到网络中心解锁。\n\n"
            "网络信息中心\n{year}年{month}月{day}日"
        ),
    },
    {
        "category": "一卡通",
        "title_tpl": "校园一卡通办理及充值指南",
        "content_tpl": (
            "一、办卡流程\n"
            "新生入学时统一办理校园一卡通，遗失可到一卡通中心补办。\n"
            "补办需携带学生证和身份证，工本费{card_fee}元。\n\n"
            "二、充值方式\n"
            "1. 线上充值：通过学校APP或微信公众号充值；\n"
            "2. 线下充值：到一卡通自助充值机或人工窗口充值。\n\n"
            "三、挂失与解挂\n"
            "卡片丢失应立即挂失，可通过APP、自助机或人工窗口办理。\n"
            "挂失后原卡余额自动转入新卡。\n\n"
            "四、使用范围\n"
            "食堂就餐、图书馆借阅、超市购物、校医院就诊等。\n\n"
            "信息化办公室\n{year}年{month}月{day}日"
        ),
    },
    {
        "category": "校医院",
        "title_tpl": "校医院就诊流程及医保报销说明",
        "content_tpl": (
            "一、就诊流程\n"
            "1. 携带校园卡到校医院挂号；\n"
            "2. 到相应科室就诊；\n"
            "3. 持处方到药房取药；\n"
            "4. 需转诊的由医生开具转诊单。\n\n"
            "二、门诊时间\n"
            "工作日：{clinic_start} - {clinic_end}\n"
            "急诊：24小时\n\n"
            "三、医保报销\n"
            "1. 校医院就诊可直接刷校园卡结算；\n"
            "2. 校外医院就诊需先自费，后凭发票到医保办报销；\n"
            "3. 报销比例：门诊{outpatient_pct}%，住院{inpatient_pct}%。\n\n"
            "校医院\n{year}年{month}月{day}日"
        ),
    },
    {
        "category": "交通",
        "title_tpl": "校车运行线路及时刻表（{year}年版）",
        "content_tpl": (
            "为方便师生出行，校车运行线路及时间安排如下：\n\n"
            "一、运行线路\n"
            "线路1：{stop_a} → {stop_b} → {stop_c}\n"
            "线路2：{stop_d} → {stop_e} → {stop_f}\n\n"
            "二、运行时间\n"
            "工作日：{bus_start} - {bus_end}，每{bus_interval}分钟一班\n"
            "周末：减少班次，具体见站点公告。\n\n"
            "三、乘车须知\n"
            "1. 凭校园卡免费乘坐；\n"
            "2. 高峰期请自觉排队；\n"
            "3. 请保持车内清洁。\n\n"
            "后勤管理处\n{year}年{month}月{day}日"
        ),
    },
    {
        "category": "社团",
        "title_tpl": "{year}年学生社团注册及活动审批指南",
        "content_tpl": (
            "一、社团注册\n"
            "每学年开学后{reg_weeks}周内完成社团注册，逾期视为自动注销。\n"
            "注册需提交：社团章程、成员名单、指导老师确认函。\n\n"
            "二、活动审批\n"
            "1. 活动前{apply_days}天提交《学生活动申请表》；\n"
            "2. 涉及场地使用需同时提交场地申请；\n"
            "3. 大型活动（{large_threshold}人以上）需报学校审批。\n\n"
            "三、经费管理\n"
            "社团活动经费实行预算管理，活动结束后{settle_days}天内完成报销。\n\n"
            "团委\n{year}年{month}月{day}日"
        ),
    },
]


# ─────────────────────────────────────────────
#  数据生成器
# ─────────────────────────────────────────────

def generate_policies(count: int = 100, output_dir: str = "data/raw/policies") -> Path:
    """生成教务政策通知数据"""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    results = []
    random.seed(42)

    for i in range(count):
        tpl = _POLICY_TEMPLATES[i % len(_POLICY_TEMPLATES)]
        year = random.randint(2022, 2026)
        year2 = year + 1
        month = random.randint(1, 12)
        day = random.randint(1, 28)

        # 所有可能的格式化变量
        fmt_kwargs = {
            "year": year, "year2": year2, "month": month, "day": day,
            "semester": random.choice(["一", "二"]),
            "half": random.choice(["上半年", "下半年"]),
            "semester_name": random.choice(["春季", "秋季"]),
            "grade": random.choice(["一", "二"]),
            "top_pct": random.choice([25, 30, 35]),
            "quota": random.choice([5, 10, 15]),
            "written_pct": random.choice([60, 70]),
            "oral_pct": random.choice([30, 40]),
            "sel_month": random.choice([6, 7]),
            "sel_month2": random.choice([6, 7]),
            "sel_day": random.randint(15, 25),
            "sel_day2": random.randint(25, 30),
            "max_credits": random.choice([25, 30]),
            "max_retry": random.choice([2, 3]),
            "reg_day": random.randint(10, 20),
            "reg_day2": random.randint(20, 31),
            "exam_month": random.choice([6, 12]),
            "exam_day": random.choice([14, 15, 16]),
            "cet4_fee": random.choice([25, 30]),
            "cet6_fee": random.choice([30, 35]),
            "nat_count": random.randint(1, 3),
            "n_amount": random.choice([8000, 10000]),
            "first_pct": random.choice([5, 10]),
            "f_amount": random.choice([3000, 5000]),
            "second_pct": random.choice([15, 20]),
            "s_amount": random.choice([1500, 2000]),
            "days_before": random.choice([1, 2]),
            "max_leave": random.choice([2, 3]),
            "gpa_req": random.choice([2.0, 2.5, 3.0]),
        }

        # 格式化标题
        title = _safe_format(tpl["title_tpl"], fmt_kwargs)
        # 格式化内容
        content = _safe_format(tpl["content_tpl"], fmt_kwargs)

        # 日期格式化
        pub_date = f"{year}年{month}月{day}日"
        crawl_time = f"{year}-{month:02d}-{day:02d}T08:00:00"

        results.append({
            "url": f"https://jwc.example.edu.cn/notice/{year}/{i:04d}.html",
            "title": title,
            "content": content,
            "publish_date": pub_date,
            "crawl_time": crawl_time,
            "attachments": [],
            "category": tpl["category"],
        })

    output_path = output_dir / "bulk_policies.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    logger.info("[BulkGen] 生成 %d 条政策通知 → %s", len(results), output_path)
    return output_path


def generate_life_guides(count: int = 50, output_dir: str = "data/raw/life") -> Path:
    """生成校园生活指南数据"""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    results = []
    random.seed(123)

    for i in range(count):
        tpl = _LIFE_TEMPLATES[i % len(_LIFE_TEMPLATES)]
        year = random.randint(2022, 2026)
        month = random.randint(1, 12)
        day = random.randint(1, 28)

        title = _safe_format(tpl["title_tpl"], {"year": year})

        fmt_kwargs = {
            "year": year, "month": month, "day": day,
            "open_time": random.choice(["8:00", "8:30", "9:00"]),
            "close_time": random.choice(["21:00", "22:00", "22:30"]),
            "weekend_open": random.choice(["9:00", "10:00"]),
            "weekend_close": random.choice(["17:00", "18:00"]),
            "borrow_count": random.choice([8, 10, 12]),
            "borrow_days": random.choice([30, 60]),
            "floor": random.choice(["2", "3", "4"]),
            "breakfast_start": random.choice(["6:30", "7:00"]),
            "breakfast_end": random.choice(["9:00", "9:30"]),
            "lunch_start": random.choice(["11:00", "11:30"]),
            "lunch_end": random.choice(["13:30", "14:00"]),
            "dinner_start": random.choice(["17:00", "17:30"]),
            "dinner_end": random.choice(["20:00", "20:30"]),
            "canteen": random.choice(["第一", "第二", "第三"]),
            "new_windows": random.randint(2, 5),
            "curfew_time": random.choice(["22:00", "23:00"]),
            "power_limit": random.choice([500, 800, 1000]),
            "check_day": random.choice(["周一", "周三", "周五"]),
            "net_phone": random.choice(["0531-1234567", "0532-7654321"]),
            "max_attempts": random.choice([3, 5]),
            "card_fee": random.choice([10, 15, 20]),
            "clinic_start": random.choice(["8:00", "8:30"]),
            "clinic_end": random.choice(["17:00", "17:30"]),
            "outpatient_pct": random.choice([60, 70, 80]),
            "inpatient_pct": random.choice([70, 80, 90]),
            "stop_a": random.choice(["东门", "西门", "南门"]),
            "stop_b": random.choice(["教学楼", "实验楼", "图书馆"]),
            "stop_c": random.choice(["北门", "宿舍区", "体育馆"]),
            "stop_d": random.choice(["行政楼", "食堂", "医院"]),
            "stop_e": random.choice(["计算机楼", "外语楼", "理科楼"]),
            "stop_f": random.choice(["工科楼", "文科楼", "艺术中心"]),
            "bus_start": random.choice(["7:00", "7:30"]),
            "bus_end": random.choice(["21:00", "22:00"]),
            "bus_interval": random.choice([15, 20, 30]),
            "reg_weeks": random.choice([2, 3]),
            "apply_days": random.choice([3, 5, 7]),
            "large_threshold": random.choice([100, 200, 500]),
            "settle_days": random.choice([7, 14]),
        }

        content = _safe_format(tpl["content_tpl"], fmt_kwargs)

        pub_date = f"{year}年{month}月{day}日"
        crawl_time = f"{year}-{month:02d}-{day:02d}T09:00:00"

        results.append({
            "url": f"https://life.example.edu.cn/guide/{year}/{i:04d}.html",
            "title": title,
            "content": content,
            "publish_date": pub_date,
            "crawl_time": crawl_time,
            "attachments": [],
            "category": tpl["category"],
        })

    output_path = output_dir / "bulk_life_guides.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    logger.info("[BulkGen] 生成 %d 条生活指南 → %s", len(results), output_path)
    return output_path


# ─────────────────────────────────────────────
#  命令行入口
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="批量生成校园数据")
    parser.add_argument("--policies", type=int, default=100, help="政策通知数量")
    parser.add_argument("--life", type=int, default=50, help="生活指南数量")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")

    p1 = generate_policies(args.policies)
    print(f"[OK] 政策通知: {p1} ({args.policies} 条)")

    p2 = generate_life_guides(args.life)
    print(f"[OK] 生活指南: {p2} ({args.life} 条)")


if __name__ == "__main__":
    main()
