/* gs_43 - FILENAME and LIBNAME with various engines */
FILENAME indata '/data/incoming/daily_feed.dat' RECFM=V LRECL=500;
FILENAME outlog '/logs/processing.log';
LIBNAME myora ORACLE USER=sas_user PASSWORD="{SAS002}XXXXX"
    PATH='proddb' SCHEMA='analytics';
LIBNAME myxls XLSX '/data/reference/lookup_tables.xlsx';

DATA work.daily_feed;
    INFILE indata DLM='|' DSD TRUNCOVER;
    INPUT record_id $10.
          trans_date YYMMDD10.
          amount 12.2
          category $20.
          description $100.;
    FORMAT trans_date DATE9. amount DOLLAR12.2;
RUN;

PROC APPEND BASE=myora.transaction_history DATA=work.daily_feed FORCE;
RUN;
