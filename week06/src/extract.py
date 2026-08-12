import json
import sqlite3
import pandas as pd
from .config import RAW_DIR, SOURCE_DB


def extract_data():
    """
    TODO 1 (done)
    Extract data from:
      - customers.csv
      - orders.csv
      - products.json
      - stores table in store.db
    Return a dictionary of DataFrames.
    """
    customers = pd.read_csv(RAW_DIR / "customers.csv")
    orders = pd.read_csv(RAW_DIR / "orders.csv")

    with open(RAW_DIR / "products.json", encoding="utf-8") as f:
        products_raw = json.load(f)
    # products.json has nested fields: category.name, pricing.price -> flatten
    products = pd.json_normalize(products_raw)

    with sqlite3.connect(SOURCE_DB) as conn:
        stores = pd.read_sql_query("SELECT * FROM stores", conn)

    print(f"[Extract] customers={len(customers)} orders={len(orders)} "
          f"products={len(products)} stores={len(stores)}")

    return {
        "customers": customers,
        "orders": orders,
        "products": products,
        "stores": stores,
    }
