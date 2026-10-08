"""
utils.py — Helpers dùng chung: logging, config, phone validation
"""
import re
import os
import logging
from pathlib import Path
from datetime import datetime


def setup_logger(name: str, level=logging.INFO) -> logging.Logger:
    """Tạo logger có màu sắc cho console"""
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(level)
    handler = logging.StreamHandler()
    handler.setLevel(level)

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        datefmt="%H:%M:%S"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger


log = setup_logger("bds_pipeline")


# ─── Phone Number Utilities ───────────────────────────────────────────────────

# Đầu số di động hợp lệ tại Việt Nam (theo nghị định mới nhất)
VALID_MOBILE_PREFIXES = {
    "032", "033", "034", "035", "036", "037", "038", "039",  # Viettel
    "056", "058",                                              # Vietnamobile
    "059",                                                     # Gmobile
    "070", "076", "077", "078", "079",                        # Mobifone
    "081", "082", "083", "084", "085",                        # Vinaphone
    "086",                                                     # Viettel
    "088", "089",                                             # Vinaphone
    "090", "093",                                             # Mobifone
    "091", "094",                                             # Vinaphone
    "092",                                                     # Vietnamobile
    "096", "097", "098",                                      # Viettel
    "099",                                                     # Gmobile
}


def clean_phone_number(phone: str) -> str | None:
    """
    Chuẩn hóa số điện thoại về định dạng +84xxxxxxxxx.
    Trả về None nếu số không hợp lệ.

    Xử lý các định dạng:
      - 0912345678   → +84912345678
      - 84912345678  → +84912345678
      - +84912345678 → +84912345678
      - 912345678    → +84912345678 (9 chữ số, thiếu số 0)
    """
    if not phone or not isinstance(phone, (str, int, float)):
        return None

    # Xử lý trường hợp Excel để dạng float/scientific notation (VD: 9.74E+08)
    phone_str = str(phone).strip()
    if 'e' in phone_str.lower() or '.' in phone_str:
        try:
            # Chuyển về số nguyên rồi mới lấy string để mất phần .0 hoặc E+
            phone_str = str(int(float(phone_str)))
        except (ValueError, TypeError):
            pass

    # Loại bỏ tất cả ký tự không phải số và dấu + (Xử lý cả dấu phẩy, dấu chấm ngăn cách)
    raw = re.sub(r"[^\d+]", "", phone_str)

    # Bỏ dấu + đầu nếu có để xử lý thuần số
    if raw.startswith("+"):
        raw = raw[1:]

    # Từ +84... hoặc 84... → chuẩn hóa về 0...
    if raw.startswith("84") and len(raw) == 11:
        raw = "0" + raw[2:]
    # 9 chữ số (thiếu số 0 đầu)
    elif len(raw) == 9:
        raw = "0" + raw

    # Kiểm tra: phải là 10 chữ số bắt đầu bằng 0
    if not re.match(r"^0\d{9}$", raw):
        return None

    # Kiểm tra đầu số hợp lệ (di động, không phải máy bàn)
    prefix = raw[:3]
    if prefix not in VALID_MOBILE_PREFIXES:
        return None

    # Chuyển về format +84
    return "+84" + raw[1:]


def normalize_phone_vn(phone: str) -> str | None:
    """
    Chuẩn hóa số điện thoại về định dạng 0xxxxxxxxx (10 chữ số).
    Dùng cho các báo cáo nội bộ cần format 0 đầu.
    """
    cleaned = clean_phone_number(phone)
    if not cleaned:
        return None
    # +84912345678 -> 0912345678
    return "0" + cleaned[3:]


def validate_email(email: str) -> bool:
    """Kiểm tra định dạng email cơ bản"""
    if not email or not isinstance(email, str):
        return False
    pattern = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
    return bool(re.match(pattern, email.strip()))


def is_valid_mobile(phone: str) -> bool:
    """Kiểm tra nhanh SĐT có hợp lệ không"""
    return clean_phone_number(phone) is not None


def extract_phones_from_text(text: str) -> list[str]:
    """
    Trích xuất tất cả số điện thoại từ một đoạn văn bản.
    Sử dụng cho Google scraping.
    """
    if not text:
        return []

    # Pattern rộng để bắt nhiều định dạng
    pattern = r"""
        (?:
            (?:\+84|0084|84)?   # Mã quốc gia tùy chọn
            [3-9]\d{8}          # 9 chữ số sau (không kể mã QG)
            |
            0[3-9]\d{8}         # Format 0xxx... 10 chữ số
        )
    """
    raw_phones = re.findall(pattern, text.replace("-", "").replace(" ", ""), re.VERBOSE)

    valid = []
    for p in raw_phones:
        cleaned = clean_phone_number(p)
        if cleaned and cleaned not in valid:
            valid.append(cleaned)
    return valid


