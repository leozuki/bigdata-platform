"""
google_scraper.py — Quét SĐT BĐS từ Google Search
Hỗ trợ hai chế độ:
  1. Google Custom Search API (chính xác, 100 query/ngày miễn phí)
  2. googlesearch-python fallback (không cần API key, chậm hơn)
"""
import os
import sys
import re
import time
import random
import requests
from pathlib import Path
from datetime import datetime
from urllib.parse import urljoin, urlparse

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.utils import setup_logger, extract_phones_from_text, clean_phone_number, format_number
from src.database import init_db, SessionLocal, GoogleLead

try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False

try:
    from googlesearch import search as google_search
    GOOGLESEARCH_AVAILABLE = True
except ImportError:
    GOOGLESEARCH_AVAILABLE = False

log = setup_logger("google_scraper")

# ─── Cấu hình ────────────────────────────────────────────────────────────────

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
GOOGLE_CSE_ID  = os.getenv("GOOGLE_CSE_ID", "")
REQUEST_DELAY  = float(os.getenv("GOOGLE_REQUEST_DELAY", "1.5"))
MAX_PAGES      = int(os.getenv("GOOGLE_MAX_PAGES", "5"))

# Từ khóa tìm kiếm mặc định
DEFAULT_QUERIES = [
    'bán đất nền "liên hệ" OR "hotline" OR "sdt"',
    'bán căn hộ TP.HCM "liên hệ" OR "0[3-9]"',
    'cần bán nhà đất "điện thoại" OR "zalo"',
    '"bảng giá" dự án bất động sản "liên hệ"',
    '"cọc thiện chí" OR "mở bán" bds "sdt" OR "phone"',
    'site:batdongsan.com.vn bán đất',
    'site:nha.com.vn bán nhà',
    'site:alonhadat.com.vn bất động sản',
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8",
}

# Các domain BĐS uy tín để ưu tiên crawl sâu
BDS_DOMAINS = {
    "batdongsan.com.vn",
    "nha.com.vn",
    "alonhadat.com.vn",
    "muanhadat.vn",
    "homedy.com",
    "nhadatso.com",
    "chotot.com",
}


# ─── Google Custom Search API ─────────────────────────────────────────────────

def search_via_api(query: str, start: int = 1) -> list[dict]:
    """
    Gọi Google Custom Search JSON API.
    Trả về list các kết quả {"title", "link", "snippet"}
    """
    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        "key": GOOGLE_API_KEY,
        "cx":  GOOGLE_CSE_ID,
        "q":   query,
        "start": start,
        "num": 10,
        "lr":  "lang_vi",
        "gl":  "vn",
    }
    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return data.get("items", [])
    except Exception as e:
        log.warning(f"  API error: {e}")
        return []


# ─── Direct Page Crawling ─────────────────────────────────────────────────────

def crawl_page_for_phones(url: str) -> list[str]:
    """
    Crawl một trang web và extract tất cả SĐT từ nội dung.
    Ưu tiên các trang BĐS listing.
    """
    if not BS4_AVAILABLE:
        return []

    try:
        time.sleep(random.uniform(0.5, REQUEST_DELAY))
        resp = requests.get(url, headers=HEADERS, timeout=10, allow_redirects=True)
        resp.raise_for_status()
        html = resp.text

        soup = BeautifulSoup(html, "lxml" if "lxml" in sys.modules else "html.parser")

        # Loại bỏ script, style (nhiễu)
        for tag in soup(["script", "style", "nav", "footer"]):
            tag.decompose()

        text = soup.get_text(separator=" ", strip=True)

        # Tìm phone trong thuộc tính href (tel: links)
        tel_phones = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.startswith("tel:"):
                number = href[4:].strip()
                cleaned = clean_phone_number(number)
                if cleaned:
                    tel_phones.append(cleaned)

        # Extract từ text content
        text_phones = extract_phones_from_text(text)

        all_phones = list(dict.fromkeys(tel_phones + text_phones))  # Deduplicate, giữ thứ tự
        return all_phones[:10]  # Tối đa 10 SĐT mỗi trang

    except Exception as e:
        log.debug(f"  Crawl failed {url}: {e}")
        return []


# ─── Main Scraping Logic ──────────────────────────────────────────────────────

