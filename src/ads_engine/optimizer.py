"""
optimizer.py — Tự động tối ưu Facebook Ads dựa trên rules
=========================================================
5 rules tự động:
  1. PAUSE      — CPL > 500k VÀ quality < 4
  2. SCALE      — CPL < 150k VÀ quality >= 7
  3. TEST_BUDGET — CTR < 1%
  4. FREQ_CAP   — Frequency > 3.5
  5. WINNER     — quality >= 8 → duplicate với budget x2

Hỗ trợ DRY_RUN mode (chỉ preview, không gọi API).
"""
import os
import json
import logging
from datetime import datetime
from typing import Optional

log = logging.getLogger("ads_optimizer")

DRY_RUN = os.getenv("ADS_DRY_RUN", "true").lower() == "true"

# ── Rule thresholds ───────────────────────────────────────────────────────────
RULE_PAUSE_CPL      = float(os.getenv("RULE_PAUSE_CPL",      "500000"))
RULE_PAUSE_QUALITY  = float(os.getenv("RULE_PAUSE_QUALITY",  "4.0"))
RULE_SCALE_CPL      = float(os.getenv("RULE_SCALE_CPL",      "150000"))
RULE_SCALE_QUALITY  = float(os.getenv("RULE_SCALE_QUALITY",  "7.0"))
RULE_SCALE_FACTOR   = float(os.getenv("RULE_SCALE_FACTOR",   "1.5"))    # +50%
RULE_CTR_POOR       = float(os.getenv("RULE_CTR_POOR",       "1.0"))
RULE_CTR_BUDGET_CUT = float(os.getenv("RULE_CTR_BUDGET_CUT", "0.7"))    # -30%
RULE_FREQ_CAP       = float(os.getenv("RULE_FREQ_CAP",       "3.5"))
RULE_WINNER_QUALITY = float(os.getenv("RULE_WINNER_QUALITY", "8.0"))
RULE_WINNER_BUDGET  = float(os.getenv("RULE_WINNER_BUDGET",  "2.0"))    # x2


