"""
multi_account_simulator.py — Giả lập dữ liệu thực từ nhiều nguồn
=================================================================
Mô phỏng hệ sinh thái quảng cáo thực tế của một công ty BĐS lớn:

  3 Business Managers (BM):
    - BM_CORP: BM của công ty chính
    - BM_AGENCY: Agency thuê ngoài
    - BM_AGENT: Các môi giới cá nhân

  Mỗi BM có nhiều Ad Accounts (TKQC):
    - BM_CORP:   3 TKQC (HCM, HN, MiềnTrung)
    - BM_AGENCY: 2 TKQC (Agency A, Agency B)
    - BM_AGENT:  4 TKQC cá nhân

  Mỗi TKQC kết nối với 1-2 Pages:
    - 9 Fanpages tổng cộng (chuyên trang, cá nhân, nhóm dự án)

  30+ campaigns với performance phân loại rõ ràng:
    - WINNER:    CPL thấp, quality cao, đang scale
    - STABLE:    CPL trung bình, ổn định
    - DECLINING: Frequency cao, CTR giảm, cần refresh
    - POOR:      CPL cao, quality thấp, cần pause
    - TESTING:   Campaign mới, chưa có kết quả
"""
import random
import hashlib
from datetime import datetime, timedelta
from typing import Optional

# ── Seed cố định để data nhất quán ──────────────────────────────────────────
BASE_RNG = random.Random(42)

# ── Cấu trúc Business Manager ────────────────────────────────────────────────
BUSINESS_MANAGERS = {
    "bm_corp_001": {
        "name": "BM Công ty Chính — Vinhomes HCM",
        "type": "corporate",
        "accounts": ["act_corp_hcm_001", "act_corp_hn_001", "act_corp_mt_001"],
        "pages": {
            "act_corp_hcm_001": ["page_vinhomes_hcm", "page_bds_hcm_global"],
            "act_corp_hn_001":  ["page_vinhomes_hn"],
            "act_corp_mt_001":  ["page_bds_miennam"],
        }
    },
    "bm_agency_002": {
        "name": "BM Agency Quảng Cáo — Digital House",
        "type": "agency",
        "accounts": ["act_agency_a_001", "act_agency_b_001"],
        "pages": {
            "act_agency_a_001": ["page_agency_product_a", "page_bds_investment"],
            "act_agency_b_001": ["page_bds_luxury"],
        }
    },
    "bm_agent_003": {
        "name": "BM Nhóm Môi Giới Cá Nhân",
        "type": "individual",
        "accounts": ["act_agent_001", "act_agent_002", "act_agent_003", "act_agent_004"],
        "pages": {
            "act_agent_001": ["page_agent_nguyen"],
            "act_agent_002": ["page_agent_tran"],
            "act_agent_003": ["page_agent_le"],
            "act_agent_004": ["page_agent_pham"],
        }
    },
}

PAGES = {
    "page_vinhomes_hcm":    {"name": "Vinhomes TP.HCM — Chính thức", "fans": 125_000, "type": "brand"},
    "page_bds_hcm_global":  {"name": "BĐS HCM Global Investment",    "fans": 48_000,  "type": "brand"},
    "page_vinhomes_hn":     {"name": "Vinhomes Hà Nội — Official",    "fans": 87_000,  "type": "brand"},
    "page_bds_miennam":     {"name": "BĐS Miền Trung & Tây Nguyên",   "fans": 32_000,  "type": "regional"},
    "page_agency_product_a":{"name": "Dự Án Hot 2026 — Mở Bán",       "fans": 22_000,  "type": "project"},
    "page_bds_investment":  {"name": "Đầu Tư BĐS Sinh Lời Cao",       "fans": 35_000,  "type": "content"},
    "page_bds_luxury":      {"name": "Luxury Real Estate Vietnam",     "fans": 15_000,  "type": "luxury"},
    "page_agent_nguyen":    {"name": "Nguyễn Minh Tuấn — BĐS",        "fans": 8_200,   "type": "personal"},
    "page_agent_tran":      {"name": "Trần Thu Hà Realty",             "fans": 6_500,   "type": "personal"},
    "page_agent_le":        {"name": "Lê Văn Phong | BĐS Uy Tín",     "fans": 4_800,   "type": "personal"},
    "page_agent_pham":      {"name": "Phạm Đình Dũng — Đầu Tư",       "fans": 3_100,   "type": "personal"},
}

