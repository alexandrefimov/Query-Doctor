SELECT q.id, q.payload
FROM (
  SELECT id, event_day AS ds, payload
  FROM db.source_table
) q
WHERE q.ds = 20260503
