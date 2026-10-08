"""
database.py — SQLAlchemy models & connection
Hỗ trợ SQLite (mặc định), PostgreSQL, và BigQuery
"""
import os
import json
from datetime import datetime
from dotenv import load_dotenv
from sqlalchemy import (
    create_engine, Column, Integer, String, Float, DateTime,
    Text, Boolean, Index, event
)
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import StaticPool

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///d:/AI/01_Products/BigData/data/bigdata.db")

# SQLite cần thêm check_same_thread=False
connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    echo=False
)

# Bật WAL mode + performance pragmas cho SQLite
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_conn, connection_record):
    if DATABASE_URL.startswith("sqlite"):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=30000")       # 30s timeout tránh DB lock
        cursor.execute("PRAGMA wal_autocheckpoint=500")   # Checkpoint mỗi ~2MB WAL
        cursor.execute("PRAGMA cache_size=-65536")        # 64MB page cache in RAM
        cursor.execute("PRAGMA temp_store=MEMORY")        # Temp tables in RAM
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class RawContact(Base):
    """Bảng chứa dữ liệu thô từ các file Excel/CSV đầu vào"""
    __tablename__ = "raw_contacts"

    id = Column(Integer, primary_key=True, index=True)
    ho_ten = Column(String(200))
    so_dien_thoai = Column(String(30))
    email = Column(String(200))
    dia_chi = Column(String(500))
    nguon = Column(String(100))           # Tên file nguồn
    ghi_chu = Column(Text)
    ngay_tao = Column(String(50))
    raw_data = Column(Text)               # JSON toàn bộ row gốc
    file_source = Column(String(500))     # Đường dẫn file nguồn
    facebook_uid = Column(String(50))
    facebook_link = Column(String(500))
    imported_at = Column(DateTime, default=datetime.utcnow)


class CleanContact(Base):
    """Bảng chứa dữ liệu sau khi làm sạch và chuẩn hóa SĐT"""
    __tablename__ = "clean_contacts"

    id = Column(Integer, primary_key=True, index=True)
    ho_ten = Column(String(200))
    all_names = Column(Text)                                     # Danh sách tên từ các nguồn khác nhau
    so_dien_thoai = Column(String(20), unique=True, index=True)  # Format +84xxx
    so_dien_thoai_goc = Column(String(30))                       # SĐT gốc trước khi clean
    email = Column(String(200))
    dia_chi = Column(String(500))
    nguon = Column(String(100))
    all_sources = Column(Text)                                   # Danh sách tất cả file chứa lead này
    ghi_chu = Column(Text)
    metadata_json = Column(Text)                                 # Chứa các thông tin bổ sung (address, note history)
    file_source = Column(String(500))
    facebook_uid = Column(String(50), index=True)
    facebook_link = Column(String(500))
    score = Column(Integer, default=0, index=True)              # Điểm chất lượng lead (0-10)
    cleaned_at = Column(DateTime, default=datetime.utcnow)
    # ── Analytics columns (Sprint 3) ──────────────────────────────────────────
    source_tier     = Column(String(30), default="unknown")      # banking_vip, real_estate_vip...
    source_weight   = Column(Float, default=0.25)                # Trọng số nguồn 0.25-1.0
    source_count    = Column(Integer, default=1)                 # Số nguồn khác nhau chứa lead
    latest_file_ts  = Column(String(50))                         # Timestamp file nguồn mới nhất
    rfm_score       = Column(Float, default=0.0)                 # RFM composite 0-10
    unified_score   = Column(Float, default=0.0)                 # Unified 100-pt score
    province_phone  = Column(String(100))                        # Province từ phone prefix


class DashboardStats(Base):
    """Bảng lưu trữ cache các chỉ số Dashboard để hiển thị tức thì"""
    __tablename__ = "dashboard_stats"

    id = Column(Integer, primary_key=True)
    snapshot_time = Column(DateTime, default=datetime.utcnow)
    total_leads = Column(Integer, default=0)
    vip_leads = Column(Integer, default=0)
    provincial_distribution = Column(Text)  # Lưu JSON string {"HN": 5000, "HCM": 10000, ...}
    is_latest = Column(Boolean, default=True)