# ── Định nghĩa campaigns theo performance tier ──────────────────────────────
CAMPAIGN_TEMPLATES = [
    # TKQC corp HCM — 8 campaigns
    {"account": "act_corp_hcm_001", "bm": "bm_corp_001", "page": "page_vinhomes_hcm",
     "name": "Vinhomes Grand Park Q9 — Lead Gen 2026",     "tier": "WINNER",   "budget": 3_000_000,
     "objective": "LEAD_GENERATION", "content_type": "video_testimonial"},

    {"account": "act_corp_hcm_001", "bm": "bm_corp_001", "page": "page_vinhomes_hcm",
     "name": "The Beverly — Căn hộ Cao Cấp Retarget",      "tier": "STABLE",   "budget": 1_500_000,
     "objective": "LEAD_GENERATION", "content_type": "carousel_project"},

    {"account": "act_corp_hcm_001", "bm": "bm_corp_001", "page": "page_bds_hcm_global",
     "name": "Shophouse Vinhomes — Đầu Tư Sinh Lời",       "tier": "SCALING",  "budget": 2_000_000,
     "objective": "LEAD_GENERATION", "content_type": "image_roi"},

    {"account": "act_corp_hcm_001", "bm": "bm_corp_001", "page": "page_bds_hcm_global",
     "name": "Biệt Thự The Rainbow — LAL 3%",               "tier": "POOR",     "budget": 800_000,
     "objective": "LEAD_GENERATION", "content_type": "video_luxury"},

    {"account": "act_corp_hcm_001", "bm": "bm_corp_001", "page": "page_vinhomes_hcm",
     "name": "Sky Park — View Sông Retarget 30 ngày",       "tier": "DECLINING","budget": 600_000,
     "objective": "LEAD_GENERATION", "content_type": "image_view"},

    {"account": "act_corp_hcm_001", "bm": "bm_corp_001", "page": "page_bds_hcm_global",
     "name": "Smart City HCM — Prospecting Cold",           "tier": "TESTING",  "budget": 400_000,
     "objective": "LEAD_GENERATION", "content_type": "video_lifestyle"},

    {"account": "act_corp_hcm_001", "bm": "bm_corp_001", "page": "page_vinhomes_hcm",
     "name": "Căn Hộ Studio Giá Rẻ — Mass Market",         "tier": "WINNER",   "budget": 1_200_000,
     "objective": "LEAD_GENERATION", "content_type": "image_price"},

    {"account": "act_corp_hcm_001", "bm": "bm_corp_001", "page": "page_bds_hcm_global",
     "name": "Bàn Giao Ngay Q4 — Urgency Push",             "tier": "SCALING",  "budget": 900_000,
     "objective": "LEAD_GENERATION", "content_type": "countdown_creative"},

    # TKQC corp HN — 5 campaigns
    {"account": "act_corp_hn_001", "bm": "bm_corp_001", "page": "page_vinhomes_hn",
     "name": "Vinhomes Ocean Park 3 — Launch",              "tier": "WINNER",   "budget": 2_500_000,
     "objective": "LEAD_GENERATION", "content_type": "video_drone"},

    {"account": "act_corp_hn_001", "bm": "bm_corp_001", "page": "page_vinhomes_hn",
     "name": "Smart Home Hà Nội — Segment IT",              "tier": "STABLE",   "budget": 1_000_000,
     "objective": "LEAD_GENERATION", "content_type": "tech_creative"},

    {"account": "act_corp_hn_001", "bm": "bm_corp_001", "page": "page_vinhomes_hn",
     "name": "Đất Nền Gia Lâm — LOT Sales",                 "tier": "DECLINING","budget": 700_000,
     "objective": "LEAD_GENERATION", "content_type": "image_map"},

    {"account": "act_corp_hn_001", "bm": "bm_corp_001", "page": "page_vinhomes_hn",
     "name": "Penthouse Westlake — Ultra VIP",               "tier": "POOR",     "budget": 500_000,
     "objective": "LEAD_GENERATION", "content_type": "video_vip"},

    {"account": "act_corp_hn_001", "bm": "bm_corp_001", "page": "page_vinhomes_hn",
     "name": "Pháp Lý Rõ Ràng — Trust Campaign",            "tier": "TESTING",  "budget": 300_000,
     "objective": "LEAD_GENERATION", "content_type": "document_creative"},

    # TKQC Miền Trung — 3 campaigns
    {"account": "act_corp_mt_001", "bm": "bm_corp_001", "page": "page_bds_miennam",
     "name": "Hải Vân Bay — Nghỉ Dưỡng Đà Nẵng",           "tier": "WINNER",   "budget": 1_800_000,
     "objective": "LEAD_GENERATION", "content_type": "video_resort"},

    {"account": "act_corp_mt_001", "bm": "bm_corp_001", "page": "page_bds_miennam",
     "name": "Đà Lạt Boutique Villa — Đầu Tư",             "tier": "STABLE",   "budget": 900_000,
     "objective": "LEAD_GENERATION", "content_type": "lifestyle_creative"},

    {"account": "act_corp_mt_001", "bm": "bm_corp_001", "page": "page_bds_miennam",
     "name": "Nha Trang Beachfront — Retarget IG",          "tier": "DECLINING","budget": 400_000,
     "objective": "LEAD_GENERATION", "content_type": "story_beach"},

    # Agency A — 5 campaigns
    {"account": "act_agency_a_001", "bm": "bm_agency_002", "page": "page_agency_product_a",
     "name": "[Agency] Vinhomes HCM — A/B Test Creative",   "tier": "TESTING",  "budget": 600_000,
     "objective": "LEAD_GENERATION", "content_type": "ab_test"},

    {"account": "act_agency_a_001", "bm": "bm_agency_002", "page": "page_bds_investment",
     "name": "[Agency] Đất Nền Long An — ROI Campaign",     "tier": "WINNER",   "budget": 1_400_000,
     "objective": "LEAD_GENERATION", "content_type": "roi_calculator"},

    {"account": "act_agency_a_001", "bm": "bm_agency_002", "page": "page_agency_product_a",
     "name": "[Agency] Mass Prospecting — Interest BDS",    "tier": "POOR",     "budget": 500_000,
     "objective": "LEAD_GENERATION", "content_type": "mass_creative"},

    {"account": "act_agency_a_001", "bm": "bm_agency_002", "page": "page_bds_investment",
     "name": "[Agency] Lookalike 1% — Khách VIP",           "tier": "SCALING",  "budget": 1_100_000,
     "objective": "LEAD_GENERATION", "content_type": "lal_creative"},

    {"account": "act_agency_a_001", "bm": "bm_agency_002", "page": "page_agency_product_a",
     "name": "[Agency] Video 15s — TOFU Awareness",         "tier": "STABLE",   "budget": 800_000,
     "objective": "REACH", "content_type": "video_short"},

    # Agency B — 3 campaigns
    {"account": "act_agency_b_001", "bm": "bm_agency_002", "page": "page_bds_luxury",
     "name": "[Luxury] Penthouse Golf View — UHN",          "tier": "STABLE",   "budget": 2_000_000,
     "objective": "LEAD_GENERATION", "content_type": "premium_creative"},

    {"account": "act_agency_b_001", "bm": "bm_agency_002", "page": "page_bds_luxury",
     "name": "[Luxury] The Residences — International",     "tier": "POOR",     "budget": 1_500_000,
     "objective": "LEAD_GENERATION", "content_type": "international"},

    {"account": "act_agency_b_001", "bm": "bm_agency_002", "page": "page_bds_luxury",
     "name": "[Luxury] Smart ROAS — Conv Opt",              "tier": "TESTING",  "budget": 400_000,
     "objective": "CONVERSIONS", "content_type": "smart_creative"},

    # Individual agents — 8 campaigns
    {"account": "act_agent_001", "bm": "bm_agent_003", "page": "page_agent_nguyen",
     "name": "Tuấn BĐS — Vinhomes Q9 List",                 "tier": "WINNER",   "budget": 300_000,
     "objective": "LEAD_GENERATION", "content_type": "personal_brand"},

    {"account": "act_agent_002", "bm": "bm_agent_003", "page": "page_agent_tran",
     "name": "Thu Hà Realty — Đất Nền Bình Dương",          "tier": "STABLE",   "budget": 200_000,
     "objective": "LEAD_GENERATION", "content_type": "personal_brand"},

    {"account": "act_agent_003", "bm": "bm_agent_003", "page": "page_agent_le",
     "name": "Phong BĐS — Chung Cư Mini HN",                "tier": "DECLINING","budget": 150_000,
     "objective": "LEAD_GENERATION", "content_type": "personal_brand"},

    {"account": "act_agent_004", "bm": "bm_agent_003", "page": "page_agent_pham",
     "name": "Dũng Đầu Tư — Shophouse Tây Ninh",            "tier": "POOR",     "budget": 100_000,
     "objective": "LEAD_GENERATION", "content_type": "personal_brand"},

    {"account": "act_agent_001", "bm": "bm_agent_003", "page": "page_agent_nguyen",
     "name": "Tuấn BĐS — Retarget Danh Sách Cũ",            "tier": "SCALING",  "budget": 250_000,
     "objective": "LEAD_GENERATION", "content_type": "retarget"},

    {"account": "act_agent_002", "bm": "bm_agent_003", "page": "page_agent_tran",
     "name": "Thu Hà — Căn Hộ Bình Thạnh Launch",           "tier": "TESTING",  "budget": 120_000,
     "objective": "LEAD_GENERATION", "content_type": "launch_creative"},

    {"account": "act_agent_003", "bm": "bm_agent_003", "page": "page_agent_le",
     "name": "Phong — LAL Khách Vay Ngân Hàng",             "tier": "WINNER",   "budget": 220_000,
     "objective": "LEAD_GENERATION", "content_type": "lal_creative"},

    {"account": "act_agent_004", "bm": "bm_agent_003", "page": "page_agent_pham",
     "name": "Dũng — Interest Investors 35-50",              "tier": "STABLE",   "budget": 180_000,
     "objective": "LEAD_GENERATION", "content_type": "interest_segment"},
]

