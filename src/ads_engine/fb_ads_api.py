"""
fb_ads_api.py — Wrapper Facebook Marketing API
==============================================
Hỗ trợ: tạo campaign, adset, ad; kéo insights; điều chỉnh ngân sách; bật/tắt ad.
Hoạt động ở 2 chế độ:
  - LIVE: Gọi API thực (cần META_ACCESS_TOKEN, META_AD_ACCOUNT_ID)
  - MOCK: Trả dữ liệu giả để test/demo dashboard
"""
import os
import json
import time
import logging
from datetime import datetime, timedelta
from typing import Optional

import requests

log = logging.getLogger("fb_ads_api")

# ── Config từ env ─────────────────────────────────────────────────────────────
ACCESS_TOKEN   = os.getenv("META_ACCESS_TOKEN", "")
AD_ACCOUNT_ID  = os.getenv("META_AD_ACCOUNT_ID", "act_000000000")  # dạng act_xxxxxxx
APP_ID         = os.getenv("META_APP_ID", "")
API_VERSION    = os.getenv("META_API_VERSION", "v20.0")
BASE_URL       = f"https://graph.facebook.com/{API_VERSION}"
MOCK_MODE      = not bool(ACCESS_TOKEN) or os.getenv("ADS_MOCK_MODE", "false").lower() == "true"


