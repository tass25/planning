/* gs_03 - DATA step with MERGE and BY-group processing */
PROC SORT DATA=work.orders OUT=work.orders_sorted;
    BY customer_id;
RUN;

PROC SORT DATA=work.customers OUT=work.customers_sorted;
    BY customer_id;
RUN;

DATA work.customer_orders;
    MERGE work.customers_sorted (IN=a)
          work.orders_sorted (IN=b);
    BY customer_id;
    IF a AND b;
    order_year = YEAR(order_date);
    days_since_order = TODAY() - order_date;
RUN;
