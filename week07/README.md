# Python Data Pipeline Engineering — Lab Submission

ETL pipeline that loads omnichannel retail orders into a **Star Schema**
(SQLite), with idempotent + incremental loading and a quarantine path for
bad data.

## 1. วิธีติดตั้งและวิธีรัน

```bash
pip install pandas
```

Input files (CSV, extracted from the lab dataset workbook) must sit in one
folder, e.g. `./data/`:

```
data/
  customers.csv
  products.csv
  orders_batch_1.csv
  orders_batch_2.csv
  orders_batch_3.csv
```

Run:

```bash
python pipeline.py
```

This will, in order:

1. Load `dim_customer` / `dim_product`.
2. Run `orders_batch_1` → load into `retail_dw.db`.
3. Re-run `orders_batch_1` → proves idempotency (fact row count unchanged).
4. Run `orders_batch_2` → new rows + late corrections to some batch‑1 orders.
5. Run `orders_batch_3` → new rows + late corrections to earlier orders.
6. Write `retail_dw.db`, `pipeline_run_log.csv`, `quarantine.csv`.

To load only specific batches or point at a different folder, construct
`PipelineConfig` yourself:

```python
from pipeline import PipelineConfig, run_pipeline
cfg = PipelineConfig(input_path="data", output_db="retail_dw.db",
                      batches=["orders_batch_1"])
run_pipeline(cfg)
```

## 2. โครงสร้าง Star Schema

**Grain of `fact_sales`**: one *validated* sales line per `order_id`
(the source data is already one product per order, so no further
line-item splitting is needed).

| Table | Type | Key columns |
|---|---|---|
| `dim_customer` | Dimension | `customer_key` (PK, surrogate), `customer_id` (business key, unique) |
| `dim_product` | Dimension | `product_key` (PK, surrogate), `product_id` (business key, unique) |
| `dim_date` | Dimension | `date_key` (PK, `YYYYMMDD` int), `full_date`, `day/month/quarter/year` |
| `fact_sales` | Fact | `order_id` (PK — enforces "no duplicate order"), FKs to the three dims above, measures (`quantity`, `unit_price`, `discount_pct`, `gross_amount`, `net_amount`), degenerate dims (`payment_method`, `sales_channel`), plus `updated_at` / `source_batch` used for incremental watermarking |
| `quarantine` | Side table | rejected rows + `reason_code` + `source_batch`, `UNIQUE(order_id, reason_code, source_batch)` so re-running a batch doesn't duplicate quarantine entries |
| `pipeline_run_log` | Ops table | one row per batch run: `started_at`, `ended_at`, `rows_read`, `rows_valid`, `rows_rejected`, `rows_duplicated`, `rows_loaded`, `status` |

`fact_sales.order_id` is declared `PRIMARY KEY`, so SQLite itself rejects
duplicate order rows — idempotency is enforced at the schema level, not
just in application code.

## 3. Idempotent + Incremental loading (Task 4)

Loading uses a single SQL statement per row:

```sql
INSERT INTO fact_sales (...) SELECT ...
WHERE NOT EXISTS (
    SELECT 1 FROM fact_sales WHERE order_id = :order_id AND updated_at >= :updated_at
)
ON CONFLICT(order_id) DO UPDATE SET ...
WHERE excluded.updated_at > fact_sales.updated_at;
```

- **New `order_id`** → plain insert.
- **Same `order_id`, same/older `updated_at`** (e.g. re-running the same
  batch) → no-op. Fact row count does not grow.
- **Same `order_id`, newer `updated_at`** (a late-arriving correction that
  shows up in a later batch) → the existing fact row is updated in place.

Evidence in `pipeline_run_log.csv` — 4 rounds were run:

| batch | rows_read | rows_valid | rows_rejected | rows_duplicated (within batch) | rows_loaded | fact row count after |
|---|---|---|---|---|---|---|
| orders_batch_1 | 420 | 376 | 44 | 0 | 376 | 376 |
| orders_batch_1 (re-run) | 420 | 376 | 44 | 0 | **0** | **376** (unchanged ✔) |
| orders_batch_2 | 424 | 369 | 55 | 1 | 368 | 743 |
| orders_batch_3 | 424 | 372 | 52 | 3 | 368 | 1,111 |

`rows_read = rows_valid + rows_rejected` in every row above (checked
**before** deduplication, as required by the acceptance test).
`rows_duplicated` counts rows removed because the *same batch file*
contained more than one row for the same `order_id` (keeping the one with
the latest `updated_at`). `rows_loaded` can be smaller than
`rows_valid − rows_duplicated` whenever a row's `updated_at` is not newer
than what's already stored (a genuine no-op, separate from in-batch dedup).

## 4. Data quality rules applied (Task 2)

