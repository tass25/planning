/* gs_30 - Macro library with utility macros */
%MACRO check_missing(dsn=, var=);
    PROC SQL NOPRINT;
        SELECT COUNT(*) INTO :total_obs FROM &dsn;
        SELECT COUNT(*) INTO :missing_count FROM &dsn WHERE &var IS MISSING;
    QUIT;

    %LET pct = %SYSEVALF(&missing_count / &total_obs * 100, CEIL);
    %PUT NOTE: &var in &dsn — &missing_count / &total_obs missing (&pct%);

    %IF &pct > 20 %THEN %DO;
        %PUT WARNING: High missing rate for &var in &dsn;
    %END;
%MEND check_missing;

%MACRO export_csv(dsn=, outfile=, dlm=%STR(,));
    PROC EXPORT DATA=&dsn
        OUTFILE="&outfile"
        DBMS=DLM REPLACE;
        DELIMITER="&dlm";
    RUN;
    %PUT NOTE: Exported &dsn to &outfile;
%MEND export_csv;

%check_missing(dsn=work.patients, var=diagnosis_code);
%export_csv(dsn=work.report_data, outfile=/output/report.csv);
