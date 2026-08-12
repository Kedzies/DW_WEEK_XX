import sqlite3
import pandas as pd
from .config import WAREHOUSE_DB


def validate_data(source_sales):
    """
    TODO 4 (done)
    Cross-checks the transformed (source) sales against what's actually in
    the warehouse and returns a PASS/FAIL result dict.
    """
    source_valid_rows = len(source_sales)
    source_total_sales = round(float(source_sales["sales_amount"].sum()), 2)

    with sqlite3.connect(WAREHOUSE_DB) as conn:
        warehouse_df = pd.read_sql_query("SELECT * FROM fact_sales", conn)

    warehouse_rows = len(warehouse_df)
    warehouse_total_sales = round(float(warehouse_df["sales_amount"].sum()), 2)
    duplicate_order_ids = int(warehouse_df["order_id"].duplicated().sum())

    rows_match = source_valid_rows == warehouse_rows
    totals_match = abs(source_total_sales - warehouse_total_sales) < 0.01
    no_dupes = duplicate_order_ids == 0

    status = "PASS" if (rows_match and totals_match and no_dupes) else "FAIL"

    return {
        "source_valid_rows": source_valid_rows,
        "warehouse_rows": warehouse_rows,
        "duplicate_order_ids": duplicate_order_ids,
        "warehouse_total_sales": warehouse_total_sales,
        "source_total_sales": source_total_sales,
        "status": status,
    }
