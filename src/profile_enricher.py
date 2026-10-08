"""
profile_enricher.py — Tổng hợp hồ sơ khách hàng 360°
======================================================
Kết hợp dữ liệu từ nhiều nguồn:
  1. CustomerProfile  → pipeline data (SĐT, cluster, lead_score)
  2. HotLead          → behavior signals (comment, share, tag)
  3. GoogleLead       → search intent signals
  4. MessengerLead    → conversation quality, intent
  5. AdPerformance    → which ads they interacted with
  6. FB Profile mock  → enriched profile từ Extension (demo mode)

Khi Extension thật được tích hợp, thay hàm `_get_fb_profile_mock`
bằng dữ liệu thật từ API endpoint mà Extension POST về.
"""
import json
import random
import hashlib
from datetime import datetime, timedelta
from collections import defaultdict


# ── Fake FB Profile Data (sẽ thay bằng dữ liệu thật từ Extension) ────────────

JOBS = [
    ("Kỹ sư phần mềm", "tech", 25_000_000),
    ("Giám đốc kinh doanh", "management", 45_000_000),
    ("Bác sĩ", "healthcare", 35_000_000),
    ("Nhân viên ngân hàng", "finance", 22_000_000),
    ("Kinh doanh tự do", "entrepreneur", 50_000_000),
    ("Giáo viên", "education", 15_000_000),
    ("Kế toán", "finance", 18_000_000),
    ("Nhà đầu tư BĐS", "realestate", 80_000_000),
    ("Marketing Manager", "marketing", 28_000_000),
    ("Luật sư", "legal", 40_000_000),
]
LOCATIONS = [
    "TP.HCM - Quận 2", "TP.HCM - Quận 7", "TP.HCM - Bình Thạnh",
    "Hà Nội - Cầu Giấy", "Hà Nội - Đống Đa", "Đà Nẵng - Hải Châu",
    "TP.HCM - Thủ Đức", "Bình Dương - Dĩ An", "Long An - Bến Lức",
]
INTERESTS = [
    ["BĐS đầu tư", "Chứng khoán", "Tài chính cá nhân"],
    ["Du lịch cao cấp", "Mua nhà ở thực", "Tiện ích gia đình"],
    ["Đầu tư thụ động", "Nghỉ dưỡng", "Phong thủy BĐS"],
    ["Thiết kế nội thất", "Gia đình & con cái", "Khu đô thị hiện đại"],
    ["Golf", "Luxury lifestyle", "Bất động sản nghỉ dưỡng"],
]
BUYING_SIGNALS = [
    "Đã xem 5+ bài viết về dự án",
    "Đã click vào nút 'Xem báo giá'",
    "Đã lưu bài viết về sản phẩm",
    "Đã chia sẻ link dự án",
    "Đã tham gia group mua nhà",
    "Đã hỏi về chính sách vay ưu đãi",
    "Đã so sánh 2-3 dự án cùng phân khúc",
    "Đã hỏi về tiến độ bàn giao",
    "Đã yêu cầu gặp Sales trực tiếp",
]
MESSENGER_SAMPLES = [
    ("Dự án này có mấy loại căn hộ vậy bạn?", 1),
    ("Cho mình hỏi giá căn 2PN tầm bao nhiêu?", 3),
    ("Pháp lý dự án như thế nào? Sổ hồng chưa?", 4),
    ("Mình cần căn 3PN, ngân sách khoảng 4-5 tỷ được không?", 8),
    ("Khu vực này tiện ích thế nào? Gần trường không?", 2),
    ("Bao giờ bàn giao được vậy anh/chị?", 5),
    ("Cho mình đặt lịch xem nhà mẫu cuối tuần này được không?", 9),
    ("Mình đang cân nhắc dự án này và dự án X, anh tư vấn thêm nhé?", 4),
    ("Có chính sách vay ưu đãi nào không? Lãi suất bao nhiêu?", 6),
    ("Mình quan tâm, anh gửi bản vẽ mặt bằng cho mình xem với?", 7),
]


def _seed(uid: str) -> random.Random:
    """Seed RNG từ UID để dữ liệu nhất quán"""
    h = int(hashlib.md5((uid or "default").encode()).hexdigest()[:8], 16)
    return random.Random(h)


def _get_fb_profile_mock(uid: str, name: str = "") -> dict:
    """
    Sinh FB profile demo dựa trên UID.
    → Trong production: thay bằng data POST từ Extension.
    """
    rng = _seed(uid)
    age  = rng.randint(26, 55)
    job, sector, income = rng.choice(JOBS)
    loc  = rng.choice(LOCATIONS)
    ints = rng.choice(INTERESTS)
    married = rng.random() > 0.4
    children = rng.randint(0, 3) if married else 0

    # Activity score: 0-10
    activity = round(rng.uniform(2, 9.5), 1)
    signals  = rng.sample(BUYING_SIGNALS, k=rng.randint(1, 4))

    # Profile pic placeholder — trong thực tế là avatar URL từ extension
    avatar_seed = abs(hash(uid + "avatar")) % 70
    avatar_url  = f"https://i.pravatar.cc/120?img={avatar_seed}"

    return {
        "uid":              uid,
        "avatar_url":       avatar_url,
        "display_name":     name or f"Facebook User {uid[-6:]}",
        "age":              age,
        "location":         loc,
        "job":              job,
        "job_sector":       sector,
        "estimated_income": income,
        "married":          married,
        "children":         children,
        "interests":        ints,
        "activity_score":   activity,
        "buying_signals":   signals,
        "profile_source":   "extension_mock",  # "extension_real" khi tích hợp
        "scraped_at":       (datetime.now() - timedelta(hours=rng.randint(1, 48))).isoformat(),
    }


