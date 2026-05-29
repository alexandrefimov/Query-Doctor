WITH events AS (
  SELECT user_id, ds, payload
  FROM db.events_a
  UNION ALL
  SELECT user_id, ds, payload
  FROM db.events_b
)
SELECT user_id, payload
FROM events
WHERE ds = 20260503
