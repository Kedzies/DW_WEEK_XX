-- q07: HAVING – จังหวัดที่ยอดรวมกันยายนเกิน 400 บาท เรียงมากไปน้อย
-- WHERE กรองเดือนก่อน GROUP BY (row-level)
-- HAVING กรองยอดรวม SUM หลัง GROUP BY (aggregate-level)
SELECT province, SUM(amount) AS revenue
FROM sales
WHERE month = '2026-09'
GROUP BY province
HAVING revenue > 400
ORDER BY revenue DESC;
