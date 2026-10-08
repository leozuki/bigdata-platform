"""
app.py — Flask Web Dashboard cho BDS Data Pipeline
Chạy: python dashboard/app.py
Mở:  http://localhost:5000
"""
import os
import sys
import json
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from flask import Flask, render_template, jsonify, request, redirect, url_for
from dotenv import load_dotenv

load_dotenv()

from src.database import (init_db, SessionLocal,
                           RawContact, CleanContact, CustomerProfile, HotLead, GoogleLead,
                           AdCampaign, AdSet, AdPerformance, MessengerLead,
                           LeadAdMapping, OptimizationLog)

app = Flask(__name__)


# ─── CORE Pipeline API Routes ─────────────────────────────────────────────────

@app.route("/api/stats")
def api_stats():
    """Thống kê tổng quan cho dashboard"""
    db = SessionLocal()
    try:
        raw_count     = db.query(RawContact).count()
        clean_count   = db.query(CleanContact).count()
        profile_count = db.query(CustomerProfile).count()
        hot_count     = db.query(HotLead).filter(HotLead.hot_score > 0).count()
        google_count  = db.query(GoogleLead).count()
        # VIP: lead_score >= 8 (reliable — không phụ thuộc cluster convergence)
        vip_count     = db.query(CustomerProfile).filter(CustomerProfile.lead_score >= 8).count()
        warm_count    = db.query(CustomerProfile).filter(
            CustomerProfile.lead_score >= 5, CustomerProfile.lead_score < 8).count()
        uid_count     = db.query(CustomerProfile).filter(
            CustomerProfile.facebook_uid.isnot(None)).count()
        return jsonify({
            "raw_contacts":      raw_count,
            "clean_contacts":    clean_count,
            "customer_profiles": profile_count,
            "hot_leads":         hot_count,
            "google_leads":      google_count,
            "vip_customers":     vip_count,
            "warm_leads":        warm_count,
            "with_fb_uid":       uid_count,
            "last_updated":      datetime.now().strftime("%d/%m/%Y %H:%M"),
        })
    finally:
        db.close()


@app.route("/api/leads")
def api_leads():
    """Danh sách lead scoring với filter/sort"""
    page           = int(request.args.get("page", 1))
    per_page       = int(request.args.get("per_page", 50))
    min_score      = float(request.args.get("min_score", 0))
    cluster_filter = request.args.get("cluster", "all")

    db = SessionLocal()
    try:
        query = db.query(CustomerProfile).filter(CustomerProfile.lead_score >= min_score)
        if cluster_filter != "all":
            query = query.filter(CustomerProfile.cluster == int(cluster_filter))

        total   = query.count()
        records = query.order_by(CustomerProfile.lead_score.desc()) \
                       .offset((page - 1) * per_page).limit(per_page).all()

        items = [{
            "id":            p.id,
            "ho_ten":        p.ho_ten or "",
            "sdt":           p.so_dien_thoai or "",
            "email":         p.email or "",
            "fb_uid":        p.facebook_uid or "",
            "cluster":       p.cluster,
            "cluster_label": p.cluster_label or "Chưa phân",
            "lead_score":    p.lead_score or 0,
            "nguon":         p.nguon or "",
        } for p in records]

        return jsonify({"total": total, "page": page, "items": items})
    finally:
        db.close()


@app.route("/api/clusters")
def api_clusters():
    """Dữ liệu phân cụm cho biểu đồ"""
    db = SessionLocal()
    try:
        from sqlalchemy import func
        results = db.query(
            CustomerProfile.cluster_label,
            func.count(CustomerProfile.id).label("count"),
            func.avg(CustomerProfile.lead_score).label("avg_score"),
        ).group_by(CustomerProfile.cluster_label).all()
        return jsonify([{
            "label":     r.cluster_label or "Chưa phân",
            "count":     r.count,
            "avg_score": round(r.avg_score or 0, 2),
        } for r in results])
    finally:
        db.close()


