WITH src AS (
  SELECT category, amount FROM db.source_a WHERE ds = 1
  UNION ALL
  SELECT category, amount FROM db.source_b WHERE ds = 1
), purchases AS (
  SELECT category, AVG(amount) AS avg_amount
  FROM src
  GROUP BY category
)
SELECT category, avg_amount FROM purchases
