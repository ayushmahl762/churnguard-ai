"""
preprocessor.py
---------------
Loads, validates, and cleans all 4 source tables.
Outputs analysis-ready DataFrames and a unified SQLite database.

Tables handled:
  customers.csv       → 8,000 rows, 20 cols, churn label included
  orders.csv          → 25,000 rows, 28 cols, 15,749 null customer_ratings
  monthly_revenue.csv → 75 rows, 10 cols (Jan 2020 – Mar 2026)
  product_summary.csv → 140 rows, 9 cols
"""

import pandas as pd
import numpy as np
import sqlite3
import os
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
log = logging.getLogger(__name__)

RAW_DIR   = Path("data/raw")
PROC_DIR  = Path("data/processed")
DB_PATH   = Path("database/churnguard.db")


# ─────────────────────────────────────────────────────────────
#  LOAD
# ─────────────────────────────────────────────────────────────
def load_all() -> dict[str, pd.DataFrame]:
    tables = {
        "customers":       "customers.csv",
        "orders":          "orders.csv",
        "monthly_revenue": "monthly_revenue.csv",
        "product_summary": "product_summary.csv",
    }
    data = {}
    for name, fname in tables.items():
        path = RAW_DIR / fname
        df = pd.read_csv(path)
        log.info(f"Loaded {name}: {df.shape}")
        data[name] = df
    return data