def _get_messenger_history_mock(uid: str, quality: float = 5.0) -> list:
    """Sinh lịch sử hội thoại demo"""
    rng = _seed(uid + "_msg")
    n   = rng.randint(2, 5)
    msgs = []
    base = datetime.now() - timedelta(days=rng.randint(1, 14))
    for i, (text, intent) in enumerate(rng.sample(MESSENGER_SAMPLES, n)):
        msgs.append({
            "timestamp":   (base + timedelta(hours=i * 3 + rng.randint(0, 2))).strftime("%d/%m %H:%M"),
            "sender":      "customer",
            "text":        text,
            "intent_score": min(10, intent + rng.randint(-1, 2)),
        })
        # Agent reply
        msgs.append({
            "timestamp": (base + timedelta(hours=i * 3 + rng.randint(1, 2))).strftime("%d/%m %H:%M"),
            "sender":    "agent",
            "text":      "Cảm ơn bạn đã quan tâm! Mình sẽ gửi thông tin ngay ạ.",
            "intent_score": None,
        })
    return msgs


def _get_ad_journey_mock(uid: str) -> list:
    """Sinh hành trình ads giả lập"""
    rng = _seed(uid + "_ads")
    content_types = ["video_testimonial", "carousel_project", "image_roi", "personal_brand", "roi_calculator"]
    n = rng.randint(1, 4)
    base = datetime.now() - timedelta(days=14)
    journey = []
    for i in range(n):
        ct = rng.choice(content_types)
        journey.append({
            "date":         (base + timedelta(days=i * 3)).strftime("%d/%m"),
            "content_type": ct,
            "action":       rng.choice(["Xem video 75%", "Click vào ad", "Nhắn tin Messenger", "Lưu bài viết", "Xem trang dự án"]),
            "campaign":     rng.choice(["Vinhomes Grand Park Q9", "The Beverly", "Shophouse Đầu Tư", "Biệt Thự Rainbow"]),
            "quality_signal": rng.choice(["High intent", "Medium interest", "Low intent", "Retarget"]),
        })
    return journey


