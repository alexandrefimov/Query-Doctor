WITH
  cte_1 AS (SELECT id, ds FROM db.source_a WHERE ds = 20260503),
  cte_2 AS (SELECT id, ds FROM db.source_b WHERE ds = 20260503),
  cte_3 AS (SELECT cte_1.id, cte_1.ds FROM cte_1 JOIN cte_2 ON cte_1.id = cte_2.id),
  cte_4 AS (SELECT id, ds FROM cte_3 WHERE id > 10),
  cte_5 AS (SELECT id, ds FROM cte_3 WHERE ds = 20260503),
  cte_6 AS (SELECT id, ds FROM db.unused_source WHERE ds = 20260503),
  cte_7 AS (SELECT cte_4.id, cte_4.ds FROM cte_4 JOIN cte_5 ON cte_4.id = cte_5.id)
SELECT id, ds FROM cte_7 WHERE ds = 20260503
