-- q12: Drill-through – แสดง order line detail ของสาขาใน Bangkok
SELECT order_id, line_no, product_name, quantity, amount
FROM sales
WHERE province = 'Bangkok'
ORDER BY order_id, line_no;
