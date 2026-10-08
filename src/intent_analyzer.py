"""
intent_analyzer.py — Phân tích ý định mua hàng từ hội thoại Messenger
======================================================================
Phát hiện 6 nhóm tín hiệu intent trong tin nhắn tiếng Việt BĐS:

  TRANSACTION  (35%) — Tín hiệu mua / chốt trực tiếp
  SCHEDULING   (25%) — Muốn xem nhà / gặp Sales
  QUALIFICATION(20%) — Ngân sách, vay, tài chính
  LEGAL_CHECK  (10%) — Pháp lý, sổ hồng, quy hoạch
  RESEARCH     (10%) — Thu thập thông tin chung
  CONCERN      (adj) — Phản đối, do dự (giảm điểm)

Output chuẩn: IntentResult dataclass có thể serialize ra JSON.
"""

import re
import json
from datetime import datetime
from dataclasses import dataclass, field, asdict
from typing import Optional


# ═══════════════════════════════════════════════════════════════════════════════
# SIGNAL PATTERNS — Vietnamese Real Estate
# ═══════════════════════════════════════════════════════════════════════════════
# Format: (pattern_regex, score_0_to_10, human_label)

TRANSACTION_SIGNALS = [
    # Cực kỳ cao — quyết định
    (r"(muốn|tôi\s+đặt|muốn\s+đặt)\s*(cọc|mua)", 10, "Muốn đặt cọc/mua"),
    (r"(chốt|ký\s*hợp\s*đồng|mua\s*ngay|đồng\s*ý\s*mua)", 10, "Tín hiệu chốt deal"),
    (r"(đặt\s*cọc|cọc\s*bao\s*nhiêu|đặt\s*giữ\s*chỗ)", 9, "Hỏi đặt cọc"),
    (r"(tôi\s*lấy|mình\s*lấy|anh\s*lấy|chị\s*lấy)\s*căn", 9, "Xác nhận muốn lấy căn"),
    # Cao
    (r"(gửi\s*hợp\s*đồng|xem\s*hợp\s*đồng|điều\s*khoản)", 8, "Hỏi hợp đồng"),
    (r"(anh\s*chị\s*quan\s*tâm|mình\s*quan\s*tâm|tôi\s*quan\s*tâm).{0,20}này", 7, "Xác nhận quan tâm"),
    (r"(giá\s*(căn|phòng|nhà|đó|này|bao\s*nhiêu)|báo\s*giá|bảng\s*giá)", 7, "Hỏi giá cụ thể"),
    (r"(phương\s*thức\s*thanh\s*toán|lịch\s*thanh\s*toán|trả\s*góp)", 8, "Hỏi thanh toán"),
    (r"(còn\s*(hàng|căn|suất|slot)|còn\s*không|còn\s*bán\s*không)", 7, "Hỏi còn hàng"),
    # Trung bình
    (r"(so\s*sánh|cân\s*nhắc|đang\s*xem\s*xét).{0,30}(dự\s*án|căn)", 5, "Đang so sánh dự án"),
    (r"(anh\s*chị\s*đang\s*tìm|mình\s*đang\s*tìm)\s*(nhà|căn|đất)", 5, "Đang tìm kiếm"),
]

SCHEDULING_SIGNALS = [
    # Rất cao — lịch hẹn cụ thể
    (r"(đặt\s*lịch|book\s*lịch|hẹn\s*xem|xem\s*nhà\s*mẫu|xem\s*trực\s*tiếp)", 10, "Muốn đặt lịch xem"),
    (r"(cuối\s*tuần\s*(này|tới)|thứ\s*[2-7bcdsbtbn]|sáng|chiều|tối)\s*(nào|này|mai|kia)", 9, "Đề xuất thời gian cụ thể"),
    (r"(gặp\s*(trực\s*tiếp|anh|chị|sales|nhân\s*viên)|gặp\s*mặt)", 9, "Muốn gặp trực tiếp"),
    (r"(tham\s*quan|đến\s*xem|muốn\s*xem|đến\s*dự\s*án)", 8, "Muốn đến xem dự án"),
    # Trung bình
    (r"(khi\s*nào\s*(có\s*thể|được)|lúc\s*nào\s*tiện)", 6, "Hỏi thời gian hẹn"),
    (r"(gọi\s*lại|liên\s*hệ\s*lại|gọi\s*cho\s*tôi)", 7, "Yêu cầu liên hệ lại"),
    (r"(zalo|số\s*điện\s*thoại|contact|liên\s*lạc)\s*(của|anh|chị|bạn)", 7, "Xin thông tin liên lạc"),
    (r"(tư\s*vấn\s*thêm|giải\s*thích\s*thêm|nói\s*chuyện)", 5, "Muốn tư vấn thêm"),
]