| Rule | reason_code |
|---|---|
| `order_datetime` not parseable | `INVALID_DATETIME` |
| `updated_at` not parseable | `INVALID_UPDATED_AT` |
| `quantity` not numeric | `INVALID_QUANTITY_TYPE` |
| `quantity` not an integer in 1–20 | `QUANTITY_OUT_OF_RANGE` |
| `unit_price` not numeric (after stripping currency prefixes like `THB `) | `INVALID_UNIT_PRICE` |
| `unit_price` ≤ 0 | `UNIT_PRICE_NOT_POSITIVE` |
| `discount_pct` not numeric | `INVALID_DISCOUNT_PCT` |
| `discount_pct` outside 0–100 | `DISCOUNT_OUT_OF_RANGE` |
| `payment_method` not one of Cash / Credit Card / Bank Transfer / PromptPay (case/space normalized) | `UNKNOWN_PAYMENT_METHOD` |
| `sales_channel` not one of Store / Online / Marketplace / E-Commerce | `UNKNOWN_SALES_CHANNEL` |
| `customer_id` missing or not in `dim_customer` | `CUSTOMER_NOT_FOUND` |
| `product_id` not in `dim_product` | `PRODUCT_NOT_FOUND` |
| `product_id` exists but `active_flag != 'Y'` | `PRODUCT_INACTIVE` |

A row can carry more than one `reason_code`, joined with `|`.

Final `quarantine.csv` breakdown (149 unique rejected rows across all 3 batches):

`PRODUCT_INACTIVE` (48) · `CUSTOMER_NOT_FOUND` (22) · `INVALID_DATETIME` (21) ·
`QUANTITY_OUT_OF_RANGE` (14) · `DISCOUNT_OUT_OF_RANGE` (12) ·
`PRODUCT_NOT_FOUND` (11) · `INVALID_QUANTITY_TYPE` (10) ·
`INVALID_UNIT_PRICE` (8) · a few rows with combined reasons.

## 5. KPI summary (final state after all 3 batches)

- **Total rows read**: 1,268 (across 3 batches)
- **Rows loaded into `fact_sales`**: 1,111 (unique `order_id`)
- **Rows quarantined**: 149 (unique)
- **Total net sales**: ฿2,720,914.79

## 6. Reflection — เหตุใด Availability จึงมักสำคัญกว่า Strictness

ใน Production Pipeline ถ้าเราตั้งกฎเข้มงวดจนแถวที่มีปัญหาเพียงแถวเดียว
ทำให้ทั้ง batch ล้มเหลว (fail-fast ทั้งไฟล์) ผลลัพธ์คือฝ่ายวิเคราะห์จะไม่มี
ข้อมูลใหม่เลยในวันนั้น แม้ 95% ของแถวจะถูกต้องสมบูรณ์ก็ตาม ความเสียหายจาก
"ไม่มีข้อมูล" (ตัวเลขยอดขายเป็นศูนย์ รายงานว่างเปล่า) มักร้ายแรงกว่าความ
เสียหายจาก "ข้อมูลบางส่วนขาดหายชั่วคราว" เพราะทีมธุรกิจยังสามารถตัดสินใจ
จากข้อมูล 95% ที่ดีได้ ในขณะที่ไม่มีข้อมูลเลยจะทำให้ตัดสินใจผิดพลาดทันที
การออกแบบ Pipeline ในแล็บนี้จึงเลือกแยกแถวเสียออกไปที่ตาราง `quarantine`
พร้อม `reason_code` แทนที่จะโยน exception ทั้ง batch — ข้อมูลที่ดีถูกโหลด
ต่อได้เสมอ ส่วนแถวที่มีปัญหาก็ยังถูกบันทึกไว้ตรวจสอบและแก้ไขย้อนหลังได้
โดยไม่สูญหาย นอกจากนี้การรันซ้ำได้อย่างปลอดภัย (Idempotent) และการโหลด
เฉพาะข้อมูลใหม่ (Incremental) ก็ช่วยให้ระบบ "พร้อมใช้งานเสมอ" — วิศวกร
สามารถรัน Pipeline ซ้ำได้ทุกเมื่อโดยไม่ต้องกลัวข้อมูลซ้ำหรือพัง ซึ่งสำคัญกว่า
การมีกฎที่เข้มงวดจนเปราะบางเกินไปสำหรับข้อมูลจริงที่ไม่สมบูรณ์แบบเสมอ

## 7. Deliverables in this submission

| File | Description |
|---|---|
| `pipeline.py` | Full source: `PipelineConfig`, extract/transform/load, `run_pipeline()`, demo of 4 runs |
| `retail_dw.db` | SQLite DB after loading all 3 batches |
| `quarantine.csv` | 149 rejected rows with `reason_code` + `source_batch` |
| `pipeline_run_log.csv` | 4 run records (batch_1, batch_1 re-run, batch_2, batch_3) |
| `README.md` | This file |
