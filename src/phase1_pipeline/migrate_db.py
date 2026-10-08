import sqlite3
import os
from dotenv import load_dotenv
load_dotenv()

_db_url = os.getenv("DATABASE_URL", "sqlite:///d:/AI/01_Products/BigData/data/bigdata.db")
DB_PATH = _db_url.replace("sqlite:///", "")

def migrate():
    if not os.path.exists(DB_PATH):
        print("Database not found. No migration needed.")
        return
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    print("🚀 Starting Database Migration for Deep Profiling...")
    
    # Danh sách các cột cần thêm
    new_columns = [
        ("all_names", "TEXT"),
        ("all_sources", "TEXT"),
        ("metadata_json", "TEXT")
    ]
    
    for col_name, col_type in new_columns:
        try:
            cursor.execute(f"ALTER TABLE clean_contacts ADD COLUMN {col_name} {col_type}")
            print(f"✅ Added column: {col_name}")
        except sqlite3.OperationalError:
            print(f"ℹ️ Column {col_name} already exists.")
            
    conn.commit()
    conn.close()
    print("✨ Migration completed successfully.")

if __name__ == "__main__":
    migrate()