class FacebookAdsAPI:
    """Wrapper gọi Facebook Marketing API với fallback sang mock data."""

    def __init__(self):
        self.token   = ACCESS_TOKEN
        self.account = AD_ACCOUNT_ID
        self.mock    = MOCK_MODE
        if self.mock:
            log.warning("⚠️  FacebookAdsAPI chạy ở MOCK MODE — không gọi API thực")

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _get(self, endpoint: str, params: dict = None) -> dict:
        if self.mock:
            return {}
        params = params or {}
        params["access_token"] = self.token
        r = requests.get(f"{BASE_URL}/{endpoint}", params=params, timeout=30)
        r.raise_for_status()
        return r.json()

    def _post(self, endpoint: str, data: dict = None) -> dict:
        if self.mock:
            log.info(f"[MOCK] POST /{endpoint} data={data}")
            return {"id": f"mock_{int(time.time())}", "success": True}
        data = data or {}
        data["access_token"] = self.token
        r = requests.post(f"{BASE_URL}/{endpoint}", json=data, timeout=30)
        r.raise_for_status()
        return r.json()

    def _delete(self, endpoint: str) -> dict:
        if self.mock:
            log.info(f"[MOCK] DELETE /{endpoint}")
            return {"success": True}
        r = requests.delete(f"{BASE_URL}/{endpoint}",
                            params={"access_token": self.token}, timeout=30)
        r.raise_for_status()
        return r.json()

    # ── Campaigns ─────────────────────────────────────────────────────────────

    def get_campaigns(self, status_filter: str = "ACTIVE,PAUSED") -> list[dict]:
        """Lấy danh sách campaigns của ad account."""
        if self.mock:
            return _mock_campaigns()
        fields = "id,name,status,objective,daily_budget,lifetime_budget,start_time,stop_time"
        data = self._get(f"{self.account}/campaigns",
                         {"fields": fields, "filtering": f"[{{\"field\":\"effective_status\",\"operator\":\"IN\",\"value\":{json.dumps(status_filter.split(','))}}}]"})
        return data.get("data", [])

    def create_campaign(self, name: str, objective: str = "LEAD_GENERATION",
                        daily_budget_vnd: int = 200_000,
                        status: str = "PAUSED") -> dict:
        """Tạo campaign mới. Mặc định PAUSED để xem xét trước khi chạy."""
        payload = {
            "name": name,
            "objective": objective,
            "status": status,
            "daily_budget": daily_budget_vnd,  # VND (đơn vị nhỏ nhất = đồng)
            "special_ad_categories": [],
        }
        result = self._post(f"{self.account}/campaigns", payload)
        log.info(f"✅ Tạo campaign '{name}' → id={result.get('id')}")
        return result

    # ── Ad Sets ───────────────────────────────────────────────────────────────

    def get_adsets(self, campaign_id: str) -> list[dict]:
        """Lấy tất cả adsets trong một campaign."""
        if self.mock:
            return _mock_adsets(campaign_id)
        fields = "id,name,status,daily_budget,targeting,start_time,end_time,bid_amount"
        data = self._get(f"{campaign_id}/adsets", {"fields": fields})
        return data.get("data", [])

    def create_adset(self, campaign_id: str, name: str,
                     daily_budget_vnd: int = 100_000,
                     targeting: dict = None,
                     optimization_goal: str = "LEAD_GENERATION",
                     status: str = "PAUSED") -> dict:
        """Tạo adset với targeting tùy chỉnh."""
        targeting = targeting or {
            "geo_locations": {"countries": ["VN"]},
            "age_min": 25,
            "age_max": 55,
        }
        payload = {
            "campaign_id": campaign_id,
            "name": name,
            "daily_budget": daily_budget_vnd,
            "targeting": json.dumps(targeting),
            "optimization_goal": optimization_goal,
            "billing_event": "IMPRESSIONS",
            "status": status,
            "start_time": (datetime.now() + timedelta(hours=1)).isoformat(),
        }
        result = self._post(f"{self.account}/adsets", payload)
        log.info(f"✅ Tạo adset '{name}' trong campaign {campaign_id}")
        return result

    def update_budget(self, adset_id: str, new_daily_budget_vnd: int) -> dict:
        """Cập nhật ngân sách hàng ngày của adset."""
        result = self._post(adset_id, {"daily_budget": new_daily_budget_vnd})
        log.info(f"💰 Update budget adset {adset_id} → {new_daily_budget_vnd:,}đ/ngày")
        return result

    def pause_adset(self, adset_id: str) -> dict:
        """Tạm dừng adset."""
        result = self._post(adset_id, {"status": "PAUSED"})
        log.info(f"⏸️  Pause adset {adset_id}")
        return result

    def enable_adset(self, adset_id: str) -> dict:
        """Bật lại adset."""
        result = self._post(adset_id, {"status": "ACTIVE"})
        log.info(f"▶️  Enable adset {adset_id}")
        return result

    def duplicate_adset(self, adset_id: str, new_budget_vnd: int,
                        new_name_suffix: str = "_SCALED") -> dict:
        """Nhân bản adset thắng với ngân sách mới."""
        if self.mock:
            log.info(f"[MOCK] Duplicate adset {adset_id} budget={new_budget_vnd:,}đ")
            return {"id": f"dup_{adset_id}_{int(time.time())}", "success": True}
        result = self._post(f"{adset_id}/copies", {
            "campaign_id": None,  # giữ nguyên campaign
            "deep_copy": False,
            "status_option": "PAUSED",
            "rename_options": {
                "rename_suffix": new_name_suffix,
                "rename_type": "SUFFIX",
            },
        })
        if result.get("copied_adset_id"):
            self.update_budget(result["copied_adset_id"], new_budget_vnd)
        log.info(f"📋 Duplicate adset {adset_id} → {result.get('copied_adset_id')}")
        return result

    # ── Ads ───────────────────────────────────────────────────────────────────

    def get_ads(self, adset_id: str) -> list[dict]:
        """Lấy tất cả ads trong adset."""
        if self.mock:
            return _mock_ads(adset_id)
        fields = "id,name,status,creative,effective_status"
        data = self._get(f"{adset_id}/ads", {"fields": fields})
        return data.get("data", [])

    def pause_ad(self, ad_id: str) -> dict:
        result = self._post(ad_id, {"status": "PAUSED"})
        log.info(f"⏸️  Pause ad {ad_id}")
        return result

    def enable_ad(self, ad_id: str) -> dict:
        result = self._post(ad_id, {"status": "ACTIVE"})
        log.info(f"▶️  Enable ad {ad_id}")
        return result

    # ── Insights (metrics) ────────────────────────────────────────────────────

    def get_insights(self, object_id: str, date_preset: str = "last_7d",
                     level: str = "ad",
                     date_range: tuple = None) -> list[dict]:
        """
        Kéo metrics từ Ads Insights API.
        object_id: campaign_id | adset_id | ad_id
        level: campaign | adset | ad
        """
        if self.mock:
            return _mock_insights(object_id, level)

        fields = ",".join([
            "campaign_id", "campaign_name",
            "adset_id", "adset_name",
            "ad_id", "ad_name",
            "impressions", "clicks", "spend",
            "cpm", "cpc", "ctr", "frequency", "reach",
            "actions", "cost_per_action_type",
            "conversions", "cost_per_conversion",
        ])
        params = {
            "fields": fields,
            "level": level,
            "limit": 200,
        }
        if date_range:
            params["time_range"] = json.dumps({
                "since": date_range[0],
                "until": date_range[1],
            })
        else:
            params["date_preset"] = date_preset

        data = self._get(f"{object_id}/insights", params)
        return data.get("data", [])

    def get_lead_form_submissions(self, form_id: str) -> list[dict]:
        """Lấy submissions từ Lead Form (Lead Ads)."""
        if self.mock:
            return _mock_lead_submissions(form_id)
        fields = "id,created_time,field_data"
        data = self._get(f"{form_id}/leads", {"fields": fields, "limit": 500})
        return data.get("data", [])


