"""
campaign_recommender.py — Đề xuất nhân rộng campaign hiệu quả
=============================================================
Xác định "winner" campaigns/adsets và tạo kế hoạch scale-up cụ thể.
"""
import logging
from datetime import datetime

log = logging.getLogger("campaign_recommender")


class CampaignRecommender:
    """Tạo đề xuất nhân rộng campaign hiệu quả."""

    def __init__(self,
                 threshold_quality: float = 7.0,
                 threshold_cpl: int = 200_000):
        from .fb_ads_api          import FacebookAdsAPI
        from .cost_analyzer       import CostAnalyzer
        from .lead_quality_scorer import LeadQualityScorer

        self.fb        = FacebookAdsAPI()
        self.analyzer  = CostAnalyzer(fb_api=self.fb)
        self.scorer    = LeadQualityScorer()
        self.threshold_quality = threshold_quality
        self.threshold_cpl     = threshold_cpl

    # ── Identify winners ──────────────────────────────────────────────────────

    def identify_winners(self) -> list[dict]:
        """
        Tìm campaigns/adsets thỏa mãn cả hai điều kiện:
          - avg_quality >= threshold_quality (mặc định 7.0)
          - cpl <= threshold_cpl (mặc định 200,000đ)
        """
        matrix = self.scorer.get_quality_vs_cost_matrix()
        winners = [
            item for item in matrix
            if item["quadrant"] == "SCALE_UP"
        ]
        log.info(f"🏆 Tìm thấy {len(winners)} winner campaigns")
        return winners

    def recommend_scale_up(self, winners: list[dict] = None) -> list[dict]:
        """
        Tạo recommendation chi tiết cho từng winner:
          - Mức ngân sách đề xuất
          - Lý do cụ thể
          - Expected outcome
        """
        if winners is None:
            winners = self.identify_winners()

        recommendations = []
        for w in winners:
            camp_id   = w["campaign_id"]
            camp_name = w["campaign_name"]
            curr_spend = float(w["total_spend"])
            cpl        = float(w["cpl"])
            avg_q      = float(w["avg_quality"])
            total_l    = int(w["total_leads"])

            # Đề xuất ngân sách: scale theo tiềm năng
            if avg_q >= 9.0:
                scale_factor = 3.0
                rationale    = "Quality score xuất sắc (≥9) — nhân 3x ngân sách"
            elif avg_q >= 8.0:
                scale_factor = 2.0
                rationale    = "Quality score rất cao (≥8) — nhân đôi ngân sách"
            else:
                scale_factor = 1.5
                rationale    = "Quality score tốt (≥7) — tăng 50% ngân sách"

            new_daily_budget = int(curr_spend / 7 * scale_factor)  # chia 7 ngày

            # Expected leads nếu scale
            expected_leads = int(total_l * scale_factor)
            expected_spend = int(curr_spend * scale_factor)

            # Adsets trong campaign để nhân rộng
            adsets       = self.fb.get_adsets(camp_id)
            top_adsets   = adsets[:3]  # Scale top 3 adsets trước

            recommendations.append({
                "campaign_id":     camp_id,
                "campaign_name":   camp_name,
                "current_metrics": {
                    "spend_7d":    curr_spend,
                    "cpl":         cpl,
                    "avg_quality": avg_q,
                    "total_leads": total_l,
                },
                "recommendation": {
                    "action":           "SCALE_UP",
                    "scale_factor":     scale_factor,
                    "rationale":        rationale,
                    "new_daily_budget": new_daily_budget,
                    "adsets_to_scale":  [
                        {
                            "adset_id":   adset["id"],
                            "adset_name": adset.get("name", adset["id"]),
                            "action":     "duplicate_and_scale",
                            "new_budget": int(int(adset.get("daily_budget", 100_000)) * scale_factor),
                        }
                        for adset in top_adsets
                    ],
                },
                "expected_outcome": {
                    "leads_7d":   expected_leads,
                    "spend_7d":   expected_spend,
                    "est_cpl":    int(expected_spend / expected_leads) if expected_leads else 0,
                },
                "priority":   1 if avg_q >= 8 else 2,
                "created_at": datetime.now().isoformat(),
            })

        return sorted(recommendations, key=lambda x: x["priority"])

    def generate_recommendations_report(self) -> dict:
        """
        Tạo báo cáo tổng hợp đề xuất — dùng cho dashboard và email.
        """
        matrix          = self.scorer.get_quality_vs_cost_matrix()
        winners         = [m for m in matrix if m["quadrant"] == "SCALE_UP"]
        to_optimize     = [m for m in matrix if m["quadrant"] in ("OPTIMIZE_TARGETING", "TEST_CREATIVE")]
        to_pause        = [m for m in matrix if m["quadrant"] == "PAUSE"]

        recommendations = self.recommend_scale_up(winners)

        total_potential_spend = sum(
            r["expected_outcome"]["spend_7d"] - r["current_metrics"]["spend_7d"]
            for r in recommendations
        )
        total_expected_leads = sum(
            r["expected_outcome"]["leads_7d"]
            for r in recommendations
        )

        return {
            "generated_at":   datetime.now().isoformat(),
            "summary": {
                "winners":        len(winners),
                "to_optimize":    len(to_optimize),
                "to_pause":       len(to_pause),
                "total_campaigns": len(matrix),
                "extra_budget_needed_7d": total_potential_spend,
                "expected_extra_leads_7d": total_expected_leads,
            },
            "scale_up_plans":        recommendations,
            "optimize_campaigns":    [
                {
                    "campaign_id":   m["campaign_id"],
                    "campaign_name": m["campaign_name"],
                    "quadrant":      m["quadrant"],
                    "label":         m["label"],
                    "cpl":           m["cpl"],
                    "avg_quality":   m["avg_quality"],
                    "suggestion":    (
                        "Thử narrow targeting hoặc lookalike audience chất lượng hơn"
                        if m["quadrant"] == "OPTIMIZE_TARGETING"
                        else "Thử creative mới: video testimonial, carousel dự án"
                    ),
                }
                for m in to_optimize
            ],
            "pause_campaigns": [
                {
                    "campaign_id":   m["campaign_id"],
                    "campaign_name": m["campaign_name"],
                    "cpl":           m["cpl"],
                    "avg_quality":   m["avg_quality"],
                    "label":         m["label"],
                    "reason":        f"CPL {m['cpl']:,.0f}đ cao + quality {m['avg_quality']:.1f} thấp",
                }
                for m in to_pause
            ],
            "all_campaigns_matrix": matrix,
        }
