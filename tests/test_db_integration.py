"""
tests/test_db_integration.py
==============================
Integration test: validate da migrated correctly, rescore ran, province enriched.
Tests real data from bigdata.db.
"""
import sys, io, sqlite3, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

# DB path: ưu tiên DATABASE_URL từ .env, fallback về path mới
_db_url = os.getenv("DATABASE_URL", "sqlite:///d:/AI/01_Products/BigData/data/bigdata.db")
DB_PATH = _db_url.replace("sqlite:///", "")

PASS, FAIL = "PASS", "FAIL"
results = []

def check(name, condition, detail=""):
    status = PASS if condition else FAIL
    results.append((status, name, detail))
    icon = "[OK ]" if condition else "[ERR]"
    print(f"  {icon} {name}" + (f": {detail}" if detail else ""))
    return condition

def q(sql, *args):
    conn = sqlite3.connect(DB_PATH, timeout=30)
    try:
        row = conn.execute(sql, args).fetchone()
        return row[0] if row else None
    finally:
        conn.close()

def qall(sql, *args):
    conn = sqlite3.connect(DB_PATH, timeout=30)
    try:
        return conn.execute(sql, args).fetchall()
    finally:
        conn.close()

print("=" * 60)
print("  DB INTEGRATION TEST SUITE")
print("=" * 60)

# ── TEST 1: Schema Migration ───────────────────────────────
print("\n=== Test 1: Schema Migration (clean_contacts) ===")

total = q("SELECT COUNT(*) FROM clean_contacts")
check("Table clean_contacts exists + has rows", total and total > 0, f"{total:,} rows")

cols = [r[1] for r in qall("PRAGMA table_info(clean_contacts)")]
for col in ["source_tier", "source_weight", "source_count",
            "latest_file_ts", "rfm_score", "unified_score", "province_phone"]:
    check(f"Column '{col}' exists", col in cols)

# customer_profiles
cp_cols = [r[1] for r in qall("PRAGMA table_info(customer_profiles)")]
check("customer_profiles.source_tier",   "source_tier"   in cp_cols)
check("customer_profiles.unified_score", "unified_score" in cp_cols)

# conversion_events table
ce = q("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='conversion_events'")
check("Table conversion_events exists", ce == 1)

# Indexes
idxs = [r[1] for r in qall("SELECT * FROM sqlite_master WHERE type='index'")]
check("Index idx_cc_unified exists",  any("idx_cc_unified"  in i for i in idxs))
check("Index idx_cc_tier exists",     any("idx_cc_tier"     in i for i in idxs))
check("Index idx_cc_province exists", any("idx_cc_province" in i for i in idxs))

# ── TEST 2: Rescore Results ────────────────────────────────
print("\n=== Test 2: Batch Rescore Validation ===")

rescored = q("SELECT COUNT(*) FROM clean_contacts WHERE unified_score > 0")
pct = (rescored / total * 100) if total else 0
check("Rescored > 90% of records", pct > 90, f"{rescored:,} records ({pct:.1f}%)")

max_score = q("SELECT MAX(unified_score) FROM clean_contacts")
min_score = q("SELECT MIN(unified_score) FROM clean_contacts WHERE unified_score > 0")
avg_score = q("SELECT ROUND(AVG(unified_score), 2) FROM clean_contacts WHERE unified_score > 0")
check("Max unified_score <= 100",   max_score is not None and max_score <= 100, f"max={max_score}")
check("Min unified_score > 0",      min_score is not None and min_score > 0,    f"min={min_score}")
check("Avg unified_score 25-60",    avg_score and 15 < avg_score < 70,          f"avg={avg_score}")

