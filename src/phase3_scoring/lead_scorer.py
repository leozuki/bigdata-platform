"""
lead_scorer.py — Chấm điểm tiềm năng 1-10 cho từng khách hàng
và export danh sách gọi điện ưu tiên
"""
import os
import sys
from pathlib import Path
from datetime import datetime

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.utils import setup_logger, format_number
from src.database import init_db, SessionLocal, CustomerProfile, HotLead

log = setup_logger("lead_scorer")

PROCESSED_DIR = os.getenv("PROCESSED_DATA_DIR", "d:/AI/01_Products/BigData/data/processed")

CLUSTER_LABELS = {0: "Đầu cơ", 1: "Ở thực", 2: "VIP"}


def calculate_lead_score(profile: CustomerProfile, hot_data: dict, clean_data: dict = None) -> float:
    """
    Chấm điểm tiềm năng (max 10) — Enhanced v2:
      +2    Có SĐT hợp lệ
      +1    Có Facebook UID
      +1    Có Email
      +2    VIP cluster (cluster == 2)
      +1    Ở thực cluster (cluster == 1)
      +2    Đang tương tác Facebook (hot_score_fb > 0)
      +2    Xuất hiện trên Google BĐS (hot_score_google > 0)
      +0.5  Cross-source: xuất hiện ở 2+ nguồn dữ liệu
      +1.0  Cross-source: xuất hiện ở 4+ nguồn dữ liệu
      +0.5  unified_score >= 50 (tier trung)
      +1.0  unified_score >= 70 (tier cao)
      +0.5  source_tier banking_vip / real_estate_vip
    """
    if clean_data is None:
        clean_data = {}
    score = 0.0

    # SĐT hợp lệ (+2)
    if profile.so_dien_thoai:
        score += 2.0

    # Có Facebook UID (+1)
    if profile.facebook_uid:
        score += 1.0

    # Có email (+1)
    if profile.email:
        score += 1.0

    # Cluster bonus
    if profile.cluster == 2:
        score += 2.0   # VIP cluster
    elif profile.cluster == 1:
        score += 1.0   # Ở thực cluster

    # Facebook hot (+2)
    fb_score = hot_data.get("fb_score", 0)
    if fb_score > 0:
        score += min(2.0, fb_score / 5.0)

    # Google hot (+2)
    google_score = hot_data.get("google_score", 0)
    if google_score > 0:
        score += min(2.0, google_score / 4.0)

    # Cross-source bonus (từ CleanContact)
    source_count = clean_data.get("source_count", 1)
    if source_count >= 4:
        score += 1.5
    elif source_count >= 2:
        score += 1.0
    else:
        score += 0.0

    # Unified score bonus
    unified = clean_data.get("unified_score", 0.0) or 0.0
    if unified >= 80:
        score += 2.0
    elif unified >= 70:
        score += 1.5
    elif unified >= 50:
        score += 0.5

    # Source tier bonus — key differentiator khi không có FB/Google data
    tier = clean_data.get("source_tier", "unknown") or "unknown"
    if tier in ("banking_vip", "real_estate_vip"):
        score += 2.0
    elif tier in ("ceo_director", "automotive_vip"):
        score += 1.5
    elif tier in ("stock_gold", "fitness_health"):
        score += 1.0
    elif tier in ("education_hr", "telecom_mass"):
        score += 0.5

    return round(min(score, 10.0), 2)


