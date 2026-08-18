"""
Python Data Pipeline Engineering - Lab Assignment
ETL Pipeline: Omnichannel Retail -> Star Schema (SQLite)

Run:
    python pipeline.py
"""

from __future__ import annotations

import logging
import re
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

# --------------------------------------------------------------------------
# Logging setup
# --------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("pipeline")


# ==========================================================================
# TASK 1 - Pipeline Configuration
# ==========================================================================
@dataclass
class PipelineConfig:
    """Central configuration object for a pipeline run."""
    input_path: Path
    output_db: Path
    batches: list[str] = field(default_factory=lambda: ["orders_batch_1", "orders_batch_2", "orders_batch_3"])
    error_mode: str = "quarantine"          # "quarantine" (skip+log bad rows) or "fail_fast"
    quarantine_csv: Path = Path("quarantine.csv")
    run_log_csv: Path = Path("pipeline_run_log.csv")

    def __post_init__(self):
        self.input_path = Path(self.input_path)
        self.output_db = Path(self.output_db)
        self.quarantine_csv = Path(self.quarantine_csv)
        self.run_log_csv = Path(self.run_log_csv)


# ==========================================================================
# TASK 1 - Extract
# ==========================================================================
def extract_csv(path: Path, name: str) -> pd.DataFrame:
    """Read one source file with logging + error handling. Never mutates the source."""
    started = time.time()
    try:
        df = pd.read_csv(path, dtype=str)  # read everything as string; we coerce types ourselves
        elapsed = time.time() - started
        log.info(f"EXTRACT  {name:<18} rows={len(df):<5} time={elapsed:.3f}s  <- {path.name}")
        return df
    except Exception as exc:
        elapsed = time.time() - started
        log.error(f"EXTRACT  {name:<18} FAILED after {elapsed:.3f}s : {exc}")
        raise


# ==========================================================================
# TASK 2 - Transform + Data Quality
# ==========================================================================
VALID_PAYMENT_METHODS = {"cash": "Cash", "credit card": "Credit Card",
                          "bank transfer": "Bank Transfer", "promptpay": "PromptPay"}
VALID_SALES_CHANNELS = {"store": "Store", "online": "Online",
                         "marketplace": "Marketplace", "e-commerce": "E-Commerce"}


def _clean_price(raw: str) -> float:
    """Strip currency prefixes like 'THB 979.4' -> 979.4. Returns NaN if unparsable."""
    if pd.isna(raw):
        return float("nan")
    cleaned = re.sub(r"[^0-9.\-]", "", str(raw))
    try:
        return float(cleaned) if cleaned not in ("", "-", ".") else float("nan")
    except ValueError:
        return float("nan")