# ─── Classification Utilities ────────────────────────────────────────────────

VIETNAM_PROVINCES = [
    "Hà Nội", "Hồ Chí Minh", "HCM", "Sài Gòn", "Đà Nẵng", "Hải Phòng", "Cần Thơ",
    "Bình Dương", "Đồng Nai", "Bà Rịa", "Vũng Tàu", "Khánh Hòa", "Nha Trang",
    "Quảng Ninh", "Tây Ninh", "Bình Phước", "Long An", "Tiền Giang", "Bến Tre",
    "Trà Vinh", "Vĩnh Long", "Đồng Tháp", "An Giang", "Kiên Giang", "Cà Mau",
    "Bạc Liêu", "Sóc Trăng", "Hậu Giang", "Lâm Đồng", "Đà Lạt", "Đắk Lắk",
    "Buôn Ma Thuột", "Đắk Nông", "Gia Lai", "Pleiku", "Kon Tum", "Phú Yên",
    "Bình Định", "Quy Nhơn", "Quảng Ngãi", "Quảng Nam", "Thừa Thiên Huế", "Huế",
    "Quảng Trị", "Quảng Bình", "Hà Tĩnh", "Nghệ An", "Vinh", "Thanh Hóa",
    "Ninh Bình", "Nam Định", "Thái Bình", "Hà Nam", "Hưng Yên", "Hải Dương",
    "Bắc Ninh", "Vĩnh Phúc", "Bắc Giang", "Thái Nguyên", "Phú Thọ", "Tuyên Quang",
    "Hà Giang", "Cao Bằng", "Bắc Kạn", "Lạng Sơn", "Hòa Bình", "Sơn La",
    "Điện Biên", "Lai Châu", "Lào Cai", "Yên Bái"
]

def extract_province(address: str, filename: str) -> str:
    """Trích xuất tự động tỉnh thành từ chuỗi địa chỉ và tên file gốc."""
    text = f"{address} {filename}".lower()
    
    # Ưu tiên các từ khóa phổ biến
    if "sg" in text or "ho chi minh" in text or "hcm" in text or "sài gòn" in text:
        return "TP. Hồ Chí Minh"
    if "hn" in text or "ha noi" in text or "hà nội" in text:
        return "Hà Nội"
    if "đn" in text or "da nang" in text or "đà nẵng" in text:
        return "Đà Nẵng"
        
    for prov in VIETNAM_PROVINCES:
        if prov.lower() in text:
            if prov == "Nha Trang": return "Khánh Hòa"
            if prov == "Vũng Tàu": return "Bà Rịa - Vũng Tàu"
            if prov == "Đà Lạt": return "Lâm Đồng"
            if prov == "Buôn Ma Thuột": return "Đắk Lắk"
            if prov == "Pleiku": return "Gia Lai"
            if prov == "Quy Nhơn": return "Bình Định"
            if prov == "Vinh": return "Nghệ An"
            if prov == "Huế": return "Thừa Thiên Huế"
            if prov == "Bà Rịa": return "Bà Rịa - Vũng Tàu"
            return prov
            
    return "Unknown"

# ─── File & Directory Utilities ───────────────────────────────────────────────

def get_all_data_files(directory: str, extensions=(".xlsx", ".xls", ".csv", ".txt", ".doc", ".docx")) -> list[Path]:
    """Quét đệ quy tất cả file data trong thư mục (Không phân biệt hoa thường)"""
    base = Path(directory)
    files = []
    ext_lower = [e.lower() for e in extensions]
    
    # Duyệt qua tất cả file và kiểm tra extension
    if base.exists():
        for item in base.rglob("*"):
            if item.is_file() and item.suffix.lower() in ext_lower:
                files.append(item)
    return sorted(files)


def format_number(n: int) -> str:
    """Format số có dấu phẩy: 1000000 → 1,000,000"""
    return f"{n:,}"


