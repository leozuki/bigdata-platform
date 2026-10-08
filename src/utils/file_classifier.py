"""
File Classifier — Phân loại 8 tier cho raw data files
Dựa trên pattern matching tên file.
"""
import re
from pathlib import Path

# ══════════════════════════════════════════════════════
# SOURCE TIER DEFINITIONS (Weight 0.25 → 1.00)
# ══════════════════════════════════════════════════════

SOURCE_TIERS = {
    "banking_vip": {
        "weight": 1.00,
        "label": "Ngan hang VIP",
        "icon": "🏦",
        "patterns": [
            r"(HSBC|ACB|VCB|VIB|Techcombank|BIDV|Sacombank|MBBank|VPBank|Ocb|Msb|TPBank)",
            r"(tiet[_\s\-]?kiem|tiet\.?kiem)",
            r"(co[_\s]?dong|co[_\s]?tuc|chia[_\s]?co[_\s]?tuc)",
            r"(ngan[_\s]?hang|banking).*(vip|cao[_\s]?cap|elite|priority)",
            r"ANZ|LienViet|SeABank|MaritimeBank|BaoViet|VietBank|Manulife|MNL|Chubb|AIA|Prudential",
            r"(private[_\s]?banking|priority[_\s]?banking)",
        ],
    },
    "real_estate_vip": {
        "weight": 0.95,
        "label": "BDS Cao Cap",
        "icon": "🏙️",
        "patterns": [
            r"Vinhomes|Novaland|NovaWorld|Masteri|HAGL|Hoang[_\s]?Anh[_\s]?Gia[_\s]?Lai",
            r"(biet[_\s]?thu|bietthu|villa|penthouse|shophouse|duplex)",
            r"(him[_\s]?lam|saigon[_\s]?pearl|times[_\s]?city|royal[_\s]?city)",
            r"(the[_\s]?manor|the[_\s]?tresor|sky[_\s]?center|midtown|Wilton|Riverview)",
            r"(phu[_\s]?my[_\s]?hung|diamond[_\s]?island|Riviera|Ehome|Phu[_\s]?Gia|KDC)",
            r"CBRE|Savills|JLL|Colliers",
            r"(resort|nghỉ[_\s]?dưỡng|nghi[_\s]?duong).*(can[_\s]?ho|chung[_\s]?cu|biet[_\s]?thu)",
        ],
    },
    "ceo_director": {
        "weight": 0.90,
        "label": "CEO / Giam Doc",
        "icon": "👔",
        "patterns": [
            r"(giam[_\s]?doc|GiamDoc|giamDoc|Ke[_\s]?toan[_\s]?truong)",
            r"(CEO|chu[_\s]?tich|lanh[_\s]?dao|doanh[_\s]?nhan)",
            r"CLB.*(2030|YBA|SG|Dat[_\s]?Viet|doanh|lanh)",
            r"(quan[_\s]?ly[_\s]?cao|cap[_\s]?cao|c[_\-]?level)",
            r"(director|manager|president|founder|co[_\-]?founder)",
            r"(ACCA|MBA|CFA|CPA).*(list|danh|KH)",
            r"(ca[_\s]?si|nguoi[_\s]?noi[_\s]?tieng)",
        ],
    },
    "automotive_vip": {
        "weight": 0.80,
        "label": "O To Cao Cap",
        "icon": "🚗",
        "patterns": [
            r"(BMW|Mercedes|Lexus|Land[_\s]?Rover|Audi|Porsche|Bentley|Ferrari|Maserati)",
            r"(xe[_\s]?sang|xe[_\s]?vip|xe[_\s]?cao[_\s]?cap|luxury[_\s]?car)",
            r"(TOYOTA|FORD|HONDA).*(giam[_\s]?doc|vip|private|cao[_\s]?cap)",
        ],
    },
    "stock_gold": {
        "weight": 0.80,
        "label": "Chung Khoan / Vang",
        "icon": "📈",
        "patterns": [
            r"(chung[_\s]?khoan|ChungKhoan|co[_\s]?phieu|coPhieu)",
            r"(HOSE|HNX|UPCOM|VN-?Index)",
            r"(san[_\s]?vang|vang[_\s]?vat[_\s]?chat|dau[_\s]?tu[_\s]?vang)",
            r"(VGB|NDT|nha[_\s]?dau[_\s]?tu|quỹ[_\s]?đầu[_\s]?tư)",
            r"(SSI|VPS|VCSC|Dragon[_\s]?Capital|VinaCapital|HSC|TVSI|vndirect|MBS)",
        ],
    },
    "fitness_health": {
        "weight": 0.65,
        "label": "Fitness / Suc Khoe",
        "icon": "💪",
        "patterns": [
            r"(gym|fitness|yoga|pilates|zumba|Golf)",
            r"(25[_\s]?FIT|King[_\s]?Fitness|California|Crunch|Anytime)",
            r"(InBody|The[_\s]?Gym|Chivas|Citimart[_\s]?Health)",
            r"(spa|tham[_\s]?my|tham\.?my|sac[_\s]?dep|beauty|skincare)",
            r"(benh[_\s]?vien|hospital).*(vip|quoc[_\s]?te|international|FV|Vinmec|Hong[_\s]?Ngoc)",
        ],
    },
    "education_hr": {
        "weight": 0.50,
        "label": "Giao duc / HR",
        "icon": "🎓",
        "patterns": [
            r"(Vietnamwork|TimViecNhanh|CareerBuilder|TopCV)",
            r"(tuyen[_\s]?dung|tuyendung|nhan[_\s]?su|nhanSu)",
            r"(PACE|hoc[_\s]?vien|DH|dai[_\s]?hoc|truong[_\s]?dai[_\s]?hoc)",
            r"(ung[_\s]?vien|ungvien|chung[_\s]?chi|certificate)",
            r"(du[_\s]?hoc|study[_\s]?abroad|ielts|toefl|GMAT)",
        ],
    },
    "telecom_mass": {
        "weight": 0.40,
        "label": "Thue Bao Vien Thong",
        "icon": "📱",
        "patterns": [
            r"(Viettel|Mobifone|Vinaphone|Vietnamobile|Gmobile|Reddi)",
            r"(thue[_\s]?bao|thuebao|tra[_\s]?sau|trasau|sim[_\s]?data)",
            r"(MOBI|VINA|VIET|VTT).*(TPHCM|HCM|HN|HaNoi|QB|DN|TP)",
            r"(dien[_\s]?thoai|smartphone).*(kh|danh[_\s]?sach|list)",
        ],
    },
}

