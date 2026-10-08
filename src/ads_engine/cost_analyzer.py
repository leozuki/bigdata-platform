"""
cost_analyzer.py — Phân tích sâu chỉ số chi phí Facebook Ads
============================================================
Tính toán & đánh giá: CPL, CPM, CPC, CTR, Frequency, ROAS, CPA
So sánh với ngưỡng chuẩn ngành BĐS Việt Nam.
Phát hiện anomaly và tạo báo cáo tổng hợp.
"""
import os
import logging
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd

log = logging.getLogger("cost_analyzer")

# ── Ngưỡng chuẩn ngành BĐS Việt Nam ─────────────────────────────────────────
# Có thể override qua env hoặc tham số khi gọi hàm
BENCHMARKS = {
    "cpl": {           # Cost Per Lead (VND)
        "good":   float(os.getenv("BENCH_CPL_GOOD",   "150000")),
        "medium": float(os.getenv("BENCH_CPL_MEDIUM",  "400000")),
        # > medium = cần optimize
    },
    "cpm": {           # Cost Per 1000 Impressions (VND)
        "good":   float(os.getenv("BENCH_CPM_GOOD",   "50000")),
        "medium": float(os.getenv("BENCH_CPM_MEDIUM", "100000")),
    },
    "cpc": {           # Cost Per Click (VND)
        "good":   float(os.getenv("BENCH_CPC_GOOD",   "5000")),
        "medium": float(os.getenv("BENCH_CPC_MEDIUM", "15000")),
    },
    "ctr": {           # Click-Through Rate (%)
        "good":   float(os.getenv("BENCH_CTR_GOOD",   "2.0")),
        "medium": float(os.getenv("BENCH_CTR_MEDIUM", "1.0")),
        # < medium = cần optimize
    },
    "frequency": {     # Tần suất hiển thị/user
        "good":   float(os.getenv("BENCH_FREQ_GOOD",   "2.5")),
        "medium": float(os.getenv("BENCH_FREQ_MEDIUM", "3.5")),
        # > medium = ad fatigue
    },
    "conv_rate": {     # Conversion rate leads/clicks (%)
        "good":   float(os.getenv("BENCH_CONV_GOOD",   "8.0")),
        "medium": float(os.getenv("BENCH_CONV_MEDIUM", "4.0")),
    },
}


