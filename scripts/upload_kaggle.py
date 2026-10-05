"""
upload_kaggle.py
-----------------
อัปโหลดไฟล์ทั้งหมดในโฟลเดอร์ data_output/ ขึ้น Kaggle dataset เป็นเวอร์ชันใหม่

ต้องตั้งค่า KAGGLE_USERNAME และ KAGGLE_KEY เป็น environment variable ก่อน
(ใน GitHub Actions จะมาจาก Secrets)
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import config as cfg

from kaggle.api.kaggle_api_extended import KaggleApi


def main():
    if not os.listdir(cfg.OUTPUT_DIR):
        print("ไม่มีไฟล์ใหม่ให้อัป ข้าม")
        return

    api = KaggleApi()
    api.authenticate()

    # ถ้า dataset ยังไม่เคยสร้าง ต้องสร้างครั้งแรกบนเว็บ Kaggle ก่อน 1 ครั้ง
    # จากนั้นสคริปต์นี้จะใช้ version_create เพื่ออัปเดตข้อมูลไปเรื่อยๆ
    api.dataset_create_version(
        folder=cfg.OUTPUT_DIR,
        version_notes="auto-update from GitHub Actions pipeline",
        delete_old_versions=False,
        dir_mode="zip",
    )
    print("อัปโหลดขึ้น Kaggle สำเร็จ")


if __name__ == "__main__":
    main()