def transform_orders(
    raw: pd.DataFrame,
    customers: pd.DataFrame,
    products: pd.DataFrame,
    batch_name: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Returns (clean_df, quarantine_df).
    clean_df:  rows that passed every rule, deduplicated by order_id (latest updated_at wins).
    quarantine_df: rejected rows with a reason_code (rows can fail more than one rule).
    """
    df = raw.copy()
    n_read = len(df)
    reasons = pd.Series([[] for _ in range(len(df))], index=df.index)

    def flag(mask: pd.Series, code: str) -> None:
        for idx in df.index[mask.fillna(False)]:
            reasons.at[idx].append(code)

    # --- safe type coercion (errors="coerce") -----------------------------
    df["order_datetime_parsed"] = pd.to_datetime(df["order_datetime"], errors="coerce")
    df["quantity_parsed"] = pd.to_numeric(df["quantity"], errors="coerce")
    df["unit_price_parsed"] = df["unit_price"].apply(_clean_price)
    df["discount_pct_parsed"] = pd.to_numeric(df["discount_pct"], errors="coerce")
    df["updated_at_parsed"] = pd.to_datetime(df["updated_at"], errors="coerce")

    # --- normalize categorical fields (documented mapping) -----------------
    df["payment_method_norm"] = (
        df["payment_method"].str.strip().str.lower().map(VALID_PAYMENT_METHODS)
    )
    df["sales_channel_norm"] = (
        df["sales_channel"].str.strip().str.lower().map(VALID_SALES_CHANNELS)
    )

    # --- rule checks ---------------------------------------------------------
    flag(df["order_datetime_parsed"].isna(), "INVALID_DATETIME")
    flag(df["updated_at_parsed"].isna(), "INVALID_UPDATED_AT")
    flag(df["quantity_parsed"].isna(), "INVALID_QUANTITY_TYPE")
    flag(df["quantity_parsed"].notna() & ((df["quantity_parsed"] <= 0) | (df["quantity_parsed"] > 20)
                                           | (df["quantity_parsed"] % 1 != 0)), "QUANTITY_OUT_OF_RANGE")
    flag(df["unit_price_parsed"].isna(), "INVALID_UNIT_PRICE")
    flag(df["unit_price_parsed"].notna() & (df["unit_price_parsed"] <= 0), "UNIT_PRICE_NOT_POSITIVE")
    flag(df["discount_pct_parsed"].isna(), "INVALID_DISCOUNT_PCT")
    flag(df["discount_pct_parsed"].notna() & ((df["discount_pct_parsed"] < 0) | (df["discount_pct_parsed"] > 100)),
         "DISCOUNT_OUT_OF_RANGE")
    flag(df["payment_method_norm"].isna(), "UNKNOWN_PAYMENT_METHOD")
    flag(df["sales_channel_norm"].isna(), "UNKNOWN_SALES_CHANNEL")

    # --- referential integrity ------------------------------------------------
    valid_customers = set(customers["customer_id"])
    valid_products_active = set(products.loc[products["active_flag"] == "Y", "product_id"])
    valid_products_all = set(products["product_id"])

    flag(~df["customer_id"].isin(valid_customers), "CUSTOMER_NOT_FOUND")
    flag(df["product_id"].isin(valid_products_all) & ~df["product_id"].isin(valid_products_active),
         "PRODUCT_INACTIVE")
    flag(~df["product_id"].isin(valid_products_all), "PRODUCT_NOT_FOUND")

    df["reason_codes"] = reasons
    df["is_bad"] = df["reason_codes"].apply(len) > 0

    quarantine_df = df[df["is_bad"]].copy()
    quarantine_df["reason_code"] = quarantine_df["reason_codes"].apply(lambda r: "|".join(r))
    quarantine_df["source_batch"] = batch_name
    quarantine_cols = ["order_id", "customer_id", "product_id", "order_datetime", "quantity",
                        "unit_price", "discount_pct", "payment_method", "sales_channel",
                        "updated_at", "reason_code", "source_batch"]
    quarantine_df = quarantine_df[quarantine_cols]

    good = df[~df["is_bad"]].copy()

    # --- deduplicate by order_id, keep latest updated_at (within this batch) ---
    n_valid_pre_dedup = len(good)
    good = good.sort_values("updated_at_parsed").drop_duplicates("order_id", keep="last")
    n_duplicated_in_batch = n_valid_pre_dedup - len(good)

    # --- derived measures -------------------------------------------------
    good["gross_amount"] = (good["quantity_parsed"] * good["unit_price_parsed"]).round(2)
    good["net_amount"] = (good["gross_amount"] * (1 - good["discount_pct_parsed"] / 100)).round(2)

    # Build explicitly (rather than rename-in-place) because `good` still holds the
    # original raw-string columns alongside the *_parsed ones; renaming onto the same
    # name would create duplicate columns and silently break single-column selection.
    clean_df = pd.DataFrame({
        "order_id": good["order_id"].values,
        "order_datetime": good["order_datetime_parsed"].values,
        "customer_id": good["customer_id"].values,
        "product_id": good["product_id"].values,
        "quantity": good["quantity_parsed"].values,
        "unit_price": good["unit_price_parsed"].values,
        "discount_pct": good["discount_pct_parsed"].values,
        "payment_method": good["payment_method_norm"].values,
        "sales_channel": good["sales_channel_norm"].values,
        "updated_at": good["updated_at_parsed"].values,
        "gross_amount": good["gross_amount"].values,
        "net_amount": good["net_amount"].values,
        "source_batch": batch_name,
    })

    log.info(
        f"TRANSFORM {batch_name:<15} read={n_read:<5} valid={n_valid_pre_dedup:<5} "
        f"rejected={len(quarantine_df):<5} dup_in_batch={n_duplicated_in_batch:<4} "
        f"(read = valid + rejected, pre-dedup: {n_read} == {n_valid_pre_dedup + len(quarantine_df)})"
    )
    return clean_df, quarantine_df


# ==========================================================================
# TASK 3 - Star Schema DDL
# ==========================================================================
DDL = """
CREATE TABLE IF NOT EXISTS dim_customer (
    customer_key    INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id     TEXT UNIQUE NOT NULL,
    customer_name   TEXT,
    province         TEXT,
    segment         TEXT
);

CREATE TABLE IF NOT EXISTS dim_product (
    product_key     INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id      TEXT UNIQUE NOT NULL,
    product_name    TEXT,
    category        TEXT
);

CREATE TABLE IF NOT EXISTS dim_date (
    date_key        INTEGER PRIMARY KEY,
    full_date       TEXT UNIQUE NOT NULL,
    day             INTEGER,
    month           INTEGER,
    quarter         INTEGER,
    year            INTEGER
);

CREATE TABLE IF NOT EXISTS fact_sales (
    order_id        TEXT PRIMARY KEY,
    date_key        INTEGER NOT NULL REFERENCES dim_date(date_key),
    customer_key    INTEGER NOT NULL REFERENCES dim_customer(customer_key),
    product_key     INTEGER NOT NULL REFERENCES dim_product(product_key),
    quantity        INTEGER NOT NULL,
    unit_price      REAL NOT NULL,
    discount_pct    REAL NOT NULL,
    gross_amount    REAL NOT NULL,
    net_amount      REAL NOT NULL,
    payment_method  TEXT NOT NULL,
    sales_channel   TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    source_batch    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS quarantine (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id        TEXT,
    customer_id     TEXT,
    product_id      TEXT,
    order_datetime  TEXT,
    quantity        TEXT,
    unit_price      TEXT,
    discount_pct    TEXT,
    payment_method  TEXT,
    sales_channel   TEXT,
    updated_at      TEXT,
    reason_code     TEXT,
    source_batch    TEXT,
    UNIQUE(order_id, reason_code, source_batch)
);

CREATE TABLE IF NOT EXISTS pipeline_run_log (
    run_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    batch           TEXT,
    started_at      TEXT,
    ended_at        TEXT,
    rows_read       INTEGER,
    rows_valid      INTEGER,
    rows_rejected   INTEGER,
    rows_duplicated INTEGER,
    rows_loaded     INTEGER,
    status          TEXT
);
"""


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(DDL)
    conn.commit()


def load_dimensions(conn: sqlite3.Connection, customers: pd.DataFrame, products: pd.DataFrame) -> None:
    """Idempotent load of dim_customer / dim_product (INSERT OR IGNORE on business key)."""
    cur = conn.cursor()
    cur.executemany(
        "INSERT OR IGNORE INTO dim_customer (customer_id, customer_name, province, segment) VALUES (?,?,?,?)",
        customers[["customer_id", "customer_name", "province", "segment"]].itertuples(index=False, name=None),
    )
    cur.executemany(
        "INSERT OR IGNORE INTO dim_product (product_id, product_name, category) VALUES (?,?,?)",
        products[["product_id", "product_name", "category"]].itertuples(index=False, name=None),
    )
    conn.commit()
    log.info(f"LOAD     dim_customer/dim_product ready "
             f"(customers={len(customers)}, products={len(products)})")


def upsert_dim_date(conn: sqlite3.Connection, dates: pd.Series) -> None:
    cur = conn.cursor()
    rows = []
    for d in pd.to_datetime(dates.dropna().dt.date.unique()):
        date_key = int(d.strftime("%Y%m%d"))
        rows.append((date_key, d.strftime("%Y-%m-%d"), d.day, d.month, (d.month - 1) // 3 + 1, d.year))
    cur.executemany(
        "INSERT OR IGNORE INTO dim_date (date_key, full_date, day, month, quarter, year) VALUES (?,?,?,?,?,?)",
        rows,
    )
    conn.commit()


# ==========================================================================
# TASK 3/4 - Load fact_sales : idempotent + incremental UPSERT
# ==========================================================================
def load_fact(conn: sqlite3.Connection, clean_df: pd.DataFrame) -> int:
    """
    Upserts one row per order_id.
    - Same order_id + same/older updated_at  -> no-op   (idempotent re-run)
    - Same order_id + newer updated_at       -> update  (incremental correction)
    - New order_id                            -> insert
    Returns rows actually loaded (inserted or updated).
    """
    if clean_df.empty:
        return 0

    cur = conn.cursor()
    upsert_sql = """
    INSERT INTO fact_sales (order_id, date_key, customer_key, product_key, quantity, unit_price,
                             discount_pct, gross_amount, net_amount, payment_method, sales_channel,
                             updated_at, source_batch)
    SELECT
        :order_id,
        (SELECT date_key FROM dim_date WHERE full_date = :order_date),
        (SELECT customer_key FROM dim_customer WHERE customer_id = :customer_id),
        (SELECT product_key FROM dim_product WHERE product_id = :product_id),
        :quantity, :unit_price, :discount_pct, :gross_amount, :net_amount,
        :payment_method, :sales_channel, :updated_at, :source_batch
    WHERE NOT EXISTS (
        SELECT 1 FROM fact_sales WHERE order_id = :order_id AND updated_at >= :updated_at
    )
    ON CONFLICT(order_id) DO UPDATE SET
        date_key = excluded.date_key,
        customer_key = excluded.customer_key,
        product_key = excluded.product_key,
        quantity = excluded.quantity,
        unit_price = excluded.unit_price,
        discount_pct = excluded.discount_pct,
        gross_amount = excluded.gross_amount,
        net_amount = excluded.net_amount,
        payment_method = excluded.payment_method,
        sales_channel = excluded.sales_channel,
        updated_at = excluded.updated_at,
        source_batch = excluded.source_batch
    WHERE excluded.updated_at > fact_sales.updated_at;
    """

    before = conn.total_changes
    for row in clean_df.itertuples(index=False):
        cur.execute(upsert_sql, {
            "order_id": row.order_id,
            "order_date": row.order_datetime.strftime("%Y-%m-%d"),
            "customer_id": row.customer_id,
            "product_id": row.product_id,
            "quantity": int(row.quantity),
            "unit_price": float(row.unit_price),
            "discount_pct": float(row.discount_pct),
            "gross_amount": float(row.gross_amount),
            "net_amount": float(row.net_amount),
            "payment_method": row.payment_method,
            "sales_channel": row.sales_channel,
            "updated_at": row.updated_at.strftime("%Y-%m-%d %H:%M:%S"),
            "source_batch": row.source_batch,
        })
    conn.commit()
    return conn.total_changes - before


def load_quarantine(conn: sqlite3.Connection, quarantine_df: pd.DataFrame) -> None:
    if quarantine_df.empty:
        return
    cur = conn.cursor()
    cur.executemany(
        """INSERT OR IGNORE INTO quarantine
           (order_id, customer_id, product_id, order_datetime, quantity, unit_price,
            discount_pct, payment_method, sales_channel, updated_at, reason_code, source_batch)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        quarantine_df[[
            "order_id", "customer_id", "product_id", "order_datetime", "quantity", "unit_price",
            "discount_pct", "payment_method", "sales_channel", "updated_at", "reason_code", "source_batch",
        ]].itertuples(index=False, name=None),
    )
    conn.commit()


# ==========================================================================
# TASK 5 - Orchestration
# ==========================================================================
def run_pipeline(config: PipelineConfig) -> dict:
    conn = sqlite3.connect(config.output_db)
    init_db(conn)

    customers = extract_csv(config.input_path / "customers.csv", "customers")
    products = extract_csv(config.input_path / "products.csv", "products")
    load_dimensions(conn, customers, products)

    run_log_rows = []
    all_quarantine = []
    kpi = {"rows_read": 0, "rows_valid": 0, "rows_rejected": 0, "rows_duplicated": 0, "rows_loaded": 0}

    for batch_name in config.batches:
        started_at = pd.Timestamp.now()
        status = "SUCCESS"
        rows_read = rows_valid = rows_rejected = rows_duplicated = rows_loaded = 0
        try:
            raw = extract_csv(config.input_path / f"{batch_name}.csv", batch_name)
            rows_read = len(raw)

            clean_df, quarantine_df = transform_orders(raw, customers, products, batch_name)
            rows_rejected = len(quarantine_df)
            rows_valid = rows_read - rows_rejected
            rows_duplicated = rows_valid - len(clean_df)

            upsert_dim_date(conn, clean_df["order_datetime"])
            rows_loaded = load_fact(conn, clean_df)
            load_quarantine(conn, quarantine_df)
            all_quarantine.append(quarantine_df)

        except Exception as exc:
            # A whole-batch failure must not destroy previously loaded data.
            status = "FAILED"
            log.error(f"LOAD     {batch_name} FAILED: {exc}")
            if config.error_mode == "fail_fast":
                raise
        finally:
            ended_at = pd.Timestamp.now()
            conn.execute(
                """INSERT INTO pipeline_run_log
                   (batch, started_at, ended_at, rows_read, rows_valid, rows_rejected,
                    rows_duplicated, rows_loaded, status)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (batch_name, str(started_at), str(ended_at), rows_read, rows_valid,
                 rows_rejected, rows_duplicated, rows_loaded, status),
            )
            conn.commit()
            run_log_rows.append({
                "batch": batch_name, "started_at": started_at, "ended_at": ended_at,
                "rows_read": rows_read, "rows_valid": rows_valid, "rows_rejected": rows_rejected,
                "rows_duplicated": rows_duplicated, "rows_loaded": rows_loaded, "status": status,
            })
            log.info(f"RUN      {batch_name:<15} status={status} loaded={rows_loaded} "
                     f"(fact rows now = {conn.execute('SELECT COUNT(*) FROM fact_sales').fetchone()[0]})")

            for k in kpi:
                kpi[k] += locals()[k]

    kpi["net_sales_total"] = conn.execute("SELECT ROUND(SUM(net_amount), 2) FROM fact_sales").fetchone()[0]
    kpi["fact_row_count"] = conn.execute("SELECT COUNT(*) FROM fact_sales").fetchone()[0]

    run_log_df = pd.DataFrame(run_log_rows)
    quarantine_all_df = pd.concat(all_quarantine, ignore_index=True) if all_quarantine else pd.DataFrame()

    conn.close()
    return {"kpi": kpi, "run_log": run_log_df, "quarantine": quarantine_all_df}


# ==========================================================================
# MAIN - demonstrate idempotency + incremental loading
# ==========================================================================
if __name__ == "__main__":
    DATA_DIR = Path("/home/claude/data")
    OUT_DIR = Path("/home/claude/work")
    db_path = OUT_DIR / "retail_dw.db"
    db_path.unlink(missing_ok=True)  # fresh demo run

    all_run_logs = []
    all_quarantine = []

    print("\n" + "=" * 78)
    print("ROUND 1: load batch_1")
    print("=" * 78)
    cfg = PipelineConfig(input_path=DATA_DIR, output_db=db_path, batches=["orders_batch_1"])
    result = run_pipeline(cfg)
    all_run_logs.append(result["run_log"])
    all_quarantine.append(result["quarantine"])
    print("KPI:", result["kpi"])

    print("\n" + "=" * 78)
    print("ROUND 2: re-run batch_1 (idempotency check -> fact count must NOT grow)")
    print("=" * 78)
    fact_count_before = sqlite3.connect(db_path).execute("SELECT COUNT(*) FROM fact_sales").fetchone()[0]
    cfg = PipelineConfig(input_path=DATA_DIR, output_db=db_path, batches=["orders_batch_1"])
    result = run_pipeline(cfg)
    fact_count_after = sqlite3.connect(db_path).execute("SELECT COUNT(*) FROM fact_sales").fetchone()[0]
    all_run_logs.append(result["run_log"])
    all_quarantine.append(result["quarantine"])
    print(f"fact_sales count before={fact_count_before} after={fact_count_after} "
          f"-> {'IDEMPOTENT OK' if fact_count_before == fact_count_after else 'FAILED!'}")
    print("KPI:", result["kpi"])

    print("\n" + "=" * 78)
    print("ROUND 3: load batch_2 (includes late corrections to some batch_1 orders)")
    print("=" * 78)
    cfg = PipelineConfig(input_path=DATA_DIR, output_db=db_path, batches=["orders_batch_2"])
    result = run_pipeline(cfg)
    all_run_logs.append(result["run_log"])
    all_quarantine.append(result["quarantine"])
    print("KPI:", result["kpi"])

    print("\n" + "=" * 78)
    print("ROUND 4: load batch_3 (includes late corrections to earlier orders)")
    print("=" * 78)
    cfg = PipelineConfig(input_path=DATA_DIR, output_db=db_path, batches=["orders_batch_3"])
    result = run_pipeline(cfg)
    all_run_logs.append(result["run_log"])
    all_quarantine.append(result["quarantine"])
    print("KPI:", result["kpi"])

    # ---- persist deliverables -------------------------------------------
    full_run_log = pd.concat(all_run_logs, ignore_index=True)
    full_run_log.to_csv(OUT_DIR / "pipeline_run_log.csv", index=False)

    full_quarantine = pd.concat(all_quarantine, ignore_index=True)
    full_quarantine = full_quarantine.drop_duplicates(subset=["order_id", "reason_code", "source_batch"])
    full_quarantine.to_csv(OUT_DIR / "quarantine.csv", index=False)

    conn = sqlite3.connect(db_path)
    final_fact_count = conn.execute("SELECT COUNT(*) FROM fact_sales").fetchone()[0]
    final_net_sales = conn.execute("SELECT ROUND(SUM(net_amount),2) FROM fact_sales").fetchone()[0]
    total_quarantine_rows = conn.execute("SELECT COUNT(*) FROM quarantine").fetchone()[0]
    conn.close()

    print("\n" + "=" * 78)
    print("FINAL SUMMARY")
    print("=" * 78)
    print(f"fact_sales rows (unique order_id) : {final_fact_count}")
    print(f"quarantine rows (unique)          : {total_quarantine_rows}")
    print(f"Total net sales                   : {final_net_sales:,.2f}")
    print(f"\nWrote: {db_path}")
    print(f"Wrote: {OUT_DIR/'pipeline_run_log.csv'}")
    print(f"Wrote: {OUT_DIR/'quarantine.csv'}")
