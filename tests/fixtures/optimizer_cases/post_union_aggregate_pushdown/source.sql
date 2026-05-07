WITH src AS (
    SELECT category, user_id, amount, 1 AS n_transactions
    FROM db.a
    WHERE ds = 1
    UNION ALL
    SELECT category, user_id, amount, 1 AS n_transactions
    FROM db.b
    WHERE ds = 1
), purchases AS (
    SELECT category,
           CAST(SUM(n_transactions) AS BIGINT) AS n_transactions,
           CAST(SUM(amount * n_transactions) AS BIGINT) AS spends
    FROM src
    GROUP BY category
)
SELECT category, n_transactions, spends FROM purchases
