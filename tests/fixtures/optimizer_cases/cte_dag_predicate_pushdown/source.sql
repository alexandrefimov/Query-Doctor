WITH
  cte_1 AS (SELECT id, ds, payload FROM db.source_a),
  cte_2 AS (SELECT id, ds, metric FROM db.source_b),
  cte_3 AS (SELECT cte_1.id, cte_1.ds, cte_1.payload, cte_2.metric FROM cte_1 JOIN cte_2 ON cte_1.id = cte_2.id),
  cte_4 AS (SELECT id, ds, payload FROM cte_3),
  cte_5 AS (SELECT id, ds, metric FROM cte_3),
  cte_6 AS (SELECT id, ds, SUM(metric) AS metric_sum FROM db.source_c GROUP BY id, ds),
  cte_7 AS (
    SELECT id, ds, payload AS value FROM cte_4
    UNION ALL
    SELECT cte_5.id, cte_5.ds, CAST(cte_6.metric_sum AS STRING) AS value FROM cte_5 JOIN cte_6 ON cte_5.id = cte_6.id
  )
SELECT id, value FROM cte_7 WHERE ds = 20260503
