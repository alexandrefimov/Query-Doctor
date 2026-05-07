WITH raw AS (
    SELECT category, user_id, price, event_ts, 1 AS n_transactions
    FROM db.a
    WHERE ds = 1
    UNION ALL
    SELECT category, user_id, price, event_ts, 1 AS n_transactions
    FROM db.b
    WHERE ds = 1
)
SELECT category,
       price,
       COUNT(DISTINCT user_id) AS n_buyers,
       CAST(SUM(n_transactions) AS BIGINT) AS n_transactions,
       CAST(SUM(price * n_transactions) AS BIGINT) AS spends
FROM raw
GROUP BY category, price
