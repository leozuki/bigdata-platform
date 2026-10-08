import sys
import os
import json
from pathlib import Path
from sqlalchemy import create_engine, or_
from sqlalchemy.orm import sessionmaker

# Setup path to import from src
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.database import CleanContact, SessionLocal

def format_score(score):
    if score >= 10: return f"💎 Siêu VIP ({score})"
    if score >= 5: return f"⭐ VIP ({score})"
    return f"👤 Tiêu chuẩn ({score})"

def lookup(phone_or_email):
    session = SessionLocal()
    query_val = phone_or_email.strip().replace(".", "").replace(" ", "")
    
    # Chuẩn hóa nếu là SĐT
    if query_val.isdigit() or query_val.startswith("+"):
        # Xóa dấu + nếu có
        if query_val.startswith("+"):
            query_val = query_val[1:]
        
        # Nếu bắt đầu bằng 84 (ví dụ 84938...) và có 11 chữ số -> chuyển về 0938...
        if query_val.startswith("84") and len(query_val) == 11:
            query_val = "0" + query_val[2:]
        # Nếu là 9 chữ số (thiếu số 0) -> thêm số 0
        elif len(query_val) == 9:
            query_val = "0" + query_val
        # Nếu đã có 10 chữ số và bắt đầu bằng 0 -> giữ nguyên
        elif len(query_val) == 10 and query_val.startswith("0"):
            pass
        # Các trường hợp khác để SQLite search tự bắt (ví dụ Name)
            
    # Search by phone or email or name (partial)
    results = session.query(CleanContact).filter(
        or_(
            CleanContact.so_dien_thoai == query_val,
            CleanContact.so_dien_thoai_goc == query_val,
            CleanContact.email == query_val.lower(),
            CleanContact.ho_ten.ilike(f"%{query_val}%")
        )
    ).all()
    
    if not results:
        print(f"\n❌ Không tìm thấy thông tin cho: {query_val}")
        return

    print(f"\n✅ Tìm thấy {len(results)} kết quả cho: {query_val}")
    print("=" * 60)
    
    for lead in results:
        print(f"👤 Họ tên:    {lead.ho_ten or 'Trống'}")
        if lead.all_names:
            print(f"📝 Tên khác:  {lead.all_names}")
            
        print(f"📞 Số ĐT:     {lead.so_dien_thoai} (Gốc: {lead.so_dien_thoai_goc or 'N/A'})")
        print(f"📧 Email:      {lead.email or 'Trống'}")
        if getattr(lead, 'facebook_uid', None):
            print(f"🆔 FB UID:    {lead.facebook_uid}")
        if getattr(lead, 'facebook_link', None):
            print(f"🔗 FB Link:   {lead.facebook_link}")
        print(f"📍 Địa chỉ:   {lead.dia_chi or 'Trống'}")
        
        # Deep Profiling info
        sources = lead.all_sources.split(",") if lead.all_sources else [lead.nguon]
        print(f"📂 Nguồn ({len(sources)}):")
        for s in sources:
            print(f"   - {s.strip()}")
            
        if lead.ghi_chu:
            print(f"💬 Ghi chú:   {lead.ghi_chu}")
            
        if lead.metadata_json:
            try:
                meta = json.loads(lead.metadata_json)
                print(f"📊 Meta:      {json.dumps(meta, indent=2, ensure_ascii=False)}")
            except:
                pass
                
        print(f"📅 Cập nhật:   {lead.cleaned_at.strftime('%d/%m/%Y %H:%M')}")
        print("-" * 60)
    
    session.close()

if __name__ == "__main__":
    print("🚀 LEAD LOOKUP ENGINE - DEEP PROFILING MODE")
    print("Bạn có thể nhập Số điện thoại, Email hoặc Họ tên để tra cứu.")
    
    if len(sys.argv) > 1:
        lookup(" ".join(sys.argv[1:]))
    else:
        while True:
            val = input("\n🔍 Nhập thông tin tra cứu (hoặc 'q' để thoát): ")
            if val.lower() == 'q':
                break
            lookup(val)
