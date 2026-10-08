"""
excel_ingestor.py — Hệ thống lọc và chuẩn hóa dữ liệu từ 1000+ file Excel.
Tự động detect column, làm sạch, deduplicate và báo cáo.
"""
import os
import pandas as pd
import json
import re
import shutil
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.utils import (
    setup_logger, normalize_phone_vn, validate_email, 
    get_all_data_files, format_number, extract_province
)
from src.database import init_db, SessionLocal, CleanContact

log = setup_logger("excel_ingestor")

# Schema chuẩn
STANDARD_SCHEMA = ["name", "phone", "email", "address", "province", "source", "campaign", "date", "note"]

# Map các cột thô sang schema chuẩn
COLUMN_MAPPING = {
    "name": ["họ tên", "full name", "tên", "customer name", "khách hàng", "họ và tên", "tên khách hàng", "first name", "last name", "họ", "đệm"],
    "phone": ["số điện thoại", "sđt", "phone", "mobile", "tel", "di động", "contact", "số đt", "điện thoại", "tổng số"],
    "email": ["email", "thư điện tử", "e-mail", "địa chỉ email"],
    "address": ["địa chỉ", "address", "địa chỉ thường trú", "thường trú", "location", "đv"],
    "source": ["nguồn", "source", "origin", "nguồn khách"],
    "campaign": ["chiến dịch", "campaign", "ad name", "ad set", "tên chiến dịch"],
    "date": ["ngày", "date", "ngày tạo", "created at", "ngay", "time"],
    "note": ["ghi chú", "note", "comment", "yêu cầu", "nội dung", "request"],
    "fb_uid": ["fb_uid", "uid facebook", "uid", "facebook id", "id facebook", "fb id"],
    "fb_link": ["link facebook", "facebook link", "fb link", "link fb", "fb_link", "trang cá nhân", "profile"],
}

class ExcelProcessResult:
    def __init__(self):
        self.total_rows = 0
        self.valid_leads = 0
        self.duplicate_count = 0
        self.missing_phone_email = 0
        self.invalid_phone_count = 0
        self.unclassified_count = 0
        self.cleaned_data = []
        self.rejected_data = [] # Lead bị loại kèm lý do

def detect_column_mapping(df_columns: list) -> dict:
    """
    Tự động map các cột của dataframe sang schema chuẩn.
    Trả về dict: {standard_col: raw_col}
    """
    mapping = {}
    used_raw_cols = set()
    
    # 1. Tìm các cột khớp keywords chuẩn
    for std_col, keywords in COLUMN_MAPPING.items():
        for col in df_columns:
            col_lower = str(col).lower().strip()
            if any(kw == col_lower or kw in col_lower for kw in keywords):
                if col not in used_raw_cols:
                    mapping[std_col] = col
                    used_raw_cols.add(col)
                    break
    
    # 2. Đặc biệt cho HubSpot/CRM: Nếu ko có 'name' chuẩn, tìm First/Last Name
    if "name" not in mapping:
        f_col = next((c for c in df_columns if "first name" in str(c).lower()), None)
        l_col = next((c for c in df_columns if "last name" in str(c).lower()), None)
        if f_col: mapping["first_name"] = f_col
        if l_col: mapping["last_name"] = l_col
        
    return mapping

def clean_name(name) -> str:
    if pd.isna(name) or str(name).lower() in ['nan', 'none', 'null', 'unknown']: return ""
    # Trim spaces, remove special characters (keep Vietnamese chars)
    s = str(name).strip()
    s = re.sub(r'[\r\n\t]', ' ', s)
    # Tự động viết hoa chữ cái đầu (để đẹp hơn trên dashboard)
    s = " ".join([w.capitalize() for w in s.split()])
    return s

def infer_source_from_content(row, filename):
    """Suy luận nguồn từ tên file hoặc nội dung hàng"""
    content = str(row).lower() + str(filename).lower()
    if "facebook" in content or "fb " in content: return "Facebook"
    if "google" in content or "gg " in content: return "Google"
    if "zalo" in content: return "Zalo"
    if "tikt" in content: return "TikTok"
    return "Unknown"

