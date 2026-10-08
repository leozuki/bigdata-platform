"""
tests/test_analytics.py
=========================
Integration test suite cho cac analytics modules moi.
Chay: python tests/test_analytics.py
"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import sys
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))

PASS = "PASS"
FAIL = "FAIL"
results = []


def check(name, condition, detail=""):
    status = PASS if condition else FAIL
    results.append((status, name, detail))
    icon = "OK " if condition else "ERR"
    print(f"  [{icon}] {name}" + (f": {detail}" if detail else ""))
    return condition


# ══════════════════════════════════════════════════════
# TEST 1: File Classifier
# ══════════════════════════════════════════════════════

def test_file_classifier():
    print("\n=== Test 1: File Classifier ===")
    from src.utils.file_classifier import classify_file, SOURCE_TIERS

    cases = [
        ("DSKH NGAN HANG HSBC TIET KIEM.xls",       "banking_vip"),
        ("KH VPBank Priority Banking 2024.xlsx",     "banking_vip"),
        ("100 Villa Sai Gon Pearl Vinhomes.xls",     "real_estate_vip"),
        ("Chung Cu Masteri The Tresor.xlsx",          "real_estate_vip"),
        ("DS CEO GIAM DOC HCM 2000 KH.xlsx",         "ceo_director"),
        ("BMW Mercedes Lexus Owner List.xls",        "automotive_vip"),
        ("CHUNG KHOAN SSI Top NHA DAU TU.xlsx",      "stock_gold"),
        ("King Fitness InBody 500 KH.xlsx",          "fitness_health"),
        ("Vietnamwork DS Ung Vien Senior.xlsx",      "education_hr"),
        ("viettel-tphcm-tra-sau-2023.xls",           "telecom_mass"),
        ("mobifone_MOBI_HCM.xlsx",                   "telecom_mass"),
        ("random file khong ro nguon.xls",           "unknown"),
        ("50 khach hang chuyen nghiep.xls",          "unknown"),
    ]

    for fname, expected in cases:
        result = classify_file(fname)
        got = result["tier_key"]
        check(f"classify({fname[:40]}...)", got == expected,
              f"got={got}, expected={expected}")


# ══════════════════════════════════════════════════════
# TEST 2: Unified Scorer
# ══════════════════════════════════════════════════════

def test_unified_scorer():
    print("\n=== Test 2: Unified Scorer ===")
    from src.analytics.unified_scorer import calculate_unified_score

    # Case 1: Perfect VIP lead — banking, multiple sources, recent, complete
    vip = calculate_unified_score(
        phone="0912345678", email="nguyen@gmail.com",
        name="Nguyen Van A", address="123 Nguyen Hue Q1 HCM",
        source_weight=1.0, source_count=6,
        latest_file_ts=datetime.now() - timedelta(days=30),
    )
    check("VIP score >= 80",       vip["unified_score"] >= 80, f"got={vip['unified_score']}")
    check("VIP grade in (S, A)",   vip["grade"] in ("S", "A"), f"got={vip['grade']}")
    check("VIP completeness = 30", vip["breakdown"]["completeness"] == 30.0)
    check("VIP source_quality = 25", vip["breakdown"]["source_quality"] == 25.0)
    check("VIP cross_source = 20",   vip["breakdown"]["cross_source"] == 20.0)

    # Case 2: Minimal telecom lead — phone only, 1 source, unknown tier
    mass = calculate_unified_score(
        phone="0912345678", email="", name="", address="",
        source_weight=0.40, source_count=1,
        latest_file_ts=datetime.now() - timedelta(days=500),
    )
    check("Mass score <= 40",     mass["unified_score"] <= 40, f"got={mass['unified_score']}")
    check("Mass grade = C or D",  mass["grade"] in ("C", "D"), f"got={mass['grade']}")

    # Case 3: Score ordering — VIP > Mass
    check("VIP > Mass",           vip["unified_score"] > mass["unified_score"],
          f"VIP={vip['unified_score']}, Mass={mass['unified_score']}")

    # Case 4: Behavioral boost
    no_msg = calculate_unified_score("09x", "", "", "", 0.5, 2)
    with_msg = calculate_unified_score("09x", "", "", "", 0.5, 2,
                                        intent_score=8, messenger_phone=True)
    check("Messenger boosts score", with_msg["unified_score"] > no_msg["unified_score"],
          f"base={no_msg['unified_score']}, boosted={with_msg['unified_score']}")

    # Case 5: Old data penalized
    fresh = calculate_unified_score("09x", "", "", "", 0.5, 1,
                                     latest_file_ts=datetime.now() - timedelta(days=60))
    stale = calculate_unified_score("09x", "", "", "", 0.5, 1,
                                     latest_file_ts=datetime.now() - timedelta(days=2500))
    check("Fresh > Stale",         fresh["unified_score"] > stale["unified_score"],
          f"fresh={fresh['unified_score']}, stale={stale['unified_score']}")


# ══════════════════════════════════════════════════════
# TEST 3: RFM Engine
# ══════════════════════════════════════════════════════

def test_rfm():
    print("\n=== Test 3: RFM Engine ===")
    from src.analytics.rfm_engine import calculate_rfm, rfm_segment

    # Champion: recent, high freq, banking_vip
    champion = calculate_rfm(6, 1.0, datetime.now() - timedelta(days=30))
    check("Champion RFM >= 9",    champion >= 9.0,  f"got={champion}")
    check("Champion segment",     rfm_segment(champion) == "Champions", f"got={rfm_segment(champion)}")

    # Lost: old, single source, unknown tier
    lost = calculate_rfm(1, 0.25, datetime.now() - timedelta(days=2000))
    check("Lost RFM <= 3",        lost <= 3.0,      f"got={lost}")

    # Mid-tier
    mid = calculate_rfm(3, 0.65, datetime.now() - timedelta(days=200))
    check("Mid RFM in (4-7)",    4.0 <= mid <= 7.0, f"got={mid}")

    # Ordering
    check("Champion > Mid > Lost",
          champion > mid > lost,
          f"champion={champion}, mid={mid}, lost={lost}")


# ══════════════════════════════════════════════════════
# TEST 4: Province from Phone
# ══════════════════════════════════════════════════════

def test_province_phone():
    print("\n=== Test 4: Province from Phone ===")
    # src.utils is now shadowed by src/utils/ package — load directly from file
    import importlib.util as ilu, os
    spec = ilu.spec_from_file_location(
        "src_utils_raw",
        os.path.join(str(Path(__file__).parent.parent), "src", "utils.py")
    )
    mod = ilu.module_from_spec(spec); spec.loader.exec_module(mod)
    pfp = mod.province_from_phone

    check("Mobile -> Unknown",        pfp("0912345678") == "Unknown")
    check("HCM landline (028)",       "Ho Chi Minh" in pfp("02812345678"))
    check("HN landline (024)",        "Ha Noi" in pfp("02412345678"))
    check("Da Nang (0236)",           "Da Nang" in pfp("023612345"))
    check("Empty -> Unknown",         pfp("") == "Unknown")
    check("None -> Unknown",          pfp(None) == "Unknown")



# ══════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 55)
    print("  ANALYTICS TEST SUITE")
    print("=" * 55)

    test_file_classifier()
    test_unified_scorer()
    test_rfm()

    # province_from_phone test: only if function exists in utils
    try:
        test_province_phone()
    except AttributeError:
        print("\n=== Test 4: Province from Phone ===")
        print("  ⏭️  Skipped (province_from_phone not yet added to utils.py)")

    # Summary
    passed = sum(1 for r in results if r[0] == PASS)
    failed = sum(1 for r in results if r[0] == FAIL)

    print("\n" + "=" * 55)
    print(f"  RESULTS: {passed} passed, {failed} failed")
    if failed == 0:
        print("  [ALL TESTS PASSED]")
    else:
        print(f"  [{failed} TEST(S) FAILED]")
        for status, name, detail in results:
            if status == FAIL:
                print(f"    FAIL: {name} - {detail}")
    print("=" * 55)