# ── Performance profiles theo tier ──────────────────────────────────────────
TIER_PROFILES = {
    "WINNER": {
        "cpl_range":   (60_000, 140_000),
        "ctr_range":   (2.5, 5.5),
        "cpm_range":   (30_000, 65_000),
        "freq_range":  (1.2, 2.3),
        "conv_range":  (9, 18),        # leads/day
        "quality_range": (7.0, 9.5),
        "trend": "up",                 # chi tiêu đang tăng
        "status": "ACTIVE",
    },
    "SCALING": {
        "cpl_range":   (80_000, 160_000),
        "ctr_range":   (2.0, 4.0),
        "cpm_range":   (35_000, 75_000),
        "freq_range":  (1.4, 2.5),
        "conv_range":  (6, 15),
        "quality_range": (6.5, 8.5),
        "trend": "up",
        "status": "ACTIVE",
    },
    "STABLE": {
        "cpl_range":   (140_000, 280_000),
        "ctr_range":   (1.3, 2.5),
        "cpm_range":   (50_000, 90_000),
        "freq_range":  (1.8, 3.0),
        "conv_range":  (3, 9),
        "quality_range": (5.0, 7.5),
        "trend": "flat",
        "status": "ACTIVE",
    },
    "DECLINING": {
        "cpl_range":   (280_000, 450_000),
        "ctr_range":   (0.7, 1.5),
        "cpm_range":   (70_000, 130_000),
        "freq_range":  (3.2, 5.0),    # ad fatigue
        "conv_range":  (1, 5),
        "quality_range": (3.5, 6.0),
        "trend": "down",
        "status": "ACTIVE",           # đang chạy nhưng kém
    },
    "POOR": {
        "cpl_range":   (450_000, 900_000),
        "ctr_range":   (0.3, 0.9),
        "cpm_range":   (90_000, 180_000),
        "freq_range":  (3.5, 5.5),
        "conv_range":  (0, 3),
        "quality_range": (1.5, 4.0),
        "trend": "down",
        "status": "ACTIVE",           # đáng lẽ nên pause
    },
    "TESTING": {
        "cpl_range":   (100_000, 600_000),  # variance cao khi mới
        "ctr_range":   (0.5, 4.0),
        "cpm_range":   (40_000, 120_000),
        "freq_range":  (1.0, 2.0),
        "conv_range":  (0, 8),
        "quality_range": (2.0, 8.0),
        "trend": "volatile",
        "status": "ACTIVE",
    },
}

