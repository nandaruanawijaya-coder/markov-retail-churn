WITH ranked AS (
  SELECT
    nmid,
    week_start,
    weeks_since_first_tx,
    transaction_days,
    ROW_NUMBER() OVER (PARTITION BY nmid ORDER BY week_start DESC) AS rn
  FROM `temp_amal.retail_weekly_rfm`
  WHERE weeks_since_first_tx >= 2  -- need at least 2 weeks of history
),

latest_two AS (
  -- get current week (rn=1) and previous week (rn=2) per merchant
  SELECT
    nmid,
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

    -- tenure bucket
    CASE
      WHEN weeks_since_first_tx BETWEEN 0  AND 1  THEN 'new_user'
      WHEN weeks_since_first_tx BETWEEN 2  AND 4  THEN 'early'
      WHEN weeks_since_first_tx BETWEEN 5  AND 12 THEN 'growing'
      WHEN weeks_since_first_tx >= 13             THEN 'mature'
      -- WHEN weeks_since_first_tx BETWEEN 13 AND 26 THEN 'mature'
      -- WHEN weeks_since_first_tx >= 27             THEN 'veteran'
    END AS tenure_bucket

  FROM latest_two
)

SELECT
  nmid,
  latest_week_start,
  weeks_since_first_tx,
  current_transaction_days,
  prev_transaction_days,
  current_tier,
  prev_tier,
  tenure_bucket
FROM scored
ORDER BY nmid