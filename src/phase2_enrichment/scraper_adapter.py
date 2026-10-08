"""
scraper_adapter.py — Adapter để nhập data từ tool FB scraping (MKT Ninja, Simple UID...)

HƯỚNG DẪN SỬ DỤNG:
1. Export data từ tool scraping của bạn thành file CSV
2. Format CSV cần có các cột:
   - uid: Facebook UID của người tương tác
   - post_url: URL bài đăng
   - behavior: loại hành vi (comment | share | tag | like)
   - keyword: từ khóa dùng để tìm bài
   - timestamp: thời gian tương tác (YYYY-MM-DD HH:MM:SS)
3. Gọi: python scraper_adapter.py --file your_data.csv
"""
import sys
import csv
import json
import random
import argparse
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.utils import setup_logger, format_number
from src.database import init_db, SessionLocal, HotLead

log = setup_logger("fb_adapter")

SAMPLE_KEYWORDS = [
    "Bảng giá dự án", "Cọc thiện chí", "Pháp lý dự án",
    "Biệt thự nghỉ dưỡng", "Đất nền quy hoạch", "Căn hộ tiện ích",
    "Mở bán chính thức", "Chiết khấu ưu đãi",
]

BEHAVIORS = {
    "comment": 3.0,  # Hot score weight
    "share":   2.0,
    "tag":     2.5,
    "like":    0.5,
}


def import_from_csv(filepath: str, db) -> int:
    """Import data từ CSV export của tool FB scraping"""
    path = Path(filepath)
    if not path.exists():
        log.error(f"File không tồn tại: {filepath}")
        return 0

    count = 0
    with open(path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            uid = (row.get("uid") or row.get("facebook_uid") or "").strip()
            if not uid:
                continue

            behavior = (row.get("behavior") or "like").lower()
            hot_score = BEHAVIORS.get(behavior, 0.5)

            lead = HotLead(
                facebook_uid=uid,
                nguon="facebook",
                keyword=row.get("keyword", ""),
                behavior=behavior,
                source_url=row.get("post_url") or row.get("url", ""),
                hot_score=hot_score,
                scraped_at=datetime.now(),
            )
            db.add(lead)
            count += 1

    db.commit()
    return count


def generate_mock_facebook_data(n: int = 500) -> list[dict]:
    """Tạo dữ liệu Facebook mô phỏng để test pipeline"""
    import random

    # Pool UID giả (thực tế sẽ là UID Facebook thật)
    mock_uids = [f"10000{random.randint(10000000, 99999999)}" for _ in range(n)]
    now = datetime.now()
    records = []

    for uid in mock_uids:
        behavior = random.choices(
            list(BEHAVIORS.keys()),
            weights=[0.5, 0.2, 0.2, 0.1],  # comment phổ biến nhất
            k=1
        )[0]
        keyword = random.choice(SAMPLE_KEYWORDS)
        days_ago = random.randint(0, 6)  # 0-6 ngày trước

        records.append({
            "uid": uid,
            "post_url": f"https://facebook.com/posts/{random.randint(100000000, 999999999)}",
            "behavior": behavior,
            "keyword": keyword,
            "timestamp": (now - timedelta(days=days_ago)).strftime("%Y-%m-%d %H:%M:%S"),
        })

    return records


def run_facebook_scraper_import(csv_file: str = None) -> dict:
    """
    Giai đoạn 2A: Import data FB scraping vào HotLeads.

    Args:
        csv_file: Đường dẫn file CSV từ tool của bạn.
                  None = dùng mock data để test.
    """
    log.info("=" * 60)
    log.info("PHASE 2A — FACEBOOK SCRAPER ADAPTER")

    init_db()
    db = SessionLocal()

    # Xóa hot_leads cũ (chỉ nguồn facebook)
    db.query(HotLead).filter(HotLead.nguon == "facebook").delete()
    db.commit()

    if csv_file:
        log.info(f"Import từ file: {csv_file}")
        count = import_from_csv(csv_file, db)
    else:
        log.info("⚠ Không có file CSV → dùng MOCK DATA để test")
        mock_data = generate_mock_facebook_data(500)
        count = 0
        for row in mock_data:
            behavior = row["behavior"]
            lead = HotLead(
                facebook_uid=row["uid"],
                nguon="facebook",
                keyword=row["keyword"],
                behavior=behavior,
                source_url=row["post_url"],
                hot_score=BEHAVIORS.get(behavior, 0.5),
                scraped_at=datetime.strptime(row["timestamp"], "%Y-%m-%d %H:%M:%S"),
            )
            db.add(lead)
            count += 1
        db.commit()

    db.close()
    log.info(f"✅ HOÀN TẤT: {format_number(count)} FB hot leads imported")
    return {"facebook_leads": count, "source": csv_file or "mock_data"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Import FB scraping data")
    parser.add_argument("--file", type=str, help="Path to CSV file from FB scraping tool")
    args = parser.parse_args()
    result = run_facebook_scraper_import(args.file)
    print(f"\nKết quả: {result}")
