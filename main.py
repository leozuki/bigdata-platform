"""
main.py — CLI Entry Point cho BDS Data Pipeline
Usage:
  python main.py --phase all        # Chạy toàn bộ 3 giai đoạn
  python main.py --phase 1          # Chỉ Phase 1 (Ingest + Score + Segment)
  python main.py --phase 2          # Chỉ Phase 2 (Enrichment: FB + Google)
  python main.py --phase 3          # Chỉ Phase 3 (AI Clustering + Scoring)
  python main.py --phase 1 --raw-dir D:/MyData/files
  python main.py --phase 2 --fb-csv path/to/fb_export.csv
"""
import sys
import time
import argparse
from pathlib import Path
from datetime import datetime

# Fix encoding on Windows PowerShell (cp1252 does not support Vietnamese)
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, str(Path(__file__).parent))

from src.utils import setup_logger

log = setup_logger("main")


def print_banner():
    banner = (
        "\n" +
        "=" * 62 + "\n" +
        "  BDS DATA PIPELINE SYSTEM v1.0\n" +
        "  Xu ly | Lam giau | Cham diem KH BDS bang AI\n" +
        "=" * 62
    )
    print(banner)


def run_phase1(raw_dir: str = None, uid_mapping: str = None):
    log.info("▶ GIAI ĐOẠN 1: DATA PIPELINE")
    t0 = time.time()

    import os
    from src.phase1_pipeline.excel_ingestor  import run_ingestion
    from src.phase1_pipeline.identity_mapper import run_identity_mapping
    from src.phase1_pipeline.segment_audiences import run_segmentation

    # Đọc raw_dir từ env nếu không truyền tham số
    if not raw_dir:
        raw_dir = os.getenv("RAW_DATA_DIR", "data/raw")

    r1 = run_ingestion(raw_dir)
    r2 = run_identity_mapping(uid_mapping)
    r3 = run_segmentation()

    elapsed = time.time() - t0
    log.info(f"⏱ Phase 1 hoàn tất trong {elapsed:.1f}s")
    return {**r1, **r2, **r3}


def run_phase2(fb_csv: str = None, google_queries: list = None):
    log.info("▶ GIAI ĐOẠN 2: DATA ENRICHMENT")
    t0 = time.time()

    from src.phase2_enrichment.scraper_adapter import run_facebook_scraper_import
    from src.phase2_enrichment.google_scraper  import run_google_scraper
    from src.phase2_enrichment.filter_engine   import run_filter_engine
    from src.phase2_enrichment.matcher         import run_matching

    r1 = run_facebook_scraper_import(fb_csv)
    r2 = run_google_scraper(google_queries)
    r3 = run_filter_engine()
    r4 = run_matching()

    elapsed = time.time() - t0
    log.info(f"⏱ Phase 2 hoàn tất trong {elapsed:.1f}s")
    return {**r1, **r2, **r3, **r4}


def run_phase3():
    log.info("▶ GIAI ĐOẠN 3: AI SCORING")
    t0 = time.time()

    from src.phase3_scoring.clustering  import run_clustering
    from src.phase3_scoring.lead_scorer import run_lead_scoring

    r1 = run_clustering()
    r2 = run_lead_scoring()

    elapsed = time.time() - t0
    log.info(f"⏱ Phase 3 hoàn tất trong {elapsed:.1f}s")
    return {**r1, **r2}


def main():
    print_banner()

    parser = argparse.ArgumentParser(
        description="BDS Data Pipeline -- Xu ly va cham diem khach hang BDS"
    )
    parser.add_argument(
        "--phase", choices=["1", "2", "3", "all"], default="all",
        help="Giai đoạn cần chạy: 1 | 2 | 3 | all"
    )
    parser.add_argument("--raw-dir", type=str, default=None,
                        help="Thư mục chứa file Excel/CSV thô (mặc định: data/raw/)")
    parser.add_argument("--fb-csv", type=str, default=None,
                        help="File CSV export từ tool FB scraping (MKT Ninja, Simple UID...)")
    parser.add_argument("--uid-mapping", type=str, default=None,
                        help="File CSV map SĐT → Facebook UID")
    parser.add_argument("--google-queries", type=str, default=None,
                        help="Query Google, phân cách bằng dấu |")

    args = parser.parse_args()

    google_queries = args.google_queries.split("|") if args.google_queries else None

    start_time = time.time()
    results = {}

    try:
        if args.phase in ("1", "all"):
            results.update(run_phase1(args.raw_dir, args.uid_mapping))

        if args.phase in ("2", "all"):
            results.update(run_phase2(args.fb_csv, google_queries))

        if args.phase in ("3", "all"):
            results.update(run_phase3())

        total_time = time.time() - start_time
        log.info("=" * 62)
        log.info(f"🎉 PIPELINE HOÀN TẤT trong {total_time:.1f}s")
        log.info("=" * 62)

        if "output_file" in results:
            log.info(f"📊 File xuất: {results['output_file']}")
        if "total" in results:
            log.info(f"👥 Tổng KH:  {results.get('total', 0):,}")
        if "vip" in results:
            log.info(f"⭐ VIP (8-10 điểm): {results.get('vip', 0):,} → Giao Sales giỏi nhất!")

    except KeyboardInterrupt:
        log.warning("\n⛔ Pipeline bị dừng bởi người dùng")
        sys.exit(1)
    except Exception as e:
        log.error(f"Pipeline lỗi: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