def run_lead_scoring() -> dict:
    """
    Giai đoạn 3B: Chấm điểm tất cả customer_profiles và export Excel.
    """
    log.info("=" * 60)
    log.info("PHASE 3B — LEAD SCORING")

    init_db()
    db = SessionLocal()

    profiles = db.query(CustomerProfile).all()
    log.info(f"Customer profiles: {format_number(len(profiles))}")

    # Build hot_leads lookup by profile_id
    hot_leads = db.query(HotLead).all()
    hot_by_profile: dict[int, dict] = {}
    hot_by_phone:   dict[str, dict] = {}

    for lead in hot_leads:
        pid  = lead.customer_profile_id
        data = {"fb_score": 0, "google_score": 0, "fb_behavior": "", "gg_keyword": ""}

        if lead.nguon == "facebook":
            data["fb_score"]    = lead.hot_score or 0
            data["fb_behavior"] = lead.behavior or ""
        else:
            data["google_score"] = lead.hot_score or 0
            data["gg_keyword"]   = lead.keyword or ""

        if pid:
            existing = hot_by_profile.get(pid, {"fb_score": 0, "google_score": 0,
                                                 "fb_behavior": "", "gg_keyword": ""})
            existing["fb_score"]     = max(existing["fb_score"], data["fb_score"])
            existing["google_score"] = max(existing["google_score"], data["google_score"])
            existing["fb_behavior"]  = existing["fb_behavior"] or data["fb_behavior"]
            existing["gg_keyword"]   = existing["gg_keyword"] or data["gg_keyword"]
            hot_by_profile[pid] = existing

        if lead.so_dien_thoai:
            existing = hot_by_phone.get(lead.so_dien_thoai, {"fb_score": 0, "google_score": 0,
                                                               "fb_behavior": "", "gg_keyword": ""})
            existing["google_score"] = max(existing["google_score"], data["google_score"])
            hot_by_phone[lead.so_dien_thoai] = existing

    # ── Build CleanContact lookup ──────────────────────────────────
    # CleanContact stores '0xxx', CustomerProfile stores '+84xxx'
    # Build BOTH formats as keys for robust matching
    from src.database import CleanContact

    def _to_p84(phone: str) -> str:
        """Convert '0xxx' → '+84xxx', leave '+84xxx' unchanged"""
        p = (phone or "").strip()
        if p.startswith("0"):
            return "+84" + p[1:]
        return p

    clean_contacts = db.query(
        CleanContact.so_dien_thoai,
        CleanContact.source_count,
        CleanContact.unified_score,
        CleanContact.source_tier,
    ).all()

    clean_by_phone: dict[str, dict] = {}
    for c in clean_contacts:
        if not c.so_dien_thoai:
            continue
        entry = {
            "source_count":  c.source_count  or 1,
            "unified_score": c.unified_score or 0.0,
            "source_tier":   c.source_tier   or "unknown",
        }
        raw = c.so_dien_thoai
        clean_by_phone[raw] = entry                  # '0xxx' key
        clean_by_phone[_to_p84(raw)] = entry         # '+84xxx' key

    log.info(f"CleanContact lookup: {len(clean_contacts):,} entries ({len(clean_by_phone):,} keys)")

    # Chấm điểm và cập nhật DB
    records = []
    for profile in profiles:
        hot_data   = hot_by_profile.get(profile.id) or hot_by_phone.get(profile.so_dien_thoai, {})
        clean_data = clean_by_phone.get(profile.so_dien_thoai, {})
        score = calculate_lead_score(profile, hot_data, clean_data)
        profile.lead_score = score

        records.append({
            "STT":          0,
            "Họ Tên":       profile.ho_ten or "",
            "Số ĐT":        profile.so_dien_thoai or "",
            "Facebook UID": profile.facebook_uid or "",
            "Email":        profile.email or "",
            "Địa Chỉ":      profile.dia_chi or "",
            "Nguồn":        profile.nguon or "",
            "Nhóm KH":      profile.cluster_label or "Chưa phân",
            "X-Ref (nguồn)": clean_data.get("source_count", 1),
            "Tier":         clean_data.get("source_tier", "unknown"),
            "FB Hot Score": hot_data.get("fb_score", 0),
            "GG Hot Score": hot_data.get("google_score", 0),
            "ĐIỂM":         score,
        })

    db.commit()
    db.close()

    # Sort by score descending
    df = pd.DataFrame(records)
    df = df.sort_values("ĐIỂM", ascending=False).reset_index(drop=True)
    df["STT"] = df.index + 1

    # Export Excel
    Path(PROCESSED_DIR).mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = Path(PROCESSED_DIR) / f"priority_call_list_{timestamp}.xlsx"

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        # Sheet 1: Tất cả
        df.to_excel(writer, sheet_name="Tất cả", index=False)

        # Sheet 2: VIP (điểm >= 8)
        vip_df = df[df["ĐIỂM"] >= 8]
        vip_df.to_excel(writer, sheet_name="VIP (≥8 điểm)", index=False)

        # Sheet 3: Đang nóng Facebook
        fb_hot = df[df["FB Hot Score"] > 0].sort_values("FB Hot Score", ascending=False)
        fb_hot.to_excel(writer, sheet_name="Nóng FB", index=False)

        # Sheet 4: Rao bán Google
        gg_hot = df[df["GG Hot Score"] > 0].sort_values("GG Hot Score", ascending=False)
        gg_hot.to_excel(writer, sheet_name="Rao Bán Google", index=False)

    # Style Excel
    _apply_excel_style(output_path)

    score_dist = df["ĐIỂM"].describe().to_dict()
    log.info("─" * 60)
    log.info(f"✅ XUẤT FILE: {output_path}")
    log.info(f"   Tổng:      {format_number(len(df))}")
    log.info(f"   Điểm 8-10: {format_number(len(df[df['ĐIỂM'] >= 8]))} (chuyển Sales giỏi)")
    log.info(f"   Điểm 5-7:  {format_number(len(df[(df['ĐIỂM'] >= 5) & (df['ĐIỂM'] < 8)]))} (cần chăm sóc)")
    log.info(f"   Điểm <5:   {format_number(len(df[df['ĐIỂM'] < 5]))} (cold lead)")

    return {
        "total": len(df),
        "vip":   len(vip_df),
        "output_file": str(output_path),
        "score_stats": {k: round(v, 2) for k, v in score_dist.items()},
    }


