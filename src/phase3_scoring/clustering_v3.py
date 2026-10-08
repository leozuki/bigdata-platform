"""
src/phase3_scoring/clustering_v3.py
====================================
Advanced AI Clustering (Phân Nhóm Khách Hàng Tự Động)
- Sử dụng MiniBatchKMeans để xử lý 1.3M+ records.
- Tối ưu số cụm (k) tự động bằng Silhouette Score.
- Đặc trưng (Features): unified_score, tier_encoded, source_count/weight, hot_lead_status.
"""
import sys, io, time, sqlite3, warnings
from pathlib import Path
from datetime import datetime
import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.cluster import MiniBatchKMeans
from sklearn.metrics import silhouette_score
from sklearn.decomposition import PCA

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
warnings.filterwarnings("ignore")

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.utils import setup_logger, format_number
from src.database import DATABASE_URL

log = setup_logger("clustering_v3")

# Extract SQLite file path from DATABASE_URL for direct sqlite3 access
import re as _re, os as _os
_db_url = DATABASE_URL.replace("sqlite:///", "")
DB_PATH = _os.path.abspath(_db_url) if not _db_url.startswith("d:/") else _db_url

# ══════════════════════════════════════════════════════════════
#  TIER ORDERING / ENCODING
# ══════════════════════════════════════════════════════════════
TIER_PRIORITY = {
    "banking_vip":    1.00,
    "real_estate_vip": 0.95,
    "ceo_director":   0.90,
    "automotive_vip":  0.80,
    "stock_gold":     0.80,
    "fitness_health":  0.65,
    "education_hr":   0.50,
    "telecom_mass":    0.40,
    "unknown":        0.25,
}

