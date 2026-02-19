/* gs_35 - Mixed macro and DATA step processing */
%LET input_path = /data/monthly;
%LET output_lib = work;

%MACRO load_monthly(month_num=);
    %LET month_name = %SYSFUNC(PUTN(&month_num, MONNAME3.));
    %LET file = &input_path./&month_name..csv;

    PROC IMPORT DATAFILE="&file"
        OUT=&output_lib..raw_&month_name DBMS=CSV REPLACE;
    RUN;
%MEND load_monthly;

%load_monthly(month_num=1);
%load_monthly(month_num=2);
%load_monthly(month_num=3);

DATA work.quarterly_combined;
    SET work.raw_JAN work.raw_FEB work.raw_MAR;
    quarter = 'Q1';
    record_source = 'MONTHLY_LOAD';
RUN;

PROC MEANS DATA=work.quarterly_combined NOPRINT;
    CLASS product_line;
    VAR revenue quantity;
    OUTPUT OUT=work.q1_summary SUM=;
RUN;
