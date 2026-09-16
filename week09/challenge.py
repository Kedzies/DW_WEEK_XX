"""โจทย์ต่อยอด ข. — สำเนา warehouse.db เป็น challenge.db
เพิ่ม dim_date 2026-10-01 และรายการ O1007, O1008 แล้วสร้าง Pivot ใหม่
ตรวจจำนวนแถว ออเดอร์ และยอดรวมก่อน/หลัง JOIN
"""
from pathlib import Path
import shutil
import sqlite3
import pandas as pd

ROOT = Path(__file__).resolve().parent
SRC = ROOT / 'data' / 'warehouse.db'
DST = ROOT / 'data' / 'challenge.db'

if not SRC.exists():
    raise SystemExit('Run lab.py first')

shutil.copy(SRC, DST)
print(f'Copied {SRC.name} -> {DST.name}')

con = sqlite3.connect(DST)
con.execute('PRAGMA foreign_keys=ON')

# ---------- ก่อน INSERT ----------
before = con.execute("""
    SELECT COUNT(*), COUNT(DISTINCT order_id), SUM(quantity), SUM(quantity*unit_price)
    FROM fact_sales
""").fetchone()
print(f'ก่อน : rows={before[0]}  orders={before[1]}  units={before[2]}  revenue={before[3]}')

# ---------- เพิ่ม dim_date ของ 2026-10-01 ----------
con.execute("""
    INSERT OR IGNORE INTO dim_date(date_key, full_date, year, month)
    VALUES (20261001, '2026-10-01', 2026, '2026-10')
""")

# ---------- เพิ่มรายการใหม่ ----------
# product_key: 1=Tea(50), 2=Cookie(80)   |   store_key: 1=Bangsaen(Chonburi), 2=Siam(Bangkok)
new_rows = [
    ('O1007', 1, 20261001, 1, 1, 3, 50),   # Tea    3 ชิ้น @ Chonburi
    ('O1007', 2, 20261001, 2, 1, 2, 80),   # Cookie 2 ชิ้น @ Chonburi
    ('O1008', 1, 20261001, 1, 2, 4, 50),   # Tea    4 ชิ้น @ Bangkok
]
con.executemany("""
    INSERT INTO fact_sales(order_id, line_no, date_key, product_key, store_key, quantity, unit_price)
    VALUES (?,?,?,?,?,?,?)
""", new_rows)
con.commit()

# ---------- หลัง INSERT ----------
after = con.execute("""
    SELECT COUNT(*), COUNT(DISTINCT order_id), SUM(quantity), SUM(quantity*unit_price)
    FROM fact_sales
""").fetchone()
print(f'หลัง : rows={after[0]}  orders={after[1]}  units={after[2]}  revenue={after[3]}')
print(f'เพิ่ม: +{after[0]-before[0]} rows  +{after[1]-before[1]} orders  '
      f'+{after[2]-before[2]} units  +{after[3]-before[3]} บาท')

# ---------- Pivot ใหม่ ----------
df = pd.read_sql_query('SELECT * FROM sales', con)
pivot = df.pivot_table(index='province', columns='month', values='amount',
                       aggfunc='sum', fill_value=0, margins=True, margins_name='Total')
print('\nPivot Province x Month (รวมตุลาคม):')
print(pivot)
pivot.to_csv(ROOT / 'data' / 'pivot_challenge.csv')

# ---------- ตรวจก่อน/หลัง JOIN ----------
view = con.execute('SELECT COUNT(*), SUM(amount) FROM sales').fetchone()
print(f'\nก่อน JOIN (fact_sales) : rows={after[0]}  revenue={after[3]}')
print(f'หลัง JOIN (sales view) : rows={view[0]}  revenue={view[1]}')
print('ตรงกัน' if (after[0], after[3]) == view else 'ไม่ตรง — ตรวจ JOIN')

violations = con.execute('PRAGMA foreign_key_check').fetchall()
print('FK check:', violations if violations else 'OK — ไม่มี FK violation')

con.close()