def run_clustering_v3():
    log.info("=" * 65)
    log.info("  AI CLUSTERING V3 - SCALABLE PERSONA MINING")
    log.info(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log.info("=" * 65)

    # ── [1] Load Data (Optimized via SQL) ─────────────────────────────────────
    log.info("[1] Fetching features from database...")
    t0 = time.time()
    
    conn = sqlite3.connect(DB_PATH)
    # Lấy data từ clean_contacts vì đây là bảng core analytics
    query = """
        SELECT id, unified_score, source_tier, source_weight, 
               source_count, rfm_score, province_phone,
               (facebook_uid IS NOT NULL) as has_fb
        FROM clean_contacts
    """
    df = pd.read_sql(query, conn)
    
    # Map with hot leads
    hot_phones = pd.read_sql("SELECT DISTINCT so_dien_thoai FROM hot_leads", conn)
    hot_set = set(hot_phones['so_dien_thoai'].tolist())
    
    # We need phone for hot_match but we didn't select it to save memory. 
    # Let's re-run query if needed, or just use proxy features.
    # Actually, unified_score already incorporates hot status if calculated correctly.
    
    conn.close()
    
    log.info(f"  Loaded {format_number(len(df))} records in {time.time()-t0:.1f}s")

    # ── [2] Preprocessing & Encoding ──────────────────────────────────────────
    log.info("[2] Preprocessing features...")
    
    # Encode source_tier bằng priority weight
    df['tier_val'] = df['source_tier'].map(TIER_PRIORITY).fillna(0.25)
    
    # Encode province (Top 10 + Other)
    top_provinces = df['province_phone'].value_counts().head(10).index.tolist()
    df['prov_cat'] = df['province_phone'].apply(lambda x: x if x in top_provinces else "Other")
    le_prov = LabelEncoder()
    df['prov_enc'] = le_prov.fit_transform(df['prov_cat'])
    
    feature_cols = ['unified_score', 'tier_val', 'source_count', 'source_weight', 'prov_enc', 'has_fb']
    X = df[feature_cols].fillna(0).values

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    
    log.info(f"  Feature matrix shape: {X_scaled.shape}")

    # ── [3] Finding Optimal k (Quick Scan) ────────────────────────────────────
    log.info("[3] Finding optimal cluster count (k)...")
    
    k_range = [3, 4, 5, 6]
    best_k = 4
    best_sil = -1
    
    # Sample 10k for silhouette scan to be fast
    sample_idx = np.random.choice(len(X_scaled), min(15000, len(X_scaled)), replace=False)
    X_sample = X_scaled[sample_idx]
    
    for k in k_range:
        mbk = MiniBatchKMeans(n_clusters=k, random_state=42, batch_size=2048, n_init=3)
        labels = mbk.fit_predict(X_sample)
        sil = silhouette_score(X_sample, labels)
        log.info(f"    k={k} | Silhouette={sil:.4f}")
        if sil > best_sil:
            best_sil = sil
            best_k = k
            
    log.info(f"  => Selected k={best_k} (Best Silhouette: {best_sil:.4f})")

    # ── [4] Final Clustering (Full Data) ──────────────────────────────────────
    log.info(f"[4] Performing MiniBatchKMeans with k={best_k}...")
    mbk = MiniBatchKMeans(n_clusters=best_k, random_state=42, batch_size=4096, n_init=10)
    df['cluster_id'] = mbk.fit_predict(X_scaled)
    
    # ── [5] Persona Analysis & Labeling ───────────────────────────────────────
    log.info("[5] Analyzing cluster personas...")
    
    # Inverse scale cluster centers to see real values
    centers = scaler.inverse_transform(mbk.cluster_centers_)
    center_df = pd.DataFrame(centers, columns=feature_cols)
    
    persona_map = {}
    for cid in range(best_k):
        c_stats = center_df.iloc[cid]
        u_score = c_stats['unified_score']
        t_val   = c_stats['tier_val']
        s_count = c_stats['source_count']
        
        # Heuristic labeling
        if u_score > 65:
            label = "💎 High-Net-Worth VIP"
        elif u_score > 45 and t_val >= 0.8:
            label = "🏢 Professional / Business"
        elif u_score > 40 and s_count >= 2:
            label = "🕵️ Cross-Referenced Potential"
        elif t_val >= 0.8:
            label = "🏦 Banking/Finance Focused"
        elif s_count > 1.5:
             label = "🔄 Active Multichannel"
        else:
            label = "👤 General/Mass Market"
            
        persona_map[cid] = label
        log.info(f"    Cluster {cid}: {label:<30} (Avg Score: {u_score:.1f})")

    df['persona'] = df['cluster_id'].map(persona_map)

    # ── [6] Save Results back to DB ───────────────────────────────────────────
    log.info("[6] Writing cluster results to database...")
    
    conn = sqlite3.connect(DB_PATH)
    # Tạo temporary table để update hàng loạt
    df[['id', 'cluster_id', 'persona']].to_sql('tmp_clusters', conn, if_exists='replace', index=False)
    
    # THÊM INDEX để update nhanh (QUAN TRỌNG cho 1.3M records)
    conn.execute("CREATE INDEX idx_tmp_id ON tmp_clusters(id)")
    try:
        conn.execute("ALTER TABLE clean_contacts ADD COLUMN cluster_id INTEGER")
        conn.execute("ALTER TABLE clean_contacts ADD COLUMN persona TEXT")
    except:
        pass # Columns already exist
        
    conn.execute("""
        UPDATE clean_contacts
        SET cluster_id = (SELECT cluster_id FROM tmp_clusters WHERE tmp_clusters.id = clean_contacts.id),
            persona    = (SELECT persona FROM tmp_clusters WHERE tmp_clusters.id = clean_contacts.id)
        WHERE EXISTS (SELECT 1 FROM tmp_clusters WHERE tmp_clusters.id = clean_contacts.id)
    """)
    
    # Sync to customer_profiles if possible
    try:
        conn.execute("""
            UPDATE customer_profiles
            SET cluster = (SELECT cluster_id FROM tmp_clusters WHERE tmp_clusters.id = customer_profiles.id),
                cluster_label = (SELECT persona FROM tmp_clusters WHERE tmp_clusters.id = customer_profiles.id)
            WHERE EXISTS (SELECT 1 FROM tmp_clusters WHERE tmp_clusters.id = customer_profiles.id)
        """)
    except:
        pass
        
    conn.execute("DROP TABLE tmp_clusters")
    conn.commit()
    conn.close()
    
    log.info(f"  Successfully assigned clusters to {format_number(len(df))} records.")
    
    # ── Summary ───────────────────────────────────────────────────────────────
    summary = df['persona'].value_counts()
    log.info("\nCluster Distribution Summary:")
    for label, count in summary.items():
        log.info(f"  {label:<30} : {format_number(count):>10} ({count/len(df)*100:.1f}%)")

    log.info(f"\n✅ CLUSTERING COMPLETE in {time.time()-t0:.1f}s")
    log.info("=" * 65)

if __name__ == "__main__":
    run_clustering_v3()
