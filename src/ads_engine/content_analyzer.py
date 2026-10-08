"""
content_analyzer.py — Phân tích hiệu suất theo loại nội dung (Creative)
=========================================================================
So sánh các loại content (video, carousel, image, v.v.) dựa trên:
  - CPL (Cost Per Lead)
  - CTR (Click-Through Rate)
  - Conversion Rate (lead/click)
  - Quality Score từ Messenger
  - Frequency (ad fatigue risk)
  - Trend (đang tăng/giảm)
  - Reach efficiency

Nội dung được phân loại thành các nhóm parent:
  video    → video_testimonial, video_luxury, video_drone, video_resort, video_lifestyle, video_short, video_vip
  carousel → carousel_project
  image    → image_roi, image_price, image_view, image_map
  personal → personal_brand
  creative → countdown_creative, roi_calculator, tech_creative, ab_test, smart_creative, lal_creative, retarget, launch_creative, mass_creative, interest_segment, international, premium_creative, lifestyle_creative, story_beach, document_creative
"""
from collections import defaultdict
from typing import Dict, List, Any

# ── Mapping content_type → nhóm cha ──────────────────────────────────────────
CONTENT_GROUP_MAP = {
    "video_testimonial": "Video — KH thực tế",
    "video_luxury":      "Video — Luxury/VIP",
    "video_drone":       "Video — Drone/Dự án",
    "video_resort":      "Video — Nghỉ dưỡng",
    "video_lifestyle":   "Video — Lifestyle",
    "video_short":       "Video — 15s TOFU",
    "video_vip":         "Video — Ultra VIP",
    "carousel_project":  "Carousel — Dự án",
    "image_roi":         "Image — ROI/Đầu tư",
    "image_price":       "Image — Giá/Ưu đãi",
    "image_view":        "Image — View/Tiện ích",
    "image_map":         "Image — Bản đồ/Vị trí",
    "personal_brand":    "Personal Brand — Agent",
    "countdown_creative": "Countdown/Urgency",
    "roi_calculator":    "ROI Calculator",
    "lal_creative":      "Lookalike Audience",
    "retarget":          "Retarget — Custom Audience",
    "ab_test":           "A/B Test Creative",
    "tech_creative":     "Tech/Smart Home",
    "smart_creative":    "Smart ROAS",
    "mass_creative":     "Mass Interest",
    "international":     "International Audience",
    "premium_creative":  "Premium/Luxury Static",
    "lifestyle_creative":"Lifestyle — Travel",
    "story_beach":       "Story — Beachfront",
    "document_creative": "Pháp lý/Trust",
    "launch_creative":   "Launch Campaign",
    "interest_segment":  "Interest Segment",
}

CONTENT_FORMAT = {
    "video_testimonial": "video",  "video_luxury": "video",
    "video_drone": "video",        "video_resort": "video",
    "video_lifestyle": "video",    "video_short": "video",
    "video_vip": "video",
    "carousel_project": "carousel",
    "image_roi": "image",          "image_price": "image",
    "image_view": "image",         "image_map": "image",
    "personal_brand": "personal",
    "countdown_creative": "creative", "roi_calculator": "creative",
    "lal_creative": "audience",    "retarget": "audience",
    "ab_test": "creative",         "tech_creative": "creative",
    "smart_creative": "creative",  "mass_creative": "creative",
    "international": "creative",   "premium_creative": "creative",
    "lifestyle_creative": "creative","story_beach": "creative",
    "document_creative": "creative","launch_creative": "creative",
    "interest_segment": "audience",
}

# ── Ngưỡng benchmark ──────────────────────────────────────────────────────────
BENCH = {
    "cpl_good": 150_000, "cpl_poor": 400_000,
    "ctr_good": 2.0,     "ctr_poor": 1.0,
    "quality_good": 7.0, "quality_poor": 4.0,
    "freq_good": 2.5,    "freq_warn": 3.5,
    "conv_good": 5.0,    "conv_poor": 2.0,  # leads per 100 clicks
}