@app.route("/api/hot-leads")
def api_hot_leads():
    """Top 100 hot leads"""
    db = SessionLocal()
    try:
        leads = db.query(HotLead).filter(HotLead.hot_score >= 1) \
                  .order_by(HotLead.hot_score.desc()).limit(100).all()
        return jsonify([{
            "sdt":        lead.so_dien_thoai or "",
            "uid":        lead.facebook_uid or "",
            "nguon":      lead.nguon,
            "behavior":   lead.behavior or "",
            "keyword":    lead.keyword or "",
            "hot_score":  lead.hot_score,
            "is_existing": lead.is_existing_customer,
        } for lead in leads])
    finally:
        db.close()


@app.route("/api/run/<phase>", methods=["POST"])
def api_run_phase(phase):
    """Trigger chạy một phase"""
    try:
        if phase == "1":
            import os
            from src.phase1_pipeline.excel_ingestor      import run_ingestion
            from src.phase1_pipeline.identity_mapper     import run_identity_mapping
            from src.phase1_pipeline.segment_audiences   import run_segmentation
            raw_dir = os.getenv("RAW_DATA_DIR", "data/raw")
            r = {**run_ingestion(raw_dir), **run_identity_mapping(), **run_segmentation()}
        elif phase == "2":
            from src.phase2_enrichment.scraper_adapter import run_facebook_scraper_import
            from src.phase2_enrichment.google_scraper  import run_google_scraper
            from src.phase2_enrichment.filter_engine   import run_filter_engine
            from src.phase2_enrichment.matcher         import run_matching
            r = {**run_facebook_scraper_import(), **run_google_scraper(),
                 **run_filter_engine(), **run_matching()}
        elif phase == "3":
            from src.phase3_scoring.clustering  import run_clustering
            from src.phase3_scoring.lead_scorer import run_lead_scoring
            r = {**run_clustering(), **run_lead_scoring()}
        else:
            return jsonify({"error": "Phase không hợp lệ"}), 400
        return jsonify({"success": True, "result": r})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ─── ADS ENGINE API Routes ────────────────────────────────────────────────────

@app.route("/api/ads/campaigns")
def api_ads_campaigns():
    """Danh sách campaigns với tổng metrics"""
    try:
        date_preset = request.args.get("date_preset", "last_7d")
        from src.ads_engine.cost_analyzer import CostAnalyzer
        return jsonify(CostAnalyzer().generate_cost_report(date_preset))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/ads/performance")
