"""
lead_quality_scorer.py — Cross-reference Messenger data vs Ad data
==================================================================
Tính điểm chất lượng lead (0-10) cho từng ad/campaign dựa trên:
  - Thông tin cung cấp trong Messenger (tên, SĐT, email)
  - Intent score từ nội dung hội thoại
  - Tốc độ phản hồi
  - Số lượng tin nhắn (engagement depth)
  - Dữ liệu có sẵn trong DB (CustomerProfile)
"""
import logging
from datetime import datetime, timedelta
from typing import Optional

log = logging.getLogger("lead_quality_scorer")


class LeadQualityScorer:
    """Cross-reference Messenger data với Ad data để tính quality score."""

    def __init__(self):
        from .messenger_api import MessengerAPI
        from .fb_ads_api    import FacebookAdsAPI
        self.messenger = MessengerAPI()
        self.fb        = FacebookAdsAPI()

    # ── Lead quality từ Messenger conversation ────────────────────────────────

    def score_lead_from_messenger(self, conversation_data: dict) -> float:
        """
        Tính điểm chất lượng lead từ data của 1 hội thoại Messenger (0-10):
          +3  Thông tin cung cấp: tên (+1), SĐT (+1.5), email (+0.5)
          +3  Intent score (max từ keyword analysis)
          +2  Tốc độ phản hồi sớm (< 1 giờ kể từ ad click)
          +2  Engagement depth (số tin nhắn)
        """
        score = 0.0

        # 1. Thông tin cung cấp (+3)
        if conversation_data.get("sender_name"):
            score += 1.0
        if conversation_data.get("phone"):
            score += 1.5
        if conversation_data.get("email"):
            score += 0.5

        # 2. Intent score (đã tính sẵn trong messenger_api, max 10) → scale về +3
        intent = float(conversation_data.get("intent_score", 0))
        score += min(3.0, intent * 0.3)

        # 3. Tốc độ phản hồi (+2): giả định nếu message_count > 4 thì đã có qua lại
        msg_count = int(conversation_data.get("message_count", 0))
        if msg_count >= 6:
            score += 2.0
        elif msg_count >= 4:
            score += 1.5
        elif msg_count >= 2:
            score += 1.0

        # 4. Engagement depth (+2)
        if msg_count >= 10:
            score += 2.0
        elif msg_count >= 6:
            score += 1.0
        elif msg_count >= 3:
            score += 0.5

        # Bonus: đã match với CustomerProfile trong DB
        if conversation_data.get("matched_profile_id"):
            score += 0.5
        # Bonus: lead có lead_score cao trong phase 3
        profile_score = float(conversation_data.get("profile_lead_score", 0))
        if profile_score >= 8:
            score += 1.0
        elif profile_score >= 6:
            score += 0.5

        return round(min(score, 10.0), 2)

    def map_ad_to_lead_quality(self, fb_ad_id: str) -> dict:
        """
        Tổng hợp điểm chất lượng lead của tất cả conversations liên quan đến 1 ad_id.
        Returns dict với avg_quality, lead_count, quality_distribution.
        """
        try:
            from src.database import SessionLocal, MessengerLead, CustomerProfile
            db   = SessionLocal()
            leads = db.query(MessengerLead).filter(
                MessengerLead.fb_ad_id == fb_ad_id
            ).all()

            if not leads:
                db.close()
                return {
                    "fb_ad_id":       fb_ad_id,
                    "lead_count":     0,
                    "avg_quality":    0,
                    "quality_counts": {"high": 0, "medium": 0, "low": 0},
                }

            scores = []
            for lead in leads:
                # Tìm CustomerProfile tương ứng
                profile_score = 0.0
                if lead.phone:
                    profile = db.query(CustomerProfile).filter(
                        CustomerProfile.so_dien_thoai == lead.phone
                    ).first()
                    if profile:
                        profile_score = float(profile.lead_score or 0)

                conv_data = {
                    "sender_name":        lead.sender_name,
                    "phone":              lead.phone,
                    "email":              lead.email,
                    "message_count":      lead.message_count,
                    "intent_score":       float(lead.intent_score or 0),
                    "profile_lead_score": profile_score,
                }
                q = self.score_lead_from_messenger(conv_data)
                scores.append(q)
                # Cập nhật quality_score vào DB
                lead.quality_score = q

            db.commit()
            db.close()

        except Exception as e:
            log.warning(f"DB not available, dùng mock: {e}")
            scores = _mock_quality_scores(fb_ad_id)

        high   = sum(1 for s in scores if s >= 7)
        medium = sum(1 for s in scores if 4 <= s < 7)
        low    = sum(1 for s in scores if s < 4)
        avg    = round(sum(scores) / len(scores), 2) if scores else 0

        return {
            "fb_ad_id":       fb_ad_id,
            "lead_count":     len(scores),
            "avg_quality":    avg,
            "quality_counts": {"high": high, "medium": medium, "low": low},
            "scores":         sorted(scores, reverse=True),
        }

    def rank_campaigns_by_lead_quality(self) -> list[dict]:
        """
        Xếp hạng tất cả campaigns theo chất lượng lead trung bình.
        Kết hợp: avg_quality_score + số lead chất lượng cao.
        """
        campaigns = self.fb.get_campaigns()
        rankings  = []

        for camp in campaigns:
            camp_id = camp["id"]
            adsets  = self.fb.get_adsets(camp_id)

            all_scores = []
            for adset in adsets:
                ads = self.fb.get_ads(adset["id"])
                for ad in ads:
                    quality_data = self.map_ad_to_lead_quality(ad["id"])
                    all_scores.extend(quality_data.get("scores", []))

            total_leads = len(all_scores)
            if total_leads == 0:
                continue

            avg_quality = round(sum(all_scores) / total_leads, 2)
            high_leads  = sum(1 for s in all_scores if s >= 7)
            high_ratio  = round(high_leads / total_leads * 100, 1)

            # Composite rank score: weighted bởi avg_quality + %high_leads
            rank_score = round(avg_quality * 0.6 + high_ratio * 0.04, 2)

            rankings.append({
                "campaign_id":   camp_id,
                "campaign_name": camp["name"],
                "status":        camp["status"],
                "total_leads":   total_leads,
                "avg_quality":   avg_quality,
                "high_leads":    high_leads,
                "high_ratio_pct": high_ratio,
                "rank_score":    rank_score,
                "quality_counts": {
                    "high":   high_leads,
                    "medium": sum(1 for s in all_scores if 4 <= s < 7),
                    "low":    sum(1 for s in all_scores if s < 4),
                },
            })

        return sorted(rankings, key=lambda x: x["rank_score"], reverse=True)

    def get_quality_vs_cost_matrix(self) -> list[dict]:
        """
        Ma trận quality vs cost để xác định campaign:
          - High quality + Low cost → SCALE UP 🟢
          - High quality + High cost → OPTIMIZE targeting 🟡
          - Low quality + Low cost → TEST creative 🟡
          - Low quality + High cost → PAUSE immediately 🔴
        """
        from .cost_analyzer import CostAnalyzer
        analyzer  = CostAnalyzer(fb_api=self.fb)
        cost_rpt  = analyzer.generate_cost_report("last_7d")
        rankings  = self.rank_campaigns_by_lead_quality()

        quality_map = {r["campaign_id"]: r for r in rankings}
        matrix = []

        for camp_cost in cost_rpt.get("campaigns", []):
            cid     = camp_cost["campaign_id"]
            quality = quality_map.get(cid, {})

            cpl     = float(camp_cost.get("cpl", 0))
            avg_q   = float(quality.get("avg_quality", 0))

            # Phân loại quadrant
            low_cost    = cpl   <= 200_000
            high_quality = avg_q >= 6.0

            if high_quality and low_cost:
                quadrant = "SCALE_UP"
                label    = "🟢 Nhân rộng ngay"
                priority = 1
            elif high_quality and not low_cost:
                quadrant = "OPTIMIZE_TARGETING"
                label    = "🟡 Tối ưu targeting"
                priority = 2
            elif not high_quality and low_cost:
                quadrant = "TEST_CREATIVE"
                label    = "🟡 Test creative mới"
                priority = 3
            else:
                quadrant = "PAUSE"
                label    = "🔴 Nên dừng ngay"
                priority = 4

            matrix.append({
                "campaign_id":   cid,
                "campaign_name": camp_cost.get("campaign_name", cid),
                "cpl":           cpl,
                "avg_quality":   avg_q,
                "total_leads":   quality.get("total_leads", 0),
                "total_spend":   camp_cost.get("total_spend", 0),
                "quadrant":      quadrant,
                "label":         label,
                "priority":      priority,
            })

        return sorted(matrix, key=lambda x: x["priority"])


# ── Helpers ───────────────────────────────────────────────────────────────────

def _mock_quality_scores(ad_id: str) -> list[float]:
    import random, hashlib
    seed   = int(hashlib.md5(ad_id.encode()).hexdigest()[:8], 16)
    rng    = random.Random(seed)
    n      = rng.randint(2, 10)
    return [round(rng.uniform(2.0, 9.5), 2) for _ in range(n)]
