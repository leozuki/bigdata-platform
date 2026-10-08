"""
generate_sample_data.py — Tạo dữ liệu mẫu để test pipeline
Tạo 50 file CSV với tổng ~10,000 bản ghi liên hệ giả
"""
import sys
import os
import random
import csv
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))

# ─── Dữ liệu mẫu Việt Nam ────────────────────────────────────────────────────

HO = ["Nguyễn", "Trần", "Lê", "Phạm", "Hoàng", "Vũ", "Đặng", "Bùi", "Đỗ", "Hồ",
      "Ngô", "Dương", "Lý", "Đinh", "Phan", "Võ", "Trịnh", "Tô", "Thái", "Châu"]
TEN_DEM_NAM = ["Văn", "Hữu", "Đức", "Công", "Thế", "Minh", "Quang", "Anh", "Tuấn", "Bá"]
TEN_DEM_NU  = ["Thị", "Ngọc", "Thanh", "Thúy", "Hương", "Thu", "Hiền", "Mai", "Lan", "Hoa"]
TEN_NAM = ["An", "Bình", "Cường", "Dũng", "Đạt", "Hùng", "Khoa", "Long", "Minh", "Nam",
           "Phong", "Quân", "Sơn", "Tâm", "Tuấn", "Vinh", "Khải", "Hải", "Thắng", "Tùng"]
TEN_NU  = ["Anh", "Bình", "Chi", "Dung", "Hà", "Lan", "Linh", "Nga", "Nhung", "Oanh",
           "Phương", "Quyên", "Thảo", "Trang", "Vân", "Xuân", "Yên", "Ly", "Hằng", "Nhi"]

TINH_THANH = ["Hà Nội", "TP.HCM", "Đà Nẵng", "Hải Phòng", "Cần Thơ", "Bình Dương",
               "Đồng Nai", "Khánh Hòa", "Bà Rịa - Vũng Tàu", "Hưng Yên", "Bắc Ninh"]

NGUON = ["Facebook Ads", "Google Ads", "Zalo OA", "Giới thiệu", "Hội chợ BĐS",
         "Sự kiện mở bán", "Truyền thông", "Cộng tác viên", "Website", "Khác"]

EMAIL_DOMAINS = ["gmail.com", "yahoo.com", "hotmail.com", "outlook.com"]

# Đầu số di động hợp lệ
PREFIXES = ["032", "033", "036", "038", "039", "070", "076", "077", "079",
            "081", "082", "083", "084", "085", "086", "088", "089",
            "090", "091", "093", "096", "097", "098"]

# Cột header đa dạng (giả lập nhiều nguồn file khác nhau)
COLUMN_SETS = [
    ["Họ Tên", "Số ĐT", "Email", "Địa Chỉ", "Nguồn", "Ghi Chú"],
    ["ho ten", "sdt", "email", "dia chi", "nguon", "note"],
    ["Name", "Phone", "Email", "Address", "Source"],
    ["KHÁCH HÀNG", "ĐIỆN THOẠI", "EMAIL", "TỈNH/THÀNH"],
    ["họ và tên", "số điện thoại", "email", "nguồn dữ liệu"],
    ["full_name", "mobile", "email", "location", "channel"],
    ["Tên", "SĐT", "Email"],
]


def random_phone(invalid_chance: float = 0.15) -> str:
    """Tạo SĐT ngẫu nhiên, với 15% là không hợp lệ"""
    if random.random() < invalid_chance:
        # Tạo số bàn hoặc số không hợp lệ
        invalid_types = [
            f"024{random.randint(1000000, 9999999)}",     # Số bàn Hà Nội
            f"028{random.randint(1000000, 9999999)}",     # Số bàn HCM
            f"01{random.randint(100000000, 999999999)}",  # Đầu số cũ
            f"{random.randint(100, 999)}{random.randint(1000000, 9999999)}",
        ]
        return random.choice(invalid_types)

    prefix = random.choice(PREFIXES)
    suffix = "".join([str(random.randint(0, 9)) for _ in range(7)])

    # Đôi khi thêm định dạng lạ
    phone = prefix + suffix
    fmt = random.choice(["normal", "84prefix", "spaced", "dashed"])
    if fmt == "84prefix":
        return "84" + phone[1:]
    elif fmt == "spaced":
        return f"{phone[:4]} {phone[4:7]} {phone[7:]}"
    elif fmt == "dashed":
        return f"{phone[:4]}-{phone[4:7]}-{phone[7:]}"
    return phone