def scrape_query(query: str, db, max_pages: int = MAX_PAGES) -> int:
    """Thực hiện một query Google và thu thập SĐT"""
    results_added = 0
    log.info(f"  🔍 Query: '{query}'")

    if GOOGLE_API_KEY and GOOGLE_CSE_ID:
        # Dùng API
        for page in range(max_pages):
            start = page * 10 + 1
            items = search_via_api(query, start=start)
            if not items:
                break

            for item in items:
                url        = item.get("link", "")
                title      = item.get("title", "")
                snippet    = item.get("snippet", "")

                # Extract SĐT từ snippet (nhanh, không cần crawl)
                phones_from_snippet = extract_phones_from_text(snippet + " " + title)

                # Nếu là domain BĐS → crawl sâu
                domain = urlparse(url).netloc.replace("www.", "")
                phones_from_page = []
                if domain in BDS_DOMAINS:
                    phones_from_page = crawl_page_for_phones(url)

                all_phones = list(dict.fromkeys(phones_from_snippet + phones_from_page))

                for phone in all_phones:
                    lead = GoogleLead(
                        so_dien_thoai=phone,
                        source_url=url,
                        page_title=title[:300],
                        keyword=query,
                        snippet=snippet[:500],
                        scraped_at=datetime.now(),
                    )
                    db.add(lead)
                    results_added += 1

            db.commit()
            time.sleep(REQUEST_DELAY)

    elif GOOGLESEARCH_AVAILABLE:
        # Fallback: googlesearch-python (không cần API key)
        log.info("  ℹ Dùng googlesearch fallback (không có API key)")
        try:
            urls = list(google_search(query, num_results=max_pages * 10,
                                      lang="vi", region="VN", sleep_interval=2))
            for url in urls:
                domain = urlparse(url).netloc.replace("www.", "")
                phones = crawl_page_for_phones(url) if domain in BDS_DOMAINS else []
                for phone in phones:
                    lead = GoogleLead(
                        so_dien_thoai=phone,
                        source_url=url,
                        page_title="",
                        keyword=query,
                        snippet="",
                        scraped_at=datetime.now(),
                    )
                    db.add(lead)
                    results_added += 1
            db.commit()
        except Exception as e:
            log.warning(f"  googlesearch error: {e}")

    else:
        log.warning("  ⚠ Không có Google API key và googlesearch-python. Dùng Mock data.")
        # Mock: Tạo dữ liệu giả để test pipeline
        for i in range(random.randint(5, 20)):
            # Tạo SĐT ngẫu nhiên hợp lệ
            prefix = random.choice(["032", "033", "036", "090", "091", "096", "097", "098",
                                    "070", "079", "083", "084", "085", "086", "088", "089"])
            phone = "+84" + prefix[1:] + "".join([str(random.randint(0, 9)) for _ in range(7)])
            lead = GoogleLead(
                so_dien_thoai=phone,
                source_url=f"https://batdongsan.com.vn/listing/{random.randint(10000, 99999)}",
                page_title=f"Bán BĐS - {query[:50]}",
                keyword=query,
                snippet=f"Liên hệ: {phone} để biết thêm thông tin chi tiết về bất động sản.",
                scraped_at=datetime.now(),
            )
            db.add(lead)
            results_added += 1
        db.commit()

    log.info(f"     → {results_added} SĐT collected")
    return results_added


def run_google_scraper(custom_queries: list[str] = None) -> dict:
    """
    Giai đoạn 2B: Quét SĐT BĐS từ Google Search.

    Args:
        custom_queries: Danh sách query tùy chỉnh.
                        None = dùng queries từ .env hoặc DEFAULT_QUERIES
    """
    log.info("=" * 60)
    log.info("PHASE 2B — GOOGLE SĐT SCRAPER")

    # Lấy query từ config hoặc dùng default
    env_queries = os.getenv("GOOGLE_SEARCH_QUERIES", "")
    queries = custom_queries or (env_queries.split(",") if env_queries else DEFAULT_QUERIES)
    queries = [q.strip() for q in queries if q.strip()]
    log.info(f"Số queries: {len(queries)}")

    init_db()
    db = SessionLocal()

    # Xóa google_leads cũ
    db.execute(GoogleLead.__table__.delete())
    db.commit()

    total = 0
    for i, query in enumerate(queries, 1):
        log.info(f"[{i}/{len(queries)}]")
        count = scrape_query(query, db)
        total += count

    # Deduplicate trong DB (xóa SĐT trùng, giữ bản ghi đầu tiên)
    from sqlalchemy import text as sql_text
    db.execute(sql_text("""
        DELETE FROM google_leads
        WHERE id NOT IN (
            SELECT MIN(id) FROM google_leads
            GROUP BY so_dien_thoai
        )
    """))
    db.commit()

    final_count = db.query(GoogleLead).count()
    db.close()

    log.info("─" * 60)
    log.info(f"✅ HOÀN TẤT: {format_number(final_count)} SĐT duy nhất từ Google")
    return {"google_leads": final_count, "queries_run": len(queries)}


if __name__ == "__main__":
    result = run_google_scraper()
    print(f"\nKết quả: {result}")
