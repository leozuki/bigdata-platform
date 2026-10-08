"""
matcher.py — So khớp hot_leads với customer_profiles (khách cũ đang nóng)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.utils import setup_logger, format_number
from src.database import init_db, SessionLocal, HotLead, CustomerProfile

log = setup_logger("matcher")


def run_matching() -> dict:
    """
    Giai đoạn 2C: So khớp hot_leads với customer_profiles.

    Kết quả:
    - is_existing_customer = True  → khách cũ đang nóng (ưu tiên gọi #1)
    - is_existing_customer = False → khách mới từ Google (thêm vào DB)
    """
    log.info("=" * 60)
    log.info("PHASE 2C — MATCHING")

    init_db()
    db = SessionLocal()

    # Build lookup maps từ customer_profiles
    profiles_by_phone = {
        p.so_dien_thoai: p for p in db.query(CustomerProfile).all()
    }
    profiles_by_uid = {
        p.facebook_uid: p for p in db.query(CustomerProfile).filter(
            CustomerProfile.facebook_uid.isnot(None)
        ).all()
    }

    log.info(f"Customer profiles: {format_number(len(profiles_by_phone))}")
    log.info(f"  Có Facebook UID: {format_number(len(profiles_by_uid))}")

    all_hot_leads = db.query(HotLead).all()
    log.info(f"Hot leads: {format_number(len(all_hot_leads))}")

    existing_matched = 0
    new_from_google  = 0

    for lead in all_hot_leads:
        profile = None

        # Match theo UID (Facebook)
        if lead.facebook_uid:
            profile = profiles_by_uid.get(lead.facebook_uid)

        # Match theo SĐT (Google leads)
        if not profile and lead.so_dien_thoai:
            profile = profiles_by_phone.get(lead.so_dien_thoai)

        if profile:
            lead.is_existing_customer = True
            lead.customer_profile_id  = profile.id
            existing_matched += 1
        else:
            lead.is_existing_customer = False

            # Thêm Google leads mới vào CustomerProfile
            if lead.nguon == "google" and lead.so_dien_thoai:
                new_profile = CustomerProfile(
                    so_dien_thoai=lead.so_dien_thoai,
                    nguon="google_scraping",
                    ghi_chu=f"Thu thập từ Google: {lead.keyword} | {lead.source_url}",
                )
                db.add(new_profile)
                new_from_google += 1

    db.commit()
    db.close()

    log.info("─" * 60)
    log.info(f"✅ Khách CŨ đang NÓNG:  {format_number(existing_matched)} (ưu tiên gọi #1)")
    log.info(f"   Khách MỚI từ Google: {format_number(new_from_google)} (thêm vào DB)")

    return {
        "existing_hot_customers": existing_matched,
        "new_from_google":        new_from_google,
    }


if __name__ == "__main__":
    result = run_matching()
    print(f"\nKết quả: {result}")
