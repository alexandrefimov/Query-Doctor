WITH events AS (
SELECT user_id, ds, payload
  FROM db.events_a
WHERE ds = 20260503
    UNION ALL
SELECT user_id, ds, payload
  FROM db.events_b
WHERE ds = 20260503
)
SELECT user_id, payload
FROM events
WHERE ds = 20260503
