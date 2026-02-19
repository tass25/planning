/* gs_10 - DATA step with transposing logic */
PROC SORT DATA=work.quarterly_sales;
    BY product_id;
RUN;

PROC TRANSPOSE DATA=work.quarterly_sales
               OUT=work.sales_wide (DROP=_NAME_)
               PREFIX=q;
    BY product_id;
    ID quarter;
    VAR revenue;
RUN;

DATA work.sales_analysis;
    SET work.sales_wide;
    annual_total = SUM(q1, q2, q3, q4);
    growth_rate = (q4 - q1) / q1 * 100;
    IF annual_total > 0 THEN
        avg_quarterly = annual_total / 4;
    ELSE
        avg_quarterly = 0;
    FORMAT annual_total avg_quarterly DOLLAR12.2
           growth_rate PERCENT8.1;
RUN;