# ── Adset templates theo content_type ────────────────────────────────────────
ADSET_TEMPLATES = {
    "video_testimonial": [
        {"name": "Video KH thực tế — Nam 30-40 HCM", "age": "30-40", "gender": "nam"},
        {"name": "Video KH thực tế — Nữ 28-38 HCM",  "age": "28-38", "gender": "nu"},
        {"name": "Lookalike 2% — Lead cũ 90d",        "age": "25-45", "gender": "all"},
    ],
    "carousel_project": [
        {"name": "Carousel Dự Án — Investmen 35-50",  "age": "35-50", "gender": "all"},
        {"name": "Carousel Dự Án — Ở thực 28-40",     "age": "28-40", "gender": "all"},
    ],
    "image_roi":    [{"name": "Image ROI — Nhà Đầu Tư", "age": "30-50", "gender": "all"}],
    "personal_brand": [
        {"name": "Tệp khách quen Retarget", "age": "25-55", "gender": "all"},
        {"name": "Bạn bè của KH cũ LAL",   "age": "28-50", "gender": "all"},
    ],
    "default": [
        {"name": "Nhóm chính — Core audience", "age": "25-45", "gender": "all"},
        {"name": "Mở rộng — Broad targeting",  "age": "22-55", "gender": "all"},
        {"name": "Retarget — Đã xem 75%",      "age": "25-55", "gender": "all"},
    ],
}