def random_name() -> str:
    ho = random.choice(HO)
    is_male = random.random() > 0.45
    if is_male:
        ten_dem = random.choice(TEN_DEM_NAM)
        ten = random.choice(TEN_NAM)
    else:
        ten_dem = random.choice(TEN_DEM_NU)
        ten = random.choice(TEN_NU)
    return f"{ho} {ten_dem} {ten}"


def random_email(name: str) -> str | None:
    if random.random() < 0.4:  # 40% có email
        slug = name.lower().replace(" ", "").replace("đ", "d")
        slug = ''.join(c for c in slug if c.isalpha())
        num = random.randint(1, 999)
        domain = random.choice(EMAIL_DOMAINS)
        return f"{slug}{num}@{domain}"
    return None


def generate_contacts(n: int) -> list[dict]:
    """Tạo n bản ghi liên hệ giả"""
    records = []
    # Tạo pool SĐT để đảm bảo có một số trùng lặp
    phone_pool = [random_phone() for _ in range(int(n * 0.85))]

    for _ in range(n):
        name = random_name()
        # 30% lấy lại từ pool (tạo duplicate)
        phone = random.choice(phone_pool) if random.random() < 0.3 else random_phone()
        email = random_email(name)
        tinh = random.choice(TINH_THANH)
        nguon = random.choice(NGUON)
        days_ago = random.randint(0, 365)
        date_str = (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%d")

        records.append({
            "name":    name,
            "phone":   phone,
            "email":   email or "",
            "address": tinh,
            "source":  nguon,
            "date":    date_str,
            "note":    "",
        })
    return records


def save_as_csv(records: list[dict], filepath: Path, column_set: list[str]):
    """Lưu records thành CSV với tên cột ngẫu nhiên"""
    col_map = {
        "name":    column_set[0] if len(column_set) > 0 else "name",
        "phone":   column_set[1] if len(column_set) > 1 else "phone",
        "email":   column_set[2] if len(column_set) > 2 else "email",
        "address": column_set[3] if len(column_set) > 3 else "address",
        "source":  column_set[4] if len(column_set) > 4 else "source",
        "date":    column_set[5] if len(column_set) > 5 else "date",
    }

    used_keys = list(col_map.keys())[:len(column_set)]

    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=[col_map[k] for k in used_keys])
        writer.writeheader()
        for rec in records:
            row = {col_map[k]: rec[k] for k in used_keys}
            writer.writerow(row)


def main():
    raw_dir = Path(os.getenv(
        "RAW_DATA_DIR",
        str(Path(__file__).parent.parent / "data" / "raw")
    ))
    raw_dir.mkdir(parents=True, exist_ok=True)

    print("[*] Dang tao du lieu mau...")
    total_records = 0
    num_files = 50

    for i in range(1, num_files + 1):
        # Số lượng bản ghi ngẫu nhiên 50-400 mỗi file
        n = random.randint(50, 400)
        records = generate_contacts(n)

        # Chọn format cột ngẫu nhiên
        col_set = random.choice(COLUMN_SETS)

        # Tạo tên file đa dạng
        prefixes_file = ["khachhang", "danhmuc", "contact", "leads", "data", "bds", "kh"]
        file_name = f"{random.choice(prefixes_file)}_{i:03d}_{random.randint(2023,2025)}.csv"
        filepath = raw_dir / file_name

        save_as_csv(records, filepath, col_set)
        total_records += n
        print(f"  [{i:2d}/{num_files}] {file_name} -- {n} ban ghi")

    print(f"\n[OK] Da tao {num_files} file CSV voi {total_records:,} ban ghi")
    print(f"     Thu muc: {raw_dir}")
    print(f"\n     Buoc tiep theo: python main.py --phase all")


if __name__ == "__main__":
    main()