class CustomerProfile(Base):
    """Bảng hồ sơ khách hàng hoàn chỉnh (sau khi map UID Facebook)"""
    __tablename__ = "customer_profiles"

    id = Column(Integer, primary_key=True, index=True)
    ho_ten = Column(String(200))
    so_dien_thoai = Column(String(20), unique=True, index=True)
    email = Column(String(200))
    dia_chi = Column(String(500))
    facebook_uid = Column(String(50), index=True)
    facebook_name = Column(String(200))
    nguon = Column(String(100))
    ghi_chu = Column(Text)
    # Phase 3 fields
    cluster = Column(Integer)                    # 0=Đầu cơ, 1=Ở thực, 2=VIP
    cluster_label = Column(String(50))
    lead_score = Column(Float, default=0)
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    # ── Analytics columns (Sprint 3) ──────────────────────────
    source_tier   = Column(String(30), default="unknown")
    unified_score = Column(Float, default=0.0)


class HotLead(Base):
    """Danh sách lead đang nóng — từ Facebook scraping hoặc Google search"""
    __tablename__ = "hot_leads"

    id = Column(Integer, primary_key=True, index=True)
    so_dien_thoai = Column(String(20), index=True)
    facebook_uid = Column(String(50), index=True)
    nguon = Column(String(20))             # 'facebook' hoặc 'google'
    keyword = Column(String(200))          # Từ khóa đã tìm/scrape
    behavior = Column(String(50))          # comment, share, tag, listing
    source_url = Column(String(500))       # URL bài đăng / trang listing
    hot_score = Column(Float, default=0)
    is_existing_customer = Column(Boolean, default=False)  # Có trong DB cũ không?
    customer_profile_id = Column(Integer)  # FK đến customer_profiles nếu match
    scraped_at = Column(DateTime, default=datetime.utcnow)


class GoogleLead(Base):
    """SĐT thu thập được từ Google Search về mua bán BĐS"""
    __tablename__ = "google_leads"

    id = Column(Integer, primary_key=True, index=True)
    so_dien_thoai = Column(String(20), index=True)
    source_url = Column(String(500))
    page_title = Column(String(300))
    keyword = Column(String(200))
    snippet = Column(Text)                 # Đoạn text context từ Google
    scraped_at = Column(DateTime, default=datetime.utcnow)



# ─── ADS ENGINE MODELS ────────────────────────────────────────────────────────

class AdCampaign(Base):
    """Campaigns đồng bộ từ Meta Ads Manager"""
    __tablename__ = "ad_campaigns"

    id              = Column(Integer, primary_key=True, index=True)
    fb_campaign_id  = Column(String(50), unique=True, index=True)
    name            = Column(String(300))
    objective       = Column(String(100))
    status          = Column(String(30))         # ACTIVE | PAUSED | DELETED
    daily_budget    = Column(Integer, default=0) # VND
    lifetime_budget = Column(Integer, default=0)
    synced_at       = Column(DateTime, default=datetime.utcnow)
    created_at      = Column(DateTime, default=datetime.utcnow)
    updated_at      = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AdSet(Base):
    """AdSets đồng bộ từ Meta Ads Manager"""
    __tablename__ = "ad_sets"

    id              = Column(Integer, primary_key=True, index=True)
    fb_adset_id     = Column(String(50), unique=True, index=True)
    fb_campaign_id  = Column(String(50), index=True)   # FK logic → AdCampaign
    name            = Column(String(300))
    status          = Column(String(30))
    daily_budget    = Column(Integer, default=0)
    targeting_json  = Column(Text)
    synced_at       = Column(DateTime, default=datetime.utcnow)
    created_at      = Column(DateTime, default=datetime.utcnow)


