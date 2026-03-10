/* Create a sample dataset */
DATA sales;
    INPUT id region $ product $ amount date : yymmdd10.;
    FORMAT date yymmdd10.;
    DATALINES;
1 North A 120 2024-01-01
2 South B 200 2024-01-03
3 North A 150 2024-01-05
4 East  C 300 2024-01-07
5 South B 250 2024-01-10
;
RUN;

/* Create a new variable with conditional logic */
DATA sales_updated;
    SET sales;
    IF amount >= 200 THEN category = "High";
    ELSE category = "Low";
RUN;

/* Aggregate using PROC MEANS */
PROC MEANS DATA=sales_updated NOPRINT;
    CLASS region;
    VAR amount;
    OUTPUT OUT=region_summary
        SUM=total_sales
        MEAN=avg_sales;
RUN;

/* SQL example */
PROC SQL;
    CREATE TABLE high_sales AS
    SELECT id, region, product, amount
    FROM sales_updated
    WHERE category = "High";
QUIT;
