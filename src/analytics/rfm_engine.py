"""
src/analytics/rfm_engine.py
============================
RFM (Recency - Frequency - Monetary) Model cho Lead Scoring.

Thay thế behavioral model dựa vào hot_leads (thường rỗng)
bằng signals từ dữ liệu file nguồn — luôn có sẵn.

  R = Recency:   File nguồn mới nhất là bao lâu trước?
  F = Frequency: Lead xuất hiện ở bao nhiêu nguồn khác nhau?
  M = Monetary:  Nguồn dữ liệu có chất lượng cao (banking_vip) hay thấp (telecom)?

RFM Composite = R×0.30 + F×0.40 + M×0.30 → Scale 0-10
"""

from datetime import datetime
from typing import Optional


# ══════════════════════════════════════════════════════
# 1. RECENCY SCORE (1-5)
# ══════════════════════════════════════════════════════

def recency_score(latest_file_ts: Optional[datetime] = None) -> float:
    """
    File nguồn gần nhất là bao lâu trước? Score 1-5.
    5 = < 6 tháng (data nóng)
    1 = > 5 năm   (data lạnh)
    """
    if not latest_file_ts:
        return 1.0  # Không biết → assume worst case

    if isinstance(latest_file_ts, str):
        try:
            latest_file_ts = datetime.fromisoformat(latest_file_ts)
        except (ValueError, TypeError):
            return 1.0

    days = (datetime.now() - latest_file_ts).days

    if days <= 90:   return 5.0   # < 3 tháng
    if days <= 180:  return 4.5   # 3-6 tháng
    if days <= 365:  return 4.0   # 6-12 tháng
    if days <= 730:  return 3.0   # 1-2 năm
    if days <= 1095: return 2.0   # 2-3 năm
    if days <= 1825: return 1.5   # 3-5 năm
    return 1.0                     # > 5 năm


# ══════════════════════════════════════════════════════
# 2. FREQUENCY SCORE (1-5)
# ══════════════════════════════════════════════════════

def frequency_score(source_count: int) -> float:
    """
    Lead xuất hiện ở bao nhiêu nguồn dữ liệu khác nhau? Score 1-5.
    5 = 6+ nguồn  (cross-verified, rất đáng tin)
    1 = 1 nguồn   (chưa xác thực chéo)
    """
    if source_count >= 7: return 5.0
    if source_count >= 5: return 4.5
    if source_count >= 4: return 4.0
    if source_count >= 3: return 3.0
    if source_count >= 2: return 2.0
    return 1.0


# ══════════════════════════════════════════════════════
# 3. MONETARY SCORE (1-5)
# ══════════════════════════════════════════════════════

def monetary_score(source_weight: float) -> float:
    """
    Chất lượng nguồn dữ liệu → proxy cho "mức chi tiêu". Score 1-5.
    5 = banking_vip (weight=1.00)
    1 = unknown     (weight=0.25)
    """
    # Map weight range [0.25, 1.00] → score [1, 5]
    if source_weight >= 0.95: return 5.0
    if source_weight >= 0.85: return 4.5
    if source_weight >= 0.75: return 4.0
    if source_weight >= 0.60: return 3.0
    if source_weight >= 0.45: return 2.0
    if source_weight >= 0.35: return 1.5
    return 1.0


# ══════════════════════════════════════════════════════
# 4. COMPOSITE RFM (0-10)
# ══════════════════════════════════════════════════════

def calculate_rfm(
    source_count: int,
    source_weight: float,
    latest_file_ts: Optional[datetime] = None,
) -> float:
    """
    RFM composite score — scale to 0-10.

    Formula: (R*0.30 + F*0.40 + M*0.30) * 2
    Min: (1*0.30 + 1*0.40 + 1*0.30) * 2 = 2.0
    Max: (5*0.30 + 5*0.40 + 5*0.30) * 2 = 10.0

    Args:
        source_count:    Number of distinct sources containing this lead
        source_weight:   Quality weight of best source (0.25-1.00)
        latest_file_ts:  Datetime of most recent source file

    Returns:
        float 0-10
    """
    R = recency_score(latest_file_ts)
    F = frequency_score(source_count)
    M = monetary_score(source_weight)

    raw = R * 0.30 + F * 0.40 + M * 0.30  # max = 5.0
    return round(raw * 2.0, 2)              # scale to 0-10


def rfm_segment(rfm_score: float) -> str:
    """Map RFM score to human-readable segment label."""
    if rfm_score >= 9.0: return "Champions"
    if rfm_score >= 7.5: return "Loyal"
    if rfm_score >= 6.0: return "Potential Loyalist"
    if rfm_score >= 4.5: return "At Risk"
    if rfm_score >= 3.0: return "Hibernating"
    return "Lost"
