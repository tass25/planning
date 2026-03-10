/* gs_22 - PROC SQL with multi-table JOINs */
PROC SQL;
    CREATE TABLE work.order_details AS
    SELECT o.order_id,
           o.order_date,
           c.customer_name,
           c.segment,
           p.product_name,
           p.category,
           oi.quantity,
           oi.unit_price,
           oi.quantity * oi.unit_price AS line_total FORMAT=DOLLAR10.2,
           s.shipper_name,
           s.shipping_cost FORMAT=DOLLAR8.2
    FROM work.orders AS o
    INNER JOIN work.customers AS c ON o.customer_id = c.customer_id
    INNER JOIN work.order_items AS oi ON o.order_id = oi.order_id
    INNER JOIN work.products AS p ON oi.product_id = p.product_id
    LEFT JOIN work.shipments AS s ON o.order_id = s.order_id
    WHERE o.order_date BETWEEN '01JAN2025'd AND '31DEC2025'd
    ORDER BY o.order_date, o.order_id;
QUIT;