# ── Generators ────────────────────────────────────────────────────────────────

def get_adset_templates(content_type: str) -> list[dict]:
    return ADSET_TEMPLATES.get(content_type, ADSET_TEMPLATES["default"])


def generate_campaign_id(account: str, idx: int) -> str:
    return f"camp_{account}_{idx:03d}"


def generate_adset_id(camp_id: str, idx: int) -> str:
    return f"adset_{camp_id}_{idx}"


def generate_ad_id(adset_id: str, idx: int) -> str:
    return f"ad_{adset_id}_v{idx+1}"


def _rng(campaign_id: str) -> random.Random:
    seed = int(hashlib.md5(campaign_id.encode()).hexdigest()[:8], 16)
    return random.Random(seed)


def generate_insights_for_campaign(camp: dict, days: int = 7) -> list[dict]:
    """Tạo dữ liệu insights theo ngày cho 1 campaign."""
    tier     = camp["tier"]
    profile  = TIER_PROFILES[tier]
    rng      = _rng(camp["id"])
    budget   = camp["budget"]
    rows     = []

    for i in range(days):
        date = (datetime.now() - timedelta(days=days - 1 - i)).strftime("%Y-%m-%d")

        # Trend multiplier
        if profile["trend"] == "up":
            trend_mult = 1.0 + (i / days) * 0.4
        elif profile["trend"] == "down":
            trend_mult = 1.0 - (i / days) * 0.35
        elif profile["trend"] == "volatile":
            trend_mult = rng.uniform(0.5, 1.8)
        else:
            trend_mult = rng.uniform(0.9, 1.1)

        # Spend: dựa trên budget × utilization × trend
        utilization = rng.uniform(0.70, 0.98)
        spend       = min(budget * utilization * trend_mult, budget * 1.05)

        # CTR
        ctr_base = rng.uniform(*profile["ctr_range"])
        ctr      = ctr_base * trend_mult if profile["trend"] == "up" else ctr_base / (trend_mult if profile["trend"] == "down" else 1)
        ctr      = round(max(0.1, min(ctr, 8.0)), 4)

        # CPM
        cpm = rng.uniform(*profile["cpm_range"])

        # Impressions from spend/CPM
        impressions = max(100, int(spend / cpm * 1000))
        clicks      = max(1, int(impressions * ctr / 100))
        reach       = max(1, int(impressions / rng.uniform(1.1, profile["freq_range"][1])))
        frequency   = round(impressions / max(reach, 1), 2)
        frequency   = round(min(6.0, max(1.0, rng.uniform(*profile["freq_range"]))), 2)

        cpc       = round(spend / clicks if clicks else 0, 0)
        leads_day = rng.randint(*profile["conv_range"])
        cpl       = round(spend / leads_day if leads_day else spend, 0)

        rows.append({
            "campaign_id":   camp["id"],
            "campaign_name": camp["name"],
            "adset_id":      f"adset_{camp['id']}_agg",
            "ad_id":         f"ad_{camp['id']}_agg",
            "account_id":    camp["account"],
            "bm_id":         camp["bm"],
            "page_id":       camp["page"],
            "date_start":    date,
            "date_stop":     date,
            "impressions":   impressions,
            "clicks":        clicks,
            "spend":         round(spend, 0),
            "spend_vnd":     round(spend, 0),
            "cpm":           round(cpm, 2),
            "cpc":           cpc,
            "ctr":           ctr,
            "frequency":     frequency,
            "reach":         reach,
            "leads":         leads_day,
            "cpl":           cpl,
            "tier":          tier,
            "objective":     camp["objective"],
            "content_type":  camp["content_type"],
        })
    return rows


