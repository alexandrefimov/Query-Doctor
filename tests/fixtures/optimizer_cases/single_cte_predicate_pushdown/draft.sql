WITH base AS (
  SELECT id, ds, payload
  FROM db.source_table
  WHERE ds = 20260503
)
SELECT id, payload
FROM base
WHERE ds = 20260503