def process_single_file(file_path: Path, seen_leads: set) -> ExcelProcessResult:
    res = ExcelProcessResult()
    try:
        # Load file (csv hoặc xlsx hoặc doc/docx)
        if file_path.suffix.lower() == ".txt":
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                lines = [line.strip() for line in f if line.strip()]
            
            # Detect complex format (Social Data)
            # Dấu hiệu: Có email facebook, hoặc bắt đầu bằng UID (dãy số dài)
            is_social = any("facebook.com" in ln.lower() for ln in lines[:10]) or \
                        (len(lines) > 0 and lines[0].split() and lines[0].split()[0].isdigit() and len(lines[0].split()[0]) >= 9)
            
            if is_social:
                records = []
                for ln in lines:
                    p = ln.split()
                    if len(p) < 2: continue
                    
                    # 1. Tìm UID (Dãy số >= 15 ký tự hoặc số dài đầu tiên)
                    uid = ""
                    for x in p:
                        if x.isdigit() and len(x) >= 14: # Hầu hết UID FB hiện nay 15 số
                            uid = x
                            break
                    if not uid and p[0].isdigit() and len(p[0]) >= 9:
                        uid = p[0]
                        
                    # 2. Tìm Phone
                    phone = next((x for x in p if x.startswith("+84") or (x.startswith("0") and len(x)>=10 and x.isdigit())), "")
                    
                    # 3. Tìm Email
                    email = next((x for x in p if "@" in x), "")
                    
                    # 4. Trích xuất Tên (Phần còn lại sau khi loại UID, Phone, Email, Locale)
                    # Một cách đơn giản: Lấy part 1, 2, 3 nếu không phải UID/Email/Phone
                    exclude = [uid, phone, email, "vi_VN", "en_US", "vi", "en", "VN", "US"]
                    name_parts = [x for x in p if x not in exclude and not x.lower().startswith("http") and not x.isdigit()]
                    name = " ".join(name_parts[:3]) # Lấy 3 từ đầu tiên còn lại làm tên
                    
                    records.append({
                        "phone": phone, "email": email, "name": name, 
                        "fb_uid": uid, "fb_link": f"https://facebook.com/{uid}" if uid else ""
                    })
                df = pd.DataFrame(records)
            else:
                df = pd.DataFrame(lines, columns=["phone"])
        elif file_path.suffix.lower() in [".doc", ".docx"]:
            # Thử đọc như HTML trước vì nhiều file .doc marketing thực chất là HTML
            try:
                dfs = pd.read_html(file_path, encoding='utf-8')
                df = dfs[0] if dfs else pd.DataFrame()
            except Exception:
                # Nếu không phải HTML, đọc binary và trích xuất phone bằng regex
                with open(file_path, "rb") as f:
                    content = f.read().decode('utf-8', errors='ignore')
                # Tìm các chuỗi giống số điện thoại VN (9-11 chữ số)
                phones = re.findall(r'(?:0|\+84)\d{8,10}', content)
                df = pd.DataFrame(phones, columns=["phone"])
        elif file_path.suffix.lower() in [".csv", ".xls", ".xlsx"]:
            # Smart Header Detection: Thử đọc 5 dòng đầu để tìm dòng chứa Header thực sự
            df_preview = pd.read_excel(file_path, header=None, nrows=10) if file_path.suffix.lower() != ".csv" else pd.read_csv(file_path, header=None, nrows=10)
            
            best_header = 0
            max_matches = 0
            for i in range(len(df_preview)):
                row_vals = [str(x).lower() for x in df_preview.iloc[i].values]
                matches = sum(1 for std_col, keywords in COLUMN_MAPPING.items() if any(any(kw in val for kw in keywords) for val in row_vals))
                if matches > max_matches:
                    max_matches = matches
                    best_header = i
            
            # Re-read với header chuẩn
            if file_path.suffix.lower() == ".csv":
                try:
                    df = pd.read_csv(file_path, header=best_header, encoding='utf-8')
                except:
                    df = pd.read_csv(file_path, header=best_header, encoding='latin1')
            else:
                try:
                    df = pd.read_excel(file_path, header=best_header)
                except Exception:
                    # Fallback cho HTML-as-Excel
                    dfs = pd.read_html(file_path, header=best_header)
                    df = dfs[0] if dfs else pd.DataFrame()
        else:
            df = pd.DataFrame()
                        
        res.total_rows = len(df)
        mapping = detect_column_mapping(df.columns.tolist())
        if not mapping and file_path.suffix == ".txt":
            mapping = {"phone": "phone"} # Fallback cho định dạng txt thuần
        
        # Log mapping nếu cần
        # log.debug(f"File {file_path.name} mapping: {mapping}")
        
        for _, row in df.iterrows():
            # 1. Trích xuất data theo mapping
            raw_phone = row.get(mapping.get("phone"), "")
            raw_email = str(row.get(mapping.get("email"), ""))
            
            # Xử lý ghép cột Tên (Dành cho HubSpot/Salesforce có First Name, Last Name)
            raw_name = ""
            if mapping.get("name"):
                raw_name = str(row.get(mapping.get("name"), ""))
            
            if not raw_name or raw_name.lower() == 'nan':
                # Map kiểu HubSpot: First Name + Last Name
                f_name = str(row.get(mapping.get("first_name"), "")) if mapping.get("first_name") else ""
                l_name = str(row.get(mapping.get("last_name"), "")) if mapping.get("last_name") else ""
                
                # Loại bỏ chuỗi 'nan' nếu có
                f_clean = f_name if f_name.lower() != 'nan' else ""
                l_clean = l_name if l_name.lower() != 'nan' else ""
                
                if f_clean or l_clean:
                    raw_name = f"{l_clean} {f_clean}".strip()
            
            raw_name = str(raw_name)
            raw_address = str(row.get(mapping.get("address"), ""))
            raw_source = str(row.get(mapping.get("source"), ""))
            raw_campaign = str(row.get(mapping.get("campaign"), ""))
            raw_date = str(row.get(mapping.get("date"), ""))
            raw_note = str(row.get(mapping.get("note"), ""))
            raw_fb_uid = str(row.get(mapping.get("fb_uid"), ""))
            raw_fb_link = str(row.get(mapping.get("fb_link"), ""))
            
            # 2. Làm sạch data
            phone = normalize_phone_vn(raw_phone)
            email = raw_email.strip().lower() if validate_email(raw_email) else ""
            name = clean_name(raw_name)
            address = raw_address.strip() if not pd.isna(raw_address) else ""
            
            fb_uid = raw_fb_uid.strip() if raw_fb_uid and raw_fb_uid.lower() != "nan" else ""
            fb_link = raw_fb_link.strip() if raw_fb_link and raw_fb_link.lower() != "nan" else ""
            
            # 3. Validation & Stats
            reject_reason = ""
            
            if not raw_phone and not raw_email:
                reject_reason = "Thiếu cả SĐT và Email"
                res.missing_phone_email += 1
            elif raw_phone and not phone:
                reject_reason = f"SĐT không hợp lệ: {raw_phone}"
                res.invalid_phone_count += 1
            
            if reject_reason:
                res.rejected_data.append({
                    "raw_name": raw_name, "raw_phone": raw_phone, "raw_email": raw_email,
                    "raw_fb_uid": raw_fb_uid, "raw_fb_link": raw_fb_link,
                    "reason": reject_reason, "file_origin": file_path.name
                })
                continue
                
            # Tạo unique key để deduplicate
            # Ưu tiên phone, nếu ko có thì email
            lead_key = phone if phone else email
            if lead_key in seen_leads:
                res.duplicate_count += 1
                res.rejected_data.append({
                    "raw_name": raw_name, "raw_phone": raw_phone, "raw_email": raw_email,
                    "raw_fb_uid": raw_fb_uid, "raw_fb_link": raw_fb_link,
                    "reason": "Trùng lặp (Duplicate)", "file_origin": file_path.name
                })
                continue
            
            seen_leads.add(lead_key)
            res.valid_leads += 1
            
            # 4. Enrichment
            source = raw_source if raw_source and not pd.isna(raw_source) else infer_source_from_content(row, file_path.name)
            campaign = raw_campaign if raw_campaign and not pd.isna(raw_campaign) else ""
            province = extract_province(address, file_path.name)
            
            if province == "Unknown":
                res.unclassified_count += 1
            
            # 5. Add to cleaned data
            res.cleaned_data.append({
                "name": name,
                "phone": phone,
                "email": email,
                "address": address,
                "province": province,
                "source": source,
                "campaign": campaign,
                "date": str(raw_date),
                "note": raw_note,
                "file_origin": file_path.name,
                "facebook_uid": fb_uid,
                "facebook_link": fb_link
            })
            
    except Exception as e:
        log.error(f"Error processing {file_path.name}: {e}")
        
    return res

