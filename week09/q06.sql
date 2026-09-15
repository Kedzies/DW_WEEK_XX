-- q06: Dice – กันยายน + หมวด Drink + จังหวัด Bangkok หรือ Chonburi
SELECT province, product_name, SUM(amount) AS revenue
FROM sales
WHERE month = '2026-09'
  AND category = 'Drink'
  AND province IN ('Bangkok', 'Chonburi')
GROUP BY province, product_name;