def generate_adsets_for_campaign(camp: dict) -> list[dict]:
    """Tạo adsets với performance phân tán."""
    tier       = camp["tier"]
    profile    = TIER_PROFILES[tier]
    rng        = _rng(camp["id"] + "_adsets")
    templates  = get_adset_templates(camp["content_type"])
    adsets     = []

    for j, tmpl in enumerate(templates):
        aid = generate_adset_id(camp["id"], j)
        # Mỗi adset có performance hơi khác nhau
        perf_mult = rng.uniform(0.7, 1.3)
        cpl_base  = rng.uniform(*profile["cpl_range"]) * perf_mult
        adsets.append({
            "id":           aid,
            "campaign_id":  camp["id"],
            "account_id":   camp["account"],
            "bm_id":        camp["bm"],
            "page_id":      camp["page"],
            "name":         tmpl["name"],
            "age_targeting": tmpl["age"],
            "gender":       tmpl["gender"],
            "status":       "ACTIVE" if rng.random() > 0.2 else "PAUSED",
            "daily_budget": int(camp["budget"] / max(len(templates), 1)),
            "cpl_7d":       round(cpl_base, 0),
            "quality_score": round(rng.uniform(*profile["quality_range"]), 1),
            "tier":         tier,
        })
    return adsets


def generate_messenger_leads_for_page(page_id: str, ad_id: str,
                                       tier: str, n: int = None) -> list[dict]:
    """Tạo Messenger leads cho 1 ad với chất lượng theo tier."""
    profile  = TIER_PROFILES.get(tier, TIER_PROFILES["STABLE"])
    rng      = _rng(page_id + ad_id)
    n        = n or rng.randint(2, 12)

    vn_names = [
        "Nguyễn Thanh Hùng", "Trần Thị Hoa", "Lê Minh Tuấn", "Phạm Thị Lan",
        "Hoàng Đức Mạnh", "Vũ Thị Kim Anh", "Đặng Văn Bình", "Bùi Thị Ngọc",
        "Phan Văn Long", "Ngô Thị Thúy", "Đinh Đình Dũng", "Lý Thị Mai",
        "Trịnh Văn Quang", "Đỗ Thị Hương", "Hồ Sĩ Tuấn", "Dương Thị Linh",
    ]
    phones = [f"09{rng.randint(10000000,99999999)}" for _ in range(n)]
    quality_min, quality_max = profile["quality_range"]
    leads = []

    for i in range(n):
        # High-tier ads có content chất lượng hơn → intent cao hơn
        quality = round(rng.uniform(quality_min, quality_max), 1)
        intent  = round(rng.uniform(max(2, quality_min - 1), min(10, quality_max + 0.5)), 1)
        msgs    = rng.randint(2, 15)

        leads.append({
            "conversation_id":  f"conv_{page_id}_{ad_id}_{i}",
            "fb_ad_id":         ad_id,
            "page_id":          page_id,
            "sender_name":      vn_names[i % len(vn_names)],
            "sender_psid":      f"psid_{rng.randint(1000000, 9999999)}",
            "phone":            phones[i] if rng.random() > 0.3 else None,
            "email":            f"kh{i}@example.com" if rng.random() > 0.6 else None,
            "message_count":    msgs,
            "intent_score":     intent,
            "quality_score":    quality,
            "tier":             tier,
            "first_message_at": (datetime.now() - timedelta(hours=rng.randint(1, 168))),
            "last_message_at":  (datetime.now() - timedelta(hours=rng.randint(0, 24))),
        })
    return leads


# ── Main generator: tạo toàn bộ universe ─────────────────────────────────────

def generate_full_universe(days: int = 7) -> dict:
    """
    Tạo toàn bộ dữ liệu giả lập cho:
      - Tất cả campaigns (30+)
      - Tất cả adsets
      - Insights theo ngày
      - Messenger leads
    
    Returns dict với tất cả data.
    """
    campaigns_all  = []
    adsets_all     = []
    insights_all   = []
    messenger_all  = []

    for idx, tmpl in enumerate(CAMPAIGN_TEMPLATES):
        camp_id = generate_campaign_id(tmpl["account"], idx)
        camp = {
            **tmpl,
            "id":     camp_id,
            "status": TIER_PROFILES[tmpl["tier"]]["status"],
        }
        campaigns_all.append(camp)

        # Adsets
        adsets = generate_adsets_for_campaign(camp)
        adsets_all.extend(adsets)

        # Insights
        insights = generate_insights_for_campaign(camp, days=days)
        insights_all.extend(insights)

        # Messenger leads (từ mỗi adset)
        for adset in adsets:
            rng = _rng(adset["id"])
            n_leads = rng.randint(1, 8) if tmpl["tier"] in ("WINNER","SCALING") else rng.randint(0, 4)
            leads = generate_messenger_leads_for_page(
                tmpl["page"], adset["id"], tmpl["tier"], n=n_leads
            )
            messenger_all.extend(leads)

    return {
        "campaigns":   campaigns_all,
        "adsets":      adsets_all,
        "insights":    insights_all,
        "messenger":   messenger_all,
        "bms":         BUSINESS_MANAGERS,
        "pages":       PAGES,
        "generated_at": datetime.now().isoformat(),
        "days":        days,
    }


