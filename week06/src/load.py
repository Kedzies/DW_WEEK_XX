import sqlite3
from .config import WAREHOUSE_DB

SCHEMA = """
CREATE TABLE IF NOT EXISTS dim_customer (
    customer_id TEXT PRIMARY KEY,
    name        TEXT,
    province    TEXT,
    email       TEXT
);

CREATE TABLE IF NOT EXISTS dim_product (
    product_id   TEXT PRIMARY KEY,
    product_name TEXT,
    category     TEXT,
    price        REAL
);

CREATE TABLE IF NOT EXISTS fact_sales (
    order_id      TEXT PRIMARY KEY,
    customer_id   TEXT,
    product_id    TEXT,
    order_date    TEXT,
    qty           REAL,
    unit_price    REAL,
    discount_pct  REAL,
    sales_amount  REAL
);
"""


def _upsert(conn, table, df, cols):
    placeholders = ", ".join(["?"] * len(cols))
    sql = f"INSERT OR REPLACE INTO {table} ({', '.join(cols)}) VALUES ({placeholders})"
    conn.executemany(sql, df[cols].itertuples(index=False, name=None))


def load_data(customers, products, sales):
    """
    TODO 3 (done)
    Loads dim_customer, dim_product, fact_sales into warehouse.db.

    Idempotency: order_id / customer_id / product_id are PRIMARY KEY
    (which enforces UNIQUE automatically), and every insert uses
    "INSERT OR REPLACE" instead of a plain INSERT. So running the
    pipeline again with the same source data overwrites existing rows
    in place instead of appending duplicates -> row counts never grow.
    """
    WAREHOUSE_DB.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(WAREHOUSE_DB) as conn:
        conn.executescript(SCHEMA)

        dim_customer = customers[["customer_id", "name", "province", "email"]] \
            .drop_duplicates(subset="customer_id", keep="last")
        dim_product = products[["product_id", "product_name", "category", "price"]] \
            .drop_duplicates(subset="product_id", keep="last")
        fact_sales = sales[["order_id", "customer_id", "product_id", "order_date",
                             "qty", "unit_price", "discount_pct", "sales_amount"]] \
            .drop_duplicates(subset="order_id", keep="last")

        _upsert(conn, "dim_customer", dim_customer,
                ["customer_id", "name", "province", "email"])
        _upsert(conn, "dim_product", dim_product,
                ["product_id", "product_name", "category", "price"])
        _upsert(conn, "fact_sales", fact_sales,
                ["order_id", "customer_id", "product_id", "order_date",
                 "qty", "unit_price", "discount_pct", "sales_amount"])
        conn.commit()

        counts = {
            t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            for t in ("dim_customer", "dim_product", "fact_sales")
        }
        print(f"[Load] row counts = {counts}")
        return counts
