# -*- coding: utf-8 -*-
"""Day 28 前端可导入性检查（模拟 streamlit run frontend/app.py 的导入环境）"""
import sys

sys.path.insert(0, r"d:\python\code\test")
# Streamlit 会把主脚本所在目录（frontend/）加入 sys.path
sys.path.insert(0, r"d:\python\code\test\frontend")

ok = True

modules = [
    "state_sync",
    "global_styles",
    "components.interrupt_modal",
    "pages.00_home",
    "pages.01_activity_push",
    "pages.02_campus_qa",
    "pages.03_course_materials",
    "pages.04_settings",
    "pages.05_onboarding",
    "pages.06_study_buddy",
    "config.config_api",
]
for m in modules:
    try:
        __import__(m)
        print(f"  [PASS] {m}")
    except Exception as e:
        print(f"  [FAIL] {m}: {type(e).__name__}: {e}")
        ok = False

print("结果:", "全部通过 ✅" if ok else "存在失败项 ❌")
sys.exit(0 if ok else 1)
