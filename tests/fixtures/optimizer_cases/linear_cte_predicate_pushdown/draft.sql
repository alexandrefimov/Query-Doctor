WITH
  cte_1 AS (SELECT id, ds, payload FROM db.source_table WHERE ds = 20260503),
  cte_2 AS (SELECT id, ds, payload FROM cte_1),
  cte_3 AS (SELECT id, ds, payload FROM cte_2),
  cte_4 AS (SELECT id, ds, payload FROM cte_3),
  cte_5 AS (SELECT id, ds, payload FROM cte_4),
  cte_6 AS (SELECT id, ds, payload FROM cte_5)
SELECT id, payload FROM cte_6 WHERE ds = 20260503 AND id > 10
