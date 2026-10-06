
SOLUTIONS = {
"1. How much history?": """SELECT COUNT(*) AS trading_days,
       MIN(date) AS first_day,
       MAX(date) AS last_day
FROM bajaj_auto;""",

"2. Eicher's five best closes": """SELECT date, close_price
FROM eicher_motors
ORDER BY close_price DESC
LIMIT 5;""",

"3. TCS, year by year": """SELECT strftime('%Y', date) AS year,
       ROUND(AVG(close_price), 2) AS avg_close
FROM tcs
GROUP BY year
ORDER BY year;""",

"4. Find the holes": """SELECT 'bajaj_auto' AS stock, date FROM bajaj_auto WHERE deliverable_qty IS NULL
UNION ALL
SELECT 'eicher_motors', date FROM eicher_motors WHERE deliverable_qty IS NULL
UNION ALL
SELECT 'hero_motocorp', date FROM hero_motocorp WHERE deliverable_qty IS NULL
UNION ALL
SELECT 'infosys', date FROM infosys WHERE deliverable_qty IS NULL
UNION ALL
SELECT 'tcs', date FROM tcs WHERE deliverable_qty IS NULL
UNION ALL
SELECT 'tvs_motors', date FROM tvs_motors WHERE deliverable_qty IS NULL;""",

"5. Moving averages (bajaj1)": """DROP TABLE IF EXISTS bajaj1;
CREATE TABLE bajaj1 AS
SELECT date, close_price,
  CASE WHEN ROW_NUMBER() OVER (ORDER BY date) >= 20
       THEN ROUND(AVG(close_price) OVER (ORDER BY date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW), 2)
  END AS ma20,
  CASE WHEN ROW_NUMBER() OVER (ORDER BY date) >= 50
       THEN ROUND(AVG(close_price) OVER (ORDER BY date ROWS BETWEEN 49 PRECEDING AND CURRENT ROW), 2)
  END AS ma50
FROM bajaj_auto;
SELECT * FROM bajaj1;""",

"6. Master table": """DROP TABLE IF EXISTS master_table;
CREATE TABLE master_table AS
SELECT b.date,
       b.close_price AS bajaj,
       t.close_price AS tcs,
       v.close_price AS tvs,
       i.close_price AS infosys,
       e.close_price AS eicher,
       h.close_price AS hero
FROM bajaj_auto b
JOIN tcs t            ON t.date = b.date
JOIN tvs_motors v     ON v.date = b.date
JOIN infosys i        ON i.date = b.date
JOIN eicher_motors e  ON e.date = b.date
JOIN hero_motocorp h  ON h.date = b.date;
SELECT * FROM master_table;""",

"7. Golden cross signals (bajaj2)": """DROP TABLE IF EXISTS bajaj2;
CREATE TABLE bajaj2 AS
WITH t AS (
  SELECT date, close_price, ma20, ma50,
         LAG(ma20) OVER (ORDER BY date) AS prev_ma20,
         LAG(ma50) OVER (ORDER BY date) AS prev_ma50
  FROM bajaj1
)
SELECT date, close_price,
  CASE
    WHEN ma50 IS NULL OR prev_ma50 IS NULL THEN 'Hold'
    WHEN ma20 > ma50 AND prev_ma20 <= prev_ma50 THEN 'Buy'
    WHEN ma20 < ma50 AND prev_ma20 >= prev_ma50 THEN 'Sell'
    ELSE 'Hold'
  END AS signal
FROM t;
SELECT * FROM bajaj2 WHERE signal <> 'Hold';""",

"8. How often did it trigger?": """SELECT signal, COUNT(*) AS days
FROM bajaj2
GROUP BY signal
ORDER BY signal;""",

"9. Signal on a given day": """SELECT signal
FROM bajaj2
WHERE date = '2018-06-21';""",

"10. All six stocks in one query": """WITH prices AS (
  SELECT 'Bajaj Auto' AS stock, date, close_price FROM bajaj_auto
  UNION ALL SELECT 'TCS', date, close_price FROM tcs
  UNION ALL SELECT 'Eicher Motors', date, close_price FROM eicher_motors
  UNION ALL SELECT 'Hero Motocorp', date, close_price FROM hero_motocorp
  UNION ALL SELECT 'Infosys', date, close_price FROM infosys
  UNION ALL SELECT 'TVS Motors', date, close_price FROM tvs_motors
),
ma AS (
  SELECT stock, date,
    CASE WHEN ROW_NUMBER() OVER (PARTITION BY stock ORDER BY date) >= 20
         THEN ROUND(AVG(close_price) OVER (PARTITION BY stock ORDER BY date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW), 2)
    END AS ma20,
    CASE WHEN ROW_NUMBER() OVER (PARTITION BY stock ORDER BY date) >= 50
         THEN ROUND(AVG(close_price) OVER (PARTITION BY stock ORDER BY date ROWS BETWEEN 49 PRECEDING AND CURRENT ROW), 2)
    END AS ma50
  FROM prices
),
lagged AS (
  SELECT stock, date, ma20, ma50,
         LAG(ma20) OVER (PARTITION BY stock ORDER BY date) AS prev_ma20,
         LAG(ma50) OVER (PARTITION BY stock ORDER BY date) AS prev_ma50
  FROM ma
),
sig AS (
  SELECT stock, date,
    CASE
      WHEN ma50 IS NULL OR prev_ma50 IS NULL THEN 'Hold'
      WHEN ma20 > ma50 AND prev_ma20 <= prev_ma50 THEN 'Buy'
      WHEN ma20 < ma50 AND prev_ma20 >= prev_ma50 THEN 'Sell'
      ELSE 'Hold'
    END AS signal
  FROM lagged
),
latest AS (
  SELECT stock, date, signal,
         ROW_NUMBER() OVER (PARTITION BY stock ORDER BY date DESC) AS rn
  FROM sig WHERE signal <> 'Hold'
),
counts AS (
  SELECT stock,
         SUM(signal = 'Buy')  AS buys,
         SUM(signal = 'Sell') AS sells
  FROM sig GROUP BY stock
)
SELECT c.stock, c.buys, c.sells,
       l.date AS last_signal_date,
       l.signal AS last_signal
FROM counts c
JOIN latest l ON l.stock = c.stock AND l.rn = 1
ORDER BY c.stock;""",

"11. Who went up?": """WITH ends AS (
  SELECT stock, MIN(date) AS first_d, MAX(date) AS last_d
  FROM stocks GROUP BY stock
)
SELECT e.stock, f.raw_close AS first_close, l.raw_close AS last_close,
       ROUND(100.0 * (l.raw_close - f.raw_close) / f.raw_close, 1) AS pct_change
FROM ends e
JOIN stocks f ON f.stock = e.stock AND f.date = e.first_d
JOIN stocks l ON l.stock = e.stock AND l.date = e.last_d
ORDER BY pct_change DESC;""",

"12. The data trap": """WITH moves AS (
  SELECT stock, date, raw_close AS close_price,
         100.0 * (raw_close / LAG(raw_close) OVER (PARTITION BY stock ORDER BY date) - 1) AS pct_move
  FROM stocks
),
ranked AS (
  SELECT *, ROW_NUMBER() OVER (PARTITION BY stock ORDER BY pct_move) AS rn
  FROM moves WHERE pct_move IS NOT NULL
)
SELECT stock, date, close_price, ROUND(pct_move, 1) AS pct_move
FROM ranked WHERE rn = 1
ORDER BY pct_move;""",

"13. Fix it": """WITH raw AS (
  SELECT 'TCS' AS stock, date, close_price FROM tcs
  UNION ALL
  SELECT 'Infosys', date, close_price FROM infosys
),
moves AS (
  SELECT stock, date, close_price,
         close_price / LAG(close_price) OVER (PARTITION BY stock ORDER BY date) - 1 AS pct_move
  FROM raw
),
cliff AS (
  SELECT stock, date AS cliff_date,
         ROW_NUMBER() OVER (PARTITION BY stock ORDER BY pct_move) AS rn
  FROM moves
  WHERE pct_move IS NOT NULL
),
adjusted AS (
  SELECT r.stock, r.date,
         CASE WHEN r.date < c.cliff_date THEN r.close_price / 2.0 ELSE r.close_price END AS adj_close
  FROM raw r
  JOIN cliff c ON c.stock = r.stock AND c.rn = 1
)
SELECT stock,
       ROUND(100.0 * (MAX(CASE WHEN date = '2018-07-31' THEN adj_close END) /
                      MAX(CASE WHEN date = '2015-01-01' THEN adj_close END) - 1), 1) AS adjusted_pct_change
FROM adjusted
GROUP BY stock
ORDER BY stock;""",
}