import sqlite3, os

conn = sqlite3.connect(r'd:\AI\01_Products\BigData\data\bigdata.db', timeout=15)
conn.execute('PRAGMA journal_mode=WAL')
conn.execute('PRAGMA cache_size=-32768')

tables = ['raw_contacts','clean_contacts','customer_profiles',
          'hot_leads','google_leads','ad_campaigns','messenger_leads',
          'dashboard_stats']

print("=" * 50)
print("  DATABASE AUDIT — BigData Pipeline")
print("=" * 50)

for t in tables:
    try:
        c = conn.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]
        print(f'  {t:<25} {c:>12,}')
    except Exception as e:
        print(f'  {t:<25} {"N/A":>12}  ({e})')

# Score distribution
print()
print("  Lead Score Distribution:")
rows = conn.execute('''
    SELECT
        SUM(CASE WHEN lead_score >= 8 THEN 1 ELSE 0 END) vip,
        SUM(CASE WHEN lead_score >= 5 AND lead_score < 8 THEN 1 ELSE 0 END) warm,
        SUM(CASE WHEN lead_score < 5 THEN 1 ELSE 0 END) cold,
        ROUND(AVG(lead_score),2) avg_score,
        MAX(lead_score) max_score
    FROM customer_profiles
''').fetchone()
print(f'    VIP  (>=8):  {rows[0]:>8,}')
print(f'    Warm (5-7):  {rows[1]:>8,}')
print(f'    Cold (<5):   {rows[2]:>8,}')
print(f'    Avg score:   {rows[3]:>8}')
print(f'    Max score:   {rows[4]:>8}')

# DB file size
size = os.path.getsize(r'd:\AI\01_Products\BigData\data\bigdata.db')
print(f'\n  DB size: {size/(1024**3):.2f} GB')

conn.close()
print("=" * 50)
