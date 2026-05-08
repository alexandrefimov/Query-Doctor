SELECT q.id, q.payload
FROM (
  SELECT id, ds, payload
  FROM db.source_table
  WHERE ds = 20260503
) q
WHERE q.ds = 20260503