QUALIFICATION_SIGNALS = [
    # Ngân sách — rất cao
    (r"ngân\s*sách.{0,20}(\d+[\.,]?\d*)\s*(tỷ|triệu|tr|t)", 10, "Tự cung cấp ngân sách"),
    (r"tầm\s*(\d+[\.,]?\d*)\s*(tỷ|triệu|tr)", 9, "Cung cấp ngân sách tầm"),
    (r"(budget|dự\s*toán).{0,10}(\d+)", 9, "Đề cập budget"),
    (r"(\d+[\.,]?\d*)\s*tỷ\s*(được\s*không|có\s*không|phù\s*hợp)", 9, "Xác nhận budget cụ thể"),
    # Vay/Tài chính
    (r"(vay\s*(ngân\s*hàng|tiền|vốn)|cho\s*vay|hỗ\s*trợ\s*vay)", 8, "Hỏi chính sách vay"),
    (r"(lãi\s*suất|ưu\s*đãi\s*vay|gói\s*vay|tín\s*dụng)", 8, "Hỏi lãi suất/vay"),
    (r"(trả\s*trước|vốn\s*tự\s*có|equity|đặt\s*trước\s*bao\s*nhiêu)", 8, "Hỏi vốn ban đầu"),
    (r"(khả\s*năng\s*tài\s*chính|tài\s*chính\s*của\s*tôi|thu\s*nhập)", 6, "Đề cập tài chính cá nhân"),
    # Trung bình
    (r"(phí\s*(quản\s*lý|bảo\s*trì|dịch\s*vụ)|chi\s*phí\s*hàng\s*tháng)", 5, "Hỏi chi phí phát sinh"),
]

LEGAL_SIGNALS = [
    # Pháp lý — cao
    (r"(sổ\s*(hồng|đỏ)|giấy\s*chứng\s*nhận|cấp\s*sổ)", 9, "Hỏi sổ hồng/pháp lý"),
    (r"(pháp\s*lý|pháp\s*lí|tính\s*pháp\s*lý|hồ\s*sơ\s*pháp\s*lý)", 9, "Hỏi pháp lý"),
    (r"(quy\s*hoạch|không\s*trong\s*lộ\s*giới|tranh\s*chấp|kiện)", 8, "Hỏi quy hoạch"),
    (r"(chủ\s*đầu\s*tư\s*uy\s*tín|uy\s*tín\s*của\s*chủ|bảo\s*lãnh\s*ngân\s*hàng)", 8, "Hỏi uy tín CĐT"),
    # Tiến độ / cam kết
    (r"(bàn\s*giao\s*(khi\s*nào|tháng|quý|năm)|tiến\s*độ\s*xây\s*dựng)", 8, "Hỏi tiến độ bàn giao"),
    (r"(phạt\s*chậm\s*bàn\s*giao|cam\s*kết\s*bàn\s*giao|đúng\s*tiến\s*độ)", 7, "Hỏi cam kết tiến độ"),
    (r"(hợp\s*đồng\s*(mua\s*bán|đặt\s*cọc|chuyển\s*nhượng))", 7, "Hỏi loại hợp đồng"),
]

RESEARCH_SIGNALS = [
    # Thu thập thông tin chung
    (r"(dự\s*án\s*(này|đó|ở\s*đâu|như\s*thế\s*nào)|thông\s*tin\s*dự\s*án)", 4, "Hỏi thông tin dự án"),
    (r"(diện\s*tích|số\s*phòng|bao\s*nhiêu\s*(phòng|tầng)|layout|mặt\s*bằng)", 5, "Hỏi thông số căn hộ"),
    (r"(tiện\s*(ích|nghi)|hồ\s*bơi|gym|trường\s*học|bệnh\s*viện|siêu\s*thị)", 4, "Hỏi tiện ích"),
    (r"(vị\s*trí|gần\s*(đâu|trung\s*tâm|quận)|khoảng\s*cách|đường\s*nào)", 4, "Hỏi vị trí"),
    (r"(view\s*(sông|biển|thành\s*phố|hồ)|tầng\s*(cao|thấp|mấy))", 4, "Hỏi view/tầng"),
    (r"(nội\s*thất|bàn\s*giao\s*nội\s*thất|full\s*nội\s*thất|đầy\s*đủ\s*nội\s*thất)", 5, "Hỏi nội thất"),
    (r"(dân\s*cư|cộng\s*đồng|hàng\s*xóm|môi\s*trường\s*sống)", 3, "Hỏi cộng đồng"),
    (r"(gửi\s*(thông\s*tin|brochure|file|catalog|link|tài\s*liệu))", 5, "Yêu cầu tài liệu"),
]