# ─────────────────────────────────────────────────────────────
#  CLEAN CUSTOMERS
# ─────────────────────────────────────────────────────────────
def clean_customers(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # Date parsing
    df["registration_date"] = pd.to_datetime(df["registration_date"], errors="coerce")

    # Days as customer (tenure proxy)
    snapshot = pd.Timestamp("2026-04-01")
    df["customer_tenure_days"] = (snapshot - df["registration_date"]).dt.days

    # Sanity bounds
    df = df[df["age"].between(16, 100)]
    df = df[df["total_orders"] >= 0]
    df = df[df["total_spend_usd"] >= 0]
    df = df[df["avg_review_score"].between(0, 5)]

    # avg_review_score of 0 where reviews_given==0 → fill NaN so it doesn't skew
    df.loc[df["reviews_given"] == 0, "avg_review_score"] = np.nan

    # Standardise string cols
    for col in ["membership_tier", "gender", "preferred_category",
                "preferred_device", "preferred_payment_method",
                "acquisition_channel", "country"]:
        df[col] = df[col].str.strip().str.title()

    log.info(f"Customers clean: {df.shape} | Churn rate: {df['churned'].mean()*100:.1f}%")
    return df.reset_index(drop=True)


# ─────────────────────────────────────────────────────────────
#  CLEAN ORDERS
# ─────────────────────────────────────────────────────────────
def clean_orders(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # Dates
    df["order_date"]    = pd.to_datetime(df["order_date"],    errors="coerce")
    df["delivery_date"] = pd.to_datetime(df["delivery_date"], errors="coerce")

    # customer_rating: 15,749 nulls — fill with per-category median
    # (orders without a rating simply weren't reviewed, not random missingness)
    cat_median = df.groupby("category")["customer_rating"].transform("median")
    df["customer_rating"] = df["customer_rating"].fillna(cat_median)
    # any remaining nulls (category with all nulls) → global median
    df["customer_rating"] = df["customer_rating"].fillna(df["customer_rating"].median())

    # Flag the imputed rows for transparency
    df["rating_imputed"] = df["customer_rating"].isna().astype(int)

    # Derived
    df["order_month_label"] = df["order_date"].dt.to_period("M").astype(str)
    df["is_discounted"]     = (df["discount_pct"] > 0).astype(int)
    df["is_returned"]       = df["returned"]

    log.info(f"Orders clean: {df.shape} | Return rate: {df['returned'].mean()*100:.1f}%")
    return df.reset_index(drop=True)


# ─────────────────────────────────────────────────────────────
#  CLEAN MONTHLY REVENUE
# ─────────────────────────────────────────────────────────────
def clean_monthly_revenue(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["period_label"] = df["year"].astype(str) + "-" + df["month"].astype(str).str.zfill(2)
    df["revenue_mom_pct"] = df["revenue_usd"].pct_change() * 100
    log.info(f"Monthly revenue clean: {df.shape}")
    return df.reset_index(drop=True)


# ─────────────────────────────────────────────────────────────
#  SAVE & DATABASE
# ─────────────────────────────────────────────────────────────
def save_processed(data: dict[str, pd.DataFrame]) -> None:
    PROC_DIR.mkdir(parents=True, exist_ok=True)
    for name, df in data.items():
        path = PROC_DIR / f"{name}_clean.csv"
        df.to_csv(path, index=False)
        log.info(f"Saved → {path}")


def build_sqlite(data: dict[str, pd.DataFrame], db_path: Path = DB_PATH) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)

    for name, df in data.items():
        df.to_sql(name, conn, if_exists="replace", index=False)
        log.info(f"SQLite table '{name}': {len(df):,} rows")

    # ── Business views ───────────────────────────────────────
    conn.executescript("""
    DROP VIEW IF EXISTS v_executive_kpis;
    CREATE VIEW v_executive_kpis AS
    SELECT
        COUNT(*)                                     AS total_customers,
        SUM(churned)                                 AS total_churned,
        ROUND(AVG(churned)*100, 2)                   AS churn_rate_pct,
        ROUND(AVG(total_spend_usd), 2)               AS avg_ltv_usd,
        ROUND(SUM(CASE WHEN churned=1 THEN total_spend_usd END), 2) AS lost_revenue_usd,
        ROUND(SUM(CASE WHEN churned=0 THEN total_spend_usd END), 2) AS retained_revenue_usd
    FROM customers;

    DROP VIEW IF EXISTS v_churn_by_tier;
    CREATE VIEW v_churn_by_tier AS
    SELECT
        membership_tier,
        COUNT(*)                    AS customers,
        SUM(churned)                AS churned,
        ROUND(AVG(churned)*100, 2)  AS churn_rate_pct,
        ROUND(AVG(total_spend_usd), 2) AS avg_ltv_usd
    FROM customers
    GROUP BY membership_tier
    ORDER BY churn_rate_pct DESC;

    DROP VIEW IF EXISTS v_churn_by_channel;
    CREATE VIEW v_churn_by_channel AS
    SELECT
        acquisition_channel,
        COUNT(*)                    AS customers,
        ROUND(AVG(churned)*100, 2)  AS churn_rate_pct,
        ROUND(AVG(total_spend_usd), 2) AS avg_ltv_usd
    FROM customers
    GROUP BY acquisition_channel
    ORDER BY churn_rate_pct DESC;

    DROP VIEW IF EXISTS v_revenue_trend;
    CREATE VIEW v_revenue_trend AS
    SELECT
        year, month, quarter, revenue_usd,
        unique_customers, new_customers,
        ROUND(return_rate*100, 2) AS return_rate_pct,
        period_label,
        ROUND(revenue_mom_pct, 2) AS mom_growth_pct
    FROM monthly_revenue;
    """)
    conn.commit()
    conn.close()
    log.info(f"SQLite database built → {db_path}")


# ─────────────────────────────────────────────────────────────
#  PIPELINE ENTRY POINT
# ─────────────────────────────────────────────────────────────
def run() -> dict[str, pd.DataFrame]:
    raw  = load_all()
    clean = {
        "customers":       clean_customers(raw["customers"]),
        "orders":          clean_orders(raw["orders"]),
        "monthly_revenue": clean_monthly_revenue(raw["monthly_revenue"]),
        "product_summary": raw["product_summary"].copy(),
    }
    save_processed(clean)
    build_sqlite(clean)
    log.info("✅ Preprocessing complete.")
    return clean


if __name__ == "__main__":
    run()