def api_ads_performance():
    """Metrics chi tiết theo thời gian cho Chart.js"""
    try:
        campaign_id = request.args.get("campaign_id", "camp_1000")
        date_preset = request.args.get("date_preset", "last_7d")
        from src.ads_engine.fb_ads_api        import FacebookAdsAPI
        from src.ads_engine.cost_analyzer     import CostAnalyzer, _normalize_insights
        import pandas as pd
        fb   = FacebookAdsAPI()
        rows = fb.get_insights(campaign_id, date_preset=date_preset, level="campaign")
        df   = _normalize_insights(rows)
        if df.empty:
            return jsonify({"labels": [], "spend": [], "leads": [], "cpl": []})
        ana  = CostAnalyzer(fb_api=fb)
        df["cpl"] = df.apply(lambda r: ana.compute_cpl(r["spend"], r["leads"]), axis=1)
        return jsonify({
            "labels":    df["date_start"].tolist(),
            "spend":     df["spend"].tolist(),
            "leads":     df["leads"].tolist(),
            "cpl":       df["cpl"].tolist(),
            "ctr":       df["ctr"].tolist(),
            "frequency": df["frequency"].tolist(),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/ads/messenger-leads")
def api_ads_messenger_leads():
    """Danh sách Messenger leads với quality score"""
    try:
        db    = SessionLocal()
        leads = db.query(MessengerLead).order_by(
            MessengerLead.quality_score.desc()).limit(200).all()
        items = [{
            "id":              l.id,
            "conversation_id": l.conversation_id,
            "fb_ad_id":        l.fb_ad_id or "",
            "sender_name":     l.sender_name or "",
            "phone":           l.phone or "",
            "email":           l.email or "",
            "message_count":   l.message_count,
            "intent_score":    l.intent_score or 0,
            "quality_score":   l.quality_score or 0,
            "last_message_at": l.last_message_at.isoformat() if l.last_message_at else "",
        } for l in leads]
        db.close()

        # Fallback mock nếu DB trống
        if not items:
            import random
            from src.ads_engine.messenger_api import _mock_conversations
            convs = _mock_conversations(10)
            items = [{
                "id":              i + 1,
                "conversation_id": c["id"],
                "fb_ad_id":        c.get("fb_ad_id") or "",
                "sender_name":     c["participants"]["data"][0]["name"],
                "phone":           "09xxxxxxxx",
                "email":           "",
                "message_count":   c["message_count"],
                "intent_score":    round(random.uniform(3, 9), 2),
                "quality_score":   round(random.uniform(3, 9), 2),
                "last_message_at": c["updated_time"],
            } for i, c in enumerate(convs)]

        return jsonify({"total": len(items), "items": items})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/ads/recommendations")
def api_ads_recommendations():
    """Báo cáo đề xuất nhân rộng campaign"""
    try:
        from src.ads_engine.campaign_recommender import CampaignRecommender
        return jsonify(CampaignRecommender().generate_recommendations_report())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/ads/content-performance")
def api_content_performance():
    """Phân tích hiệu suất theo loại content/creative — top performers và bottom"""
    try:
        from src.ads_engine.multi_account_simulator import generate_full_universe
        from src.ads_engine.content_analyzer import analyze_content_performance
        date_preset = request.args.get("date_preset", "last_7d")
        days        = {"last_7d": 7, "last_14d": 14, "last_30d": 30}.get(date_preset, 7)
        fmt_filter  = request.args.get("format", "all")

        universe = generate_full_universe(days=days)
        analysis = analyze_content_performance(universe)

        # Optionally filter by format
        if fmt_filter != "all":
            analysis["by_content_type"] = [
                r for r in analysis["by_content_type"]
                if r["format"] == fmt_filter
            ]

        return jsonify(analysis)
    except Exception as e:
        import traceback
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500


@app.route("/api/ads/multi-account/overview")
def api_multi_account_overview():

    """Tổng quan toàn bộ hệ thống: BMs, accounts, pages, campaigns"""
    try:
        from src.ads_engine.multi_account_simulator import (
            generate_full_universe, aggregate_by_bm, aggregate_by_account,
            aggregate_by_tier, BUSINESS_MANAGERS, PAGES
        )
        date_preset = request.args.get("date_preset", "last_7d")
        days = {"last_7d": 7, "last_14d": 14, "last_30d": 30}.get(date_preset, 7)
        universe = generate_full_universe(days=days)

        total_spend  = sum(r["spend"] for r in universe["insights"])
        total_leads  = sum(r["leads"] for r in universe["insights"])
        total_impr   = sum(r["impressions"] for r in universe["insights"])
        avg_quality  = sum(l["quality_score"] for l in universe["messenger"]) / max(len(universe["messenger"]), 1)

        return jsonify({
            "summary": {
                "total_spend":   round(total_spend, 0),
                "total_leads":   total_leads,
                "total_impressions": total_impr,
                "overall_cpl":   round(total_spend / total_leads, 0) if total_leads else 0,
                "avg_quality":   round(avg_quality, 2),
                "total_campaigns": len(universe["campaigns"]),
                "total_adsets":  len(universe["adsets"]),
                "total_bms":     len(universe["bms"]),
                "total_accounts": len(set(c["account"] for c in universe["campaigns"])),
                "total_pages":   len(universe["pages"]),
                "messenger_leads": len(universe["messenger"]),
            },
            "by_bm":      aggregate_by_bm(universe),
            "by_account": aggregate_by_account(universe),
            "by_tier":    aggregate_by_tier(universe),
            "bms":        universe["bms"],
            "pages":      universe["pages"],
            "generated_at": universe["generated_at"],
            "days": days,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/ads/multi-account/campaigns")
def api_multi_account_campaigns():
    """Tất cả campaigns từ mọi TKQC với filter by BM/account"""
    try:
        from src.ads_engine.multi_account_simulator import (
            generate_full_universe, aggregate_by_tier
        )
        bm_filter      = request.args.get("bm", "all")
        account_filter = request.args.get("account", "all")
        tier_filter    = request.args.get("tier", "all")
        date_preset    = request.args.get("date_preset", "last_7d")
        days           = {"last_7d": 7, "last_14d": 14, "last_30d": 30}.get(date_preset, 7)

        universe = generate_full_universe(days=days)
        camps    = universe["campaigns"]
        insights = universe["insights"]

        # Aggregate insights per campaign
        from collections import defaultdict
        camp_metrics = defaultdict(lambda: {"spend": 0, "leads": 0,
                                            "clicks": 0, "impressions": 0,
                                            "ctr_sum": 0, "freq_sum": 0, "rows": 0})
        for row in insights:
            cid = row["campaign_id"]
            camp_metrics[cid]["spend"]       += row["spend"]
            camp_metrics[cid]["leads"]       += row["leads"]
            camp_metrics[cid]["clicks"]      += row["clicks"]
            camp_metrics[cid]["impressions"] += row["impressions"]
            camp_metrics[cid]["ctr_sum"]     += row["ctr"]
            camp_metrics[cid]["freq_sum"]    += row["frequency"]
            camp_metrics[cid]["rows"]        += 1

        # Avg quality from messenger
        camp_quality = defaultdict(list)
        for lead in universe["messenger"]:
            # match by page
            for c in universe["campaigns"]:
                if c["page"] == lead["page_id"]:
                    camp_quality[c["id"]].append(lead["quality_score"])

        result = []
        for c in camps:
            if bm_filter != "all" and c["bm"] != bm_filter:
                continue
            if account_filter != "all" and c["account"] != account_filter:
                continue
            if tier_filter != "all" and c["tier"] != tier_filter:
                continue
            m     = camp_metrics[c["id"]]
            rows  = m["rows"] or 1
            spend = m["spend"]
            leads = m["leads"]
            qs    = camp_quality[c["id"]]
            result.append({
                "id":           c["id"],
                "name":         c["name"],
                "account_id":   c["account"],
                "bm_id":        c["bm"],
                "page_id":      c["page"],
                "tier":         c["tier"],
                "status":       c["status"],
                "objective":    c["objective"],
                "content_type": c["content_type"],
                "budget":       c["budget"],
                "total_spend":  round(spend, 0),
                "total_leads":  leads,
                "cpl":          round(spend / leads, 0) if leads else 0,
                "ctr":          round(m["ctr_sum"] / rows, 2),
                "frequency":    round(m["freq_sum"] / rows, 2),
                "avg_quality":  round(sum(qs) / len(qs), 1) if qs else 0,
            })

        result.sort(key=lambda x: x["total_spend"], reverse=True)
        return jsonify({
            "total": len(result),
            "campaigns": result,
            "tier_summary": aggregate_by_tier(universe),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/ads/multi-account/adsets")
def api_multi_account_adsets():
    """Tất cả adsets với performance, sorted by CPL"""
    try:
        from src.ads_engine.multi_account_simulator import generate_full_universe
        universe = generate_full_universe(days=7)
        adsets   = universe["adsets"]
        tier_filter = request.args.get("tier", "all")
        if tier_filter != "all":
            adsets = [a for a in adsets if a.get("tier") == tier_filter]
        adsets_out = sorted(adsets, key=lambda a: a.get("cpl_7d", 0))
        return jsonify({"total": len(adsets_out), "adsets": adsets_out})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/ads/multi-account/optimize-preview")
def api_multi_account_optimize_preview():
    """Preview actions optimizer trên toàn bộ multi-account universe"""
    try:
        from src.ads_engine.multi_account_simulator import (
            generate_full_universe, TIER_PROFILES
        )
        import os
        RULE_PAUSE_CPL     = float(os.getenv("RULE_PAUSE_CPL",     500_000))
        RULE_PAUSE_QUALITY = float(os.getenv("RULE_PAUSE_QUALITY", 4.0))
        RULE_SCALE_CPL     = float(os.getenv("RULE_SCALE_CPL",     150_000))
        RULE_SCALE_QUALITY = float(os.getenv("RULE_SCALE_QUALITY", 7.0))
        RULE_SCALE_FACTOR  = float(os.getenv("RULE_SCALE_FACTOR",  1.5))
        RULE_FREQ_CAP      = float(os.getenv("RULE_FREQ_CAP",      3.5))
        RULE_WINNER_Q      = float(os.getenv("RULE_WINNER_QUALITY", 8.0))
        RULE_WINNER_BUD    = float(os.getenv("RULE_WINNER_BUDGET",  2.0))

        universe = generate_full_universe(days=7)
        adsets   = universe["adsets"]
        camps    = {c["id"]: c for c in universe["campaigns"]}
        actions  = []

        for adset in adsets:
            if adset.get("status") == "PAUSED":
                continue
            cpl  = adset.get("cpl_7d", 0)
            qual = adset.get("quality_score", 5.0)
            freq = adset.get("frequency", 2.0) if "frequency" in adset else 2.0
            camp = camps.get(adset.get("campaign_id", ""), {})
            budget = adset.get("daily_budget", 0)

            if cpl > RULE_PAUSE_CPL and qual < RULE_PAUSE_QUALITY:
                actions.append({
                    "rule": "PAUSE", "adset_id": adset["id"],
                    "adset_name": adset["name"], "campaign": camp.get("name", ""),
                    "account_id": adset.get("account_id", ""),
                    "bm_id": adset.get("bm_id", ""),
                    "reason": f"CPL {cpl:,.0f}d > {RULE_PAUSE_CPL:,.0f}d & quality {qual:.1f} < {RULE_PAUSE_QUALITY}",
                    "impact": f"Tiết kiệm {budget:,.0f}d/ngày",
                    "status": "preview",
                    "metrics": {"cpl": cpl, "quality_score": qual},
                })
            elif cpl < RULE_SCALE_CPL and qual >= RULE_SCALE_QUALITY:
                new_budget = int(budget * RULE_SCALE_FACTOR)
                actions.append({
                    "rule": "SCALE", "adset_id": adset["id"],
                    "adset_name": adset["name"], "campaign": camp.get("name", ""),
                    "account_id": adset.get("account_id", ""),
                    "bm_id": adset.get("bm_id", ""),
                    "reason": f"CPL {cpl:,.0f}d < {RULE_SCALE_CPL:,.0f}d & quality {qual:.1f} >= {RULE_SCALE_QUALITY}",
                    "impact": f"Budget {budget:,.0f} → {new_budget:,.0f}d/ngày (+{(RULE_SCALE_FACTOR-1)*100:.0f}%)",
                    "status": "preview",
                    "metrics": {"cpl": cpl, "quality_score": qual, "new_budget": new_budget},
                })
            if qual >= RULE_WINNER_Q:
                new_budget = int(budget * RULE_WINNER_BUD)
                actions.append({
                    "rule": "WINNER", "adset_id": adset["id"],
                    "adset_name": adset["name"], "campaign": camp.get("name", ""),
                    "account_id": adset.get("account_id", ""),
                    "bm_id": adset.get("bm_id", ""),
                    "reason": f"Quality {qual:.1f} >= {RULE_WINNER_Q} — nhân bản",
                    "impact": f"Duplicate với budget x{RULE_WINNER_BUD:.0f} = {new_budget:,.0f}d/ngày",
                    "status": "preview",
                    "metrics": {"quality_score": qual, "new_budget": new_budget},
                })

        from collections import Counter
        rule_counts = Counter(a["rule"] for a in actions)
        total_save  = sum(a["metrics"].get("daily_budget", adsets[0].get("daily_budget", 0))
                          for a in actions if a["rule"] == "PAUSE")

        return jsonify({
            "total_actions": len(actions),
            "rule_counts":   dict(rule_counts),
            "actions":       actions,
            "dry_run":       True,
            "universe_size": {
                "campaigns": len(universe["campaigns"]),
                "adsets":    len(adsets),
            }
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/ads/multi-account/trend")
def api_multi_account_trend():
    """Trend chi tiêu và leads theo ngày, phân theo BM"""
    try:
        from src.ads_engine.multi_account_simulator import generate_full_universe
        from collections import defaultdict
        date_preset = request.args.get("date_preset", "last_7d")
        days        = {"last_7d": 7, "last_14d": 14, "last_30d": 30}.get(date_preset, 7)
        universe    = generate_full_universe(days=days)

        # group by date + bm
        day_bm = defaultdict(lambda: defaultdict(lambda: {"spend": 0, "leads": 0}))
        bm_names = {bid: bm["name"][:20] for bid, bm in universe["bms"].items()}

        for row in universe["insights"]:
            day_bm[row["date_start"]][row["bm_id"]]["spend"] += row["spend"]
            day_bm[row["date_start"]][row["bm_id"]]["leads"] += row["leads"]

        labels = sorted(day_bm.keys())
        bm_ids = list(universe["bms"].keys())
        datasets_spend = []
        datasets_leads = []
        colors = ["#1877f2", "#3fb950", "#f85149", "#bc8cff", "#d29922"]

        for i, bid in enumerate(bm_ids):
            c = colors[i % len(colors)]
            datasets_spend.append({
                "label": bm_names.get(bid, bid),
                "data":  [round(day_bm[d].get(bid, {}).get("spend", 0) / 1_000_000, 2) for d in labels],
                "borderColor": c, "backgroundColor": c + "22",
                "borderWidth": 2, "tension": 0.3, "fill": True,
            })
            datasets_leads.append({
                "label": bm_names.get(bid, bid),
                "data":  [day_bm[d].get(bid, {}).get("leads", 0) for d in labels],
                "borderColor": c, "borderWidth": 2, "tension": 0.3,
            })

        return jsonify({
            "labels": labels,
            "spend_datasets": datasets_spend,
            "leads_datasets": datasets_leads,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/ads/optimize/preview", methods=["POST"])
def api_ads_optimize_preview():
    """Preview actions sẽ thực hiện (dry run)"""
    try:
        from src.ads_engine.optimizer import AdsOptimizer
        return jsonify(AdsOptimizer(dry_run=True).run_optimization_cycle())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/ads/optimize/apply", methods=["POST"])
def api_ads_optimize_apply():
    """Áp dụng optimization (chỉ khi ADS_DRY_RUN=false)"""
    if os.getenv("ADS_DRY_RUN", "true").lower() == "true":
        return jsonify({
            "success": False,
            "message": "⚠️ DRY_RUN bật. Set ADS_DRY_RUN=false trong .env để apply thực.",
        }), 403
    try:
        from src.ads_engine.optimizer import AdsOptimizer
        return jsonify(AdsOptimizer(dry_run=False).run_optimization_cycle())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/ads/sync", methods=["POST"])
def api_ads_sync():
    """Sync Messenger leads từ Meta API"""
    try:
        from src.ads_engine.messenger_api import MessengerAPI
        result = MessengerAPI().sync_messenger_leads(limit=100)
        return jsonify({"success": True, "messenger": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/ads/cost-report")
def api_ads_cost_report():
    """Báo cáo cost tổng hợp với benchmarks"""
    try:
        from src.ads_engine.cost_analyzer import CostAnalyzer, BENCHMARKS
        date_preset = request.args.get("date_preset", "last_7d")
        report = CostAnalyzer().generate_cost_report(date_preset)
        report["benchmarks"] = BENCHMARKS
        return jsonify(report)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/ads/optimization-log")
def api_ads_optimization_log():
    """Lịch sử các lần chạy optimizer"""
    try:
        db   = SessionLocal()
        logs = db.query(OptimizationLog).order_by(
            OptimizationLog.run_at.desc()).limit(100).all()
        items = [{
            "id":         l.id,
            "run_at":     l.run_at.isoformat() if l.run_at else "",
            "dry_run":    l.dry_run,
            "rule":       l.rule or "",
            "action":     l.action or "",
            "adset_name": l.adset_name or "",
            "campaign":   l.campaign or "",
            "reason":     l.reason or "",
            "impact":     l.impact or "",
            "status":     l.status or "",
        } for l in logs]
        db.close()
        return jsonify({"total": len(items), "items": items})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─── Page Routes ─────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/leads")
def leads_page():
    return render_template("leads.html")

@app.route("/clusters")
def clusters_page():
    return render_template("clusters.html")

@app.route("/ads")
def ads_dashboard():
    return render_template("ads_dashboard.html")

@app.route("/ads/optimizer")
def ads_optimizer_page():
    return render_template("ads_optimizer.html")

@app.route("/ads/multi-account")
def ads_multi_account():
    return render_template("ads_multi_account.html")

@app.route("/ads/content")
def ads_content():
    return render_template("ads_content.html")


# ─── 360° Customer Profile Routes ────────────────────────────────────────────

@app.route("/api/leads/profile/<int:profile_id>")
def api_lead_profile(profile_id):
    """360° profile cho 1 khách hàng — kết hợp pipeline + FB + Messenger + Ads"""
    db = SessionLocal()
    try:
        from src.profile_enricher import build_360_profile
        p = db.query(CustomerProfile).filter(CustomerProfile.id == profile_id).first()
        if not p:
            return jsonify({"error": "Không tìm thấy khách hàng"}), 404

        # Lấy HotLead behaviors
        hot_leads = db.query(HotLead).filter(
            HotLead.so_dien_thoai == p.so_dien_thoai
        ).order_by(HotLead.hot_score.desc()).limit(10).all()

        # Lấy MessengerLead nếu có
        try:
            messenger = db.query(MessengerLead).filter(
                MessengerLead.fb_ad_id.isnot(None)
            ).limit(3).all() if p.facebook_uid else []
        except Exception:
            messenger = []

        profile_360 = build_360_profile(p, hot_leads=hot_leads, messenger_leads=messenger)
        return jsonify(profile_360)
    except Exception as e:
        import traceback
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500
    finally:
        db.close()


@app.route("/api/leads/profile-search")
def api_profile_search():
    """Tìm kiếm khách hàng để xem 360° profile"""
    q = request.args.get("q", "").strip()
    if len(q) < 2:
        return jsonify({"items": []})
    db = SessionLocal()
    try:
        from sqlalchemy import or_
        results = db.query(CustomerProfile).filter(
            or_(
                CustomerProfile.so_dien_thoai.contains(q),
                CustomerProfile.ho_ten.contains(q),
                CustomerProfile.facebook_uid.contains(q),
            )
        ).order_by(CustomerProfile.lead_score.desc()).limit(20).all()
        items = [{
            "id":          p.id,
            "ho_ten":      p.ho_ten or "—",
            "sdt":         p.so_dien_thoai or "",
            "fb_uid":      p.facebook_uid or "",
            "lead_score":  round(p.lead_score or 0, 1),
            "cluster_label": p.cluster_label or "Chưa phân",
            "cluster":     p.cluster,
        } for p in results]
        return jsonify({"items": items, "total": len(items)})
    finally:
        db.close()


@app.route("/api/leads/sync-profile", methods=["POST"])
def api_sync_profile():
    """
    Nhận dữ liệu profile từ Chrome Extension.
    Extension POST: { fb_uid, profile_data, messages, page_id }
    """
    try:
        data = request.get_json()
        if not data or "fb_uid" not in data:
            return jsonify({"error": "Thiếu fb_uid"}), 400

        fb_uid       = data["fb_uid"]
        profile_data = data.get("profile_data", {})
        messages     = data.get("messages", [])

        # Tìm CustomerProfile tương ứng
        db = SessionLocal()
        try:
            p = db.query(CustomerProfile).filter(
                CustomerProfile.facebook_uid == fb_uid
            ).first()
            if p:
                # Update với real profile data từ extension
                p.facebook_name = profile_data.get("name", p.facebook_name)
                p.updated_at    = datetime.utcnow()
                # Lưu profile_json vào ghi_chu tạm (sẽ có column riêng sau)
                existing = {}
                try:
                    existing = json.loads(p.ghi_chu or "{}")
                except Exception:
                    pass
                existing["extension_profile"] = profile_data
                existing["extension_messages"] = messages
                p.ghi_chu = json.dumps(existing, ensure_ascii=False)
                db.commit()
                return jsonify({"success": True, "profile_id": p.id, "message": "Profile cập nhật thành công"})
            else:
                return jsonify({"success": False, "message": f"Không tìm thấy fb_uid={fb_uid} trong DB. Hãy chạy pipeline để map SĐT → UID trước."})
        finally:
            db.close()
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/leads/profile")
def leads_profile_list():
    return render_template("lead_profile.html", profile_id=None)


@app.route("/leads/profile/<int:profile_id>")
def leads_profile_detail(profile_id):
    return render_template("lead_profile.html", profile_id=profile_id)



# ─── Intent Analyzer Routes ───────────────────────────────────────────────────

@app.route("/api/intent/analyze", methods=["POST"])
def api_intent_analyze():
    """
    Phân tích intent từ danh sách tin nhắn.
    Body: { "messages": [{"sender":"customer"|"agent","text":"...","timestamp":"..."}] }
    """
    try:
        from src.intent_analyzer import analyze_intent
        data = request.get_json()
        messages = data.get("messages", [])
        if not messages:
            return jsonify({"error": "messages không được rỗng"}), 400
        result = analyze_intent(messages)
        return jsonify(result.to_dict())
    except Exception as e:
        import traceback
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500


@app.route("/api/intent/analyze-message", methods=["POST"])
def api_intent_single():
    """
    Phân tích nhanh một tin nhắn đơn.
    Body: { "text": "..." }
    """
    try:
        from src.intent_analyzer import analyze_single_message
        data = request.get_json()
        text = data.get("text", "").strip()
        if not text:
            return jsonify({"error": "text không được rỗng"}), 400
        result = analyze_single_message(text)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/intent/profile/<int:profile_id>")
def api_intent_profile(profile_id):
    """Lấy intent analysis cho profile có sẵn (dùng mock conversation)"""
    try:
        from src.profile_enricher import _get_messenger_history_mock, _seed
        from src.intent_analyzer import analyze_intent
        db = SessionLocal()
        try:
            p = db.query(CustomerProfile).filter(CustomerProfile.id == profile_id).first()
            if not p:
                return jsonify({"error": "Không tìm thấy profile"}), 404
            uid = p.facebook_uid or f"uid_{p.id}"
            score = p.lead_score or 5.0
            # Sinh conversation từ mock nếu chưa có thật
            raw_msgs = _get_messenger_history_mock(uid, score)
            # Convert sang format mà intent analyzer cần
            msgs = []
            for m in raw_msgs:
                msgs.append({
                    "sender":    m.get("sender", "customer"),
                    "text":      m.get("text", ""),
                    "timestamp": m.get("timestamp", ""),
                })
            result = analyze_intent(msgs)
            return jsonify({**result.to_dict(), "profile_id": profile_id, "profile_name": p.ho_ten})
        finally:
            db.close()
    except Exception as e:
        import traceback
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500


@app.route("/leads/intent")
def leads_intent():
    return render_template("intent_analyzer.html")


# ─── Bootstrap ────────────────────────────────────────────────────────────────


if __name__ == "__main__":
    init_db()
    print("\nBDS Dashboard dang chay tai: http://localhost:5000\n")
    app.run(host="0.0.0.0", port=5000, debug=True)