CONCERN_SIGNALS = [
    # Phản đối / tiêu cực (điểm âm)
    (r"(đắt\s*(quá|lắm|vậy)|giá\s*(cao|đắt)\s*quá)", -4, "Phàn nàn giá đắt"),
    (r"(không\s*(phù\s*hợp|quan\s*tâm|thích|hợp))", -5, "Không quan tâm"),
    (r"(thôi|bỏ|hủy|không\s*cần\s*nữa|không\s*mua\s*nữa)", -7, "Hủy quan tâm"),
    (r"(chờ\s*(thêm|xem|đã)|suy\s*nghĩ\s*thêm|cần\s*thêm\s*thời\s*gian)", -2, "Cần thêm thời gian"),
    (r"(lo\s*(ngại|lắng)|e\s*ngại|lo\s*sợ|không\s*chắc)", -3, "Lo ngại"),
    (r"(so\s*với\s*dự\s*án\s*(khác|bên\s*kia)\s*(rẻ|tốt|đẹp|hơn))", -3, "So sánh bất lợi"),
    (r"(vợ\s*(chưa|không)\s*(đồng\s*ý|cho|chịu)|chồng\s*(chưa|không)\s*đồng\s*ý)", -2, "Cần ý kiến gia đình"),
]

# ═══════════════════════════════════════════════════════════════════════════════
# DATACLASSES
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class SignalMatch:
    """Một tín hiệu intent đã phát hiện trong tin nhắn"""
    category: str          # TRANSACTION / SCHEDULING / etc.
    label: str             # Mô tả tín hiệu
    score: float           # Điểm của tín hiệu (có thể âm nếu concern)
    snippet: str           # Đoạn text chứa tín hiệu
    message_idx: int       # Index tin nhắn trong conversation


@dataclass
class CategoryScore:
    """Điểm tổng hợp cho một nhóm intent"""
    category: str
    raw_score: float       # Tổng điểm thô
    normalized: float      # 0-10 sau normalize
    signals: list          # Danh sách SignalMatch
    weight: float          # Trọng số trong composite (0-1)
    icon: str
    color: str


@dataclass
class IntentResult:
    """Kết quả phân tích ý định đầy đủ cho một cuộc hội thoại"""
    # Core scores
    composite_score: float      # 0-10, điểm tổng hợp
    confidence: str             # "high" | "medium" | "low"
    intent_level: str           # "Rất cao" | "Cao" | "Trung bình" | "Thấp" | "Rất thấp"
    intent_color: str           # hex color
    purchase_probability: str   # % estimate

    # Category breakdown
    categories: dict            # category_name -> CategoryScore

    # Signals
    all_signals: list           # List of SignalMatch
    top_signals: list           # Top 5 most significant

    # Conversation analytics
    message_count: int
    customer_message_count: int
    avg_response_time_min: Optional[float]
    response_speed: str         # "Nhanh" | "Bình thường" | "Chậm"
    conversation_stage: str     # "Khởi đầu" | "Thu thập" | "Đánh giá" | "Sẵn sàng"
    progression: str            # "Tăng" | "Giảm" | "Ổn định"

    # Recommendations
    next_action: str
    next_action_icon: str
    urgency: str               # "Ngay" | "Trong 24h" | "Trong tuần" | "Nuture"
    summary: str               # 1-2 câu tóm tắt AI

    # Meta
    analyzed_at: str
    message_sample: list       # preview 3 messages

    def to_dict(self):
        d = asdict(self)
        return d


# ═══════════════════════════════════════════════════════════════════════════════
# CORE ENGINE
# ═══════════════════════════════════════════════════════════════════════════════