def now_str() -> str:
    """Timestamp hiện tại dạng string"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ─── Province from Phone Prefix ──────────────────────────────────────────────

# Chỉ landline (028xx) mới xác định được tỉnh thành.
# Mobile (09x, 03x, 07x...) → không xác định được province.
PHONE_PREFIX_PROVINCE: dict[str, str] = {
    # HCM & vùng miền Nam
    "028":  "TP. Ho Chi Minh",
    "0272": "Long An",
    "0273": "Tien Giang",
    "0275": "Dong Thap",
    "0270": "Vinh Long",
    "0292": "Can Tho",
    "0290": "An Giang",
    "0297": "Kien Giang",
    "0293": "Soc Trang",
    "0291": "Ben Tre",
    "0296": "Tra Vinh",
    "0295": "Bac Lieu",
    "0290": "Ca Mau",
    "0294": "Hau Giang",
    # Mien Dong Nam Bo
    "0251": "Dong Nai",
    "0254": "Ba Ria - Vung Tau",
    "0274": "Binh Duong",
    "0271": "Binh Phuoc",
    "0276": "Tay Ninh",
    # Ha Noi & Mien Bac
    "024":  "Ha Noi",
    "0225": "Hai Phong",
    "0220": "Quang Ninh",
    "0221": "Hai Duong",
    "0222": "Bac Ninh",
    "0226": "Hung Yen",
    "0227": "Ha Nam",
    "0228": "Nam Dinh",
    "0229": "Ninh Binh",
    "0232": "Quang Nam",
    "0233": "Thai Binh",
    # Mien Trung
    "0236": "Da Nang",
    "0234": "Thua Thien Hue",
    "0235": "Quang Nam",
    "0255": "Quang Ngai",
    "0256": "Binh Dinh",
    "0257": "Phu Yen",
    "0258": "Khanh Hoa",
    "0259": "Ninh Thuan",
    "0252": "Binh Thuan",
    # Tay Nguyen
    "0263": "Lam Dong",
    "0261": "Gia Lai",
    "0262": "Dak Lak",
    "0260": "Kon Tum",
    "0261": "Dak Nong",
}


def province_from_phone(phone: str) -> str:
    """
    Trích xuất tỉnh thành từ đầu số điện thoại bàn.
    Chỉ hoạt động với số cố định (không phải mobile).

    Args:
        phone: Số điện thoại (bất kỳ format)

    Returns:
        Tên tỉnh thành hoặc "Unknown" nếu không xác định được
    """
    if not phone:
        return "Unknown"

    raw = str(phone).strip()
    # Normalize: bỏ +84 hoặc 84 prefix
    raw = re.sub(r"[^\d]", "", raw)
    if raw.startswith("84") and len(raw) == 11:
        raw = "0" + raw[2:]
    if not raw.startswith("0"):
        raw = "0" + raw

    # Try 4-digit prefix first (more specific), then 3-digit
    for prefix_len in [4, 3]:
        prefix = raw[:prefix_len]
        if prefix in PHONE_PREFIX_PROVINCE:
            return PHONE_PREFIX_PROVINCE[prefix]

    return "Unknown"  # Mobile prefix → cannot determine province


# ─── Vectorized Phone Normalization ──────────────────────────────────────────

def normalize_phone_series(series):
    """
    Vectorized phone normalization cho Pandas Series.
    50-100x nhanh hơn iterrows() + clean_phone_number().

    Xử lý: 0xxx, 84xxx, +84xxx, scientific notation.
    Returns: pd.Series với phone chuẩn format '0xxxxxxxxx' hoặc None nếu invalid.
    """
    try:
        import pandas as pd
    except ImportError:
        raise ImportError("pandas is required for normalize_phone_series()")

    # Convert to string, fill NaN
    s = series.fillna("").astype(str).str.strip()

    # Handle scientific notation: 9.74E+08 → 974000000
    sci_mask = s.str.contains(r"[Ee][+\-]\d+", regex=True)
    if sci_mask.any():
        def _fix_sci(x):
            try:
                return str(int(float(x)))
            except (ValueError, TypeError):
                return x
        s = s.copy()
        s[sci_mask] = s[sci_mask].apply(_fix_sci)

    # Strip non-numeric except leading +
    s = s.str.replace(r"[^\d+]", "", regex=True)

    # Remove leading +
    s = s.str.replace(r"^\+", "", regex=True)

    # 84xxxxxxxxx (11 digits) → 0xxxxxxxxx
    mask_84 = s.str.match(r"^84\d{9}$")
    s = s.copy()
    s[mask_84] = "0" + s[mask_84].str[2:]

    # 9 digits (missing leading 0): 9xxxxxxxx → 09xxxxxxxx
    mask_9 = s.str.match(r"^[3-9]\d{8}$")
    s[mask_9] = "0" + s[mask_9]

    # Validate: 10 digits, starts with 0, valid prefix
    valid_format = s.str.match(r"^0[3-9]\d{8}$")
    s[~valid_format] = None

    return s


if __name__ == "__main__":
    # Test phone cleaning
    test_phones = [
        "0912345678", "84912345678", "+84912345678",
        "912345678",  # 9 số
        "0281234567",  # Máy bàn
        "01234567890", # Sai định dạng
        "090 1234 567",
        "0961 234 567",
    ]
    print("=== PHONE CLEANING TEST ===")
    for p in test_phones:
        result = clean_phone_number(p)
        status = "✓" if result else "✗"
        print(f"  {status}  {p:<20} → {result or 'INVALID'}")
