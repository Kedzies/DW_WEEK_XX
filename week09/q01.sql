-- q01: สรุปข้อมูลทั้งหมดใน Star Schema
-- line_count=จำนวน order lines, order_count=จำนวน orders, units=ชิ้นรวม, revenue=ยอดรวม
SELECT
    COUNT(*)                   AS line_count,
    COUNT(DISTINCT order_id)   AS order_count,
    SUM(quantity)              AS units,
    SUM(amount)                AS revenue
FROM sales;
