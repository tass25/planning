/* gs_20 - PROC CONTENTS and PROC DATASETS */
PROC CONTENTS DATA=work.customer_master OUT=work.col_metadata NOPRINT;
RUN;

PROC DATASETS LIB=work NOLIST;
    MODIFY customer_master;
    RENAME old_customer_id = customer_id
           old_name = customer_name;
    LABEL customer_id = 'Customer Identifier'
          customer_name = 'Full Name'
          join_date = 'Enrollment Date';
    FORMAT join_date YYMMDD10.
           revenue DOLLAR12.2;
QUIT;
