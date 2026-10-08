import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from sqlalchemy import create_engine, func, text
import sys
import os
from pathlib import Path
import json
import datetime
from datetime import datetime

# Setup environment
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.database import CleanContact, SessionLocal, engine
import subprocess
import time

# Base data directory — đọc từ env, fallback về cấu trúc thư mục hiện tại
_BASE_DATA = Path(os.getenv("RAW_DATA_DIR", str(Path(__file__).parent.parent.parent / "data" / "raw"))).parent

# --- AUTOMATION: Sync on Load ---
def check_and_sync_data():
    raw_dir = _BASE_DATA / "raw"
    # Check if there are any real data files
    files = [f for f in raw_dir.glob("*") if f.suffix.lower() in [".xls", ".xlsx", ".csv", ".txt"]]
    
    if files:
        # Check if already running to avoid collisions
        is_running = False
        try:
            output = subprocess.check_output('tasklist', shell=True).decode('utf-8', errors='ignore')
            if "identity_mapper" in output or "python.exe" in output: # Simplistic check
                # For more precision, we could check the specific command line but tasklist is faster
                is_running = True
        except:
            pass
            
        if not is_running:
            with st.status("🚀 Phát hiện dữ liệu mới! Đang tự động đồng bộ...", expanded=False) as status:
                st.write("Đang ánh xạ định danh (UID/Phone)...")
                subprocess.Popen([sys.executable,
                                  str(Path(__file__).parent.parent / "phase1_pipeline" / "identity_mapper.py")],
                                 creationflags=subprocess.CREATE_NEW_CONSOLE if os.name == 'nt' else 0)
                st.write("Tiến trình đã được đẩy vào hàng đợi xử lý ngầm.")
                status.update(label="✅ Đang đồng bộ ngầm. Dữ liệu sẽ xuất hiện sau vài phút.", state="complete")
        else:
            st.sidebar.warning("⚙️ Hệ thống đang xử lý dữ liệu ngầm...")

# Always check on start
if "sync_checked" not in st.session_state:
    check_and_sync_data()
    st.session_state.sync_checked = True

# --- CONFIGURATION ---
st.set_page_config(
    page_title="Antigravity Marketing OS - National Lead Ingestion",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for Premium Look
st.markdown("""
    <style>
    .main {
        background-color: #0e1117;
    }
    .stMetric {
        background-color: #1e2130;
        padding: 15px;
        border-radius: 10px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    div[data-testid="metric-container"] {
        border-left: 5px solid #00d4ff;
    }
    </style>
    """, unsafe_allow_html=True)

# --- DATA HELPERS ---
@st.cache_data(ttl=300)
def get_system_overview():
    """Lấy thống kê hệ thống về tệp và dữ liệu"""
    raw_dir = _BASE_DATA / "raw"
    processed_dir = _BASE_DATA / "processed"
    
    raw_files = len(list(raw_dir.glob("**/*.*")))
    proc_files = len(list(processed_dir.glob("**/*.*")))
    
    with engine.connect() as conn:
        total_raw = conn.execute(text("SELECT COUNT(*) FROM raw_contacts")).scalar()
        total_clean = conn.execute(text("SELECT COUNT(*) FROM clean_contacts")).scalar()
        total_profiles = conn.execute(text("SELECT COUNT(*) FROM customer_profiles")).scalar()
        
    return {
        "raw_files": raw_files,
        "processed_files": proc_files,
        "total_raw_rows": total_raw,
        "total_clean_leads": total_clean,
        "total_identity_profiles": total_profiles
    }

@st.cache_data(ttl=600)
def get_smart_clusters():
    """Lấy dữ liệu phân cụm thực tế từ AI Clustering V3"""
    with engine.connect() as conn:
        res = conn.execute(text("""
            SELECT persona as Nhóm, COUNT(*) as "Số lượng"
            FROM clean_contacts
            GROUP BY persona
            ORDER BY "Số lượng" DESC
        """)).fetchall()
        
        # Fallback if no persona column yet or empty
        if not res:
            return pd.DataFrame([{"Nhóm": "Chưa có dữ liệu AI", "Số lượng": 0}])
            
    return pd.DataFrame([{"Nhóm": r[0] if r[0] else "Chưa phân loại", "Số lượng": r[1]} for r in res])

@st.cache_data(ttl=300)
def get_dashboard_stats():
    """Lấy dữ liệu từ bảng DashboardStats để hiển thị tức thì"""
    with engine.connect() as conn:
        res = conn.execute(text("SELECT total_leads, vip_leads, provincial_distribution, snapshot_time FROM dashboard_stats WHERE is_latest = 1 ORDER BY snapshot_time DESC LIMIT 1")).fetchone()
        
    if res:
        total, vip, dist_json, snapshot_time = res
        dist_df = pd.DataFrame(json.loads(dist_json))
        return total, vip, dist_df, snapshot_time
    return None, None, None, None

@st.cache_data(ttl=600)
def get_source_distribution():
    with engine.connect() as conn:
        res = conn.execute(text("SELECT file_source, COUNT(*) as count FROM clean_contacts GROUP BY file_source ORDER BY count DESC LIMIT 15"))
        data = [{"Source": Path(str(r[0])).name if r[0] else "Unknown", "Count": r[1]} for r in res]
    return pd.DataFrame(data)

# --- DASHBOARD UI ---
st.title("Antigravity Intelligence OS")
st.subheader("He thong Quan tri Danh tinh Lead Quoc gia")

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "Tong Quan He Thong",
    "Phan Cum Thong Minh",
    "360 Profile",
    "Tieu Chuan VIP",
    "Data Health"
])