CATEGORY_META = {
    "TRANSACTION": {"weight": 0.35, "icon": "💰", "color": "#3fb950", "label": "Mua/Chốt"},
    "SCHEDULING":  {"weight": 0.25, "icon": "📅", "color": "#1877f2", "label": "Lịch hẹn"},
    "QUALIFICATION":{"weight": 0.20,"icon": "💵", "color": "#d29922", "label": "Tài chính"},
    "LEGAL_CHECK": {"weight": 0.10, "icon": "📋", "color": "#bc8cff", "label": "Pháp lý"},
    "RESEARCH":    {"weight": 0.10, "icon": "🔍", "color": "#39d353", "label": "Tìm hiểu"},
    "CONCERN":     {"weight": 0.00, "icon": "⚠️", "color": "#f85149", "label": "Lo ngại"},
}

SIGNAL_MAP = {
    "TRANSACTION":  TRANSACTION_SIGNALS,
    "SCHEDULING":   SCHEDULING_SIGNALS,
    "QUALIFICATION": QUALIFICATION_SIGNALS,
    "LEGAL_CHECK":  LEGAL_SIGNALS,
    "RESEARCH":     RESEARCH_SIGNALS,
    "CONCERN":      CONCERN_SIGNALS,
}


def normalize_text(text: str) -> str:
    """Chuẩn hóa text trước khi match"""
    text = text.lower().strip()
    text = re.sub(r'\s+', ' ', text)
    # Chuẩn hóa số: 4-5 tỷ, 4.5tỷ → 4 tỷ
    text = re.sub(r'(\d)\s*-\s*(\d)', r'\1', text)
    return text


def extract_signals(messages: list[dict]) -> list[SignalMatch]:
    """
    Phân tích toàn bộ hội thoại, trả về danh sách tín hiệu phát hiện được.
    messages: list of {"sender": "customer"|"agent", "text": "...", "timestamp": "..."}
    """
    signals = []
    for idx, msg in enumerate(messages):
        if msg.get("sender") != "customer":
            continue
        text = normalize_text(msg.get("text", ""))
        if not text:
            continue
        for category, pattern_list in SIGNAL_MAP.items():
            for pattern, score, label in pattern_list:
                match = re.search(pattern, text)
                if match:
                    snippet = text[max(0, match.start()-10): match.end()+20].strip()
                    signals.append(SignalMatch(
                        category=category,
                        label=label,
                        score=float(score),
                        snippet=f"...{snippet}...",
                        message_idx=idx,
                    ))
    return signals


def build_category_scores(signals: list[SignalMatch]) -> dict:
    """Tổng hợp điểm theo từng category"""
    cat_signals = {k: [] for k in CATEGORY_META}
    for s in signals:
        if s.category in cat_signals:
            cat_signals[s.category].append(s)

    categories = {}
    for cat, meta in CATEGORY_META.items():
        sigs = cat_signals[cat]
        if not sigs:
            raw = 0.0
        else:
            # Lấy max signal + bonus cho nhiều signals
            scores = [s.score for s in sigs]
            raw = max(scores) + 0.5 * min(sum(s for s in scores if s > 0) * 0.1, 2.0)

        # Normalize to 0-10
        if cat == "CONCERN":
            normalized = min(10, abs(raw))  # concern score riêng
        else:
            normalized = min(10, max(0, raw))

        categories[cat] = CategoryScore(
            category=cat,
            raw_score=round(raw, 2),
            normalized=round(normalized, 1),
            signals=[{"label": s.label, "score": s.score, "snippet": s.snippet} for s in sigs],
            weight=meta["weight"],
            icon=meta["icon"],
            color=meta["color"],
        )
    return categories


def compute_composite(categories: dict) -> float:
    """
    Composite = Σ(category_score × weight)
    CONCERN giảm điểm cuối cùng
    """
    total = 0.0
    for cat, cs in categories.items():
        if cat == "CONCERN":
            continue
        total += cs.normalized * cs.weight
    # Concern penalty: mỗi điểm concern giảm 0.3 điểm tổng
    concern = categories.get("CONCERN")
    if concern:
        total -= concern.normalized * 0.3
    return round(min(10, max(0, total)), 1)


