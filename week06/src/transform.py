import pandas as pd
from .config import PROVINCE_MAP

VALID_STATUSES = {"paid", "completed"}

# formats actually found in orders.csv: 2026-08-01 / 2026/08/02 / 01/08/2026 / 03-Aug-2026
DATE_FORMATS = ["%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%d-%b-%Y"]


def _std_province(p):
    if pd.isna(p) or str(p).strip() == "":
        return "Unknown"
    key = str(p).strip().lower()
    return PROVINCE_MAP.get(key, str(p).strip().title())


def _parse_mixed_date(value):
    if pd.isna(value) or str(value).strip() == "":
        return pd.NaT
    s = str(value).strip()
    for fmt in DATE_FORMATS:
        try:
            return pd.to_datetime(s, format=fmt)
        except (ValueError, TypeError):
            continue
    return pd.NaT


def _clean_customers(customers: pd.DataFrame) -> pd.DataFrame:
    df = customers.copy()
    df = df.drop_duplicates(subset="customer_id", keep="last")
    df["province"] = df["province"].apply(_std_province)
    df["email"] = df["email"].fillna("").astype(str).str.strip()
    df.loc[df["email"] == "", "email"] = "unknown@example.com"
    df["name"] = df["name"].fillna("Unknown").astype(str).str.strip()
    return df.reset_index(drop=True)


def _clean_products(products: pd.DataFrame) -> pd.DataFrame:
    df = products.copy()
    df = df.rename(columns={"category.name": "category", "pricing.price": "price"})
    # some prices are strings with thousands separators, e.g. "1,299.00"
    df["price"] = df["price"].astype(str).str.replace(",", "", regex=False)
    df["price"] = pd.to_numeric(df["price"], errors="coerce")
    df["category"] = df["category"].fillna("Unknown")
    df.loc[df["category"].astype(str).str.strip() == "", "category"] = "Unknown"
    return df[["product_id", "product_name", "category", "price"]].reset_index(drop=True)


def _clean_orders(orders: pd.DataFrame):
    df = orders.copy()

    dup_mask = df.duplicated(subset="order_id", keep="first")
    dup_rows = df[dup_mask].copy()
    dup_rows["reject_reason"] = "duplicate_order_id"
    df = df[~dup_mask].copy()

    df["status"] = df["status"].astype(str).str.strip().str.lower()
    df["order_date"] = df["order_date"].apply(_parse_mixed_date)
    df["qty"] = pd.to_numeric(df["qty"], errors="coerce")
    df["unit_price"] = pd.to_numeric(df["unit_price"], errors="coerce")
    df["discount_pct"] = pd.to_numeric(df["discount_pct"], errors="coerce")

    reasons = []
    for _, row in df.iterrows():
        r = []
        if pd.isna(row["qty"]) or row["qty"] <= 0:
            r.append("qty<=0")
        if pd.isna(row["unit_price"]) or row["unit_price"] <= 0:
            r.append("unit_price<=0")
        if pd.isna(row["discount_pct"]) or row["discount_pct"] < 0 or row["discount_pct"] > 100:
            r.append("discount_pct_out_of_range")
        if pd.isna(row["order_date"]):
            r.append("invalid_date")
        reasons.append(";".join(r))
    df["reject_reason"] = reasons

    rule_rejects = df[df["reject_reason"] != ""].copy()
    clean = df[df["reject_reason"] == ""].copy()

    return clean.reset_index(drop=True), pd.concat([dup_rows, rule_rejects], ignore_index=True, sort=False)


def transform_data(raw):
    """
    TODO 2 (done)
    Cleans customers/products/orders, merges valid paid/completed orders with
    master data, computes sales_amount, and separates everything that fails
    a rule into `rejects` (with a reject_reason column).
    Returns: clean_customers, clean_products, sales, rejects
    """
    customers = _clean_customers(raw["customers"])
    products = _clean_products(raw["products"])
    clean_orders, order_rejects = _clean_orders(raw["orders"])

    status_reject = clean_orders[~clean_orders["status"].isin(VALID_STATUSES)].copy()
    status_reject["reject_reason"] = "status_not_paid_or_completed"
    clean_orders = clean_orders[clean_orders["status"].isin(VALID_STATUSES)].copy()

    valid_customer_ids = set(customers["customer_id"])
    valid_product_ids = set(products["product_id"])
    orphan_mask = (~clean_orders["customer_id"].isin(valid_customer_ids)) | \
                  (~clean_orders["product_id"].isin(valid_product_ids))
    orphan_rows = clean_orders[orphan_mask].copy()

    def _orphan_reason(row):
        r = []
        if row["customer_id"] not in valid_customer_ids:
            r.append("customer_not_found")
        if row["product_id"] not in valid_product_ids:
            r.append("product_not_found")
        return ";".join(r)

    if len(orphan_rows):
        orphan_rows["reject_reason"] = orphan_rows.apply(_orphan_reason, axis=1)
    clean_orders = clean_orders[~orphan_mask].copy()

    sales = clean_orders.copy()
    sales["gross_amount"] = sales["qty"] * sales["unit_price"]
    sales["discount_amount"] = sales["gross_amount"] * sales["discount_pct"] / 100
    sales["sales_amount"] = (sales["gross_amount"] - sales["discount_amount"]).round(2)
    sales["order_date"] = sales["order_date"].dt.strftime("%Y-%m-%d")
    sales = sales[["order_id", "customer_id", "product_id", "order_date",
                    "qty", "unit_price", "discount_pct", "sales_amount"]].reset_index(drop=True)

    rejects = pd.concat([order_rejects, status_reject, orphan_rows], ignore_index=True, sort=False)

    print(f"[Transform] customers={len(customers)} products={len(products)} "
          f"valid_sales={len(sales)} rejects={len(rejects)} "
          f"total_sales={sales['sales_amount'].sum():.2f}")

    return customers, products, sales, rejects