with tab1:
    sys_stats = get_system_overview()
    total, vip, dist_df, snapshot_time = get_dashboard_stats()
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("📦 Tổng File Xử Lý", f"{sys_stats['processed_files'] + sys_stats['raw_files']}")
    with col2:
        st.metric("👥 Tổng Lead Sạch", f"{sys_stats['total_clean_leads']:,}")
    with col3:
        st.metric("🆔 Hồ Sơ Định Danh", f"{sys_stats['total_identity_profiles']:,}")
    with col4:
        st.metric("💎 Khách Hàng VIP", f"{vip or 0:,}")

    st.divider()
    c1, c2 = st.columns([1, 1])
    with c1:
        st.write("#### 📂 15 Nguồn Dữ Liệu Lớn Nhất")
        src_df = get_source_distribution()
        fig2 = px.bar(src_df, x='Count', y='Source', orientation='h', color='Count', color_continuous_scale='Bluered')
        fig2.update_layout(template="plotly_dark", height=400, margin=dict(l=0, r=0, b=0, t=30))
        st.plotly_chart(fig2, use_container_width=True)
        
    with c2:
        st.write("#### 📍 Phân Bổ Địa Lý (Top Tỉnh Thành)")
        if dist_df is not None:
            fig = px.pie(dist_df.head(8), values='Count', names='Province', hole=.4, color_discrete_sequence=px.colors.qualitative.Pastel)
            fig.update_layout(template="plotly_dark", height=400, margin=dict(l=0, r=0, b=0, t=30))
            st.plotly_chart(fig, use_container_width=True)

with tab2:
    st.write("### 🧩 Phân Nhóm Khách Hàng Tự Động (AI Clustering)")
    st.info("Hệ thống tự động phân loại lead dựa trên lịch sử xuất hiện và hành vi thông qua các nguồn dữ liệu.")
    
    cluster_df = get_smart_clusters()
    
    col_c1, col_c2 = st.columns([2, 1])
    with col_c1:
        fig_cluster = px.bar(cluster_df, x='Nhóm', y='Số lượng', color='Nhóm', text_auto='.2s')
        fig_cluster.update_layout(template="plotly_dark", height=500)
        st.plotly_chart(fig_cluster, use_container_width=True)
    
    with col_c2:
        st.write("#### 🏷️ Đặc điểm nhận diện:")
        st.markdown("""
        - **💎 High-Net-Worth VIP:** Nhóm có điểm chất lượng cao nhất, sở hữu BĐS hoặc tài sản lớn.
        - **🏢 Professional / Business:** Nhóm quản lý, CEO, Doanh nhân.
        - **🕵️ Cross-Referenced Potential:** Nhóm xuất hiện ở nhiều nguồn, thông tin cực kỳ tin cậy.
        - **👤 General / Mass Market:** Nhóm khách hàng đại chúng.
        """)

