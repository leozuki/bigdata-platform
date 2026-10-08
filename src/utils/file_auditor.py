import os
import shutil
import pandas as pd
from pathlib import Path
from datetime import datetime

def audit_files():
    base_dir = Path(os.getenv(
        "RAW_DATA_DIR",
        str(Path(__file__).parent.parent.parent / "data" / "raw")
    )).parent
    raw_dir = base_dir / "raw"
    processed_dir = base_dir / "processed"
    pending_dir = base_dir / "standardization_pending" / "meaningless_names"
    
    os.makedirs(pending_dir, exist_ok=True)
    
    # Enhanced Categories based on Vietnamese business data
    CATEGORIES = {
        "Doanh nhân / CLB / Quản lý": ["doanh nhan", "cap cao", "quan ly", "ceo", "yba", "2030", "clb", "phong thuong mai", "chu doanh nghiep", "lanh dao", "founder", "giam doc"],
        "BĐS / Dự án cao cấp": ["vinhomes", "bds", "him lam", "phu my hung", "lakeview", "sunrise", "ghv", "chung cu", "dat nen", "biet thu", "nha pho", "park", "eco", "novaland"],
        "Tài chính / Vip Bank": ["tiet kiem", "ngan hang", "bank", "credit", "uu tien", "the tin dung", "sacom", "techcom", "vpb", "vib", "vay", "tai chinh"],
        "Sức khỏe / Siêu giàu / Golf": ["golf", "inbody", "fitness", "gym", "yoga", "california", "diamond", "gold", "platinum"],
        "Định danh / Facebook API": ["uid", "fb", "facebook", "profile", "link", "id", "convert"],
        "Việc làm / Giáo dục": ["vietnamwork", "tuyen dung", "job", "hr", "du hoc", "giao duc"],
    }
    
    # Stricter meaningless patterns
    MEANINGLESS_PATTERNS = [
        "data", "sheet", "book", "file", "copy of", "ban sao", "test", "new microsoft", "untitled", "123", "abc", 
        "final", "final2", "fix", "updated"
    ]

    report_data = []
    meaningless_count = 0
    
    # Scan both directories
    for search_dir in [raw_dir, processed_dir]:
        if not search_dir.exists(): continue
        
        for file_path in search_dir.glob("**/*.*"):
            if file_path.suffix.lower() not in ['.xlsx', '.xls', '.csv', '.txt']:
                continue
            
            fname = file_path.name.lower()
            category = "Chưa phân loại"
            is_meaningless = False
            
            # 1. Check for category
            for cat, keywords in CATEGORIES.items():
                if any(k in fname for k in keywords):
                    category = cat
                    break
            
            # 2. Check if meaningless (if not clearly categorized)
            if category == "Chưa phân loại":
                # Check for generic patterns
                if any(p in fname for p in MEANINGLESS_PATTERNS):
                    is_meaningless = True
                # Check for short or numeric-only names
                name_stem = file_path.stem
                if len(name_stem) <= 3 or name_stem.isdigit():
                    is_meaningless = True
                
            # 3. Handle meaningless files
            if is_meaningless:
                try:
                    # Move to pending folder
                    dest_path = pending_dir / file_path.name
                    # If exists, add timestamp
                    if dest_path.exists():
                        dest_path = pending_dir / f"{datetime.now().strftime('%H%M%S')}_{file_path.name}"
                    
                    shutil.move(str(file_path), str(dest_path))
                    category = "Vô nghĩa (Đã di chuyển)"
                    meaningless_count += 1
                except Exception as e:
                    print(f"Error moving {file_path.name}: {e}")

            report_data.append({
                "Filename": file_path.name,
                "Original Path": str(file_path.parent.relative_to(base_dir)),
                "Category": category,
                "Size (KB)": round(file_path.stat().st_size / 1024, 2) if file_path.exists() else 0
            })

    # Save report
    df = pd.DataFrame(report_data)
    df.to_csv(base_dir / "file_audit_report.csv", index=False, encoding='utf-8-sig')
    
    # Generate Summary Markdown
    counts = df['Category'].value_counts().to_dict()
    category_summary = "\n".join([f"- **{cat}:** {count}" for cat, count in counts.items()])

    summary = f"""# 📊 Báo cáo Kiểm toán Kho Dữ liệu (File Audit Report)
Ngày thực hiện: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}

## 📈 Thống kê chung
- **Tổng số file đã quét:** {len(report_data)}
- **Số file đã phân loại:** {len(df[df['Category'] != 'Chưa phân loại'])}
- **Số file Vô nghĩa (Đã gom nhóm):** {meaningless_count}

## 📂 Phân bổ theo Nhóm (Dựa trên tên file)
{category_summary}

## ⚠️ Hành động đã thực hiện
Toàn bộ **{meaningless_count} file** có tên không rõ ràng đã được di chuyển về thư mục:
`data/standardization_pending/meaningless_names/`

Bạn có thể truy cập thư mục này để kiểm tra và đặt lại tên chuẩn cho chúng.
"""
    with open(base_dir / "audit_summary.md", "w", encoding='utf-8') as f:
        f.write(summary)
    
    print("Audit completed. Summary saved to data/audit_summary.md")

if __name__ == "__main__":
    audit_files()