def aggregate_by_account(universe: dict) -> list[dict]:
    """Tổng hợp metrics theo TKQC."""
    from collections import defaultdict
    acc_data = defaultdict(lambda: {
        "spend": 0, "leads": 0, "clicks": 0, "impressions": 0,
        "campaigns": set(), "bm_id": "", "page_ids": set(),
        "quality_scores": [],
    })

    for row in universe["insights"]:
        aid = row["account_id"]
        acc_data[aid]["spend"]       += row["spend"]
        acc_data[aid]["leads"]       += row["leads"]
        acc_data[aid]["clicks"]      += row["clicks"]
        acc_data[aid]["impressions"] += row["impressions"]
        acc_data[aid]["campaigns"].add(row["campaign_id"])
        acc_data[aid]["bm_id"]       = row["bm_id"]
        acc_data[aid]["page_ids"].add(row["page_id"])

    for lead in universe["messenger"]:
        aid = next((c["account"] for c in universe["campaigns"]
                    if c["page"] == lead["page_id"]), None)
        if aid:
            acc_data[aid]["quality_scores"].append(lead["quality_score"])

    result = []
    for acc_id, data in acc_data.items():
        leads = data["leads"]
        spend = data["spend"]
        scores = data["quality_scores"]
        bm_info = None
        for bm_id, bm in BUSINESS_MANAGERS.items():
            if acc_id in bm["accounts"]:
                bm_info = bm
                break
        result.append({
            "account_id":   acc_id,
            "bm_id":        data["bm_id"],
            "bm_name":      bm_info["name"] if bm_info else "",
            "bm_type":      bm_info["type"] if bm_info else "",
            "total_spend":  round(spend, 0),
            "total_leads":  leads,
            "total_clicks": data["clicks"],
            "total_impressions": data["impressions"],
            "cpl":          round(spend / leads, 0) if leads else 0,
            "ctr":          round(data["clicks"] / data["impressions"] * 100, 2) if data["impressions"] else 0,
            "campaigns":    len(data["campaigns"]),
            "pages":        list(data["page_ids"]),
            "avg_quality":  round(sum(scores) / len(scores), 2) if scores else 0,
        })
    return sorted(result, key=lambda x: x["total_spend"], reverse=True)


def aggregate_by_bm(universe: dict) -> list[dict]:
    """Tổng hợp metrics theo Business Manager."""
    from collections import defaultdict
    bm_data = defaultdict(lambda: {"spend": 0, "leads": 0, "accounts": set(),
                                    "quality_scores": [], "campaigns": set()})
    for row in universe["insights"]:
        bid = row["bm_id"]
        bm_data[bid]["spend"]    += row["spend"]
        bm_data[bid]["leads"]    += row["leads"]
        bm_data[bid]["accounts"].add(row["account_id"])
        bm_data[bid]["campaigns"].add(row["campaign_id"])

    for lead in universe["messenger"]:
        bid = next((c["bm"] for c in universe["campaigns"]
                    if c["page"] == lead["page_id"]), None)
        if bid:
            bm_data[bid]["quality_scores"].append(lead["quality_score"])

    result = []
    for bm_id, data in bm_data.items():
        bm_info = BUSINESS_MANAGERS.get(bm_id, {})
        scores  = data["quality_scores"]
        leads   = data["leads"]
        spend   = data["spend"]
        result.append({
            "bm_id":       bm_id,
            "bm_name":     bm_info.get("name", bm_id),
            "bm_type":     bm_info.get("type", ""),
            "total_spend":  round(spend, 0),
            "total_leads":  leads,
            "cpl":          round(spend / leads, 0) if leads else 0,
            "accounts":     len(data["accounts"]),
            "campaigns":    len(data["campaigns"]),
            "avg_quality":  round(sum(scores) / len(scores), 2) if scores else 0,
        })
    return sorted(result, key=lambda x: x["total_spend"], reverse=True)


