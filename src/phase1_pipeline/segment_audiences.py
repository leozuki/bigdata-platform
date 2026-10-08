import json
import os
import pandas as pd
from pathlib import Path
import sys
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.utils import setup_logger, extract_province
from src.database import SessionLocal, CleanContact, DashboardStats

log = setup_logger("segmentation")

# Base output dir — đọc từ env
_BASE_DATA = Path(os.getenv("PROCESSED_DATA_DIR", str(Path(__file__).parent.parent.parent / "data" / "processed"))).parent

def calculate_score(lead: dict) -> int:
    """
    Chấm điểm chất lượng Lead (Max 10 điểm):
    - Có Số điện thoại hợp lệ: +5
    - Có Email hợp lệ: +3
    - Có địa chỉ hoặc phân loại Tỉnh/Thành: +2
    - Nằm trong các tệp VIP (Biệt thự, Mercedes, land rover...): +Bonus 2
    """
    score = 0
    if lead.get("phone"): score += 5
    if lead.get("email"): score += 3
    if lead.get("address") or (lead.get("province") and lead.get("province") != "Unknown"): score += 2
    
    # VIP keywords detection based on file origin and notes
    vip_keywords = [
        "biệt thự", "villa", "land rover", "lexus", "audi", 
        "mercedes", "bmw", "shophouse", "penthouse", "the manor", 
        "phú mỹ hưng", "savill", "vip"
    ]
    content = (str(lead.get("file_origin", "")) + str(lead.get("note", ""))).lower()
    
    for kw in vip_keywords:
        if kw in content:
            score += 2
            break
            
    return min(score, 10)

def main():
    db = SessionLocal()
    
    log.info("Khởi tạo tiến trình chấm điểm Big Data...")
    
    # Sử dụng generator để load từng phần, tránh treo RAM
    batch_size = 5000
    total_processed = 0
    vip_leads = []
    
    while True:
        contacts = db.query(CleanContact).offset(total_processed).limit(batch_size).all()
        if not contacts:
            break
            
        for contact in contacts:
            # Chuyển đổi sang dict cho logic cũ
            lead_dict = {
                "name": contact.ho_ten,
                "phone": contact.so_dien_thoai,
                "email": contact.email,
                "address": contact.dia_chi,
                "source": contact.nguon,
                "note": contact.ghi_chu,
                "file_origin": contact.file_source
            }
            # Thêm thông tin Facebook nếu có
            if hasattr(contact, 'facebook_uid'): 
                lead_dict["fb_uid"] = contact.facebook_uid
                lead_dict["fb_link"] = contact.facebook_link

            score = calculate_score(lead_dict)
            contact.score = score
            lead_dict["score"] = score
            
            if score >= 8:
                vip_leads.append(lead_dict)
        
        db.commit()
        total_processed += len(contacts)
        log.info(f"  - Đã chấm điểm: {total_processed} leads...")
        
    # --- CẬP NHẬT DASHBOARD CACHE ---
    log.info("📊 Đang tạo bản sao lưu chỉ số Dashboard (Snapshot)...")
    db = SessionLocal()
    try:
        # 1. Tính toán phân bổ tỉnh thành (Dùng sample hoặc quét nhanh)
        provinces_list = ["Hà Nội", "Hồ Chí Minh", "Đà Nẵng", "Bình Dương", "Đồng Nai", "Nghệ An", "Hải Phòng", "Cần Thơ"]
        dist = []
        for p in provinces_list:
            count = db.query(CleanContact).filter(CleanContact.dia_chi.ilike(f"%{p}%")).count()
            dist.append({"Province": p, "Count": count})
        
        others_count = total_processed - sum(d['Count'] for d in dist)
        dist.append({"Province": "Tỉnh khác", "Count": max(0, others_count)})
        
        # 2. Vô hiệu hóa snapshot cũ
        db.query(DashboardStats).update({DashboardStats.is_latest: False})
        
        # 3. Tạo snapshot mới
        new_stats = DashboardStats(
            total_leads=total_processed,
            vip_leads=len(vip_leads),
            provincial_distribution=json.dumps(dist),
            is_latest=True,
            snapshot_time=datetime.utcnow()
        )
        db.add(new_stats)
        db.commit()
        log.info("✅ Đã cập nhật Dashboard Snapshot thành công.")
    except Exception as e:
        log.error(f"❌ Lỗi khi cập nhật Snapshot: {e}")
        db.rollback()
    finally:
        db.close()
            
    log.info("=" * 60)
    log.info(f"PHÂN TÍCH CHẤT LƯỢNG TIẾN TỚI:")
    log.info(f"  - Tổng số Leads đã quét: {total_processed}")
    log.info(f"  - Tập KH VIP (Elite):      {len(vip_leads)} leads")
    log.info("=" * 60)
    
    # --- Format chuẩn cho Custom Audience (Facebook / Google Ads) ---
    def format_audience(lead_list):
        formatted = []
        for l in lead_list:
            # Tách First Name / Last Name
            raw_name = l.get("name") or ""
            name_parts = raw_name.strip().split(" ")
            fn = name_parts[-1] if name_parts else ""
            ln = " ".join(name_parts[:-1]) if len(name_parts) > 1 else ""
            
            # Format phone chuẩn quốc tế cho FB (+84...)
            phone = str(l.get("phone", ""))
            if phone.startswith("0"):
                phone = "84" + phone[1:]
                
            formatted.append({
                "email": l.get("email", ""),
                "phone": phone,
                "fn": fn,
                "ln": ln,
                "ct": l.get("province", "").replace("TP. ", "") if l.get("province") != "Unknown" else "",
                "country": "VN" if phone else "",
                "score": l["score"],
                "source_file": l.get("file_origin", "")
            })
        return formatted
        
    vip_aud = format_audience(vip_leads)
    
    final_dir = _BASE_DATA / "final"
    final_dir.mkdir(parents=True, exist_ok=True)
    
    if vip_aud:
        # Xuất CSV chuẩn format upload Custom Audience (Tệp CSV không bỏ dấu)
        df_vip_csv = pd.DataFrame(vip_aud)
        csv_out_path = final_dir / "ads_custom_audience_vip.csv"
        df_vip_csv.to_csv(csv_out_path, index=False)
        log.info(f"✅ Đã xuất tệp CSV chạy Quảng cáo Retargeting: {csv_out_path}")
        
    # Xuất Excel để Sales có danh sách bốc máy gọi
    if vip_leads:
        df_excel = pd.DataFrame(vip_leads)
        # Reorder columns
        cols = ["score", "name", "phone", "email", "province", "address", "file_origin"]
        df_excel = df_excel[[c for c in cols if c in df_excel.columns]]
        df_excel.sort_values(by=["score", "file_origin"], ascending=[False, True], inplace=True)
        
        excel_path = final_dir / "sales_vip_priority_list.xlsx"
        df_excel.to_excel(excel_path, index=False)
        log.info(f"✅ Đã xuất tệp Excel danh sách ưu tiên Telesale:  {excel_path}")

if __name__ == "__main__":
    main()


def run_segmentation() -> dict:
    """
    Public wrapper — được gọi bởi main.py.
    Chạm điểm tất cả leads trong DB và xuất danh sách VIP.
    """
    try:
        main()
        return {"segmentation": "done"}
    except Exception as e:
        log.warning(f"[WARN] segment_audiences: {e}")
        return {"segmentation": "skipped", "error": str(e)}
