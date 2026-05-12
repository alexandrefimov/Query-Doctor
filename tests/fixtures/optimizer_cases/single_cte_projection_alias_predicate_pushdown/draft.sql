WITH base AS (
  SELECT user_id, event_day AS ds, bytes_sent
  FROM db.fact_events
  WHERE event_day = 20260503
)
SELECT user_id, bytes_sent
FROM base
WHERE ds = 20260503
