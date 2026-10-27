-- Weeks run Monday–Sunday. Only complete weeks are used (current week excluded).
-- Must stay in sync with the weekly definition, segments and tenure buckets
-- in transition_query.sql and segments.py.
--
-- Segments:
--   promo_2m_free : earliest-paid order has a free 2-month subscription SKU
--   standard      : everything else

WITH first_tx AS (
  -- one row per merchant: week of first settlement
  SELECT
    nmid,
    DATE_TRUNC(MIN(first_settlement_date), WEEK(MONDAY)) AS first_week_start
  FROM `retail_payment_base.retail_order_delivery_funnel`
  WHERE first_settlement_date IS NOT NULL
  GROUP BY nmid
),

merchant_segment AS (
  -- segment is decided by the merchant's earliest-paid order
  SELECT
    nmid,
    IF(
      ARRAY_AGG(
        COALESCE(REGEXP_CONTAINS(product_sku, r'2months-free'), FALSE)
        ORDER BY paid_date IS NULL, paid_date
        LIMIT 1
      )[OFFSET(0)],
      'promo_2m_free',
      'standard'
    ) AS segment
  FROM `retail_payment_base.retail_order_delivery_funnel`
  WHERE first_settlement_date IS NOT NULL
  GROUP BY nmid
),

weekly_activity AS (
  -- distinct settlement days per merchant per week (0–7)
  SELECT
    nmid,
    DATE_TRUNC(settlement_date, WEEK(MONDAY)) AS week_start,
    COUNT(DISTINCT settlement_date)           AS transaction_days
  FROM `retail_payment_base.retail_transaction_data`
  WHERE settlement_date IS NOT NULL
  GROUP BY nmid, week_start
),

week_spine AS (
  -- every complete week from first settlement week onward, so inactive weeks
  -- show up as transaction_days = 0 (tier 0) instead of missing rows
  SELECT
    f.nmid,
    f.first_week_start,
    week_start
  FROM first_tx f,
  UNNEST(GENERATE_DATE_ARRAY(
    f.first_week_start,
    DATE_SUB(DATE_TRUNC(CURRENT_DATE('Asia/Jakarta'), WEEK(MONDAY)), INTERVAL 1 WEEK),
    INTERVAL 1 WEEK
  )) AS week_start
),

base AS (
  SELECT
    s.nmid,
    m.segment,
    s.week_start,
    DATE_DIFF(s.week_start, s.first_week_start, WEEK(MONDAY)) AS weeks_since_first_tx,
    COALESCE(a.transaction_days, 0)                           AS transaction_days
  FROM week_spine s
  JOIN merchant_segment m
    ON m.nmid = s.nmid
  LEFT JOIN weekly_activity a
    ON a.nmid = s.nmid
   AND a.week_start = s.week_start
),

ranked AS (
  SELECT
    nmid,
    segment,
    week_start,
    weeks_since_first_tx,
    transaction_days,
    ROW_NUMBER() OVER (PARTITION BY nmid ORDER BY week_start DESC) AS rn
  FROM base
  WHERE weeks_since_first_tx >= 2  -- need at least 2 weeks of history
),

latest_two AS (
  -- get current week (rn=1) and previous week (rn=2) per merchant
  SELECT
    nmid,
    ANY_VALUE(segment)                                  AS segment,
    MAX(CASE WHEN rn = 1 THEN week_start END)          AS latest_week_start,
    MAX(CASE WHEN rn = 1 THEN weeks_since_first_tx END) AS weeks_since_first_tx,
    MAX(CASE WHEN rn = 1 THEN transaction_days END)     AS current_transaction_days,
    MAX(CASE WHEN rn = 2 THEN transaction_days END)     AS prev_transaction_days
  FROM ranked
  WHERE rn <= 2
  GROUP BY nmid
  HAVING MAX(CASE WHEN rn = 2 THEN transaction_days END) IS NOT NULL  -- must have a prev week
),

scored AS (
  SELECT
    nmid,
    segment,
    latest_week_start,
    weeks_since_first_tx,
    current_transaction_days,
    prev_transaction_days,

    -- current tier
    CASE
      WHEN current_transaction_days = 0             THEN 0
      WHEN current_transaction_days BETWEEN 1 AND 2 THEN 1
      WHEN current_transaction_days BETWEEN 3 AND 4 THEN 2
      WHEN current_transaction_days BETWEEN 5 AND 6 THEN 3
      WHEN current_transaction_days = 7             THEN 4
    END AS current_tier,

    -- previous tier
    CASE
      WHEN prev_transaction_days = 0             THEN 0
      WHEN prev_transaction_days BETWEEN 1 AND 2 THEN 1
      WHEN prev_transaction_days BETWEEN 3 AND 4 THEN 2
      WHEN prev_transaction_days BETWEEN 5 AND 6 THEN 3
      WHEN prev_transaction_days = 7             THEN 4
    END AS prev_tier,

    -- tenure bucket (per segment)
    CASE segment
      WHEN 'promo_2m_free' THEN
        CASE
          WHEN weeks_since_first_tx BETWEEN 0  AND 1  THEN 'new_user'
          WHEN weeks_since_first_tx BETWEEN 2  AND 7  THEN 'promo_free_period'
          WHEN weeks_since_first_tx BETWEEN 8  AND 12 THEN 'promo_post_free_early'
          WHEN weeks_since_first_tx >= 13             THEN 'promo_post_free'
        END
      ELSE
        CASE
          WHEN weeks_since_first_tx BETWEEN 0  AND 1  THEN 'new_user'
          WHEN weeks_since_first_tx BETWEEN 2  AND 4  THEN 'standard_early'
          WHEN weeks_since_first_tx BETWEEN 5  AND 9  THEN 'standard_growing'
          WHEN weeks_since_first_tx BETWEEN 10 AND 19 THEN 'standard_mature'
          WHEN weeks_since_first_tx >= 20             THEN 'standard_veteran'
        END
    END AS tenure_bucket

  FROM latest_two
)

SELECT
  nmid,
  segment,
  latest_week_start,
  weeks_since_first_tx,
  current_transaction_days,
  prev_transaction_days,
  current_tier,
  prev_tier,
  tenure_bucket
FROM scored
ORDER BY nmid
