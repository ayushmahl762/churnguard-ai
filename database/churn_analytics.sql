-- ============================================================
-- ChurnGuard AI — SQL Query Library
-- Database: database/churnguard.db  (SQLite)
-- Tables: customers, orders, monthly_revenue, product_summary,
--         churn_predictions, shap_importance
-- ============================================================


-- ── 1. EXECUTIVE KPIs ────────────────────────────────────────
-- Business: Headline numbers for the board / VP report
SELECT * FROM v_executive_kpis;


-- ── 2. CHURN BY MEMBERSHIP TIER ──────────────────────────────
-- Business: Which tier has the worst retention? Where to invest?
SELECT * FROM v_churn_by_tier;
-- Expected: Gold/Platinum churn = high-value risk; Free = volume risk


-- ── 3. CHURN BY ACQUISITION CHANNEL ─────────────────────────
-- Business: Which marketing channels attract loyal vs transient customers?
SELECT * FROM v_churn_by_channel;
-- Actionable: Cut spend on high-churn channels; reinvest in low-churn


-- ── 4. HIGH-VALUE AT-RISK CUSTOMERS ─────────────────────────
-- Business: Who should the retention team contact this week?
SELECT
    c.customer_id,
    c.country,
    c.age,
    c.membership_tier,
    c.total_spend_usd,
    c.days_since_last_purchase,
    c.avg_review_score,
    c.returns_made,
    c.acquisition_channel,
    p.churn_probability,
    p.risk_tier
FROM customers c
JOIN churn_predictions p ON c.customer_id = p.customer_id
WHERE p.risk_tier = 'HIGH'
  AND c.total_spend_usd > (SELECT AVG(total_spend_usd) FROM customers)
ORDER BY p.churn_probability DESC, c.total_spend_usd DESC
LIMIT 100;


-- ── 5. REVENUE TREND (MOM) ───────────────────────────────────
-- Business: Is the business growing or shrinking? When did it peak?
SELECT
    period_label,
    revenue_usd,
    unique_customers,
    new_customers,
    return_rate_pct,
    mom_growth_pct,
    ROUND(revenue_usd / unique_customers, 2) AS arpu
FROM v_revenue_trend
ORDER BY period_label;


-- ── 6. CATEGORY PERFORMANCE ──────────────────────────────────
-- Business: Which categories drive revenue, ratings, and returns?
SELECT
    category,
    COUNT(*)                                   AS total_orders,
    ROUND(SUM(total_amount_usd), 0)            AS total_revenue,
    ROUND(AVG(total_amount_usd), 2)            AS avg_order_value,
    ROUND(AVG(customer_rating), 2)             AS avg_rating,
    ROUND(AVG(returned)*100, 1)                AS return_rate_pct,
    ROUND(AVG(discount_pct), 1)                AS avg_discount_pct,
    ROUND(AVG(delivery_days), 1)               AS avg_delivery_days
FROM orders
GROUP BY category
ORDER BY total_revenue DESC;


-- ── 7. ORDER STATUS FUNNEL ────────────────────────────────────
-- Business: How many orders are lost to returns/cancellations?
SELECT
    order_status,
    COUNT(*)                               AS orders,
    ROUND(COUNT(*)*100.0 / SUM(COUNT(*)) OVER(), 1) AS pct_of_total,
    ROUND(SUM(total_amount_usd), 0)        AS total_value
FROM orders
GROUP BY order_status
ORDER BY orders DESC;


-- ── 8. DEVICE vs PAYMENT METHOD CHURN MATRIX ─────────────────
-- Business: Which device+payment combos correlate with churn?
SELECT
    c.preferred_device,
    c.preferred_payment_method,
    COUNT(*)                    AS customers,
    ROUND(AVG(c.churned)*100, 1) AS churn_rate_pct,
    ROUND(AVG(c.total_spend_usd), 0) AS avg_spend
FROM customers c
GROUP BY c.preferred_device, c.preferred_payment_method
ORDER BY churn_rate_pct DESC;


-- ── 9. TENURE COHORT ANALYSIS ────────────────────────────────
-- Business: When in the customer lifecycle does churn peak?
SELECT
    CASE
        WHEN julianday('2026-04-01') - julianday(registration_date) <= 90  THEN '0-3 months'
        WHEN julianday('2026-04-01') - julianday(registration_date) <= 365 THEN '3-12 months'
        WHEN julianday('2026-04-01') - julianday(registration_date) <= 730 THEN '1-2 years'
        ELSE '2+ years'
    END AS tenure_cohort,
    COUNT(*)                     AS customers,
    ROUND(AVG(churned)*100, 1)   AS churn_rate_pct,
    ROUND(AVG(total_spend_usd), 0) AS avg_ltv
FROM customers
GROUP BY 1
ORDER BY MIN(julianday('2026-04-01') - julianday(registration_date));


-- ── 10. PRODUCT PERFORMANCE QUADRANT ─────────────────────────
-- Business: High revenue + high return = product quality issue
SELECT
    product_name,
    category,
    total_orders,
    ROUND(total_revenue_usd, 0) AS revenue,
    avg_rating,
    return_rate,
    CASE
        WHEN total_revenue_usd > (SELECT AVG(total_revenue_usd) FROM product_summary)
             AND return_rate > (SELECT AVG(return_rate) FROM product_summary)
        THEN 'High Revenue / High Return — Fix Quality'
        WHEN total_revenue_usd > (SELECT AVG(total_revenue_usd) FROM product_summary)
             AND return_rate <= (SELECT AVG(return_rate) FROM product_summary)
        THEN 'Star Product — Promote'
        WHEN total_revenue_usd <= (SELECT AVG(total_revenue_usd) FROM product_summary)
             AND return_rate > (SELECT AVG(return_rate) FROM product_summary)
        THEN 'Low Revenue / High Return — Review or Discontinue'
        ELSE 'Low Revenue / Low Return — Grow or Phase Out'
    END AS product_quadrant
FROM product_summary
ORDER BY revenue DESC;


-- ── 11. SHAP TOP DRIVERS ─────────────────────────────────────
-- Business: Which customer behaviors most predict churn?
SELECT feature, ROUND(mean_abs_shap, 4) AS importance
FROM shap_importance
ORDER BY mean_abs_shap DESC
LIMIT 15;


-- ── 12. RISK TIER REVENUE SUMMARY ────────────────────────────
-- Business: How much revenue is actually at risk by tier?
SELECT
    p.risk_tier,
    COUNT(*)                                  AS customers,
    ROUND(AVG(c.total_spend_usd), 0)          AS avg_ltv,
    ROUND(SUM(c.total_spend_usd), 0)          AS total_at_risk_usd,
    ROUND(AVG(p.churn_probability)*100, 1)    AS avg_churn_prob_pct
FROM churn_predictions p
JOIN customers c ON p.customer_id = c.customer_id
GROUP BY p.risk_tier
ORDER BY avg_churn_prob_pct DESC;