class CostAnalyzer:
    """Phân tích chi phí quảng cáo theo nhiều chiều."""

    def __init__(self, fb_api=None):
        from .fb_ads_api import FacebookAdsAPI
        self.fb = fb_api or FacebookAdsAPI()

    # ── Tính các chỉ số ──────────────────────────────────────────────────────

    @staticmethod
    def compute_cpl(spend: float, leads: int) -> float:
        """Cost Per Lead (VND)."""
        return round(spend / leads, 0) if leads > 0 else 0.0

    @staticmethod
    def compute_quality_cpl(spend: float, quality_leads: int) -> float:
        """CPL chỉ tính lead chất lượng cao (quality_score >= 6)."""
        return round(spend / quality_leads, 0) if quality_leads > 0 else 0.0

    @staticmethod
    def compute_conv_rate(leads: int, clicks: int) -> float:
        """Tỷ lệ chuyển đổi click → lead (%)."""
        return round(leads / clicks * 100, 2) if clicks > 0 else 0.0

    @staticmethod
    def rate_metric(metric: str, value: float) -> str:
        """Trả về 'good' | 'medium' | 'poor' dựa trên ngưỡng chuẩn."""
        bench = BENCHMARKS.get(metric)
        if not bench:
            return "unknown"

        # Metrics mà cao hơn là tốt hơn
        higher_is_better = metric in ("ctr", "conv_rate")

        if higher_is_better:
            if value >= bench["good"]:   return "good"
            if value >= bench["medium"]: return "medium"
            return "poor"
        else:
            if value <= bench["good"]:   return "good"
            if value <= bench["medium"]: return "medium"
            return "poor"

    # ── Phân tích theo campaign / adset ──────────────────────────────────────

    def analyze_campaign_costs(self, campaign_id: str,
                               date_preset: str = "last_7d") -> dict:
        """
        Phân tích toàn diện chi phí của 1 campaign.
        Returns dict với tất cả metrics + đánh giá + alerts.
        """
        rows = self.fb.get_insights(campaign_id, date_preset=date_preset,
                                    level="adset")
        if not rows:
            return {"error": "Không có dữ liệu insights"}

        df = _normalize_insights(rows)

        # Tổng hợp
        total_spend  = df["spend"].sum()
        total_clicks = df["clicks"].sum()
        total_leads  = df["leads"].sum()
        total_reach  = df["reach"].sum()
        total_impr   = df["impressions"].sum()
        avg_cpm      = df["cpm"].mean()
        avg_ctr      = df["ctr"].mean()
        avg_freq     = df["frequency"].mean()
        avg_cpc      = df["cpc"].mean()

        cpl       = self.compute_cpl(total_spend, total_leads)
        conv_rate = self.compute_conv_rate(total_leads, total_clicks)

        result = {
            "campaign_id":    campaign_id,
            "date_preset":    date_preset,
            "date_analyzed":  datetime.now().isoformat(),
            # Raw metrics
            "total_spend":    total_spend,
            "total_clicks":   int(total_clicks),
            "total_leads":    int(total_leads),
            "total_reach":    int(total_reach),
            "total_impressions": int(total_impr),
            # Computed
            "cpl":      cpl,
            "cpm":      round(avg_cpm, 2),
            "ctr":      round(avg_ctr, 2),
            "cpc":      round(avg_cpc, 2),
            "frequency": round(avg_freq, 2),
            "conv_rate": conv_rate,
            # Ratings
            "ratings": {
                "cpl":       self.rate_metric("cpl", cpl),
                "cpm":       self.rate_metric("cpm", avg_cpm),
                "ctr":       self.rate_metric("ctr", avg_ctr),
                "cpc":       self.rate_metric("cpc", avg_cpc),
                "frequency": self.rate_metric("frequency", avg_freq),
                "conv_rate": self.rate_metric("conv_rate", conv_rate),
            },
            # Breakdowns by adset
            "adset_breakdown": df.to_dict(orient="records"),
            # Alerts
            "alerts":  self.detect_anomalies(df),
        }
        return result

    def detect_anomalies(self, df: pd.DataFrame) -> list[dict]:
        """
        Phát hiện các chỉ số bất thường cần xử lý gấp.
        """
        alerts = []
        for _, row in df.iterrows():
            adset_id   = row.get("adset_id", "")
            adset_name = row.get("adset_name", adset_id)

            # CPL quá cao
            if row.get("leads", 0) > 0:
                cpl = self.compute_cpl(row["spend"], row["leads"])
                if cpl > BENCHMARKS["cpl"]["medium"]:
                    alerts.append({
                        "type":     "HIGH_CPL",
                        "severity": "critical",
                        "adset":    adset_name,
                        "value":    cpl,
                        "message":  f"CPL {cpl:,.0f}đ vượt ngưỡng {BENCHMARKS['cpl']['medium']:,.0f}đ",
                    })

            # Frequency quá cao → ad fatigue
            if row.get("frequency", 0) > BENCHMARKS["frequency"]["medium"]:
                alerts.append({
                    "type":     "AD_FATIGUE",
                    "severity": "warning",
                    "adset":    adset_name,
                    "value":    row["frequency"],
                    "message":  f"Frequency {row['frequency']:.1f}x — cần refresh creative",
                })

            # CTR quá thấp
            if row.get("ctr", 0) < BENCHMARKS["ctr"]["medium"]:
                alerts.append({
                    "type":     "LOW_CTR",
                    "severity": "warning",
                    "adset":    adset_name,
                    "value":    row["ctr"],
                    "message":  f"CTR {row['ctr']:.2f}% thấp — content không hấp dẫn",
                })

            # CPM bùng nổ (> 200% ngưỡng medium)
            if row.get("cpm", 0) > BENCHMARKS["cpm"]["medium"] * 2:
                alerts.append({
                    "type":     "CPM_SPIKE",
                    "severity": "warning",
                    "adset":    adset_name,
                    "value":    row["cpm"],
                    "message":  f"CPM {row['cpm']:,.0f}đ bất thường — kiểm tra targeting",
                })

        return alerts

    def generate_cost_report(self, date_preset: str = "last_7d") -> dict:
        """
        Báo cáo tổng hợp tất cả campaigns.
        """
        from .fb_ads_api import FacebookAdsAPI
        fb       = FacebookAdsAPI()
        camps    = fb.get_campaigns()
        report   = []

        for camp in camps:
            camp_id = camp["id"]
            try:
                analysis = self.analyze_campaign_costs(camp_id, date_preset)
                report.append({
                    "campaign_id":   camp_id,
                    "campaign_name": camp["name"],
                    "status":        camp["status"],
                    "daily_budget":  int(camp.get("daily_budget", 0)),
                    **{k: analysis[k] for k in [
                        "total_spend", "total_leads", "cpl",
                        "cpm", "ctr", "frequency", "conv_rate",
                        "ratings", "alerts",
                    ] if k in analysis},
                })
            except Exception as e:
                log.warning(f"Lỗi phân tích campaign {camp_id}: {e}")

        return {
            "generated_at":   datetime.now().isoformat(),
            "date_preset":    date_preset,
            "campaigns":      report,
            "total_campaigns": len(report),
            "total_spend":    sum(r.get("total_spend", 0) for r in report),
            "total_leads":    sum(r.get("total_leads", 0) for r in report),
            "overall_cpl":    self.compute_cpl(
                sum(r.get("total_spend", 0) for r in report),
                sum(r.get("total_leads", 0) for r in report),
            ),
        }


# ── Helpers ──────────────────────────────────────────────────────────────────

def _normalize_insights(rows: list[dict]) -> pd.DataFrame:
    """Chuẩn hóa dữ liệu từ Insights API thành DataFrame."""
    records = []
    for row in rows:
        spend = float(row.get("spend", 0))
        leads = _extract_lead_count(row)
        records.append({
            "adset_id":    row.get("adset_id", ""),
            "adset_name":  row.get("adset_name", row.get("adset_id", "")),
            "ad_id":       row.get("ad_id", ""),
            "date_start":  row.get("date_start", ""),
            "impressions": int(row.get("impressions", 0)),
            "clicks":      int(row.get("clicks", 0)),
            "spend":       spend,
            "cpm":         float(row.get("cpm", 0)),
            "cpc":         float(row.get("cpc", 0)),
            "ctr":         float(row.get("ctr", 0)),
            "frequency":   float(row.get("frequency", 0)),
            "reach":       int(row.get("reach", 0)),
            "leads":       leads,
        })
    return pd.DataFrame(records) if records else pd.DataFrame()

def _extract_lead_count(row: dict) -> int:
    """Trích xuất số leads từ actions array (Meta API format)."""
    # Từ mock data trực tiếp
    if "leads" in row:
        return int(row["leads"])
    # Từ API thực: actions=[{action_type: lead, value: N}]
    for action in row.get("actions", []):
        if action.get("action_type") in ("lead", "onsite_conversion.lead_grouped"):
            return int(action.get("value", 0))
    return 0
