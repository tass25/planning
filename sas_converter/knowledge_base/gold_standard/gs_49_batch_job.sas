/* gs_49 - Parameterized batch job with all block types */
%LET batch_id = %SYSFUNC(PUTN(%SYSFUNC(DATETIME()), B8601DT.));
%LET run_date = %SYSFUNC(TODAY(), DATE9.);

OPTIONS MPRINT SYMBOLGEN;
LIBNAME warehouse '/data/warehouse';

%INCLUDE 'config/batch_params.sas';

%MACRO log_step(step_name=, status=OK);
    PROC SQL;
        INSERT INTO warehouse.batch_log
        VALUES ("&batch_id", "&step_name", "&status", DATETIME());
    QUIT;
%MEND log_step;

%log_step(step_name=START);

%IF &process_type = FULL %THEN %DO;
    PROC SQL;
        CREATE TABLE work.extract AS
        SELECT * FROM warehouse.transactions;
    QUIT;
%END;
%ELSE %DO;
    PROC SQL;
        CREATE TABLE work.extract AS
        SELECT * FROM warehouse.transactions
        WHERE load_date >= "&last_success_date"d;
    QUIT;
%END;

DATA work.transformed;
    SET work.extract;
    BY account_id;
    RETAIN running_balance 0;
    IF FIRST.account_id THEN running_balance = 0;
    running_balance + amount;
    IF LAST.account_id THEN OUTPUT;
    FORMAT running_balance DOLLAR15.2;
RUN;

PROC MEANS DATA=work.transformed NOPRINT;
    CLASS account_type;
    VAR running_balance;
    OUTPUT OUT=work.balance_summary MEAN= MEDIAN= / AUTONAME;
RUN;

%log_step(step_name=COMPLETE, status=OK);