with tab3:
    st.write("### 🔍 Truy Vết Danh Tính 360°")
    q = st.text_input("Tìm kiếm theo SĐT, Email hoặc UID...", key="search_360")
    
    if q:
        db = SessionLocal()
        lead = db.query(CleanContact).filter(
            (CleanContact.so_dien_thoai == q) | 
            (CleanContact.facebook_uid == q) |
            (CleanContact.email == q) |
            (CleanContact.ho_ten.ilike(f"%{q}%"))
        ).first()
        
        if lead:
            st.success(f"Đã tìm thấy hồ sơ: {lead.ho_ten}")
            
            c360_1, c360_2 = st.columns([1, 2])
            with c360_1:
                st.image("https://cdn-icons-png.flaticon.com/512/3135/3135715.png", width=150)
                st.write(f"### {lead.ho_ten}")
                score_val = getattr(lead, 'unified_score', None) or 0
                score_color = "green" if score_val >= 70 else "orange" if score_val >= 40 else "grey"
                label = '💎 VIP ELITE' if score_val >= 70 else '✅ ACTIVE' if score_val >= 40 else '⚪ STANDARD'
                st.markdown(f"**Trạng thái:** <span style='color:{score_color}'>{label}</span>", unsafe_allow_html=True)
                st.write(f"**Unified Score:** `{score_val}/100`")
                
                if lead.facebook_uid:
                    st.link_button("🌐 Mở Facebook Profile", f"https://facebook.com/{lead.facebook_uid}", use_container_width=True)
                if lead.so_dien_thoai:
                    st.button(f"📞 Gọi ngay: {lead.so_dien_thoai}", use_container_width=True)

            with c360_2:
                with st.expander("📌 Thông tin Cơ bản", expanded=True):
                    st.write(f"**SĐT:** {lead.so_dien_thoai}")
                    st.write(f"**Email:** {lead.email or 'N/A'}")
                    st.write(f"**Địa chỉ:** {lead.dia_chi or 'N/A'}")
                
                with st.expander("📂 Lịch sử Dấu chân (Historical Footprint)", expanded=True):
                    all_src = getattr(lead, 'all_sources', None) or getattr(lead, 'nguon', '') or 'N/A'
                    sources = all_src.split(",") if all_src else ['N/A']
                    for s in sources:
                        st.code(s.strip(), language="text")
                
                if lead.metadata_json:
                    with st.expander("📊 Dữ liệu Hành vi & Meta", expanded=True):
                        try:
                            meta = json.loads(lead.metadata_json)
                            # Render meta as nice badges if possible
                            cols_meta = st.columns(3)
                            if "source" in meta: cols_meta[0].info(f"Source: {meta['source']}")
                            if "location" in meta: cols_meta[1].success(f"Loc: {meta['location']}")
                            if "interest" in meta: cols_meta[2].warning(f"Interest: {meta['interest']}")
                            st.json(meta)
                        except:
                            st.text(lead.metadata_json)
        else:
            st.error("Không tìm thấy dữ liệu.")
        db.close()

with tab4:
    st.write("### 💎 Hệ thống Tiêu chuẩn VIP")
    st.markdown("""
    Việc xác định khách hàng VIP được dựa trên thuật toán chấm điểm đa điểm chạm (Multi-touch Scoring):
    
    1.  **Sở hữu BĐS Cao cấp (+3 điểm):** Có mặt trong danh sách Vinhomes, Novaland, biệt thự...
    2.  **Vị thế xã hội (+3 điểm):** Là CEO, Giám đốc, hoặc có chức vụ quản lý từ dữ liệu Vietnamwork.
    3.  **Sức mạnh tài chính (+2 điểm):** Lead từ các tệp Priority Banking, thẻ tín dụng hạn mức cao.
    4.  **Tần suất xuất hiện (+2 điểm):** Lead xuất hiện ở trên 3 nguồn dữ liệu khác nhau (Cross-verified).
    5.  **SĐT VIP (+1 điểm):** Sở hữu số điện thoại tứ quý, tam hoa hoặc đầu số cổ.
    """)
    
    st.divider()
    st.write("#### 🏆 Danh sách TOP 100 VIP Elite")
    with engine.connect() as conn:
        vip_data = conn.execute(text(
            "SELECT ho_ten, so_dien_thoai, facebook_uid, unified_score "
            "FROM clean_contacts WHERE unified_score >= 70 "
            "ORDER BY unified_score DESC LIMIT 100"
        ))
        st.dataframe(pd.DataFrame(vip_data), use_container_width=True)

