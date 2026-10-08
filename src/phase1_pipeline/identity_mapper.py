import pandas as pd
import os
import re
import sys
import json
from datetime import datetime

import os
from pathlib import Path

# Configure stdout for UTF-8
sys.stdout.reconfigure(encoding='utf-8')

# Base paths — đọc từ env (sau khi di chuyển project)
BASE_DIR = Path(os.getenv("RAW_DATA_DIR", str(Path(__file__).parent.parent.parent / "data" / "raw"))).parent

def update_status(current_file, processed_count, total_files, start_time):
    status_file = BASE_DIR / "pipeline_status.json"
    status = {
        "current_file": current_file,
        "processed_count": processed_count,
        "total_files": total_files,
        "start_time": start_time.isoformat(),
        "last_update": datetime.now().isoformat()
    }
    with open(status_file, 'w', encoding='utf-8') as f:
        json.dump(status, f, ensure_ascii=False, indent=4)

def clear_status():
    status_file = BASE_DIR / "pipeline_status.json"
    if status_file.exists():
        status_file.unlink()

raw_dir = str(BASE_DIR / 'raw')
output_dir = str(BASE_DIR / 'identity_mapping')
os.makedirs(output_dir, exist_ok=True)
os.makedirs(os.path.join(output_dir, 'orphans'), exist_ok=True)

def extract_uid(text):
    if not isinstance(text, str): return None
    # Extract numeric UID from facebook links or text
    match = re.search(r'(\d{9,})', text)
    if match:
        return match.group(1)
    return None

def normalize_phone(phone):
    if pd.isna(phone): return None
    s = str(phone).strip()
    s = re.sub(r'\D', '', s)
    if s.startswith('84') and len(s) > 10:
        s = '0' + s[2:]
    if len(s) == 9:
        s = '0' + s
    return s if len(s) >= 10 else None

def clean_name(name) -> str:
    if pd.isna(name) or str(name).lower() in ['nan', 'none', 'null', 'unknown']: return ""
    s = str(name).strip()
    s = re.sub(r'[\r\n\t]', ' ', s)
    s = " ".join([w.capitalize() for w in s.split()])
    return s

def get_data_files(directory):
    files = []
    for ext in ['*.xlsx', '*.xls', '*.csv', '*.txt']:
        files.extend(list(Path(directory).glob(ext)))
    return files

# Keywords for column detection
UID_KEYS = ['uid', 'facebook id', 'fb id', 'link fb', 'link facebook', 'profile']
NAME_KEYS = ['name', 'tên', 'họ tên', 'full name', 'firstname', 'last name', 'customer']
PHONE_KEYS = ['phone', 'sđt', 'số điện thoại', 'mobile', 'tel', 'liên hệ', 'contact']

# Aggregators
uid_to_name = {}
uid_to_phone = {}
phone_to_name = {}

print("Scanning all raw files for identities...")
all_files = get_data_files(raw_dir)

def load_any_file(file_path):
    """Deep scan support: Reads all sheets from Excel and handles multiple CSV encodings."""
    try:
        suffix = file_path.suffix.lower()
        if suffix in ['.xlsx', '.xls']:
            # Load all sheets and concatenate
            excel_data = pd.read_excel(file_path, sheet_name=None)
            all_sheets = []
            for sheet_name, df in excel_data.items():
                if not df.empty:
                    df['source_sheet'] = sheet_name
                    all_sheets.append(df)
            return pd.concat(all_sheets, ignore_index=True) if all_sheets else pd.DataFrame()
            
        elif suffix == '.csv':
            for enc in ['utf-8', 'utf-8-sig', 'utf-16', 'latin1', 'cp1252']:
                try:
                    return pd.read_csv(file_path, encoding=enc)
                except:
                    continue
            return pd.read_csv(file_path, encoding='utf-8', errors='ignore')
            
        elif suffix == '.txt':
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = [l.strip() for l in f if l.strip()]
            return pd.DataFrame(lines, columns=['raw_content'])
            
    except Exception as e:
        print(f"Error loading {file_path}: {e}")
        return pd.DataFrame()
    
    return pd.DataFrame()

# The global loops that were previously broken are now handled inside main()

