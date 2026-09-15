-- q09: UNION ALL – ยอดรายเดือน + แถว ALL รวมทั้งหมด
-- หมายเหตุ: ถ้านำทุกแถวของ UNION ALL บวกกันจะได้ Aug+Sep+ALL = double count
-- แถว ALL ใช้ตรวจสอบเท่านั้น ไม่ควรบวกซ้ำอีกครั้ง
SELECT month, SUM(amount) AS revenue
FROM sales
GROUP BY month
UNION ALL
SELECT 'ALL', SUM(amount)
FROM sales
ORDER BY month;