DEFAULT_TIER = {"weight": 0.25, "label": "Chua Phan Loai", "icon": "❓"}


# ══════════════════════════════════════════════════════
# CLASSIFIER FUNCTIONS
# ══════════════════════════════════════════════════════

def classify_file(filename: str) -> dict:
    """
    Phân loại 1 file dựa trên tên.
    Returns: {tier_key, weight, label, icon, confidence, matched_patterns}
    """
    best_match  = None
    best_weight = 0.0
    match_count = 0
    matched_pats = []

    for tier_key, cfg in SOURCE_TIERS.items():
        tier_matches = []
        for pattern in cfg["patterns"]:
            if re.search(pattern, filename, re.IGNORECASE):
                tier_matches.append(pattern)

        n = len(tier_matches)
        if n > 0 and cfg["weight"] > best_weight:
            best_match   = tier_key
            best_weight  = cfg["weight"]
            match_count  = n
            matched_pats = tier_matches

    if best_match:
        confidence = round(min(0.70 + (match_count - 1) * 0.15, 1.0), 2)
        return {
            "tier_key":        best_match,
            "weight":          SOURCE_TIERS[best_match]["weight"],
            "label":           SOURCE_TIERS[best_match]["label"],
            "icon":            SOURCE_TIERS[best_match]["icon"],
            "confidence":      confidence,
            "matched_patterns": len(matched_pats),
        }

    return {
        "tier_key":        "unknown",
        "weight":          DEFAULT_TIER["weight"],
        "label":           DEFAULT_TIER["label"],
        "icon":            DEFAULT_TIER["icon"],
        "confidence":      0.0,
        "matched_patterns": 0,
    }


def bulk_classify(directory: str) -> list:
    """Classify all files in a directory."""
    results = []
    for f in Path(directory).glob("*.*"):
        if f.is_file():
            cls = classify_file(f.name)
            results.append({
                "filename": f.name,
                "size_mb":  round(f.stat().st_size / 1024**2, 2),
                **cls,
            })
    return sorted(results, key=lambda r: (-r["weight"], r["filename"]))
