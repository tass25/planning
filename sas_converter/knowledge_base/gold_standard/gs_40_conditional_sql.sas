/* gs_40 - Conditional processing with PROC SQL */
%LET run_type = FULL;

%IF &run_type = FULL %THEN %DO;
    PROC SQL;
        CREATE TABLE work.full_extract AS
        SELECT * FROM work.source_data;
    QUIT;
%END;
%ELSE %IF &run_type = INCREMENTAL %THEN %DO;
    PROC SQL;
        CREATE TABLE work.full_extract AS
        SELECT * FROM work.source_data
        WHERE load_date >= "&last_run_date"d;
    QUIT;
%END;

DATA work.final_output;
    SET work.full_extract;
    process_type = "&run_type";
    processed_at = DATETIME();
    FORMAT processed_at DATETIME20.;
RUN;