def build_360_profile(db_profile, hot_leads=None, messenger_leads=None) -> dict:
    """
    Tổng hợp 360° profile từ tất cả nguồn dữ liệu.

    Args:
        db_profile: CustomerProfile ORM object
        hot_leads:  list of HotLead objects
        messenger_leads: list of MessengerLead objects

    Returns:
        dict với toàn bộ thông tin customer 360°
    """
    uid   = db_profile.facebook_uid or f"uid_{db_profile.id}"
    name  = db_profile.ho_ten or ""
    score = db_profile.lead_score or 0.0
    cluster = db_profile.cluster

    # ── FB Profile (từ Extension hoặc mock) ───────────────────────────────────
    fb = _get_fb_profile_mock(uid, name)

    # ── Cluster metadata ──────────────────────────────────────────────────────
    cluster_meta = {
        2: {"label": "VIP", "icon": "👑", "color": "#f59e0b",
            "bg": "rgba(245,158,11,.15)", "desc": "Khách VIP", "priority": "P0"},
        1: {"label": "Ở thực", "icon": "🏠", "color": "#10b981",
            "bg": "rgba(16,185,129,.15)", "desc": "Mua để ở", "priority": "P1"},
        0: {"label": "Đầu cơ", "icon": "📈", "color": "#6366f1",
            "bg": "rgba(99,102,241,.15)", "desc": "Nhà đầu tư", "priority": "P2"},
        None: {"label": "Chưa phân", "icon": "❓", "color": "#94a3b8",
               "bg": "rgba(148,163,184,.1)", "desc": "Chưa có đủ data", "priority": "P3"},
    }.get(cluster, {"label": "—", "icon": "❓", "color": "#94a3b8", "bg": "", "desc": "", "priority": "P3"})

    # ── Behavior signals từ HotLead ────────────────────────────────────────────
    behaviors = []
    if hot_leads:
        for hl in hot_leads:
            behaviors.append({
                "type":    hl.behavior or "unknown",
                "keyword": hl.keyword or "",
                "url":     hl.source_url or "",
                "score":   hl.hot_score or 0,
                "nguon":   hl.nguon or "facebook",
                "date":    hl.scraped_at.strftime("%d/%m/%Y") if hl.scraped_at else "",
            })

    # ── Messenger leads ────────────────────────────────────────────────────────
    agg_quality = 0.0
    conv_history = []
    if messenger_leads:
        for ml in messenger_leads:
            agg_quality += getattr(ml, "quality_score", 0) or 0
            conv_history.append({
                "sender_name":   getattr(ml, "sender_name", ""),
                "message_count": getattr(ml, "message_count", 0),
                "intent_score":  getattr(ml, "intent_score", 0),
                "quality_score": getattr(ml, "quality_score", 0),
                "last_message_at": str(getattr(ml, "last_message_at", "")),
            })
        agg_quality = agg_quality / len(messenger_leads)
    else:
        # Demo mode — sinh dữ liệu mock
        conv_history = _get_messenger_history_mock(uid, score)
        agg_quality  = min(10, score + random.uniform(-0.5, 1.5))

    # ── Ad Journey ────────────────────────────────────────────────────────────
    ad_journey = _get_ad_journey_mock(uid)

    # ── Intent Score tổng hợp ─────────────────────────────────────────────────
    #  Weighted: lead_score(35%) + quality(30%) + hot_behavior(20%) + fb_activity(15%)
    hot_score_norm = (max(hl.hot_score for hl in hot_leads) / 10 * 10) if hot_leads else score * 0.8
    intent_score = round(
        score * 0.35
        + agg_quality * 0.30
        + hot_score_norm * 0.20
        + fb["activity_score"] * 0.15,
        1
    )
    intent_score = min(10, intent_score)

    # ── Purchase Probability ──────────────────────────────────────────────────
    prob_map = {
        (8, 10): ("Rất cao", "85-95%", "#3fb950"),
        (6, 8):  ("Cao",     "60-80%", "#39d353"),
        (4, 6):  ("Trung bình", "35-55%", "#d29922"),
        (2, 4):  ("Thấp",    "15-30%", "#f97316"),
        (0, 2):  ("Rất thấp","<15%",   "#f85149"),
    }
    prob_label, prob_pct, prob_color = ("—", "—", "#8b949e")
    for (lo, hi), val in prob_map.items():
        if lo <= intent_score < hi or (hi == 10 and intent_score == 10):
            prob_label, prob_pct, prob_color = val
            break

    # ── Recommended action ────────────────────────────────────────────────────
    actions = []
    if intent_score >= 8:
        actions.append({"priority": 1, "icon": "📞", "action": "Gọi điện ngay", "reason": f"Intent Score {intent_score}/10 — khách đang sẵn sàng mua"})
    if cluster == 2:
        actions.append({"priority": 1, "icon": "🎁", "action": "Chuẩn bị offer VIP", "reason": "Khách VIP cần chế độ riêng"})
    if agg_quality >= 7:
        actions.append({"priority": 2, "icon": "🏠", "action": "Đặt lịch xem nhà mẫu", "reason": f"Messenger quality {agg_quality:.1f}/10"})
    if fb.get("job_sector") == "realestate":
        actions.append({"priority": 2, "icon": "🤝", "action": "Tư vấn đầu tư", "reason": "Ngành BĐS — khả năng đầu tư cao"})
    if len(ad_journey) >= 2:
        actions.append({"priority": 3, "icon": "📧", "action": "Gửi tài liệu dự án", "reason": f"Đã tương tác {len(ad_journey)} ads"})
    if not actions:
        actions.append({"priority": 3, "icon": "📱", "action": "Nuture qua Messenger", "reason": "Cần thêm thời gian để xây dựng trust"})

    actions.sort(key=lambda x: x["priority"])

    # ── Demographic fit score ─────────────────────────────────────────────────
    # Mức độ phù hợp profile vs cluster target
    fit = 5.0
    if cluster == 2 and fb["estimated_income"] >= 40_000_000: fit += 3.0
    if cluster == 0 and fb["job_sector"] in ["realestate", "finance"]: fit += 2.5
    if cluster == 1 and fb["children"] > 0: fit += 2.0
    if fb["age"] >= 30: fit += 1.0
    profile_fit = min(10, round(fit, 1))

    return {
        # Core
        "id":          db_profile.id,
        "phone":       db_profile.so_dien_thoai or "",
        "email":       db_profile.email or "",
        "nguon":       db_profile.nguon or "",
        "lead_score":  round(score, 1),
        "cluster":     cluster,
        "cluster_meta": cluster_meta,
        "created_at":  db_profile.created_at.strftime("%d/%m/%Y") if db_profile.created_at else "",
        # FB Profile
        "fb_profile":  fb,
        # Scores
        "intent_score":   round(intent_score, 1),
        "agg_quality":    round(agg_quality, 1),
        "profile_fit":    profile_fit,
        "prob_label":     prob_label,
        "prob_pct":       prob_pct,
        "prob_color":     prob_color,
        # Activity
        "behaviors":      behaviors,
        "conv_history":   conv_history,
        "ad_journey":     ad_journey,
        # Recommendations
        "actions":        actions,
        # Meta
        "data_sources":   {
            "pipeline": True,
            "hot_leads": len(behaviors) > 0,
            "messenger": len(conv_history) > 0,
            "ads": len(ad_journey) > 0,
            "extension": fb.get("profile_source") == "extension_real",
        }
    }
