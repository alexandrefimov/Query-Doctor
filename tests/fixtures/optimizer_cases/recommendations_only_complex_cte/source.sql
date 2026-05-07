WITH
  cte_1 AS (SELECT id, ds FROM db.source_table WHERE ds = 20260503),
  cte_2 AS (SELECT id, ds FROM cte_1 WHERE id > 0),
  cte_3 AS (SELECT id, ds FROM cte_2 WHERE ds = 20260503),
  cte_4 AS (SELECT id, ds FROM cte_3 WHERE id > 10),
  cte_5 AS (SELECT id, ds FROM cte_4 WHERE ds = 20260503),
  cte_6 AS (SELECT id, ds FROM cte_5 WHERE id > 20)
SELECT id, ds FROM cte_6 WHERE ds = 20260503
