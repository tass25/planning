/* gs_46 - Full ETL with macros, DATA, SQL, and PROC */
OPTIONS MPRINT FULLSTIMER;
LIBNAME src '/data/source';
LIBNAME tgt '/data/target';

%MACRO etl_customers(cutoff_date=);
    PROC SQL;
        CREATE TABLE work.active_customers AS
        SELECT c.customer_id, c.name, c.email, c.segment,
               SUM(o.total) AS lifetime_value FORMAT=DOLLAR12.2,
               COUNT(o.order_id) AS order_count
        FROM src.customers AS c
        LEFT JOIN src.orders AS o ON c.customer_id = o.customer_id
        WHERE o.order_date >= "&cutoff_date"d
        GROUP BY c.customer_id, c.name, c.email, c.segment
        HAVING CALCULATED order_count > 0;
    QUIT;
%MEND etl_customers;

%etl_customers(cutoff_date=01JAN2025);

PROC SORT DATA=work.active_customers;
    BY DESCENDING lifetime_value;
RUN;

DATA tgt.customer_tiers;
    SET work.active_customers;
    LENGTH tier $15;
    IF lifetime_value >= 50000 THEN tier = 'PLATINUM';
    ELSE IF lifetime_value >= 20000 THEN tier = 'GOLD';
    ELSE IF lifetime_value >= 5000 THEN tier = 'SILVER';
    ELSE tier = 'BRONZE';
    tier_date = TODAY();
    FORMAT tier_date DATE9.;
RUN;

PROC FREQ DATA=tgt.customer_tiers;
    TABLES tier * segment / NOCOL NOROW;
    TITLE 'Customer Tier Distribution by Segment';
RUN;
