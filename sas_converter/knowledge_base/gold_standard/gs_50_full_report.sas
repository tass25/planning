/* gs_50 - End-to-end reporting with all partition types */
OPTIONS MPRINT NODATE NONUMBER;
LIBNAME reports '/data/reports';
TITLE1 'Monthly Executive Report';

%INCLUDE 'macros/report_utils.sas';

%MACRO monthly_report(month=, year=);
    %LET month_name = %SYSFUNC(PUTN(%SYSFUNC(MDY(&month, 1, &year)), MONNAME.));

    PROC SQL;
        CREATE TABLE work.monthly_data AS
        SELECT department,
               SUM(revenue) AS total_revenue FORMAT=DOLLAR15.2,
               SUM(expenses) AS total_expenses FORMAT=DOLLAR15.2,
               SUM(revenue) - SUM(expenses) AS net_income FORMAT=DOLLAR15.2,
               COUNT(DISTINCT employee_id) AS headcount
        FROM reports.financial_data
        WHERE MONTH(trans_date) = &month AND YEAR(trans_date) = &year
        GROUP BY department;
    QUIT;

    %IF &net_income_flag = YES %THEN %DO;
        DATA work.monthly_data;
            SET work.monthly_data;
            margin_pct = net_income / total_revenue * 100;
            FORMAT margin_pct 8.1;
        RUN;
    %END;

    %DO i = 1 %TO 3;
        %LET dept = %SCAN(&departments, &i);
        PROC PRINT DATA=work.monthly_data NOOBS;
            WHERE department = "&dept";
            TITLE2 "Department: &dept — &month_name &year";
        RUN;
    %END;
%MEND monthly_report;

%monthly_report(month=1, year=2025);

PROC MEANS DATA=work.monthly_data;
    VAR total_revenue total_expenses net_income;
    OUTPUT OUT=work.grand_total SUM=;
RUN;

TITLE;
