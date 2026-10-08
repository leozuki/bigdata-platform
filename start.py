"""
start.py — Unified Launcher cho BDS Data Pipeline
Chức năng:
  - Chạy Flask dashboard tại http://localhost:5000
  - Hoặc Streamlit dashboard tại http://localhost:8502
  - Hoặc chạy đồng thời cả hai dashboard

Usage:
  python start.py              # Flask dashboard (mặc định)
  python start.py --both       # Chạy đồng thời cả Flask (:5000) & Streamlit (:8502)
  python start.py --streamlit  # Streamlit dashboard (:8502)
  python start.py --flask      # Flask dashboard (:5000)
  python start.py --pipeline   # Chạy pipeline Phase 1 rồi mở Flask
"""
import subprocess
import sys
import os
import time
import argparse
from pathlib import Path

# Fix encoding Windows
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

BASE_DIR = Path(__file__).parent


def get_python_exe():
    """Tự động tìm Python binary có cài đặt đầy đủ dependencies"""
    candidates = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Python" / "pythoncore-3.14-64" / "python.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Python" / "bin" / "python.exe",
        Path(sys.executable),
    ]
    for c in candidates:
        if c and c.exists():
            # Quick check if it has flask
            try:
                r = subprocess.run([str(c), "-c", "import flask, streamlit"],
                                   capture_output=True, timeout=5)
                if r.returncode == 0:
                    return str(c)
            except Exception:
                continue
    return sys.executable


PYTHON_EXE = get_python_exe()


def print_banner():
    print("\n" + "=" * 65)
    print("  🚀 BDS DATA PIPELINE SYSTEM v1.0 — Unified Launcher")
    print("=" * 65)
    print(f"  Python Runtime : {PYTHON_EXE}")
    print(f"  Project Root   : {BASE_DIR}")
    print("=" * 65 + "\n")


def start_flask_dashboard():
    """Chạy Flask dashboard tại http://localhost:5000"""
    dashboard = BASE_DIR / "dashboard" / "app.py"
    if not dashboard.exists():
        print(f"[ERR] Không tìm thấy: {dashboard}")
        return
    print("[*] Khởi động Flask Dashboard → http://localhost:5000")
    print("[*] Nhấn Ctrl+C để dừng\n")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(BASE_DIR)
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    try:
        subprocess.run(
            [PYTHON_EXE, str(dashboard)],
            cwd=str(BASE_DIR),
            env=env,
        )
    except KeyboardInterrupt:
        print("\n[*] Flask Dashboard đã dừng.")


def start_streamlit_dashboard():
    """Chạy Streamlit dashboard tại http://localhost:8502"""
    dashboard = BASE_DIR / "src" / "dashboard" / "app.py"
    if not dashboard.exists():
        print(f"[ERR] Không tìm thấy: {dashboard}")
        return
    print("[*] Khởi động Streamlit Dashboard → http://localhost:8502")
    print("[*] Nhấn Ctrl+C để dừng\n")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(BASE_DIR)
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    try:
        subprocess.run(
            [PYTHON_EXE, "-m", "streamlit", "run", str(dashboard),
             "--server.port", "8502", "--server.headless", "true"],
            cwd=str(BASE_DIR),
            env=env,
        )
    except KeyboardInterrupt:
        print("\n[*] Streamlit Dashboard đã dừng.")


def start_both_dashboards():
    """Chạy đồng thời cả Flask (:5000) và Streamlit (:8502)"""
    flask_app = BASE_DIR / "dashboard" / "app.py"
    streamlit_app = BASE_DIR / "src" / "dashboard" / "app.py"

    env = os.environ.copy()
    env["PYTHONPATH"] = str(BASE_DIR)
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"

    print("[*] 🌐 Đang khởi động đồng thời cả 2 Dashboard:")
    print("    - Flask Dashboard     : http://localhost:5000 (Ads Engine, CRM Leads, Multi-Account)")
    print("    - Streamlit Analytics : http://localhost:8502 (Data Health, 360 Profile, AI Clusters)")
    print("[*] Nhấn Ctrl+C để dừng toàn bộ dịch vụ.\n")

    p_flask = subprocess.Popen(
        [PYTHON_EXE, str(flask_app)],
        cwd=str(BASE_DIR),
        env=env,
    )

    time.sleep(2)

    p_streamlit = subprocess.Popen(
        [PYTHON_EXE, "-m", "streamlit", "run", str(streamlit_app),
         "--server.port", "8502", "--server.headless", "true"],
        cwd=str(BASE_DIR),
        env=env,
    )

    try:
        while True:
            time.sleep(1)
            if p_flask.poll() is not None:
                print(f"[WARN] Flask process exited with code {p_flask.poll()}")
                break
            if p_streamlit.poll() is not None:
                print(f"[WARN] Streamlit process exited with code {p_streamlit.poll()}")
                break
    except KeyboardInterrupt:
        print("\n[*] Đang tắt các tiến trình...")
    finally:
        for p in [p_flask, p_streamlit]:
            try:
                p.terminate()
                p.wait(timeout=3)
            except Exception:
                p.kill()
        print("[*] Toàn bộ Dashboard đã được tắt an toàn.")


def run_pipeline_then_dashboard():
    """Chạy Phase 1 pipeline, sau đó mở Flask dashboard"""
    print("[1] Running Phase 1 pipeline...")
    result = subprocess.run(
        [PYTHON_EXE, str(BASE_DIR / "main.py"), "--phase", "1"],
        cwd=str(BASE_DIR)
    )
    if result.returncode != 0:
        print("[WARN] Pipeline Phase 1 có lỗi — vẫn mở dashboard")
    print()
    start_flask_dashboard()


def main():
    print_banner()

    parser = argparse.ArgumentParser(
        description="BDS Pipeline Launcher -- mở dashboard hoặc chạy pipeline"
    )
    parser.add_argument(
        "--both", "--all", action="store_true",
        help="Chạy đồng thời cả Flask (:5000) và Streamlit (:8502)"
    )
    parser.add_argument(
        "--flask", action="store_true",
        help="Mở Flask dashboard (port 5000)"
    )
    parser.add_argument(
        "--streamlit", action="store_true",
        help="Mở Streamlit dashboard (port 8502)"
    )
    parser.add_argument(
        "--pipeline", action="store_true",
        help="Chạy Phase 1 pipeline trước khi mở dashboard"
    )
    args = parser.parse_args()

    if args.pipeline:
        run_pipeline_then_dashboard()
    elif args.both:
        start_both_dashboards()
    elif args.streamlit:
        start_streamlit_dashboard()
    else:
        # Default runs both or flask
        start_flask_dashboard()


if __name__ == "__main__":
    main()
