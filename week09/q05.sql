-- q05: Slice – กรองเฉพาะกันยายน สรุปยอดรายจังหวัด
SELECT province, SUM(amount) AS revenue
FROM sales
WHERE month = '2026-09'
GROUP BY province
ORDER BY revenue DESC;
