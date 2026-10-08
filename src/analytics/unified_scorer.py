"""
src/analytics/unified_scorer.py
=================================
Unified Lead Score (0-100) — thay thế 2 scoring models hiện tại.

5 chiều đo lường:
  [A] Completeness    30pts  — có đủ phone / email / name / address?
  [B] Source Quality  25pts  — tier của nguồn dữ liệu (banking_vip=25, telecom=6.7)
  [C] Cross-source    20pts  — xuất hiện ở bao nhiêu nguồn?
  [D] Recency         15pts  — file nguồn có mới không?
  [E] Behavioral      10pts  — Messenger intent (nếu có)

Grade:
  S  (85-100)  → Giao Sales giỏi nhất, gọi ngay
  A  (70-84)   → Ưu tiên cao, gọi trong tuần
  B  (55-69)   → Theo dõi, nurture
  C  (40-54)   → Mass outreach / email
  D  (<40)     → Cold data, lưu trữ
"""

from datetime import datetime
from typing import Optional


# ══════════════════════════════════════════════════════
# A. COMPLETENESS SCORE (Max 30pts)
# ══════════════════════════════════════════════════════

def score_completeness(phone, email, name, address) -> float:
    """
    Data completeness — phone là critical nhất.
    phone:   20pts (core identifier, without it lead is useless)
    email:    5pts
    name:     3pts
    address:  2pts
    """
    s = 0.0
    if phone and str(phone).strip() not in ("", "nan", "None"):
        s += 20.0
    if email and str(email).strip() not in ("", "nan", "None") and "@" in str(email):
        s += 5.0
    name_str = str(name or "").strip().lower()
    if name_str and name_str not in ("", "none", "nan", "unknown", "n/a", "-"):
        s += 3.0
    addr_str = str(address or "").strip()
    if addr_str and len(addr_str) > 4 and addr_str.lower() not in ("nan", "none"):
        s += 2.0
    return s


# ══════════════════════════════════════════════════════
# B. SOURCE QUALITY SCORE (Max 25pts)
# ══════════════════════════════════════════════════════

def score_source_quality(source_weight: float) -> float:
    """
    Linear scale: weight [0.25 → 1.0] maps to score [0 → 25]
    banking_vip (1.00) = 25pts
    telecom     (0.40) = 4pts
    unknown     (0.25) = 0pts
    """
    # Clip to [0.25, 1.0] range
    w = max(0.25, min(1.0, source_weight or 0.25))
    normalized = (w - 0.25) / (1.0 - 0.25)  # → [0, 1]
    return round(normalized * 25.0, 2)


# ══════════════════════════════════════════════════════
# C. CROSS-SOURCE SCORE (Max 20pts)
# ══════════════════════════════════════════════════════

def score_cross_source(source_count: int) -> float:
    """
    Cross-validation signal — xuất hiện nhiều nguồn = độ tin cậy cao.
    1 nguồn  →  2pts (chưa xác thực)
    2 nguồn  →  6pts
    3 nguồn  → 10pts
    4 nguồn  → 15pts
    6+ nguồn → 20pts (max)
    """
    if source_count >= 6: return 20.0
    if source_count >= 5: return 18.0
    if source_count >= 4: return 15.0
    if source_count >= 3: return 10.0
    if source_count >= 2: return 6.0
    return 2.0


# ══════════════════════════════════════════════════════
# D. RECENCY SCORE (Max 15pts)
# ══════════════════════════════════════════════════════

def score_recency(latest_file_ts: Optional[datetime] = None) -> float:
    """
    Data freshness — file nguồn mới = lead còn active.
    < 3 tháng  → 15pts
    3-6 tháng  → 12pts
    6-12 tháng →  9pts
    1-2 năm    →  6pts
    2-5 năm    →  3pts
    > 5 năm    →  0pts (số bị đổi chủ, không còn giá trị)
    """
    if not latest_file_ts:
        return 5.0  # Mid-score khi không có timestamp

    if isinstance(latest_file_ts, str):
        try:
            latest_file_ts = datetime.fromisoformat(latest_file_ts)
        except (ValueError, TypeError):
            return 5.0

    days = (datetime.now() - latest_file_ts).days

    if days <= 90:   return 15.0
    if days <= 180:  return 12.0
    if days <= 365:  return 9.0
    if days <= 730:  return 6.0
    if days <= 1825: return 3.0
    return 0.0