def _apply_excel_style(filepath: Path):
    """Áp dụng định dạng đẹp cho file Excel"""
    try:
        from openpyxl import load_workbook
        from openpyxl.styles import (PatternFill, Font, Alignment,
                                     Border, Side, GradientFill)
        from openpyxl.utils import get_column_letter

        wb = load_workbook(filepath)

        header_fill   = PatternFill("solid", fgColor="1F3864")
        header_font   = Font(bold=True, color="FFFFFF", name="Calibri", size=11)
        vip_fill      = PatternFill("solid", fgColor="FFD700")     # Gold cho điểm cao
        hot_fill      = PatternFill("solid", fgColor="FFE4B5")     # Cam nhạt
        center_align  = Alignment(horizontal="center", vertical="center")

        for ws in wb.worksheets:
            # Header
            for cell in ws[1]:
                cell.fill      = header_fill
                cell.font      = header_font
                cell.alignment = center_align

            # Data rows
            for row in ws.iter_rows(min_row=2):
                score_cell = None
                for cell in row:
                    if ws.cell(1, cell.column).value == "ĐIỂM":
                        score_cell = cell
                        break

                score_val = score_cell.value if score_cell else 0
                for cell in row:
                    cell.alignment = Alignment(vertical="center")
                    if score_val and score_val >= 8:
                        cell.fill = vip_fill
                    elif score_val and score_val >= 5:
                        cell.fill = hot_fill

            # Auto-width
            for col_idx, col in enumerate(ws.columns, 1):
                max_len = max((len(str(c.value or "")) for c in col), default=10)
                ws.column_dimensions[get_column_letter(col_idx)].width = min(max_len + 4, 40)

            ws.freeze_panes = "A2"

        wb.save(filepath)
    except Exception as e:
        log.warning(f"Không áp dụng được style Excel: {e}")


if __name__ == "__main__":
    result = run_lead_scoring()
    print(f"\nKết quả: {result}")
