/* gs_21 - PROC SQL simple queries */
PROC SQL;
    CREATE TABLE work.top_customers AS
    SELECT customer_id,
           customer_name,
           SUM(order_total) AS lifetime_value FORMAT=DOLLAR12.2,
           COUNT(*) AS order_count,
           MIN(order_date) AS first_order FORMAT=DATE9.,
           MAX(order_date) AS last_order FORMAT=DATE9.
    FROM work.orders
    GROUP BY customer_id, customer_name
    HAVING CALCULATED lifetime_value > 10000
    ORDER BY lifetime_value DESC;
QUIT;
