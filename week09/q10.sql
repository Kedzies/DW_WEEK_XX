-- q10: ตรวจยอดสรุปและ AOV
-- AOV = SUM(amount) / COUNT(DISTINCT order_id)  -- หารด้วยจำนวน orders ไม่ใช่ lines
-- avg_line = AVG(amount)                         -- ค่าเฉลี่ยต่อ order line
-- ต้องคูณ *1.0 เพื่อให้ SQLite หารเป็นทศนิยม
SELECT
    SUM(amount)                                             AS revenue,
    COUNT(DISTINCT order_id)                                AS orders,
    ROUND(SUM(amount) * 1.0 / COUNT(DISTINCT order_id), 2) AS aov,
    ROUND(AVG(amount * 1.0), 2)                            AS avg_line
FROM sales;
