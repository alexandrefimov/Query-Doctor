WITH base AS (
  SELECT user_id, ds, bytes_sent
  FROM example_events.fact_events
), filtered AS (
  SELECT user_id, ds, bytes_sent
  FROM base
  WHERE lower(ds) = '20260503'
)
SELECT user_id, bytes_sent
FROM filtered