# Sidebar Info
st.sidebar.image("https://cdn-icons-png.flaticon.com/512/3135/3135715.png", width=80)
st.sidebar.title("Antigravity OS")

# --- REAL-TIME PIPELINE MONITOR ---
status_file = _BASE_DATA / "pipeline_status.json"
if status_file.exists():
    try:
        with open(status_file, "r", encoding="utf-8") as f:
            status_data = json.load(f)
        
        st.sidebar.divider()
        st.sidebar.subheader("Pipeline running...")
        st.sidebar.info(f"File: `{status_data['current_file']}`")
        
        # Progress
        progress = status_data['processed_count'] / status_data['total_files']
        st.sidebar.progress(progress, text=f"{status_data['processed_count']}/{status_data['total_files']} files")
        
        # Duration
        start_time = datetime.fromisoformat(status_data['start_time'])
        elapsed = datetime.now() - start_time
        mins, secs = divmod(elapsed.seconds, 60)
        st.sidebar.write(f"Runtime: **{mins}p {secs}s**")
        
        # Auto-refresh
        time.sleep(2)
        st.rerun()
    except:
        pass

st.sidebar.divider()
st.sidebar.info(f"Identity Map: 15.1 GB\nLeads: {sys_stats.get('total_clean_leads', 0):,}")

if st.sidebar.button("Force Refresh Database"):
    st.cache_data.clear()
    st.rerun()

st.sidebar.divider()
st.sidebar.subheader("Manually Trigger Pipeline")
if st.sidebar.button("🚀 Run Phase 3 (Scoring)"):
    with st.status("Đang chạy AI Scoring..."):
        try:
            subprocess.Popen([sys.executable, str(Path(__file__).parent.parent.parent / "main.py"), "--phase", "3"],
                             creationflags=subprocess.CREATE_NEW_CONSOLE if os.name == 'nt' else 0)
            st.success("Phase 3 đã được kích hoạt ngầm!")
        except Exception as e:
            st.error(f"Lỗi khởi động: {e}")


# ==========================================
# TAB 5: DATA HEALTH
# ==========================================