class AdPerformance(Base):
    """Metrics hàng ngày kéo từ Insights API"""
    __tablename__ = "ad_performance"

    id              = Column(Integer, primary_key=True, index=True)
    fb_ad_id        = Column(String(50), index=True)
    fb_adset_id     = Column(String(50), index=True)
    fb_campaign_id  = Column(String(50), index=True)
    date_start      = Column(String(20))
    date_stop       = Column(String(20))
    # Raw metrics
    impressions     = Column(Integer, default=0)
    clicks          = Column(Integer, default=0)
    spend_vnd       = Column(Float,   default=0)     # Chi tiêu (VND)
    reach           = Column(Integer, default=0)
    leads           = Column(Integer, default=0)
    # Computed metrics
    cpm             = Column(Float, default=0)
    cpc             = Column(Float, default=0)
    ctr             = Column(Float, default=0)
    frequency       = Column(Float, default=0)
    cpl             = Column(Float, default=0)       # Cost Per Lead
    quality_cpl     = Column(Float, default=0)       # CPL chỉ lead chất lượng
    # Quality cross-reference
    quality_score   = Column(Float, default=0)       # Từ LeadQualityScorer
    quality_leads   = Column(Integer, default=0)     # Số lead quality >= 6
    # Ratings
    cpl_rating      = Column(String(10))             # good | medium | poor
    ctr_rating      = Column(String(10))
    freq_rating     = Column(String(10))
    # Metadata
    synced_at       = Column(DateTime, default=datetime.utcnow)


class MessengerLead(Base):
    """Hội thoại từ Facebook Page Inbox"""
    __tablename__ = "messenger_leads"

    id               = Column(Integer, primary_key=True, index=True)
    conversation_id  = Column(String(100), unique=True, index=True)
    fb_ad_id         = Column(String(50), index=True)   # Ad nào tạo ra conversation này
    page_id          = Column(String(50))
    sender_name      = Column(String(200))
    sender_psid      = Column(String(100), index=True)  # Page-scoped ID
    phone            = Column(String(30), index=True)
    email            = Column(String(200))
    message_count    = Column(Integer, default=0)
    first_message_at = Column(DateTime)
    last_message_at  = Column(DateTime)
    intent_score     = Column(Float, default=0)         # 0-10 từ keyword analysis
    quality_score    = Column(Float, default=0)         # 0-10 từ LeadQualityScorer
    raw_messages_json = Column(Text)                    # Nội dung chat (giới hạn 2000 ký tự)
    synced_at        = Column(DateTime, default=datetime.utcnow)


class LeadAdMapping(Base):
    """Bảng mapping: Messenger Lead ↔ Ad Performance ↔ CustomerProfile"""
    __tablename__ = "lead_ad_mappings"

    id                   = Column(Integer, primary_key=True, index=True)
    messenger_lead_id    = Column(Integer, index=True)  # FK → MessengerLead
    ad_performance_id    = Column(Integer, index=True)  # FK → AdPerformance
    customer_profile_id  = Column(Integer, index=True)  # FK → CustomerProfile
    match_method         = Column(String(50))           # phone | psid | email | form
    confidence_score     = Column(Float, default=1.0)   # 0-1
    created_at           = Column(DateTime, default=datetime.utcnow)


class OptimizationLog(Base):
    """Lịch sử các action của Optimizer"""
    __tablename__ = "optimization_logs"

    id           = Column(Integer, primary_key=True, index=True)
    run_at       = Column(DateTime, default=datetime.utcnow, index=True)
    dry_run      = Column(Boolean, default=True)
    rule         = Column(String(50))    # PAUSE | SCALE | TEST_BUDGET | FREQ_CAP | WINNER
    action       = Column(String(50))   # pause_adset | update_budget | duplicate_adset
    adset_id     = Column(String(50))
    adset_name   = Column(String(300))
    campaign     = Column(String(300))
    reason       = Column(Text)
    impact       = Column(Text)
    params_json  = Column(Text)
    status       = Column(String(20))   # preview | applied | failed
    metrics_json = Column(Text)


# ── DB Bootstrap ──────────────────────────────────────────────────────────────

def init_db():
    """Tạo tất cả bảng nếu chưa tồn tại"""
    Base.metadata.create_all(bind=engine)
    print(f"[DB] Database initialized: {DATABASE_URL}")


def get_db():
    """Context manager để lấy DB session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


if __name__ == "__main__":
    init_db()