# ══════════════════════════════════════════════════════
# E. BEHAVIORAL SCORE (Max 10pts)
# ══════════════════════════════════════════════════════

def score_behavioral(
    intent_score: float = 0,
    messenger_phone: bool = False,
    quality_score: float = 0,
) -> float:
    """
    Messenger behavioral signals — chỉ có khi có conversation.
    intent_score (0-10)  → 0-7pts proportional
    messenger_phone      → +2pts (đã cung cấp SĐT qua chat)
    quality_score >= 7   → +1pt bonus
    """
    s = 0.0
    if intent_score and intent_score > 0:
        s += min(7.0, float(intent_score) * 0.7)
    if messenger_phone:
        s += 2.0
    if quality_score and float(quality_score) >= 7:
        s += 1.0
    return round(min(s, 10.0), 2)


# ══════════════════════════════════════════════════════
# COMPOSITE UNIFIED SCORE
# ══════════════════════════════════════════════════════

GRADE_MAP = [
    (85, "S"),
    (70, "A"),
    (55, "B"),
    (40, "C"),
    (0,  "D"),
]

GRADE_LABELS = {
    "S": "VIP Elite — Giao Sales giỏi nhất, gọi ngay",
    "A": "Hot Lead — Ưu tiên cao, gọi trong tuần",
    "B": "Warm Lead — Theo dõi, nurture",
    "C": "Cold Lead — Mass outreach / email",
    "D": "Very Cold — Lưu trữ / bỏ qua",
}


def calculate_unified_score(
    phone,
    email,
    name,
    address,
    source_weight: float,
    source_count: int,
    latest_file_ts: Optional[datetime] = None,
    intent_score: float = 0,
    messenger_phone: bool = False,
    quality_score: float = 0,
) -> dict:
    """
    Tính Unified Lead Score (0-100) với breakdown đầy đủ.

    Args:
        phone:            Số điện thoại đã chuẩn hóa
        email:            Email
        name:             Họ tên
        address:          Địa chỉ
        source_weight:    Trọng số tier của nguồn (0.25-1.0)
        source_count:     Số nguồn khác nhau có chứa lead này
        latest_file_ts:   Timestamp của file nguồn gần nhất
        intent_score:     Điểm intent từ Messenger (0-10), default 0
        messenger_phone:  True nếu KH đã gửi SĐT qua Messenger
        quality_score:    Lead quality score từ Ads engine (0-10)

    Returns:
        dict: {
            unified_score: float,
            grade: str,
            grade_label: str,
            breakdown: {completeness, source_quality, cross_source, recency, behavioral},
            max_possible: 100.0,
        }
    """
    a = score_completeness(phone, email, name, address)
    b = score_source_quality(source_weight)
    c = score_cross_source(source_count)
    d = score_recency(latest_file_ts)
    e = score_behavioral(intent_score, messenger_phone, quality_score)

    total = round(min(a + b + c + d + e, 100.0), 1)

    # Determine grade
    grade = "D"
    for threshold, g in GRADE_MAP:
        if total >= threshold:
            grade = g
            break

    return {
        "unified_score": total,
        "grade":         grade,
        "grade_label":   GRADE_LABELS[grade],
        "breakdown": {
            "completeness":   round(a, 1),
            "source_quality": round(b, 1),
            "cross_source":   round(c, 1),
            "recency":        round(d, 1),
            "behavioral":     round(e, 1),
        },
        "max_possible": 100.0,
    }


def score_to_legacy_10(unified_score: float) -> float:
    """Convert 100-point score to legacy 0-10 scale for backward compat."""
    return round(min(unified_score / 10.0, 10.0), 1)