@st.cache_data(ttl=600)
def get_data_health_stats():
    """Pull analytics metrics from new columns for the Data Health tab."""
    with engine.connect() as conn:
        # Score distribution
        score_dist = conn.execute(text("""
            SELECT
                CASE
                    WHEN unified_score >= 85 THEN 'S (85-100) VIP Elite'
                    WHEN unified_score >= 70 THEN 'A (70-84) Hot Lead'
                    WHEN unified_score >= 55 THEN 'B (55-69) Warm Lead'
                    WHEN unified_score >= 40 THEN 'C (40-54) Cold Lead'
                    ELSE 'D (<40) Archive'
                END as grade,
                COUNT(*) as cnt
            FROM clean_contacts
            GROUP BY grade
            ORDER BY grade
        """)).fetchall()

        # Source tier distribution
        tier_dist = conn.execute(text("""
            SELECT
                COALESCE(source_tier, 'unknown') as tier,
                COUNT(*) as cnt,
                ROUND(AVG(COALESCE(unified_score, 0)), 1) as avg_score
            FROM clean_contacts
            GROUP BY tier
            ORDER BY avg_score DESC
        """)).fetchall()

        # Coverage metrics
        coverage = conn.execute(text("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN so_dien_thoai IS NOT NULL AND so_dien_thoai != '' THEN 1 ELSE 0 END) as has_phone,
                SUM(CASE WHEN email IS NOT NULL AND email != '' THEN 1 ELSE 0 END) as has_email,
                SUM(CASE WHEN facebook_uid IS NOT NULL AND facebook_uid != '' THEN 1 ELSE 0 END) as has_fb,
                SUM(CASE WHEN province_phone IS NOT NULL AND province_phone != 'Unknown' THEN 1 ELSE 0 END) as has_province,
                SUM(CASE WHEN source_count > 1 THEN 1 ELSE 0 END) as cross_source,
                SUM(CASE WHEN unified_score >= 70 THEN 1 ELSE 0 END) as grade_a_plus
            FROM clean_contacts
        """)).fetchone()

        # Province top 10
        province_top = conn.execute(text("""
            SELECT province_phone, COUNT(*) as cnt
            FROM clean_contacts
            WHERE province_phone IS NOT NULL AND province_phone != 'Unknown'
            GROUP BY province_phone
            ORDER BY cnt DESC
            LIMIT 10
        """)).fetchall()

    return {
        "score_dist": [(r[0], r[1]) for r in score_dist],
        "tier_dist":  [(r[0], r[1], r[2]) for r in tier_dist],
        "coverage":   dict(coverage._mapping) if coverage else {},
        "province_top": [(r[0], r[1]) for r in province_top],
    }


with tab5:
    st.write("### Data Health Monitor")
    st.caption("Coverage, Score Distribution, Source Quality — updated every 10 min")

    try:
        dh = get_data_health_stats()
        cov = dh["coverage"]
        total = cov.get("total", 1) or 1

        # KPI Row
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Phone Coverage",
                  f"{cov.get('has_phone', 0) / total * 100:.1f}%",
                  f"{cov.get('has_phone', 0):,} contacts")
        k2.metric("Email Coverage",
                  f"{cov.get('has_email', 0) / total * 100:.1f}%",
                  f"{cov.get('has_email', 0):,} contacts")
        k3.metric("Cross-Source Verified",
                  f"{cov.get('cross_source', 0) / total * 100:.1f}%",
                  f"{cov.get('cross_source', 0):,} contacts")
        k4.metric("Grade A+ Leads",
                  f"{cov.get('grade_a_plus', 0):,}",
                  f"{cov.get('grade_a_plus', 0) / total * 100:.2f}% of DB")

        st.divider()
        col_h1, col_h2 = st.columns([1, 1])

        with col_h1:
            st.write("#### Score Distribution")
            if dh["score_dist"]:
                sd_df = pd.DataFrame(dh["score_dist"], columns=["Grade", "Count"])
                fig_sd = px.bar(
                    sd_df, x="Grade", y="Count", color="Grade",
                    color_discrete_sequence=["#ff4b4b", "#ffa500", "#ffd700", "#00cc88", "#00d4ff"],
                    text_auto=True
                )
                fig_sd.update_layout(template="plotly_dark", height=350, showlegend=False)
                st.plotly_chart(fig_sd, use_container_width=True)

        with col_h2:
            st.write("#### Source Tier Quality")
            if dh["tier_dist"]:
                td_df = pd.DataFrame(dh["tier_dist"], columns=["Tier", "Count", "Avg Score"])
                fig_td = px.scatter(
                    td_df, x="Tier", y="Avg Score", size="Count",
                    color="Avg Score", color_continuous_scale="Viridis",
                    hover_data=["Count"],
                )
                fig_td.update_layout(template="plotly_dark", height=350)
                st.plotly_chart(fig_td, use_container_width=True)

        st.divider()
        st.write("#### Province Coverage (via Phone Prefix Lookup)")
        if dh["province_top"]:
            prov_df = pd.DataFrame(dh["province_top"], columns=["Province", "Count"])
            fig_prov = px.bar(
                prov_df, x="Count", y="Province", orientation="h",
                color="Count", color_continuous_scale="Blues",
                text_auto=True
            )
            fig_prov.update_layout(template="plotly_dark", height=400)
            st.plotly_chart(fig_prov, use_container_width=True)
        else:
            st.info("Province enrichment dang chay hoac chua co du lieu...")

        # Classification report
        report_path = _BASE_DATA / "file_classification_report.csv"
        if report_path.exists():
            st.divider()
            st.write("#### File Source Classification Report")
            cls_df = pd.read_csv(report_path, encoding="utf-8-sig")
            tier_summary = cls_df.groupby("label").agg(
                Files=("filename", "count"),
                Total_MB=("size_mb", "sum"),
                Avg_Weight=("weight", "mean"),
            ).reset_index().sort_values("Files", ascending=False)
            st.dataframe(tier_summary.style.format({"Total_MB": "{:.1f}", "Avg_Weight": "{:.2f}"}),
                         use_container_width=True)

    except Exception as e:
        st.error(f"Data Health error: {e}")
        st.info("Hay chay step10_rescore_all.py truoc khi xem tab nay.")

