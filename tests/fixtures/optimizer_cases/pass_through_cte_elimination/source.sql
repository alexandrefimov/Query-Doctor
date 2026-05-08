WITH base AS (
  SELECT id, ds, payload
  FROM db.source_table
),
pass_through AS (
  SELECT id, ds, payload
  FROM base
)
SELECT id, payload
FROM pass_through
