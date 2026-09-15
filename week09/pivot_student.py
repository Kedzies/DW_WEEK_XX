from pathlib import Path
import sqlite3
import pandas as pd
ROOT=Path(__file__).resolve().parent
with sqlite3.connect((ROOT/'data'/'warehouse.db').as_uri()+'?mode=ro',uri=True) as con:
    df=pd.read_sql_query('SELECT * FROM sales',con)
print(df.head())

# P1: province x month, aggfunc=sum, fill_value=0, margins=True, margins_name='Total'
p1 = df.pivot_table(index='province', columns='month', values='amount',
                    aggfunc='sum', fill_value=0, margins=True, margins_name='Total')
print('\nP1 - Province x Month:')
print(p1)

# ทดลองข้อผิดพลาด: ลบ aggfunc (default = mean แทน sum)
p1_bug = df.pivot_table(index='province', columns='month', values='amount',
                        fill_value=0, margins=True, margins_name='Total')
print('\n[BUG] P1 ไม่ระบุ aggfunc (ได้ mean แทน sum):')
print(p1_bug)
print(f'  Bangkok 2026-09 = {p1_bug.loc["Bangkok","2026-09"]}  '
      f'(mean ของ Tea=300, Cookie=240 → (300+240)/2 = 270)')
print('  → แก้: เพิ่ม aggfunc="sum" กลับเข้าไป')

# P2: filter September, then category x province
sep = df[df['month'] == '2026-09']
p2 = sep.pivot_table(index='category', columns='province', values='amount',
                     aggfunc='sum', fill_value=0)
print('\nP2 - September: Category x Province:')
print(p2)

# Drink pivot (pandas แทน Excel PivotTable)
drink = df[df['category'] == 'Drink']
p_drink = drink.pivot_table(index='province', columns='month', values='amount',
                            aggfunc='sum', fill_value=0, margins=True, margins_name='Total')
print('\nP_Drink - Drink category (Rows=province, Columns=month, Values=sum(amount)):')
print(p_drink)
print(f'ยอดรวมหลังกรอง Drink: {p_drink.loc["Total","Total"]} บาท')

# P3 Assert: ใช้ p1.loc['Total','Total'] เท่านั้น ห้ามรวมทุก cell
grand_total = p1.loc['Total', 'Total']
assert grand_total == df['amount'].sum(), \
    f'FAIL: pivot grand={grand_total}, df.sum={df["amount"].sum()}'
print(f'\nAssert PASSED: p1["Total","Total"] = {grand_total} = df["amount"].sum()')

# P4: export CSVs
out = ROOT / 'data'
p1.to_csv(out / 'pivot_province_month.csv')
p2.to_csv(out / 'pivot_september.csv')
p_drink.to_csv(out / 'pivot_drink.csv')
print('Exported: pivot_province_month.csv, pivot_september.csv, pivot_drink.csv')
