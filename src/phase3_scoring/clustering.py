"""
clustering.py — K-Means phân cụm khách hàng thành 3 nhóm:
  Cluster 0 — Đầu cơ: quan tâm đất nền, tỉnh, quy hoạch
  Cluster 1 — Ở thực: tìm chung cư, tiện ích, trường/bệnh viện
  Cluster 2 — VIP:    tương tác BĐS nghỉ dưỡng, biệt thự, hạng sang
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans
from sklearn.impute import SimpleImputer

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.utils import setup_logger, format_number
from src.database import init_db, SessionLocal, CustomerProfile, HotLead

log = setup_logger("clustering")

CLUSTER_LABELS = {
    0: "Đầu cơ",    # Đất nền, quy hoạch tỉnh
    1: "Ở thực",    # Chung cư, tiện ích
    2: "VIP",       # Nghỉ dưỡng, biệt thự
}

# Từ khóa phân loại sở thích
KEYWORDS_DAU_CO = ["đất nền", "đất tỉnh", "quy hoạch", "đầu tư", "lô đất",
                   "mặt tiền", "đất ven biển", "tái định cư"]
KEYWORDS_O_THUC  = ["chung cư", "căn hộ", "nhà phố", "trường học", "bệnh viện",
                    "tiện ích", "ở thực", "an cư", "bé con"]
KEYWORDS_VIP     = ["biệt thự", "nghỉ dưỡng", "villa", "penthouse", "resort",
                    "hạng sang", "cao cấp", "luxury", "shophouse"]


def keyword_score(text: str, keyword_list: list[str]) -> float:
    """Tính điểm khớp từ khóa trong text"""
    if not text:
        return 0.0
    text_lower = text.lower()
    return sum(1 for kw in keyword_list if kw in text_lower)


def build_feature_matrix(profiles: list, hot_leads_map: dict, clean_map: dict = None) -> pd.DataFrame:
    """
    Feature Matrix V2 — Dùng features có giá trị thực (không rỗng).

    **Vấn đề V1:** kw_vip / kw_dau_co / kw_o_thuc luôn = 0 với data excel
    (vì `ghi_chu` rỗng), dẫn đến cluster không có ý nghĩa.

    **Features V2:**
    - unified_score:    0-100 (composite score từ Sprint 3 — luôn có)
    - source_tier_enc:  1-8 (encoded tier — luôn có)
    - source_count:     số nguồn xuất hiện
    - has_email:        binary
    - has_uid:          binary (Facebook UID)
    - hot_score:        hot_score tổng (FB + Google, nếu có)
    """
    if clean_map is None:
        clean_map = {}
    TIER_ENCODING = {
        "banking_vip":      8,
        "real_estate_vip":  7,
        "ceo_director":     7,
        "automotive_vip":   5,
        "stock_gold":       5,
        "fitness_health":   4,
        "education_hr":     3,
        "telecom_mass":     2,
        "unknown":          1,
    }

    rows = []
    for profile in profiles:
        fb_score     = hot_leads_map.get(profile.so_dien_thoai, {}).get("fb_score", 0)
        google_score = hot_leads_map.get(profile.so_dien_thoai, {}).get("google_score", 0)
        hot_total    = min(fb_score + google_score, 10)

        # Prefer CleanContact data over profile (more accurate)
        cd       = clean_map.get(profile.so_dien_thoai, {})
        u_score  = cd.get("unified_score", 0) or getattr(profile, "unified_score", 0) or 0
        s_tier   = cd.get("source_tier", "unknown") or getattr(profile, "source_tier", "unknown") or "unknown"
        s_count  = cd.get("source_count", 1) or getattr(profile, "source_count", 1) or 1

        rows.append({
            "id":              profile.id,
            "unified_score":   u_score,
            "source_tier_enc": TIER_ENCODING.get(s_tier, 1),
            "source_count":    min(s_count, 10),
            "has_email":       1 if profile.email else 0,
            "has_uid":         1 if profile.facebook_uid else 0,
            "hot_score":       hot_total,
        })

    return pd.DataFrame(rows)


def run_clustering(n_clusters: int = 3) -> dict:
    """
    Giai đoạn 3A: K-Means clustering.

    Args:
        n_clusters: Số cụm (mặc định 3: Đầu cơ / Ở thực / VIP)
    """
    log.info("=" * 60)
    log.info("PHASE 3A — K-MEANS CLUSTERING")

    init_db()
    db = SessionLocal()

    profiles = db.query(CustomerProfile).all()
    log.info(f"Customer profiles: {format_number(len(profiles))}")

    if len(profiles) < n_clusters:
        log.warning("Không đủ data để clustering!")
        db.close()
        return {"clusters": {}, "total": 0}

    # Build hot_leads lookup
    hot_leads = db.query(HotLead).all()
    hot_map: dict[str, dict] = {}
    for lead in hot_leads:
        key = lead.so_dien_thoai or ""
        if not key and lead.customer_profile_id:
            p = db.get(CustomerProfile, lead.customer_profile_id)
            key = p.so_dien_thoai if p else ""

        if key:
            existing = hot_map.get(key, {"fb_score": 0, "google_score": 0, "keyword": ""})
            if lead.nguon == "facebook":
                existing["fb_score"] = max(existing["fb_score"], lead.hot_score or 0)
            else:
                existing["google_score"] = max(existing["google_score"], lead.hot_score or 0)
            existing["keyword"] += f" {lead.keyword or ''}"
            hot_map[key] = existing

    # ── Join CleanContact để lấy unified_score, source_count, source_tier ──
    from src.database import CleanContact
    clean_rows = db.query(
        CleanContact.so_dien_thoai,
        CleanContact.source_count,
        CleanContact.unified_score,
        CleanContact.source_tier,
    ).all()
    clean_map: dict[str, dict] = {
        c.so_dien_thoai: {
            "source_count":  c.source_count  or 1,
            "unified_score": c.unified_score or 0.0,
            "source_tier":   c.source_tier   or "unknown",
        }
        for c in clean_rows if c.so_dien_thoai
    }
    log.info(f"  CleanContact enrichment: {len(clean_map):,} phone entries loaded")

    # Build feature matrix (pass clean_map for enriched features)
    df = build_feature_matrix(profiles, hot_map, clean_map)
    feature_cols = ["unified_score", "source_tier_enc", "source_count",
                    "has_email", "has_uid", "hot_score"]

    X = df[feature_cols].values

    # Impute + Scale
    imputer = SimpleImputer(strategy="median")
    X = imputer.fit_transform(X)

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    # K-Means
    kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    labels = kmeans.fit_predict(X_scaled)
    df["cluster_raw"] = labels

    # Silhouette Score validation
    try:
        from sklearn.metrics import silhouette_score
        sample_n = min(5000, len(X_scaled))
        sil = silhouette_score(X_scaled, labels, sample_size=sample_n, random_state=42)
        log.info(f"  Silhouette Score: {sil:.3f}  (>0.3 la tot, >0.5 la rat tot)")
    except Exception as sil_err:
        log.warning(f"  Silhouette Score error: {sil_err}")

    # Map cluster ID → label dựa trên trung bình unified_score của mỗi cụm
    # (Cluster có unified_score cao nhất → VIP)
    centers = pd.DataFrame(
        scaler.inverse_transform(kmeans.cluster_centers_),
        columns=feature_cols
    )
    score_ranked  = centers["unified_score"].sort_values()
    ranked_ids    = score_ranked.index.tolist()

    vip_cluster   = ranked_ids[-1]   # unified_score cao nhất
    dauco_cluster = ranked_ids[0]    # unified_score thấp nhất
    othuc_cluster = ranked_ids[1] if n_clusters >= 3 else ranked_ids[-1]

    cluster_map = {
        dauco_cluster: (0, "Standard"),
        othuc_cluster: (1, "Growth"),
        vip_cluster:   (2, "VIP"),
    }

    # Ghi cluster về database
    cluster_counts = {0: 0, 1: 0, 2: 0}
    for _, row in df.iterrows():
        raw_cluster = int(row["cluster_raw"])
        mapped_id, label = cluster_map.get(raw_cluster, (0, "Đầu cơ"))

        profile = db.get(CustomerProfile, int(row["id"]))
        if profile:
            profile.cluster       = mapped_id
            profile.cluster_label = label
            cluster_counts[mapped_id] = cluster_counts.get(mapped_id, 0) + 1

    db.commit()
    db.close()

    log.info("─" * 60)
    for cid, label in CLUSTER_LABELS.items():
        log.info(f"  Cluster {cid} — {label}: {format_number(cluster_counts.get(cid, 0))} người")
    log.info(f"✅ HOÀN TẤT Clustering")

    return {"clusters": cluster_counts, "total": len(profiles)}


if __name__ == "__main__":
    result = run_clustering()
    print(f"\nKết quả: {result}")
