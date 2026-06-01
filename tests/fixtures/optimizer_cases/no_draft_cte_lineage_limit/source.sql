WITH base AS (
  SELECT user_id, ds, bytes_sent
  FROM example_events.fact_events
), left_branch AS (
  SELECT user_id + 0 AS user_id, ds + 0 AS ds, bytes_sent + 0 AS bytes_sent
  FROM base
), right_branch AS (
  SELECT user_id + 1 AS user_id, ds + 0 AS ds, bytes_sent + 0 AS bytes_sent
  FROM base
), unioned AS (
  SELECT user_id, ds, bytes_sent FROM left_branch
  UNION ALL
  SELECT user_id, ds, bytes_sent FROM right_branch
)
SELECT user_id, bytes_sent
FROM unioned
WHERE ds = 20260503
