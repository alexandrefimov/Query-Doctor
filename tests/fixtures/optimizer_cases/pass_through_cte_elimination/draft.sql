WITH base AS (
SELECT id, ds, payload
  FROM db.source_table
)
SELECT id, payload
FROM base