def aggregate_by_tier(universe: dict) -> dict:
    """Thống kê theo performance tier."""
    from collections import defaultdict
    tier_data = defaultdict(lambda: {"count": 0, "spend": 0, "leads": 0,
                                      "quality_scores": []})
    for camp in universe["campaigns"]:
        tier_data[camp["tier"]]["count"] += 1

    for row in universe["insights"]:
        t = row["tier"]
        tier_data[t]["spend"] += row["spend"]
        tier_data[t]["leads"] += row["leads"]

    for lead in universe["messenger"]:
        t = lead.get("tier")
        if t:
            tier_data[t]["quality_scores"].append(lead["quality_score"])

    result = {}
    for tier, data in tier_data.items():
        scores = data["quality_scores"]
        leads  = data["leads"]
        spend  = data["spend"]
        result[tier] = {
            "campaign_count": data["count"],
            "total_spend":    round(spend, 0),
            "total_leads":    leads,
            "cpl":            round(spend / leads, 0) if leads else 0,
            "avg_quality":    round(sum(scores) / len(scores), 2) if scores else 0,
            "spend_pct":      0,  # filled below
        }

    total_spend = sum(v["total_spend"] for v in result.values())
    for tier in result:
        result[tier]["spend_pct"] = round(result[tier]["total_spend"] / total_spend * 100, 1) if total_spend else 0

    return result


# ── Quick summary để in ra màn hình ──────────────────────────────────────────
def print_analysis_summary(universe: dict):
    camps    = universe["campaigns"]
    insights = universe["insights"]
    leads    = universe["messenger"]
    adsets   = universe["adsets"]

    total_spend  = sum(r["spend"] for r in insights)
    total_leads  = sum(r["leads"] for r in insights)
    total_impr   = sum(r["impressions"] for r in insights)
    overall_cpl  = total_spend / total_leads if total_leads else 0
    avg_quality  = sum(l["quality_score"] for l in leads) / len(leads) if leads else 0
    tier_summary = aggregate_by_tier(universe)
    by_bm        = aggregate_by_bm(universe)
    by_acc       = aggregate_by_account(universe)

    sep = "=" * 65
    print(f"\n{sep}")
    print(f"  SIMULATION REPORT -- {len(camps)} campaigns | {len(universe['bms'])} BMs | {len(universe['pages'])} Pages")
    print(sep)
    print(f"  Tong chi tieu:    {total_spend/1e6:.1f}M VND")
    print(f"  Tong leads:       {total_leads:,}")
    print(f"  Tong impressions: {total_impr:,}")
    print(f"  CPL tong the:     {overall_cpl:,.0f}d")
    print(f"  Tong adsets:      {len(adsets)}")
    print(f"  Messenger leads:  {len(leads)}")
    print(f"  Quality TB:       {avg_quality:.1f}/10")
    print(f"\n{'Tier':12} {'Camp':5} {'Spend(M)':10} {'Leads':6} {'CPL':10} {'Quality':8} {'Spend%':6}")
    print("-" * 65)
    for tier in ["WINNER", "SCALING", "STABLE", "DECLINING", "POOR", "TESTING"]:
        t = tier_summary.get(tier, {})
        if t:
            print(f"  {tier:12} {t['campaign_count']:3}   {t['total_spend']/1e6:7.1f}    {t['total_leads']:5}  {t['cpl']:9,.0f}   {t['avg_quality']:5.1f}   {t['spend_pct']:5.1f}%")
    print(f"\n{'BM':38} {'Camps':5} {'Spend(M)':9} {'Leads':6} {'CPL':10} {'Quality':8}")
    print("-" * 65)
    for bm in by_bm:
        bm_name = bm['bm_name'].encode('ascii', 'replace').decode('ascii')
        print(f"  {bm_name[:36]:36} {bm['campaigns']:5}  {bm['total_spend']/1e6:7.1f}   {bm['total_leads']:5}  {bm['cpl']:9,.0f}   {bm['avg_quality']:5.1f}")
    print(f"\nTop 5 TKQC by spend:")
    for acc in by_acc[:5]:
        print(f"  {acc['account_id']:28} CPL:{acc['cpl']:>9,.0f}d  Leads:{acc['total_leads']:4}  Q:{acc['avg_quality']:.1f}")
    print(sep)


if __name__ == "__main__":
    print("Generating simulation universe...")
    universe = generate_full_universe(days=7)
    print_analysis_summary(universe)
    print(f"\nDone: {len(universe['insights'])} insight rows, {len(universe['messenger'])} messenger leads")

