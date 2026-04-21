WITH base AS (
  SELECT
    nmid,
    week_start,
    weeks_since_first_tx,
    transaction_days
  FROM `temp_amal.retail_weekly_rfm`
  WHERE weeks_since_first_tx >= 2
),

with_lags AS (
  SELECT
    nmid,
    week_start,
    weeks_since_first_tx,
    transaction_days,

    LAG(transaction_days, 1) OVER (PARTITION BY nmid ORDER BY week_start) AS prev_transaction_days,
    LEAD(transaction_days, 1) OVER (PARTITION BY nmid ORDER BY week_start) AS next_transaction_days
  FROM base
),

tiered AS (
  SELECT
    nmid,
    week_start,
    weeks_since_first_tx,

    -- current tier (week T)
    CASE
      WHEN transaction_days = 0             THEN 0
      WHEN transaction_days BETWEEN 1 AND 2 THEN 1
      WHEN transaction_days BETWEEN 3 AND 4 THEN 2
      WHEN transaction_days BETWEEN 5 AND 6 THEN 3
      WHEN transaction_days = 7             THEN 4
    END AS current_tier,

    -- previous tier (week T-1)
    CASE
      WHEN prev_transaction_days IS NULL            THEN NULL
      WHEN prev_transaction_days = 0                THEN 0
      WHEN prev_transaction_days BETWEEN 1 AND 2    THEN 1
      WHEN prev_transaction_days BETWEEN 3 AND 4    THEN 2
      WHEN prev_transaction_days BETWEEN 5 AND 6    THEN 3
      WHEN prev_transaction_days = 7                THEN 4
    END AS prev_tier,

    -- next tier (week T+1) — what we're predicting
    CASE
      WHEN next_transaction_days IS NULL            THEN NULL
      WHEN next_transaction_days = 0                THEN 0
      WHEN next_transaction_days BETWEEN 1 AND 2    THEN 1
      WHEN next_transaction_days BETWEEN 3 AND 4    THEN 2
      WHEN next_transaction_days BETWEEN 5 AND 6    THEN 3
      WHEN next_transaction_days = 7                THEN 4
    END AS next_tier

  FROM with_lags
  WHERE prev_transaction_days IS NOT NULL
    AND next_transaction_days IS NOT NULL
),

tenure_bucketed AS (
  SELECT
    *,
    CASE
      WHEN weeks_since_first_tx BETWEEN 2  AND 4  THEN 'early'
      WHEN weeks_since_first_tx BETWEEN 5  AND 12 THEN 'growing'
      WHEN weeks_since_first_tx >= 13             THEN 'mature'
      -- WHEN weeks_since_first_tx BETWEEN 13 AND 26 THEN 'mature'
      -- WHEN weeks_since_first_tx >= 27             THEN 'veteran'
    END AS tenure_bucket
  FROM tiered
  WHERE prev_tier  IS NOT NULL
    AND next_tier  IS NOT NULL
)

SELECT
  tenure_bucket,
  prev_tier,
  current_tier,
  next_tier,
  COUNT(*) AS transition_count
FROM tenure_bucketed
WHERE tenure_bucket IS NOT NULL
GROUP BY tenure_bucket, prev_tier, current_tier, next_tier
ORDER BY tenure_bucket, prev_tier, current_tier, next_tier