grade_b = q("SELECT COUNT(*) FROM clean_contacts WHERE unified_score >= 55")
grade_c = q("SELECT COUNT(*) FROM clean_contacts WHERE unified_score >= 40 AND unified_score < 55")
grade_d = q("SELECT COUNT(*) FROM clean_contacts WHERE unified_score < 40")
check("Grade B+ exists", grade_b and grade_b > 0,  f"{grade_b:,} contacts")
check("Grade C exists",  grade_c and grade_c > 0,  f"{grade_c:,} contacts")
check("Grade D is majority", grade_d > grade_b,    f"D={grade_d:,} > B+={grade_b:,}")

# ── TEST 3: Source Tier ────────────────────────────────────
print("\n=== Test 3: Source Tier Classification ===")

classified = q("SELECT COUNT(*) FROM clean_contacts WHERE source_tier != 'unknown' AND source_tier IS NOT NULL")
unclassified = q("SELECT COUNT(*) FROM clean_contacts WHERE source_tier = 'unknown' OR source_tier IS NULL")
check("At least some classified", classified and classified > 0, f"{classified:,} classified")

tier_dist = qall("""
    SELECT source_tier, COUNT(*) as cnt
    FROM clean_contacts
    GROUP BY source_tier
    ORDER BY cnt DESC
    LIMIT 5
""")
print(f"\n  Top source tiers in DB:")
for tier, cnt in tier_dist:
    print(f"    {tier or 'NULL':<25} {cnt:>10,}")

# ── TEST 4: Province Enrichment ────────────────────────────
print("\n=== Test 4: Province Enrichment ===")

with_province = q("SELECT COUNT(*) FROM clean_contacts WHERE province_phone IS NOT NULL AND province_phone != 'Unknown'")
cov = (with_province / total * 100) if total else 0
check("Province coverage > 30%", cov > 30, f"{with_province:,} records ({cov:.1f}%)")

top_prov = qall("""
    SELECT province_phone, COUNT(*) as cnt
    FROM clean_contacts
    WHERE province_phone IS NOT NULL AND province_phone != 'Unknown'
    GROUP BY province_phone
    ORDER BY cnt DESC
    LIMIT 5
""")
print(f"\n  Top provinces enriched:")
for prov, cnt in top_prov:
    print(f"    {prov:<30} {cnt:>8,}")

# ── TEST 5: DB Health ──────────────────────────────────────
print("\n=== Test 5: DB Health ===")

wal_path = Path(DB_PATH + "-wal")
wal_mb = wal_path.stat().st_size / 1024**2 if wal_path.exists() else 0
check("WAL file < 50MB", wal_mb < 50, f"WAL = {wal_mb:.1f} MB")

int_ok = q("PRAGMA integrity_check")
check("DB integrity check passed", int_ok == "ok", f"result='{int_ok}'")

db_size_gb = Path(DB_PATH).stat().st_size / 1024**3
check("DB file accessible", db_size_gb > 0, f"{db_size_gb:.2f} GB")

# ── TEST 6: New files classification report ────────────────
print("\n=== Test 6: Classification Report ===")

report = Path(DB_PATH).parent / "file_classification_report.csv"
check("Classification CSV exists", report.exists(), str(report))
if report.exists():
    import csv
    with open(report, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    check("Report has 2000+ rows", len(rows) > 2000, f"{len(rows)} rows")
    classified_pct = sum(1 for r in rows if r.get("tier_key","") != "unknown") / len(rows) * 100
    check("Report classified > 30%", classified_pct > 30, f"{classified_pct:.1f}%")

# ── SUMMARY ───────────────────────────────────────────────
passed = sum(1 for r in results if r[0] == PASS)
failed = sum(1 for r in results if r[0] == FAIL)

print(f"\n{'=' * 60}")
print(f"  RESULTS: {passed} passed, {failed} failed")
if failed == 0:
    print("  [ALL TESTS PASSED]")
else:
    print(f"  [{failed} FAILED]")
    for status, name, detail in results:
        if status == FAIL:
            print(f"    FAIL: {name}" + (f" - {detail}" if detail else ""))
print(f"{'=' * 60}")
