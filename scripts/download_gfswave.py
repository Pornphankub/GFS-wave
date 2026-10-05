"""
download_gfswave.py
--------------------
ดาวน์โหลดข้อมูล GFS-Wave / WAVEWATCH III hindcast เฉพาะพื้นที่ (bounding box)
สำหรับ "หนึ่งเดือน" ต่อการรันหนึ่งครั้ง (ใช้คู่กับ GitHub Actions ที่รันเป็นรอบๆ)

วิธีใช้:
    python download_gfswave.py --year 2016 --month 3

ผลลัพธ์:
    data_output/gfswave_2016-03.nc   (ไฟล์ NetCDF เฉพาะพื้นที่ที่ตั้งไว้ใน config.py)

⚠️ สำคัญมาก ก่อนรันจริงกับทั้ง 2015-2026:
   กรุณารันทดสอบ 1 เดือนด้วยมือก่อน แล้วเปิดไฟล์ผลลัพธ์ตรวจสอบว่า
   ค่า lat/lon และค่า HTSGW สมเหตุสมผลจริง เพราะ URL ของ archive ฝั่ง NCEI/NODC
   อาจมีการเปลี่ยนโครงสร้างไปตามช่วงเวลา (ดูรายละเอียดใน README.md)
"""

import argparse
import datetime as dt
import json
import os
import sys
import time

import requests
import xarray as xr

sys.path.insert(0, os.path.dirname(__file__))
import config as cfg


def month_range_str(year: int, month: int) -> str:
    return f"{year:04d}-{month:02d}"


def which_source(year: int, month: int) -> str:
    """
    เลือกว่าช่วงเวลานี้ควรไปดึงจากแหล่งไหน
    คืนค่า: "hindcast" | "aws" | "needs_manual_check"
    """
    ym = (year, month)
    if ym <= cfg.HINDCAST_END:
        return "hindcast"
    elif ym >= cfg.AWS_START:
        return "aws"
    else:
        return "needs_manual_check"


def build_hindcast_opendap_url(year: int, month: int) -> str:
    """
    URL ของ NCEI/NODC THREDDS OPeNDAP สำหรับ multi_1 hindcast (glo_30m grid)

    *** ต้องตรวจสอบ/ปรับ path นี้ด้วยตัวเองก่อนใช้งานจริง ***
    วิธีตรวจสอบ: เปิด
        https://data.nodc.noaa.gov/thredds/catalog/ncep/nww3/catalog.html
    ไล่ตามปี/เดือนที่ต้องการ แล้ว copy ลิงก์ OPeNDAP (.html -> กด Data URL)
    มาเทียบกับรูปแบบด้านล่าง ถ้าไม่ตรงให้แก้ pattern นี้ตามจริง
    """
    ym = month_range_str(year, month)
    # รูปแบบตัวอย่าง (อาจต้องปรับ): .../ncep/nww3/YYYYMM/multi_1.glo_30m.hs.YYYYMM.grb2
    return (
        "https://data.nodc.noaa.gov/thredds/dodsC/ncep/nww3/"
        f"{ym.replace('-', '')}/multi_1.glo_30m.hs.{ym.replace('-', '')}.grb2"
    )


def build_aws_urls_for_month(year: int, month: int) -> list:
    """
    สร้างรายการ URL ของ AWS Open Data (noaa-gfs-bdp-pds) สำหรับทุกวันในเดือนนั้น
    ใช้เฉพาะ analysis (f000) รอบ 00Z เพื่อลดปริมาณ (ปรับเพิ่มรอบอื่นได้ถ้าต้องการ)

    *** ต้องตรวจสอบว่า path /wave/gridded/ และชื่อไฟล์ gfswave.tCCz... ตรงกับจริง ***
    """
    urls = []
    days_in_month = (dt.date(year + (month == 12), (month % 12) + 1, 1) - dt.timedelta(days=1)).day
    for day in range(1, days_in_month + 1):
        date_str = f"{year:04d}{month:02d}{day:02d}"
        url = (
            "https://noaa-gfs-bdp-pds.s3.amazonaws.com/"
            f"gfs.{date_str}/00/wave/gridded/gfswave.t00z.global.0p25.f000.grib2"
        )
        urls.append((date_str, url))
    return urls


