WITH src AS (
    SELECT category,
           CAST(SUM(1) AS BIGINT) AS n_transactions,
           CAST(SUM(amount * 1) AS BIGINT) AS spends
    FROM db.a
    WHERE ds = 1
    GROUP BY category
    UNION ALL
    SELECT category,
           CAST(SUM(1) AS BIGINT) AS n_transactions,
           CAST(SUM(amount * 1) AS BIGINT) AS spends
    FROM db.b
    WHERE ds = 1
    GROUP BY category
), purchases AS (
    SELECT category,
           CAST(SUM(n_transactions) AS BIGINT) AS n_transactions,
           CAST(SUM(spends) AS BIGINT) AS spends
    FROM src
    GROUP BY category
)
SELECT category, n_transactions, spends FROM purchases;
