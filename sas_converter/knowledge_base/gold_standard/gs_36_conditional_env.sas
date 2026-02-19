/* gs_36 - %IF/%THEN/%ELSE conditional blocks */
%LET env = PROD;
%LET debug = NO;

%IF &env = PROD %THEN %DO;
    LIBNAME mydata '/prod/data/warehouse';
    OPTIONS NOSOURCE NONOTES;
%END;
%ELSE %IF &env = DEV %THEN %DO;
    LIBNAME mydata '/dev/data/sandbox';
    OPTIONS SOURCE NOTES MPRINT;
%END;
%ELSE %DO;
    %PUT ERROR: Unknown environment: &env;
    %ABORT CANCEL;
%END;

%IF &debug = YES %THEN %DO;
    PROC PRINT DATA=mydata.customers (OBS=10);
        TITLE 'DEBUG: First 10 rows of customers';
    RUN;
%END;

DATA work.daily_extract;
    SET mydata.customers;
    WHERE active = 1;
    extract_date = TODAY();
RUN;
