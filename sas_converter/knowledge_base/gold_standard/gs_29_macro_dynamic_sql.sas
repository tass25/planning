/* gs_29 - Macro generating dynamic SQL */
%MACRO create_monthly_tables(base_name=, year=2025, start_month=1, end_month=12);
    PROC SQL;
    %DO month = &start_month %TO &end_month;
        %LET month_str = %SYSFUNC(PUTN(&month, Z2.));
        CREATE TABLE work.&base_name._&year._&month_str AS
        SELECT *
        FROM work.&base_name
        WHERE YEAR(transaction_date) = &year
          AND MONTH(transaction_date) = &month;
    %END;
    QUIT;

    %PUT NOTE: Created %EVAL(&end_month - &start_month + 1) monthly tables for &base_name;
%MEND create_monthly_tables;

%create_monthly_tables(base_name=transactions, year=2025, start_month=1, end_month=6);
