/* gs_16 - PROC TABULATE for multidimensional tables */
PROC TABULATE DATA=work.sales_data FORMAT=DOLLAR12.2;
    CLASS region quarter product_type;
    VAR revenue units;
    TABLE region * product_type,
          quarter * (revenue * (SUM MEAN) units * SUM) / BOX='Sales Summary';
    TITLE 'Multi-dimensional Sales Tabulation';
RUN;
