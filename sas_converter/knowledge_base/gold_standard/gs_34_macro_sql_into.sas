/* gs_34 - Macro with PROC SQL into macro variables */
%MACRO top_n_report(dsn=, measure=, n=10, by_var=);
    PROC SQL NOPRINT;
        SELECT DISTINCT &by_var INTO :group_list SEPARATED BY '|'
        FROM &dsn;
    QUIT;

    %LET i = 1;
    %LET grp = %SCAN(&group_list, &i, |);
    %DO %WHILE(&grp NE );
        PROC SQL OUTOBS=&n;
            CREATE TABLE work._top_&i AS
            SELECT * FROM &dsn
            WHERE &by_var = "&grp"
            ORDER BY &measure DESC;
        QUIT;

        PROC PRINT DATA=work._top_&i NOOBS;
            TITLE "Top &n by &measure — Group: &grp";
        RUN;

        %LET i = %EVAL(&i + 1);
        %LET grp = %SCAN(&group_list, &i, |);
    %END;
%MEND top_n_report;

%top_n_report(dsn=work.sales, measure=revenue, n=5, by_var=region);