def subset_and_save(ds: xr.Dataset, out_path: str):
    """ตัดเฉพาะ bounding box แล้วบันทึกเป็น NetCDF"""
    lat_name = "latitude" if "latitude" in ds.coords else "lat"
    lon_name = "longitude" if "longitude" in ds.coords else "lon"

    ds_subset = ds.sel(
        {lat_name: slice(cfg.LAT_MAX, cfg.LAT_MIN)},  # grib ส่วนใหญ่เรียง lat มาก->น้อย
    )
    ds_subset = ds_subset.sel({lon_name: slice(cfg.LON_MIN, cfg.LON_MAX)})

    keep_vars = [v for v in cfg.TARGET_VARIABLES if v in ds_subset.data_vars]
    if keep_vars:
        ds_subset = ds_subset[keep_vars]

    ds_subset.to_netcdf(out_path)


def download_one_file(url: str, local_path: str, retries: int = 3, timeout: int = 120) -> bool:
    for attempt in range(1, retries + 1):
        try:
            r = requests.get(url, timeout=timeout, stream=True)
            r.raise_for_status()
            with open(local_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 1024):
                    f.write(chunk)
            return True
        except Exception as e:
            print(f"  [ลองครั้งที่ {attempt}] โหลดไม่สำเร็จ: {url} -> {e}")
            time.sleep(5)
    return False


def process_month(year: int, month: int) -> str:
    """
    คืนค่าสถานะ: "done" | "failed" | "skipped_manual_check"
    """
    os.makedirs(cfg.OUTPUT_DIR, exist_ok=True)
    out_path = os.path.join(cfg.OUTPUT_DIR, f"gfswave_{month_range_str(year, month)}.nc")

    source = which_source(year, month)
    print(f"=== {month_range_str(year, month)} -> แหล่งข้อมูล: {source} ===")

    if source == "needs_manual_check":
        print("  ช่วงนี้ยังไม่มี archive ยืนยันแน่ชัด ข้ามไปก่อน (ดู README.md)")
        return "skipped_manual_check"

    try:
        if source == "hindcast":
            url = build_hindcast_opendap_url(year, month)
            ds = xr.open_dataset(url)  # OPeNDAP เปิดตรงได้โดยไม่ต้องโหลดเต็มไฟล์
            subset_and_save(ds, out_path)

        elif source == "aws":
            tmp_dir = "tmp_grib"
            os.makedirs(tmp_dir, exist_ok=True)
            daily_urls = build_aws_urls_for_month(year, month)
            monthly_datasets = []

            for date_str, url in daily_urls:
                local_grib = os.path.join(tmp_dir, f"{date_str}.grib2")
                ok = download_one_file(url, local_grib)
                if not ok:
                    print(f"  ข้ามวันที่ {date_str} (โหลดไม่สำเร็จ)")
                    continue
                ds_day = xr.open_dataset(local_grib, engine="cfgrib")
                monthly_datasets.append(ds_day)
                os.remove(local_grib)

            if not monthly_datasets:
                return "failed"

            ds = xr.concat(monthly_datasets, dim="time")
            subset_and_save(ds, out_path)

        print(f"  บันทึกสำเร็จ: {out_path}")
        return "done"

    except Exception as e:
        print(f"  เกิดข้อผิดพลาด: {e}")
        return "failed"


def load_progress() -> dict:
    if os.path.exists(cfg.PROGRESS_FILE):
        with open(cfg.PROGRESS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_progress(progress: dict):
    with open(cfg.PROGRESS_FILE, "w", encoding="utf-8") as f:
        json.dump(progress, f, ensure_ascii=False, indent=2)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--month", type=int, required=True)
    args = parser.parse_args()

    progress = load_progress()
    key = month_range_str(args.year, args.month)

    if progress.get(key) == "done":
        print(f"{key} เคยโหลดสำเร็จแล้ว ข้าม")
        return

    status = process_month(args.year, args.month)
    progress[key] = status
    save_progress(progress)


if __name__ == "__main__":
    main()