class AdsOptimizer:
    """Chạy optimization cycle và apply actions qua Meta API."""

    def __init__(self, dry_run: bool = None):
        from .fb_ads_api         import FacebookAdsAPI
        from .cost_analyzer      import CostAnalyzer
        from .lead_quality_scorer import LeadQualityScorer

        self.fb       = FacebookAdsAPI()
        self.analyzer = CostAnalyzer(fb_api=self.fb)
        self.scorer   = LeadQualityScorer()
        self.dry_run  = DRY_RUN if dry_run is None else dry_run

        if self.dry_run:
            log.info("🔍 Optimizer chạy ở DRY RUN mode — không thực thi API")

    # ── Run cycle ─────────────────────────────────────────────────────────────

    def run_optimization_cycle(self, date_preset: str = "last_7d") -> dict:
        """
        Chạy toàn bộ cycle: phân tích → generate actions → apply (nếu live).
        Returns dict với list of actions và summary.
        """
        log.info("=" * 60)
        log.info(f"🤖 ADS OPTIMIZER — {datetime.now().strftime('%d/%m/%Y %H:%M')}")
        log.info(f"   Mode: {'DRY RUN' if self.dry_run else '⚡ LIVE'}")

        campaigns = self.fb.get_campaigns()
        actions   = []
        applied   = 0
        errors    = 0

        for camp in campaigns:
            if camp.get("status") == "DELETED":
                continue

            camp_id  = camp["id"]
            camp_name = camp["name"]

            try:
                # Phân tích cost
                cost = self.analyzer.analyze_campaign_costs(camp_id, date_preset)

                # Lấy quality ranking
                adsets = self.fb.get_adsets(camp_id)

                for adset in adsets:
                    adset_id     = adset["id"]
                    adset_name   = adset.get("name", adset_id)
                    adset_budget = int(adset.get("daily_budget", 0))

                    # Quality score của adset (trung bình từ ads)
                    ads            = self.fb.get_ads(adset_id)
                    quality_scores = []
                    for ad in ads:
                        qd = self.scorer.map_ad_to_lead_quality(ad["id"])
                        if qd["lead_count"] > 0:
                            quality_scores.append(qd["avg_quality"])
                    avg_quality = (sum(quality_scores) / len(quality_scores)
                                   if quality_scores else 0)

                    cpl = float(cost.get("cpl", 0))
                    ctr = float(cost.get("ctr", 0))
                    freq = float(cost.get("frequency", 0))

                    # ── Apply rules ───────────────────────────────────────────
                    adset_actions = self._evaluate_rules(
                        adset_id, adset_name, camp_name,
                        cpl, ctr, freq, avg_quality, adset_budget,
                    )
                    actions.extend(adset_actions)

            except Exception as e:
                log.warning(f"Lỗi xử lý campaign {camp_id}: {e}")
                errors += 1

        # Apply actions nếu live mode
        if not self.dry_run:
            for action in actions:
                success = self.apply_action(action)
                if success:
                    applied += 1
                    action["status"] = "applied"
                else:
                    action["status"] = "failed"
                    errors += 1
        else:
            for action in actions:
                action["status"] = "preview"

        # Lưu log vào DB
        self._save_optimization_log(actions)

        summary = {
            "run_at":        datetime.now().isoformat(),
            "dry_run":       self.dry_run,
            "campaigns":     len(campaigns),
            "total_actions": len(actions),
            "applied":       applied,
            "errors":        errors,
            "actions":       actions,
        }

        log.info(f"✅ Cycle xong: {len(actions)} actions | {applied} applied | {errors} lỗi")
        return summary

    def _evaluate_rules(self, adset_id: str, adset_name: str, camp_name: str,
                        cpl: float, ctr: float, freq: float,
                        avg_quality: float, current_budget: int) -> list[dict]:
        """Đánh giá tất cả rules và trả về list actions."""
        actions = []
        base = {
            "adset_id":   adset_id,
            "adset_name": adset_name,
            "campaign":   camp_name,
            "evaluated_at": datetime.now().isoformat(),
            "metrics": {
                "cpl": cpl, "ctr": ctr,
                "frequency": freq, "avg_quality": avg_quality,
            }
        }

        # Rule 1 — PAUSE: CPL quá cao VÀ quality thấp
        if cpl > RULE_PAUSE_CPL and avg_quality < RULE_PAUSE_QUALITY and cpl > 0:
            actions.append({**base,
                "rule":    "PAUSE",
                "action":  "pause_adset",
                "reason":  f"CPL {cpl:,.0f}đ > {RULE_PAUSE_CPL:,.0f}đ & quality {avg_quality:.1f} < {RULE_PAUSE_QUALITY}",
                "impact":  "🔴 Tiết kiệm ngân sách — dừng adset không hiệu quả",
                "params":  {"adset_id": adset_id},
            })

        # Rule 2 — SCALE: CPL thấp VÀ quality cao
        elif cpl > 0 and cpl < RULE_SCALE_CPL and avg_quality >= RULE_SCALE_QUALITY:
            new_budget = int(current_budget * RULE_SCALE_FACTOR)
            actions.append({**base,
                "rule":    "SCALE",
                "action":  "update_budget",
                "reason":  f"CPL {cpl:,.0f}đ < {RULE_SCALE_CPL:,.0f}đ & quality {avg_quality:.1f} ≥ {RULE_SCALE_QUALITY}",
                "impact":  f"🟢 Tăng ngân sách {current_budget:,}đ → {new_budget:,}đ (+50%)",
                "params":  {"adset_id": adset_id, "new_budget": new_budget},
            })

        # Rule 3 — TEST_BUDGET: CTR quá thấp
        if ctr > 0 and ctr < RULE_CTR_POOR:
            cut_budget = int(current_budget * RULE_CTR_BUDGET_CUT)
            actions.append({**base,
                "rule":    "TEST_BUDGET",
                "action":  "update_budget",
                "reason":  f"CTR {ctr:.2f}% < {RULE_CTR_POOR}% — content không hút clicks",
                "impact":  f"🟡 Giảm budget {current_budget:,}đ → {cut_budget:,}đ, cần A/B test creative",
                "params":  {"adset_id": adset_id, "new_budget": cut_budget},
            })

        # Rule 4 — FREQUENCY CAP: Ad fatigue
        if freq > RULE_FREQ_CAP:
            actions.append({**base,
                "rule":    "FREQ_CAP",
                "action":  "pause_adset",
                "reason":  f"Frequency {freq:.1f}x > {RULE_FREQ_CAP}x — audience bão hòa",
                "impact":  "🟡 Tạm dừng để refresh creative / mở rộng audience",
                "params":  {"adset_id": adset_id},
            })

        # Rule 5 — WINNER: Nhân rộng adset chất lượng rất cao
        if avg_quality >= RULE_WINNER_QUALITY and cpl > 0 and cpl < RULE_SCALE_CPL * 2:
            winner_budget = int(current_budget * RULE_WINNER_BUDGET)
            actions.append({**base,
                "rule":    "WINNER",
                "action":  "duplicate_adset",
                "reason":  f"Quality {avg_quality:.1f} ≥ {RULE_WINNER_QUALITY} — adset VIP",
                "impact":  f"🏆 Nhân bản adset với budget {winner_budget:,}đ (x2)",
                "params":  {"adset_id": adset_id, "new_budget": winner_budget,
                             "suffix": "_WINNER_SCALED"},
            })

        return actions

    # ── Apply actions ─────────────────────────────────────────────────────────

    def apply_action(self, action: dict) -> bool:
        """Thực thi 1 action qua Meta API."""
        try:
            act    = action.get("action")
            params = action.get("params", {})

            if act == "pause_adset":
                self.fb.pause_adset(params["adset_id"])
            elif act == "enable_adset":
                self.fb.enable_adset(params["adset_id"])
            elif act == "update_budget":
                self.fb.update_budget(params["adset_id"], params["new_budget"])
            elif act == "duplicate_adset":
                self.fb.duplicate_adset(
                    params["adset_id"],
                    params["new_budget"],
                    params.get("suffix", "_SCALED"),
                )
            else:
                log.warning(f"Unknown action: {act}")
                return False

            log.info(f"  ✅ Applied [{action['rule']}] → {act} on {params.get('adset_id')}")
            return True

        except Exception as e:
            log.error(f"  ❌ Lỗi apply action {action.get('rule')}: {e}")
            return False

    def get_pending_actions(self, date_preset: str = "last_7d") -> list[dict]:
        """Preview actions sẽ được thực hiện (luôn dry run)."""
        original = self.dry_run
        self.dry_run = True
        result = self.run_optimization_cycle(date_preset)
        self.dry_run = original
        return result.get("actions", [])

    # ── Logging vào DB ────────────────────────────────────────────────────────

    def _save_optimization_log(self, actions: list[dict]):
        """Ghi log optimization vào DB."""
        try:
            from src.database import SessionLocal, OptimizationLog
            db = SessionLocal()
            for action in actions:
                entry = OptimizationLog(
                    run_at      = datetime.now(),
                    dry_run     = self.dry_run,
                    rule        = action.get("rule"),
                    action      = action.get("action"),
                    adset_id    = action.get("adset_id"),
                    adset_name  = action.get("adset_name"),
                    campaign    = action.get("campaign"),
                    reason      = action.get("reason"),
                    impact      = action.get("impact"),
                    params_json = json.dumps(action.get("params", {})),
                    status      = action.get("status", "preview"),
                    metrics_json = json.dumps(action.get("metrics", {})),
                )
                db.add(entry)
            db.commit()
            db.close()
        except Exception as e:
            log.warning(f"Không ghi được OptimizationLog: {e}")
