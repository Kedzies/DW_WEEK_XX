from pathlib import Path
import sqlite3
p=Path(__file__).resolve().parent/'data'/'oltp.db'
if not p.exists():raise SystemExit('Run lab.py first')
with sqlite3.connect(p) as con:
    print('Before:',con.execute('SELECT * FROM orders').fetchall())
    # Guarded UPDATE: เปลี่ยน status เป็น PAID เฉพาะเมื่อ status ยังเป็น PENDING
    rows_affected = con.execute(
        "UPDATE orders SET status='PAID' WHERE order_id='O1004' AND status='PENDING'"
    ).rowcount
    print(f'Rows affected: {rows_affected}')
    print('After:',con.execute('SELECT * FROM orders').fetchall())
# Run twice. Explain why the second guarded UPDATE should affect 0 rows.
