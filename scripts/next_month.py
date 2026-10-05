"""
next_month.py
-------------
หาเดือนถัดไปที่ยังไม่เคยโหลด (status != "done") แล้วพิมพ์ออกมาเป็น "YYYY MM"
ให้ GitHub Actions workflow เอาไปใช้ต่อ

ถ้าโหลดครบทุกเดือนแล้ว จะพิมพ์ "FINISHED"
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import config as cfg


def all_months(start_ym, end_ym):
    y, m = start_ym
    ey, em = end_ym
    while (y, m) <= (ey, em):
        yield (y, m)
        m += 1
        if m > 12:
            m = 1
            y += 1


def main():
    progress = {}
    if os.path.exists(cfg.PROGRESS_FILE):
        with open(cfg.PROGRESS_FILE, "r", encoding="utf-8") as f:
            progress = json.load(f)

    for (y, m) in all_months(cfg.START_YEAR_MONTH, cfg.END_YEAR_MONTH):
        key = f"{y:04d}-{m:02d}"
        status = progress.get(key)
        # รันซ้ำเฉพาะเดือนที่ยังไม่ "done" (รวมถึง failed ที่จะลองใหม่)
        if status != "done":
            print(f"{y} {m}")
            return

    print("FINISHED")


if __name__ == "__main__":
    main()