def reconciliation_loop(df, fname):
    UID_KEYS = ['uid', 'facebook id', 'fb id', 'link fb', 'link facebook', 'profile']
    NAME_KEYS = ['name', 'tên', 'họ tên', 'full name', 'firstname', 'last name', 'customer']
    PHONE_KEYS = ['phone', 'sđt', 'số điện thoại', 'mobile', 'tel', 'liên hệ', 'contact']
    
    uid_col = next((c for c in df.columns if any(k in str(c).lower() for k in UID_KEYS)), None)
    name_col = next((c for c in df.columns if any(k in str(c).lower() for k in NAME_KEYS)), None)
    phone_col = next((c for c in df.columns if any(k in str(c).lower() for k in PHONE_KEYS)), None)
    
    uid_to_name = {}
    uid_to_phone = {}
    
    for _, row in df.iterrows():
        row_dict = row.to_dict()
        uid = extract_uid(str(row_dict.get(uid_col, ''))) if uid_col else None
        name = clean_name(row_dict.get(name_col, '')) if name_col else ""
        phone = normalize_phone(row_dict.get(phone_col, '')) if phone_col else None
        
        if not phone and not uid and not name:
            raw_val = str(row_dict.get(df.columns[0], ''))
            phone = normalize_phone(raw_val)
            uid = extract_uid(raw_val)

        if uid:
            if name: uid_to_name[uid] = name
            if phone: uid_to_phone[uid] = phone
            
    mapped, orphans_no_phone, orphans_no_name = [], [], []
    for uid in set(uid_to_name.keys()) | set(uid_to_phone.keys()):
        name, phone = uid_to_name.get(uid), uid_to_phone.get(uid)
        if name and phone: mapped.append({'UID': uid, 'Name': name, 'Phone': phone})
        elif name: orphans_no_phone.append({'UID': uid, 'Name': name})
        elif phone: orphans_no_name.append({'UID': uid, 'Phone': phone})
    return mapped, orphans_no_phone, orphans_no_name

def main():
    _raw_dir = str(BASE_DIR / "raw")
    _output_dir = str(BASE_DIR / "identity_mapping")
    os.makedirs(_output_dir, exist_ok=True)
    os.makedirs(os.path.join(_output_dir, 'orphans'), exist_ok=True)

    print("Scanning all raw files for identities...")
    all_files = get_data_files(raw_dir)
    total_files = len(all_files)
    print(f"Found {total_files} files to analyze.")

    mapped_records = []
    no_phone_orphans = []
    no_name_orphans = []
    
    pipeline_start = datetime.now()

    for idx, file_path in enumerate(all_files):
        current_name = os.path.basename(file_path)
        print(f"[{idx+1}/{total_files}] Processing {current_name}...")
        update_status(current_name, idx + 1, total_files, pipeline_start)
        
        df = load_any_file(file_path)
        if df is None or df.empty:
            continue
            
        mapped, orphans_no_phone, orphans_no_name = reconciliation_loop(df, current_name)
        mapped_records.extend(mapped)
        no_phone_orphans.extend(orphans_no_phone)
        no_name_orphans.extend(orphans_no_name)

    # Save results
    pd.DataFrame(mapped_records).to_csv(os.path.join(output_dir, 'mapped_identity.csv'), index=False, encoding='utf-8-sig')
    pd.DataFrame(no_phone_orphans).to_csv(os.path.join(output_dir, 'orphans', 'uid_name_no_phone.csv'), index=False, encoding='utf-8-sig')
    pd.DataFrame(no_name_orphans).to_csv(os.path.join(output_dir, 'orphans', 'uid_phone_no_name.csv'), index=False, encoding='utf-8-sig')

    print(f"\nResults summary:")
    print(f"Mapped Identities (UID+Name+Phone): {len(mapped_records)}")
    print(f"Orphans (UID+Name, No Phone): {len(no_phone_orphans)}")
    print(f"Orphans (UID+Phone, No Name): {len(no_name_orphans)}")
    print(f"Files saved to {_output_dir}")

    # AUTO-INGEST MAPPED DATA
    print("\nTriggering auto-ingestion of bridged identities...")
    bridge_file = os.path.join(_raw_dir, 'identity_bridge_task.csv')
    pd.DataFrame(mapped_records).to_csv(bridge_file, index=False, encoding='utf-8-sig')
    
    clear_status() # Finished mapping
    os.system(f'python "{os.path.join(os.getcwd(), "src", "phase1_pipeline", "excel_ingestor.py")}"')


def run_identity_mapping(uid_mapping_file: str = None) -> dict:
    """
    Public wrapper — được gọi bởi main.py.
    Chạy quá trình map Facebook UID ←→ SĐT ←→ Tên
    đối với toàn bộ file thô trong RAW_DATA_DIR.
    """
    try:
        main()
        return {"identity_mapping": "done"}
    except Exception as e:
        print(f"[WARN] identity_mapper: {e}")
        return {"identity_mapping": "skipped", "error": str(e)}


if __name__ == "__main__":
    main()
