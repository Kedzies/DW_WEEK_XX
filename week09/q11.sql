-- q11: ตรวจความครบถ้วนของ JOIN – เปรียบจำนวนแถวและยอดรวม fact vs view
SELECT
    (SELECT COUNT(*)                    FROM fact_sales) AS fact_rows,
    (SELECT COUNT(*)                    FROM sales)      AS view_rows,
    (SELECT SUM(quantity * unit_price)  FROM fact_sales) AS fact_revenue,
    (SELECT SUM(amount)                 FROM sales)      AS view_revenue;

-- ตรวจ FK: ถ้าไม่มีแถวแสดง = ไม่มี FK violation
PRAGMA foreign_key_check;