def analyze_content_performance(universe: dict) -> dict:
    """
    Phân tích hiệu suất theo từng loại content.
    Returns dict với 4 levels của phân tích:
      - by_content_type: từng content_type cụ thể
      - by_format:       nhóm theo format (video/carousel/image/...)
      - rankings:        top 5 and bottom 5
      - funnel:          click → lead → quality funnel per content
    """
    insights = universe["insights"]
    campaigns = universe["campaigns"]
    messenger = universe["messenger"]

    # Map campaign → content_type, tier, bm
    camp_meta = {c["id"]: c for c in campaigns}

    # ── Aggregate by content_type ────────────────────────────────────────────
    ct_data: Dict[str, dict] = defaultdict(lambda: {
        "spend": 0, "leads": 0, "clicks": 0, "impressions": 0,
        "ctr_sum": 0, "freq_sum": 0, "cpl_sum": 0, "rows": 0,
        "quality_scores": [], "campaign_ids": set(),
        "tier_counts": defaultdict(int), "days_data": defaultdict(lambda: {"spend":0,"leads":0}),
    })

    for row in insights:
        ct = row.get("content_type", "unknown")
        ct_data[ct]["spend"]       += row["spend"]
        ct_data[ct]["leads"]       += row["leads"]
        ct_data[ct]["clicks"]      += row["clicks"]
        ct_data[ct]["impressions"] += row["impressions"]
        ct_data[ct]["ctr_sum"]     += row["ctr"]
        ct_data[ct]["freq_sum"]    += row["frequency"]
        ct_data[ct]["rows"]        += 1
        ct_data[ct]["campaign_ids"].add(row["campaign_id"])
        date = row.get("date_start", "")
        ct_data[ct]["days_data"][date]["spend"]  += row["spend"]
        ct_data[ct]["days_data"][date]["leads"]  += row["leads"]

        # Tier
        camp = camp_meta.get(row["campaign_id"], {})
        tier = camp.get("tier", "UNKNOWN")
        ct_data[ct]["tier_counts"][tier] += 1

    # Quality từ messenger → match qua campaign → content_type
    for lead in messenger:
        for c in campaigns:
            if c["page"] == lead["page_id"]:
                ct_data[c["content_type"]]["quality_scores"].append(lead["quality_score"])
                break

    # ── Build result per content_type ────────────────────────────────────────
    results = []
    for ct, d in ct_data.items():
        rows    = max(d["rows"], 1)
        spend   = d["spend"]
        leads   = d["leads"]
        clicks  = d["clicks"]
        impr    = d["impressions"]
        qs      = d["quality_scores"]
        n_camps = len(d["campaign_ids"])

        cpl     = round(spend / leads, 0) if leads else 0
        avg_ctr = round(d["ctr_sum"] / rows, 2)
        avg_freq= round(d["freq_sum"] / rows, 2)
        # conv rate = leads / (clicks / 100) = leads per 100 clicks
        conv_rate = round(leads / clicks * 100, 2) if clicks else 0
        avg_qual  = round(sum(qs) / len(qs), 2) if qs else 0
        cpm       = round(spend / impr * 1000, 0) if impr else 0
        reach     = round(impr / avg_freq, 0) if avg_freq else impr

        # Score composite: lower CPL + higher quality + higher CTR + lower freq
        def norm(v, lo, hi):
            return max(0, min(1, (v - lo) / (hi - lo + 1)))

        cpl_score     = 1 - norm(cpl, 0, 900_000)
        quality_score = norm(avg_qual, 0, 10)
        ctr_score     = norm(avg_ctr, 0, 6)
        freq_score    = 1 - norm(avg_freq, 1, 6)
        conv_score    = norm(conv_rate, 0, 20)
        composite     = round((cpl_score * 0.35 + quality_score * 0.30 + ctr_score * 0.15 + conv_score * 0.15 + freq_score * 0.05) * 100, 1)

        # Rating
        if composite >= 70:
            rating = "excellent"
        elif composite >= 50:
            rating = "good"
        elif composite >= 35:
            rating = "average"
        else:
            rating = "poor"

        # Trend: compare first 3 days vs last 3 days CPL
        sorted_days = sorted(d["days_data"].items())
        if len(sorted_days) >= 4:
            early = sorted_days[:3]
            recent = sorted_days[-3:]
            early_cpl  = sum(d2["spend"] for _, d2 in early) / max(sum(d2["leads"] for _, d2 in early), 1)
            recent_cpl = sum(d2["spend"] for _, d2 in recent) / max(sum(d2["leads"] for _, d2 in recent), 1)
            if recent_cpl < early_cpl * 0.9:
                trend = "improving"
            elif recent_cpl > early_cpl * 1.1:
                trend = "declining"
            else:
                trend = "stable"
        else:
            trend = "stable"

        # Main tier
        tc = d["tier_counts"]
        dominant_tier = max(tc, key=tc.get) if tc else "UNKNOWN"

        results.append({
            "content_type":    ct,
            "label":           CONTENT_GROUP_MAP.get(ct, ct),
            "format":          CONTENT_FORMAT.get(ct, "other"),
            "campaigns":       n_camps,
            "total_spend":     round(spend, 0),
            "total_leads":     leads,
            "total_clicks":    clicks,
            "total_impressions": impr,
            "cpl":             cpl,
            "avg_ctr":         avg_ctr,
            "avg_freq":        avg_freq,
            "avg_quality":     avg_qual,
            "cpm":             cpm,
            "conv_rate":       conv_rate,
            "composite_score": composite,
            "rating":          rating,
            "trend":           trend,
            "dominant_tier":   dominant_tier,
            "tier_counts":     dict(d["tier_counts"]),
            "reach":           int(reach),
            # CPL vs benchmark
            "cpl_vs_bench":    "good" if cpl < BENCH["cpl_good"] else ("poor" if cpl > BENCH["cpl_poor"] else "avg"),
            "ctr_vs_bench":    "good" if avg_ctr > BENCH["ctr_good"] else ("poor" if avg_ctr < BENCH["ctr_poor"] else "avg"),
            "qual_vs_bench":   "good" if avg_qual >= BENCH["quality_good"] else ("poor" if avg_qual < BENCH["quality_poor"] else "avg"),
            "freq_risk":       "high" if avg_freq > BENCH["freq_warn"] else ("medium" if avg_freq > BENCH["freq_good"] else "low"),
            # Spend breakdown for donut
            "spend_pct":       0,  # filled after
        })

    total_spend = sum(r["total_spend"] for r in results)
    for r in results:
        r["spend_pct"] = round(r["total_spend"] / total_spend * 100, 1) if total_spend else 0

    results.sort(key=lambda x: x["composite_score"], reverse=True)

    # ── By format ─────────────────────────────────────────────────────────────
    fmt_data: Dict[str, dict] = defaultdict(lambda: {"spend":0,"leads":0,"clicks":0,"quality_scores":[]})
    for r in results:
        fmt = r["format"]
        fmt_data[fmt]["spend"]  += r["total_spend"]
        fmt_data[fmt]["leads"]  += r["total_leads"]
        fmt_data[fmt]["clicks"] += r["total_clicks"]
        fmt_data[fmt]["quality_scores"].extend([r["avg_quality"]] * r["campaigns"])

    by_format = []
    for fmt, d in fmt_data.items():
        leads = d["leads"]
        spend = d["spend"]
        qs    = d["quality_scores"]
        by_format.append({
            "format":      fmt,
            "total_spend": round(spend, 0),
            "total_leads": leads,
            "cpl":         round(spend / leads, 0) if leads else 0,
            "avg_quality": round(sum(qs) / len(qs), 2) if qs else 0,
            "conv_rate":   round(leads / d["clicks"] * 100, 2) if d["clicks"] else 0,
        })
    by_format.sort(key=lambda x: x["cpl"])

    # ── Build CPL trend chart per format ─────────────────────────────────────
    fmt_daily: Dict[str, Dict[str, dict]] = defaultdict(lambda: defaultdict(lambda: {"spend":0,"leads":0}))
    for row in insights:
        ct  = row.get("content_type", "other")
        fmt = CONTENT_FORMAT.get(ct, "other")
        fmt_daily[fmt][row["date_start"]]["spend"] += row["spend"]
        fmt_daily[fmt][row["date_start"]]["leads"] += row["leads"]

    all_dates = sorted({row["date_start"] for row in insights})
    COLORS = {"video":"#1877f2","carousel":"#3fb950","image":"#d29922","personal":"#bc8cff","audience":"#39d353","creative":"#f85149","other":"#8b949e"}

    cpl_trends = []
    for fmt, days in fmt_daily.items():
        cpl_trend_data = []
        for d in all_dates:
            s = days.get(d, {}).get("spend", 0)
            l = days.get(d, {}).get("leads", 0)
            cpl_trend_data.append(round(s / l / 1000, 1) if l else None)
        cpl_trends.append({
            "label": fmt, "data": cpl_trend_data,
            "borderColor": COLORS.get(fmt, "#888"),
            "borderWidth": 2, "tension": 0.4, "spanGaps": True,
        })

    # ── Rankings ──────────────────────────────────────────────────────────────
    top5    = results[:5]
    bottom5 = [r for r in results if r["total_leads"] > 0][-5:]

    # ── Funnel per format ─────────────────────────────────────────────────────
    funnel = []
    for f in by_format:
        funnel.append({
            "format": f["format"],
            "impressions": sum(r["total_impressions"] for r in results if r["format"] == f["format"]),
            "clicks":      sum(r["total_clicks"] for r in results if r["format"] == f["format"]),
            "leads":       f["total_leads"],
            "quality":     f["avg_quality"],
        })

    return {
        "by_content_type": results,
        "by_format":       by_format,
        "top5":            top5,
        "bottom5":         bottom5,
        "cpl_trend_chart": {"labels": all_dates, "datasets": cpl_trends},
        "funnel":          funnel,
        "benchmark":       BENCH,
        "total_spend":     total_spend,
        "total_leads":     sum(r["total_leads"] for r in results),
        "content_group_map": CONTENT_GROUP_MAP,
    }
