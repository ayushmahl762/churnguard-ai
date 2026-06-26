"""
engineering.py
--------------
Builds all ML features from cleaned customers + orders tables.
Returns a single feature matrix with churn label.

Feature categories:
  RFM      — recency, frequency, monetary signals
  Behaviour — device, payment, category preferences
  Loyalty  — tenure, tier, newsletter, wishlist
  Risk     — returns, low ratings, days since last purchase
  Composite — engineered combinations
"""

import pandas as pd
import numpy as np
import logging

log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
#  ORDER-LEVEL AGGREGATIONS (customer rollups)
# ─────────────────────────────────────────────────────────────
def aggregate_orders(orders: pd.DataFrame) -> pd.DataFrame:
    """Roll 25K orders up to one row per customer."""
    agg = orders.groupby("customer_id").agg(
        order_count           = ("order_id",                "count"),
        total_order_revenue   = ("total_amount_usd",         "sum"),
        avg_order_value       = ("total_amount_usd",         "mean"),
        avg_session_mins      = ("session_duration_minutes", "mean"),
        avg_pages_viewed      = ("pages_viewed_before_purchase", "mean"),
        total_returns         = ("returned",                 "sum"),
        avg_rating_orders     = ("customer_rating",          "mean"),
        avg_delivery_days     = ("delivery_days",            "mean"),
        pct_discounted_orders = ("is_discounted",            "mean"),
        unique_categories     = ("category",                 "nunique"),
        max_discount_pct      = ("discount_pct",             "max"),
    ).reset_index()
    agg["return_rate"]    = agg["total_returns"] / agg["order_count"].replace(0, 1)
    agg["revenue_per_order"] = agg["total_order_revenue"] / agg["order_count"].replace(0, 1)
    return agg


# ─────────────────────────────────────────────────────────────
#  MAIN FEATURE BUILDER
# ─────────────────────────────────────────────────────────────
def build_features(customers: pd.DataFrame,
                   orders: pd.DataFrame) -> pd.DataFrame:
    """
    Returns feature matrix (X + y) ready for ML pipeline.
    One row per customer. All original columns preserved + engineered ones.
    """
    df = customers.copy()
    order_agg = aggregate_orders(orders)

    # Merge order rollups onto customer table
    df = df.merge(order_agg, on="customer_id", how="left")

    # ── RFM features ──────────────────────────────────────────
    # Recency: days_since_last_purchase already in customers
    # Recency bucket (lower is better)
    df["recency_score"] = pd.cut(
        df["days_since_last_purchase"],
        bins=[-1, 30, 90, 180, 365, 99999],
        labels=[5, 4, 3, 2, 1]
    ).astype(float)

    # Frequency score
    df["frequency_score"] = pd.cut(
        df["total_orders"],
        bins=[-1, 1, 3, 7, 15, 99999],
        labels=[1, 2, 3, 4, 5]
    ).astype(float)

    # Monetary score (spend percentile rank)
    df["monetary_score"] = pd.qcut(
        df["total_spend_usd"].clip(lower=0) + 0.01,
        q=5, labels=[1, 2, 3, 4, 5], duplicates="drop"
    ).astype(float)

    # Composite RFM score
    df["rfm_score"] = (
        df["recency_score"] * 0.35 +
        df["frequency_score"] * 0.35 +
        df["monetary_score"] * 0.30
    )

    # ── Loyalty features ──────────────────────────────────────
    # Customer tenure in months
    df["tenure_months"] = (df["customer_tenure_days"] / 30.44).round(1)

    # Tier ordinal encoding
    tier_map = {"Free": 0, "Silver": 1, "Gold": 2, "Platinum": 3}
    df["tier_rank"] = df["membership_tier"].map(tier_map).fillna(0)

    # Engagement depth: wishlist + newsletter + reviews combo
    df["engagement_score"] = (
        df["newsletter_subscribed"] * 1 +
        (df["wishlist_items"] > 0).astype(int) * 1 +
        (df["reviews_given"] > 0).astype(int) * 1
    )

    # ── Risk features ─────────────────────────────────────────
    # High return rate flag
    df["high_return_flag"] = (df["return_rate"] > 0.20).astype(int)

    # Low satisfaction: avg_review_score < 3
    df["low_satisfaction_flag"] = (df["avg_review_score"] < 3).astype(int)

    # Dormancy flag: no purchase in 180+ days
    df["dormant_flag"] = (df["days_since_last_purchase"] >= 180).astype(int)

    # Premium-but-at-risk: high spender + dormant
    df["high_value_at_risk"] = (
        (df["monetary_score"] >= 4) & (df["dormant_flag"] == 1)
    ).astype(int)

    # ── Composite churn risk score (for dashboard display) ────
    # Business-logic score independent of ML model
    df["churn_risk_score"] = (
        (1 - df["recency_score"] / 5) * 0.30 +
        (1 - df["frequency_score"] / 5) * 0.25 +
        df["high_return_flag"] * 0.20 +
        df["low_satisfaction_flag"] * 0.15 +
        (1 - df["engagement_score"] / 3) * 0.10
    ).round(4)

    # ── Value segmentation ────────────────────────────────────
    conditions = [
        (df["total_spend_usd"] >= df["total_spend_usd"].quantile(0.75)),
        (df["total_spend_usd"] >= df["total_spend_usd"].quantile(0.50)),
        (df["total_spend_usd"] >= df["total_spend_usd"].quantile(0.25)),
    ]
    df["value_segment"] = np.select(conditions,
        ["High Value", "Mid Value", "Low Value"], default="At Risk")

    log.info(f"Feature matrix: {df.shape} | Features created: {df.shape[1] - customers.shape[1]}")
    return df


# ─────────────────────────────────────────────────────────────
#  FEATURE COLUMNS FOR ML
# ─────────────────────────────────────────────────────────────
NUMERIC_FEATURES = [
    "age", "total_orders", "total_spend_usd", "avg_order_value_usd",
    "days_since_last_purchase", "reviews_given", "avg_review_score",
    "returns_made", "wishlist_items", "newsletter_subscribed",
    "customer_tenure_days", "rfm_score", "recency_score",
    "frequency_score", "monetary_score", "tier_rank",
    "engagement_score", "high_return_flag", "low_satisfaction_flag",
    "dormant_flag", "churn_risk_score", "return_rate",
    "avg_session_mins", "avg_pages_viewed", "pct_discounted_orders",
    "unique_categories",
]

CATEGORICAL_FEATURES = [
    "gender", "membership_tier", "preferred_category",
    "preferred_device", "preferred_payment_method",
    "acquisition_channel",
]

TARGET = "churned"
