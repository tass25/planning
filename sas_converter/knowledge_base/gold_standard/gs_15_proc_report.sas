/* gs_15 - PROC REPORT with computed columns */
PROC SORT DATA=work.monthly_sales;
    BY region product_line;
RUN;

PROC REPORT DATA=work.monthly_sales NOWD;
    COLUMNS region product_line units_sold revenue profit margin;
    DEFINE region / GROUP 'Region';
    DEFINE product_line / GROUP 'Product Line';
    DEFINE units_sold / SUM 'Units' FORMAT=COMMA10.;
    DEFINE revenue / SUM 'Revenue' FORMAT=DOLLAR12.2;
    DEFINE profit / SUM 'Profit' FORMAT=DOLLAR12.2;
    DEFINE margin / COMPUTED 'Margin %' FORMAT=PERCENT8.1;

    COMPUTE margin;
        IF revenue.SUM GT 0 THEN
            margin = profit.SUM / revenue.SUM;
        ELSE
            margin = 0;
    ENDCOMP;

    RBREAK AFTER / SUMMARIZE;
    TITLE 'Sales Performance Report';
RUN;