def run_ingestion(data_dir: str):
    log.info(f"Bắt đầu quá trình lọc data từ: {data_dir}")
    files = get_all_data_files(data_dir)
    log.info(f"Tìm thấy {len(files)} file dữ liệu.")
    
    overall_stats = {
        "total_files": len(files),
        "total_rows_scanned": 0,
        "valid_leads": 0,
        "duplicate_count": 0,
        "missing_phone_email": 0,
        "invalid_phone_count": 0,
        "unclassified_count": 0,
    }
    
    init_db()
    db = SessionLocal()
    
    # --- LOAD DỮ LIỆU CŨ ĐỂ CỘNG DỒN (Dùng DB để hạn chế RAM) ---
    seen_leads = set()
    try:
        # Chỉ lấy cột phone và email để tiết kiệm memory
        history_phones = db.query(CleanContact.so_dien_thoai).all()
        for p in history_phones:
            if p[0]: seen_leads.add(p[0])
            
        history_emails = db.query(CleanContact.email).filter(CleanContact.email != "").all()
        for e in history_emails:
            if e[0]: seen_leads.add(e[0])
            
        log.info(f"Đã nạp {len(seen_leads)} lead từ lịch sử DB thành công.")
    except Exception as e:
        log.warning(f"Không thể nạp dữ liệu lịch sử từ DB: {e}")
    
    all_rejected_data = []

    # Thư mục chứa file đã xử lý xong
    processed_dir = Path(data_dir).parent / "processed"
    processed_dir.mkdir(parents=True, exist_ok=True)
    
    # Ở quy mô 1000+ file, xử lý tuần tự để tránh nghẽn I/O và RAM nếu file to
    # Nếu file nhỏ có thể dùng ThreadPoolExecutor
    for i, file_path in enumerate(files):
        log.info(f"Đang xử lý file {i+1}/{overall_stats['total_files']}: {file_path.name}")
            
        file_res = process_single_file(file_path, seen_leads)
        
        overall_stats["total_rows_scanned"] += file_res.total_rows
        overall_stats["valid_leads"] += file_res.valid_leads
        overall_stats["duplicate_count"] += file_res.duplicate_count
        overall_stats["missing_phone_email"] += file_res.missing_phone_email
        overall_stats["invalid_phone_count"] += file_res.invalid_phone_count
        overall_stats["unclassified_count"] += file_res.unclassified_count
        
        # --- LƯU TRỰC TIẾP VÀO DB (Bulk insert + Source Tier) ---
        if file_res.cleaned_data:
            # Classify source tier cho file này
            try:
                from src.utils.file_classifier import classify_file
                tier_info = classify_file(file_path.name)
                s_tier   = tier_info["tier_key"]
                s_weight = tier_info["weight"]
            except Exception:
                s_tier, s_weight = "unknown", 0.25

            # BULK INSERT — new unique leads
            _CHUNK = 500
            new_records = [{
                "ho_ten":              item["name"],
                "all_names":           item["name"],
                "so_dien_thoai":       item["phone"],
                "so_dien_thoai_goc":   item["phone"],
                "email":               item["email"],
                "dia_chi":             item["address"],
                "nguon":               item["source"],
                "all_sources":         item["file_origin"],
                "ghi_chu":             item["note"],
                "file_source":         item["file_origin"],
                "facebook_uid":        item.get("facebook_uid", ""),
                "facebook_link":       item.get("facebook_link", ""),
                "source_tier":         s_tier,
                "source_weight":       s_weight,
                "source_count":        1,
            } for item in file_res.cleaned_data]

            for _i in range(0, len(new_records), _CHUNK):
                try:
                    db.bulk_insert_mappings(CleanContact, new_records[_i:_i+_CHUNK])
                    db.commit()
                except Exception as e:
                    db.rollback()
                    log.error(f"Bulk insert error (chunk {_i}): {e}")

            # MERGE duplicates — chỉ cập nhật những thông tin bổ sung, tăng source_count
            duplicates = [r for r in file_res.rejected_data if r["reason"] == "Trùng lặp (Duplicate)"]
            for dup in duplicates:
                phone = normalize_phone_vn(dup["raw_phone"])
                if not phone: continue

                existing = db.query(CleanContact).filter(CleanContact.so_dien_thoai == phone).first()
                if existing:
                    # Merge tên
                    current_names = set(existing.all_names.split(", ")) if existing.all_names else set()
                    new_name = clean_name(dup["raw_name"])
                    if new_name and new_name not in current_names:
                        current_names.add(new_name)
                        existing.all_names = ", ".join(current_names)
                        if not existing.ho_ten or existing.ho_ten.lower() in ('none', ''):
                            existing.ho_ten = new_name

                    # Merge nguồn + tăng source_count
                    current_sources = set(existing.all_sources.split(", ")) if existing.all_sources else set()
                    if dup["file_origin"] not in current_sources:
                        current_sources.add(dup["file_origin"])
                        existing.all_sources = ", ".join(current_sources)
                        existing.source_count = (existing.source_count or 1) + 1
                        # Cập nhật source_weight nếu nguồn mới có chất lượng cao hơn
                        if s_weight > (existing.source_weight or 0.25):
                            existing.source_tier   = s_tier
                            existing.source_weight = s_weight

                    # Merge email, facebook, địa chỉ
                    if not existing.email and validate_email(dup["raw_email"]):
                        existing.email = dup["raw_email"].strip().lower()
                    new_fb_uid  = dup.get("raw_fb_uid") or dup.get("facebook_uid")
                    new_fb_link = dup.get("raw_fb_link") or dup.get("facebook_link")
                    if not existing.facebook_uid  and new_fb_uid:  existing.facebook_uid  = new_fb_uid
                    if not existing.facebook_link and new_fb_link: existing.facebook_link = new_fb_link
                    new_addr = str(dup.get("raw_address", "")).strip()
                    if new_addr and len(new_addr) > len(existing.dia_chi or ""):
                        existing.dia_chi = new_addr

            try:
                db.commit()
            except Exception as e:
                db.rollback()
                log.error(f"Lỗi merge/commit: {e}")

        all_rejected_data.extend(file_res.rejected_data)
        
        # --- Lưu trữ file sau khi xử lý ---
        try:
            dest_path = processed_dir / file_path.name
            # Nếu file đã tồn tại ở đích (trùng tên), thêm timestamp vào tên file
            if dest_path.exists():
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                dest_path = processed_dir / f"{file_path.stem}_{timestamp}{file_path.suffix}"
            
            shutil.move(str(file_path), str(dest_path))
            # log.debug(f"  -> Archiving: {dest_path.name}")
        except Exception as e:
            log.error(f"  !! Lỗi khi lưu trữ file {file_path.name}: {e}")
            
    # --- XUẤT BÁO CÁO TỔNG HỢP (Lấy từ DB để map đúng toàn bộ) ---
    final_dir = Path(data_dir).parent / "final"
    final_dir.mkdir(parents=True, exist_ok=True)
    json_path = final_dir / "processed_leads.json"
    excel_path = final_dir / "processed_leads.xlsx"
    
    log.info("--- Đang xuất báo cáo tổng hợp từ Database ---")
    all_contacts = db.query(CleanContact).all()
    db.close()
    
    all_cleaned_data = []
    for c in all_contacts:
        all_cleaned_data.append({
            "name": c.ho_ten, "phone": c.so_dien_thoai, "email": c.email,
            "address": c.dia_chi, "province": extract_province(c.dia_chi, c.file_source),
            "source": c.nguon, "note": c.ghi_chu, "file_origin": c.file_source
        })

    log.info("=" * 60)
    log.info("KẾT QUẢ XỬ LÝ DỮ LIỆU:")
    log.info(f"  - Tổng số file:      {overall_stats['total_files']}")
    log.info(f"  - Tổng số dòng:      {format_number(overall_stats['total_rows_scanned'])}")
    log.info(f"  - Lead hợp lệ:       {format_number(overall_stats['valid_leads'])}")
    log.info(f"  - Lead bị trùng:     {format_number(overall_stats['duplicate_count'])}")
    log.info(f"  - Thiếu SĐT/Email:   {format_number(overall_stats['missing_phone_email'])}")
    log.info("=" * 60)
    
    # Kết quả trả về
    report = {
        "summary": overall_stats,
        "sample_data": all_cleaned_data[:10]  # Trả về mẫu 10 dòng
    }
    
    if not files and not all_cleaned_data:
        log.warning("Không tìm thấy dữ liệu mới và không có dữ liệu cũ. Kết thúc.")
        return {"summary": overall_stats, "sample_data": []}
    
    # Lưu kết quả ra file JSON
    if all_cleaned_data:
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(all_cleaned_data, f, ensure_ascii=False, indent=2)
        
    # Lưu kết quả ra file Excel (hoặc CSV nếu > 1M dòng)
    excel_path = final_dir / "processed_leads.xlsx"
    csv_path = final_dir / "processed_leads.csv"
    if all_cleaned_data:
        df_final = pd.DataFrame(all_cleaned_data)
        # Reorder columns to match schema
        cols = ["name", "phone", "email", "address", "province", "source", "campaign", "date", "note", "file_origin"]
        # Chỉ lấy những cột có trong schema chuẩn
        df_final = df_final[[c for c in cols if c in df_final.columns]]
        
        if len(df_final) <= 1048576:
            df_final.to_excel(excel_path, index=False)
            log.info(f"   - EXCEL: {excel_path}")
        else:
            df_final.to_csv(csv_path, index=False, encoding='utf-8-sig')
            log.info(f"   - CSV (Do vượt giới hạn Excel): {csv_path}")
    
    # Lưu tệp Lead bị loại (Rejected - Lưu ra CSV vì số lượng rất lớn > 2 triệu dòng)
    if all_rejected_data:
        df_rejected = pd.DataFrame(all_rejected_data)
        # Thêm timestamp vào file rejected để không mất log cũ
        timestamp = datetime.now().strftime("%Y%m%d_%H%M")
        rejected_file_path = final_dir / f"rejected_leads_{timestamp}.csv"
        df_rejected.to_csv(rejected_file_path, index=False, encoding='utf-8-sig')
        log.info(f"   - REJECTED: {rejected_file_path} ({len(all_rejected_data)} dòng)")
        
    if overall_stats["unclassified_count"] > 0:
        log.warning(f"⚠️ CẢNH BÁO: Có {format_number(overall_stats['unclassified_count'])} lead không thể tự động phân loại Tỉnh/Thành.")
        log.warning(f"  -> Bạn có thể gom lọc cột 'province' = 'Unknown' trong file processed_leads.xlsx để thiết lập lại.")

    log.info(f"✅ Đã lưu {len(all_cleaned_data)} lead (Tổng cộng) vào:")
    log.info(f"   - JSON:  {json_path}")
    log.info(f"   - EXCEL: {excel_path}")
    return report

if __name__ == "__main__":
    # Đọc từ env hoặc dùng đường dẫn chuẩn của project
    DATA_PATH = os.getenv("RAW_DATA_DIR", str(Path(__file__).parent.parent.parent / "data" / "raw"))
    if not os.path.exists(DATA_PATH):
        os.makedirs(DATA_PATH, exist_ok=True)
        log.warning(f"Thư mục {DATA_PATH} trống. Hãy copy file vào đây.")
    else:
        results = run_ingestion(DATA_PATH)
        # In bảng mẫu hoặc kết quả JSON theo yêu cầu
        # print(json.dumps(results, indent=2, ensure_ascii=False))
