/* gs_26 - Basic macro definition */
%MACRO summarize_var(dsn=, var=, stat=MEAN);
    PROC MEANS DATA=&dsn NOPRINT;
        VAR &var;
        OUTPUT OUT=work._temp_summary &stat=result;
    RUN;

    PROC PRINT DATA=work._temp_summary NOOBS;
        TITLE "Summary of &var (&stat) from &dsn";
    RUN;
    TITLE;
%MEND summarize_var;

%summarize_var(dsn=work.employees, var=salary, stat=MEDIAN);
%summarize_var(dsn=work.employees, var=years_experience);
