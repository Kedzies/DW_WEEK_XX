# ETL Lab Report

Student ID: 67160352
Name: Pannakorn Polasen

## 1. Data Quality Problems Found
- **customers.csv**: มี `customer_id` ซ้ำ 2 รายการ
- **customers.csv**: `province` เขียนไม่เป็นมาตรฐาน — ปนกันทั้งภาษาอังกฤษ (Bangkok/BKK/bangkok), ตัวย่อ, ตัวพิมพ์เล็ก-ใหญ่ และภาษาไทย (กรุงเทพฯ, ชลบุรี, จันทบุรี, ระยอง) รวมถึงมีค่าว่าง 1 รายการ
- **customers.csv**: `email` มีค่าว่าง 1 รายการ
- **products.json**: เป็น nested JSON (`category.name`, `pricing.price`) ต้อง flatten ก่อนใช้งาน, มี `category` ที่เป็น null 1 รายการ, และมี `price` ที่เก็บเป็น string พร้อม comma คั่นหลักพัน (เช่น "1,299.00") แทนที่จะเป็นตัวเลข
- **orders.csv**: มี `order_id` ซ้ำ 3 รายการ
- **orders.csv**: `order_date` มี 4 รูปแบบปนกัน (`YYYY-MM-DD`, `YYYY/MM/DD`, `DD/MM/YYYY`, `DD-Mon-YYYY`) และมี 1 ค่าที่ไม่ใช่วันที่จริง ("not-a-date")
- **orders.csv**: `qty` และ `unit_price` มีค่าติดลบ/เป็นศูนย์อยู่บ้าง
- **orders.csv**: `discount_pct` มีค่าเกิน 100 อยู่ 1 รายการ
- **orders.csv**: `status` เขียนตัวพิมพ์เล็ก/ใหญ่ปนกัน (เช่น "PAID" กับ "paid") และมีสถานะที่ไม่ใช่ยอดขายจริง (pending, cancelled) ปนอยู่กับ paid/completed

## 2. Cleaning / Transformation Rules
- **customers**: ลบ `customer_id` ที่ซ้ำ (เก็บแถวล่าสุด) → มาตรฐาน `province` ด้วย mapping table ใน `config.py` (ครอบคลุมทั้งภาษาไทยและอังกฤษ) ค่าที่ไม่รู้จัก/ว่าง → "Unknown" → เติม `email` ที่ว่างด้วย "unknown@example.com"
- **products**: flatten JSON ด้วย `pd.json_normalize()` แล้ว rename `category.name` → `category`, `pricing.price` → `price` → ลบ comma ออกจาก price ที่เป็น string แล้วแปลงเป็น numeric ด้วย `pd.to_numeric(errors="coerce")` → `category` ที่ขาดหาย → "Unknown"
- **orders**: ลบ `order_id` ที่ซ้ำ (เก็บแถวแรก) → parse `order_date` โดยลองไล่ทีละ format (`%Y-%m-%d`, `%Y/%m/%d`, `%d/%m/%Y`, `%d-%b-%Y`) จนกว่าจะสำเร็จ → `status` แปลงเป็น lowercase ทั้งหมด → reject record ที่ `qty<=0`, `unit_price<=0`, `discount_pct` นอกช่วง 0-100, หรือวันที่ parse ไม่สำเร็จ
- **merge**: กรองเฉพาะ `status` ที่เป็น "paid" หรือ "completed" → join กับ customers/products ที่สะอาดแล้ว → แถวที่ `customer_id`/`product_id` ไม่พบใน master → ย้ายไป rejects (ในชุดข้อมูลนี้ไม่พบ orphan record) → คำนวณ `gross_amount = qty * unit_price`, `discount_amount = gross_amount * discount_pct / 100`, `sales_amount = gross_amount - discount_amount`

## 3. Rejected Records
จำนวน: **83 รายการ** (จาก 183 แถวต้นทาง)

เหตุผลหลัก:
| เหตุผล | จำนวน |
|---|---|
| status ไม่ใช่ paid/completed (pending/cancelled) | 76 |
| duplicate order_id | 3 |
| qty <= 0 | 1 |
| unit_price <= 0 | 1 |
| discount_pct นอกช่วง 0-100 | 1 |
| invalid_date | 1 |

รายละเอียดทั้งหมดอยู่ใน `output/rejects.csv` (คอลัมน์ `reject_reason` อธิบายสาเหตุของแต่ละแถว)

## 4. ETL Validation
- Valid transformed rows: **100**
- Warehouse rows: **100**
- Duplicate order_id: **0**
- Source total sales: **192,074.63**
- Warehouse total sales: **192,074.63**
- Validation status: **PASS**

## 5. Idempotency Test
จำนวน fact_sales หลัง run ครั้งที่ 1: **100**

จำนวน fact_sales หลัง run ครั้งที่ 2: **100**

อธิบายผล: จำนวนแถวไม่เพิ่มขึ้นเมื่อรัน pipeline ซ้ำ เพราะ `src/load.py` กำหนดให้ `order_id` เป็น `PRIMARY KEY` ของตาราง `fact_sales` (เช่นเดียวกับ `customer_id` ใน dim_customer และ `product_id` ใน dim_product) และใช้คำสั่ง `INSERT OR REPLACE` แทน `INSERT` ธรรมดา ดังนั้นเมื่อรันซ้ำด้วยข้อมูลต้นทางเดิม แถวที่มี key เดิมจะถูก "แทนที่" (upsert) ไม่ใช่ถูกเพิ่มเป็นแถวใหม่ ทำให้ผลลัพธ์เหมือนเดิมทุกครั้งไม่ว่าจะรันกี่รอบ (idempotent)