def detect_conversation_stage(signals: list[SignalMatch], msg_count: int) -> str:
    cats = {s.category for s in signals}
    if "TRANSACTION" in cats or "SCHEDULING" in cats:
        return "Sẵn sàng chốt"
    if "QUALIFICATION" in cats or "LEGAL_CHECK" in cats:
        return "Đánh giá & cân nhắc"
    if "RESEARCH" in cats:
        return "Thu thập thông tin"
    return "Khởi đầu / Làm quen"


def detect_progression(messages: list[dict]) -> str:
    """Phân tích xem intent có tăng dần không theo thời gian"""
    customer_msgs = [m for m in messages if m.get("sender") == "customer"]
    if len(customer_msgs) < 3:
        return "Chưa đủ dữ liệu"
    n = len(customer_msgs)
    first_half = customer_msgs[:n//2]
    second_half = customer_msgs[n//2:]
    def count_signals(msgs):
        count = 0
        for m in msgs:
            txt = normalize_text(m.get("text", ""))
            for cat, pats in SIGNAL_MAP.items():
                if cat == "CONCERN":
                    continue
                for p, _, _ in pats:
                    if re.search(p, txt):
                        count += 1
        return count
    first_count  = count_signals(first_half)
    second_count = count_signals(second_half)
    if second_count > first_count * 1.3:
        return "Tăng dần →"
    if second_count < first_count * 0.7:
        return "Giảm dần ↓"
    return "Ổn định →"


def infer_response_time(messages: list[dict]) -> Optional[float]:
    """Tính thời gian phản hồi trung bình từ timestamp"""
    times = []
    prev = None
    prev_sender = None
    for m in messages:
        ts = m.get("timestamp") or m.get("time")
        sender = m.get("sender")
        if not ts or not sender:
            continue
        try:
            for fmt in ["%d/%m %H:%M", "%Y-%m-%dT%H:%M:%S", "%H:%M"]:
                try:
                    t = datetime.strptime(ts.strip(), fmt)
                    break
                except ValueError:
                    continue
            else:
                continue
            if prev is not None and prev_sender != sender:
                diff = abs((t - prev).total_seconds() / 60)
                if 0 < diff < 1440:  # Bỏ diff > 24h (offline)
                    times.append(diff)
            prev = t
            prev_sender = sender
        except Exception:
            continue
    return round(sum(times) / len(times), 1) if times else None


def generate_summary(composite: float, categories: dict, top_signals: list,
                     stage: str, msg_count: int) -> tuple[str, str, str, str]:
    """Tạo next_action, urgency, intent_level, summary"""
    trans = categories.get("TRANSACTION", CategoryScore("", 0, 0, [], 0, "", "")).normalized
    sched = categories.get("SCHEDULING",  CategoryScore("", 0, 0, [], 0, "", "")).normalized
    qual  = categories.get("QUALIFICATION", CategoryScore("", 0, 0, [], 0, "", "")).normalized
    concern = categories.get("CONCERN", CategoryScore("", 0, 0, [], 0, "", "")).normalized

    # Intent level
    if composite >= 8.0:
        level, color, prob = "Rất cao", "#3fb950", "85-95%"
    elif composite >= 6.5:
        level, color, prob = "Cao", "#39d353", "65-80%"
    elif composite >= 4.5:
        level, color, prob = "Trung bình", "#d29922", "35-55%"
    elif composite >= 2.5:
        level, color, prob = "Thấp", "#f97316", "15-30%"
    else:
        level, color, prob = "Rất thấp", "#f85149", "<15%"

    # Next action + urgency
    if trans >= 8 or sched >= 8:
        action, action_icon, urgency = "Gọi điện xác nhận ngay", "📞", "Ngay"
    elif trans >= 5 or sched >= 6:
        action, action_icon, urgency = "Gọi trong 24h tiếp theo", "📲", "Trong 24h"
    elif qual >= 6:
        action, action_icon, urgency = "Gửi thông tin vay/thanh toán", "💌", "Trong tuần"
    elif concern >= 4:
        action, action_icon, urgency = "Xử lý phản đối trước khi follow up", "🤝", "Trong tuần"
    else:
        action, action_icon, urgency = "Nuture qua content phù hợp", "📧", "Nuture"

    # Summary
    top_cats = sorted(
        [(k, v.normalized) for k, v in categories.items() if k != "CONCERN" and v.normalized > 0],
        key=lambda x: -x[1]
    )[:2]
    cat_labels = " & ".join(CATEGORY_META[c]["label"] for c, _ in top_cats) if top_cats else "chung"
    concern_note = f" Có {concern:.0f} điểm lo ngại cần xử lý." if concern >= 3 else ""
    summary = (
        f"Khách ở giai đoạn «{stage}» với intent tập trung vào {cat_labels}."
        f" Điểm tổng hợp {composite}/10 — {level}.{concern_note}"
        f" Đề xuất: {action}."
    )

    return action, action_icon, urgency, level, color, prob, summary


# ═══════════════════════════════════════════════════════════════════════════════
# PUBLIC API
# ═══════════════════════════════════════════════════════════════════════════════

def analyze_intent(messages: list[dict]) -> IntentResult:
    """
    Phân tích intent từ danh sách tin nhắn.

    Args:
        messages: list of {
            "sender": "customer" | "agent",
            "text": str,
            "timestamp": str (optional),
        }

    Returns:
        IntentResult — đầy đủ kết quả phân tích
    """
    if not messages:
        return _empty_result()

    # Step 1: Extract signals
    signals = extract_signals(messages)

    # Step 2: Score per category
    categories = build_category_scores(signals)

    # Step 3: Composite
    composite = compute_composite(categories)

    # Step 4: Conversation analytics
    customer_msgs = [m for m in messages if m.get("sender") == "customer"]
    avg_resp = infer_response_time(messages)
    if avg_resp is None:
        resp_speed = "Không đủ dữ liệu"
    elif avg_resp <= 5:
        resp_speed = "🟢 Rất nhanh (<5 phút)"
    elif avg_resp <= 30:
        resp_speed = "🟡 Nhanh (<30 phút)"
    elif avg_resp <= 120:
        resp_speed = "🟠 Bình thường (<2 giờ)"
    else:
        resp_speed = "🔴 Chậm (>2 giờ)"

    stage = detect_conversation_stage(signals, len(messages))
    progression = detect_progression(messages)

    # Step 5: Summarize
    action, action_icon, urgency, level, color, prob, summary = generate_summary(
        composite, categories, signals, stage, len(messages)
    )

    # Step 6: Top signals
    all_pos = [s for s in signals if s.score > 0]
    top_signals = sorted(all_pos, key=lambda s: -s.score)[:6]

    # Step 7: Confidence
    total_sig = len(signals)
    confidence = "high" if total_sig >= 5 else "medium" if total_sig >= 2 else "low"

    return IntentResult(
        composite_score=composite,
        confidence=confidence,
        intent_level=level,
        intent_color=color,
        purchase_probability=prob,
        categories={k: asdict(v) for k, v in categories.items()},
        all_signals=[asdict(s) for s in signals],
        top_signals=[asdict(s) for s in top_signals],
        message_count=len(messages),
        customer_message_count=len(customer_msgs),
        avg_response_time_min=avg_resp,
        response_speed=resp_speed,
        conversation_stage=stage,
        progression=progression,
        next_action=action,
        next_action_icon=action_icon,
        urgency=urgency,
        summary=summary,
        analyzed_at=datetime.now().strftime("%d/%m/%Y %H:%M"),
        message_sample=[
            {"sender": m["sender"], "text": m["text"][:60] + "…" if len(m.get("text","")) > 60 else m.get("text",""),
             "timestamp": m.get("timestamp", "")}
            for m in messages[-3:]
        ],
    )


def analyze_single_message(text: str) -> dict:
    """Phân tích nhanh một tin nhắn đơn lẻ"""
    result = analyze_intent([{"sender": "customer", "text": text, "timestamp": ""}])
    return {
        "composite_score": result.composite_score,
        "intent_level":    result.intent_level,
        "signals":         result.top_signals,
        "next_action":     result.next_action,
        "urgency":         result.urgency,
    }


def _empty_result() -> IntentResult:
    return IntentResult(
        composite_score=0, confidence="low", intent_level="Rất thấp",
        intent_color="#8b949e", purchase_probability="<5%",
        categories={}, all_signals=[], top_signals=[],
        message_count=0, customer_message_count=0,
        avg_response_time_min=None, response_speed="—",
        conversation_stage="Chưa có dữ liệu", progression="—",
        next_action="Thu thập tin nhắn từ Messenger", next_action_icon="💬",
        urgency="Nuture", summary="Không có đủ dữ liệu để phân tích.",
        analyzed_at=datetime.now().strftime("%d/%m/%Y %H:%M"), message_sample=[],
    )
