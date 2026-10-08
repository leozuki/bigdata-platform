"""
filter_engine.py — Lọc và tính hot_score cho leads từ Facebook và Google
"""
import sys
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.utils import setup_logger, format_number
from src.database import init_db, SessionLocal, HotLead, GoogleLead

log = setup_logger("filter_engine")

# Trọng số theo loại tương tác Facebook
BEHAVIOR_WEIGHTS = {
    "comment": 3.0,  # Hỏi giá, bình luận → rất quan tâm
    "tag":     2.5,  # Tag người thân → chia sẻ nhu cầu
    "share":   2.0,  # Share về tường → đang tìm kiếm
    "like":    0.5,  # Like thụ động → quan tâm nhẹ
}

# Trọng số nguồn Google (tự đăng rao bán = có ý định cao)
GOOGLE_BASE_SCORE = 3.0

# Ngưỡng thời gian (ngày)
HOT_WINDOW_DAYS = 7


def score_facebook_leads(db) -> int:
    """
    Tính lại hot_score cho tất cả Facebook leads.
    Ưu tiên:
    1. Tương tác gần đây (trong 7 ngày)
    2. Nhiều lần tương tác
    3. Hành vi có giá trị cao (comment > tag > share > like)
    """
    cutoff_date = datetime.now() - timedelta(days=HOT_WINDOW_DAYS)

    fb_leads = db.query(HotLead).filter(HotLead.nguon == "facebook").all()
    log.info(f"  FB leads tổng: {format_number(len(fb_leads))}")

    # Group theo UID để tính tổng score
    uid_scores: dict[str, float] = {}
    uid_recent: dict[str, bool] = {}

    for lead in fb_leads:
        uid = lead.facebook_uid
        behavior = lead.behavior or "like"
        base = BEHAVIOR_WEIGHTS.get(behavior, 0.5)

        # Bonus nếu trong 7 ngày gần nhất
        is_recent = lead.scraped_at >= cutoff_date if lead.scraped_at else False
        score = base * (1.5 if is_recent else 1.0)

        uid_scores[uid] = uid_scores.get(uid, 0) + score
        uid_recent[uid] = uid_recent.get(uid, False) or is_recent

    # Cập nhật hot_score
    updated = 0
    for lead in fb_leads:
        uid = lead.facebook_uid
        lead.hot_score = round(min(uid_scores.get(uid, 0), 10.0), 2)  # Cap tại 10
        updated += 1

    db.commit()

    # Lọc bỏ leads cũ và ít tương tác
    stale = db.query(HotLead).filter(
        HotLead.nguon == "facebook",
        HotLead.hot_score < 0.3,
    ).delete()
    db.commit()

    log.info(f"  FB leads sau lọc: {format_number(updated - stale)}")
    log.info(f"  Loại bỏ {stale} leads score thấp")
    return updated - stale


def score_google_leads(db) -> int:
    """
    Tính hot_score cho Google leads:
    - Người đang rao bán = đang có nhu cầu BĐS → score cao
    - SĐT trùng nhiều trang → càng nhiều lần xuất hiện → score cao hơn
    """
    google_leads = db.query(GoogleLead).all()
    log.info(f"  Google leads tổng: {format_number(len(google_leads))}")

    # Đếm tần suất xuất hiện của mỗi SĐT
    phone_count: dict[str, int] = {}
    for lead in google_leads:
        p = lead.so_dien_thoai
        phone_count[p] = phone_count.get(p, 0) + 1

    # Chuyển sang HotLead với google score
    # Xóa google hot_leads cũ
    db.query(HotLead).filter(HotLead.nguon == "google").delete()
    db.commit()

    hot_google = []
    processed_phones = set()

    for lead in google_leads:
        phone = lead.so_dien_thoai
        if phone in processed_phones:
            continue
        processed_phones.add(phone)

        frequency = phone_count[phone]
        # Score: base 3.0 + 0.5 mỗi lần thêm xuất hiện, max 8
        score = min(GOOGLE_BASE_SCORE + (frequency - 1) * 0.5, 8.0)

        hot = HotLead(
            so_dien_thoai=phone,
            nguon="google",
            keyword=lead.keyword,
            behavior="listing",  # Đang rao bán/đăng tin BĐS
            source_url=lead.source_url,
            hot_score=round(score, 2),
            scraped_at=lead.scraped_at,
        )
        hot_google.append(hot)

    db.bulk_save_objects(hot_google)
    db.commit()

    log.info(f"  Google hot leads: {format_number(len(hot_google))}")
    return len(hot_google)


def run_filter_engine() -> dict:
    """Giai đoạn 2B (filter): Chuẩn hóa và score toàn bộ leads"""
    log.info("=" * 60)
    log.info("PHASE 2B — FILTER ENGINE")

    init_db()
    db = SessionLocal()

    fb_count = score_facebook_leads(db)
    google_count = score_google_leads(db)

    db.close()

    log.info("─" * 60)
    log.info(f"✅ HOÀN TẤT: {format_number(fb_count)} FB + {format_number(google_count)} Google hot leads")
    return {"facebook_hot": fb_count, "google_hot": google_count}


if __name__ == "__main__":
    result = run_filter_engine()
    print(f"\nKết quả: {result}")