# ── Mock data generators ──────────────────────────────────────────────────────

def _mock_campaigns() -> list[dict]:
    import random
    names = [
        "BĐS Vinhomes Q7 - Lead Gen v3",
        "Đất nền Bình Dương - Retarget",
        "Căn hộ Hà Nội - Prospecting",
        "Biệt thự Đà Nẵng VIP - LAL",
        "Shophouse Hải Phòng - TOFU",
    ]
    statuses = ["ACTIVE", "ACTIVE", "ACTIVE", "PAUSED", "ACTIVE"]
    return [
        {
            "id": f"camp_{1000 + i}",
            "name": names[i],
            "status": statuses[i],
            "objective": "LEAD_GENERATION",
            "daily_budget": str(random.choice([300_000, 500_000, 1_000_000, 2_000_000])),
            "lifetime_budget": "0",
            "start_time": "2026-03-01T00:00:00+0700",
        }
        for i in range(5)
    ]

def _mock_adsets(campaign_id: str) -> list[dict]:
    import random
    return [
        {
            "id": f"adset_{campaign_id}_{j}",
            "name": f"AdSet {j+1} — {['25-35 Nam', '35-45 Nữ', 'Lookalike 2%', 'Retarget Video'][j % 4]}",
            "status": random.choice(["ACTIVE", "ACTIVE", "PAUSED"]),
            "daily_budget": str(random.choice([150_000, 250_000, 500_000])),
        }
        for j in range(random.randint(2, 4))
    ]

def _mock_ads(adset_id: str) -> list[dict]:
    import random
    creatives = ["Video BĐS 30s", "Carousel Dự Án", "Image Single", "Story Ad"]
    return [
        {
            "id": f"ad_{adset_id}_v{k+1}",
            "name": f"{creatives[k % 4]} v{k+1}",
            "status": "ACTIVE" if k == 0 else random.choice(["ACTIVE", "PAUSED"]),
            "effective_status": "ACTIVE",
        }
        for k in range(random.randint(1, 3))
    ]

def _mock_insights(object_id: str, level: str) -> list[dict]:
    import random, hashlib
    # Seed theo object_id để cho consistent data
    seed = int(hashlib.md5(object_id.encode()).hexdigest()[:8], 16)
    rng  = random.Random(seed)

    rows = []
    for i in range(7):
        date = (datetime.now() - timedelta(days=6-i)).strftime("%Y-%m-%d")
        impressions = rng.randint(3_000, 25_000)
        clicks      = rng.randint(30, max(31, int(impressions * 0.045)))
        spend       = rng.uniform(100_000, 800_000)
        leads       = rng.randint(1, max(2, int(clicks * 0.12)))
        rows.append({
            "campaign_id":   object_id if level == "campaign" else f"camp_{rng.randint(1000,1004)}",
            "adset_id":      object_id if level == "adset" else f"adset_{rng.randint(1,5)}",
            "ad_id":         object_id if level == "ad"    else f"ad_{rng.randint(1,10)}",
            "date_start":    date,
            "date_stop":     date,
            "impressions":   impressions,
            "clicks":        clicks,
            "spend":         round(spend, 0),
            "cpm":           round(spend / impressions * 1000, 2),
            "cpc":           round(spend / clicks if clicks else 0, 2),
            "ctr":           round(clicks / impressions * 100, 4),
            "frequency":     round(rng.uniform(1.1, 4.5), 2),
            "reach":         int(impressions / rng.uniform(1.1, 2.5)),
            "leads":         leads,
            "spend_vnd":     round(spend, 0),
        })
    return rows

def _mock_lead_submissions(form_id: str) -> list[dict]:
    import random
    names = ["Nguyễn Văn A", "Trần Thị B", "Lê Văn C", "Phạm Thị D", "Hoàng Văn E"]
    phones = ["0912345678", "0987654321", "0901234567", "0978654321", "0934567890"]
    results = []
    for i in range(random.randint(3, 12)):
        results.append({
            "id": f"lead_{form_id}_{i}",
            "created_time": (datetime.now() - timedelta(hours=random.randint(1, 168))).isoformat(),
            "field_data": [
                {"name": "full_name",    "values": [names[i % 5]]},
                {"name": "phone_number", "values": [phones[i % 5]]},
                {"name": "email",        "values": [f"user{i}@example.com"]},
            ]
        })
    return results
