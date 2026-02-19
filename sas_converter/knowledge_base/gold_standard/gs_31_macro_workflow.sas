/* gs_31 - Multiple macro invocations in a workflow */
OPTIONS MPRINT MLOGIC;

%LET reporting_date = %SYSFUNC(TODAY(), DATE9.);
%LET fiscal_year = 2025;

%load_data(source=oracle, table=transactions, where=fiscal_year=&fiscal_year);
%clean_data(dsn=work.transactions, drop_missing=YES);
%apply_business_rules(dsn=work.transactions, ruleset=standard);

PROC MEANS DATA=work.transactions NOPRINT;
    VAR amount;
    OUTPUT OUT=work.trans_summary SUM=total MEAN=average N=count;
RUN;

%generate_report(dsn=work.trans_summary, title=Transaction Summary &reporting_date);
%send_email(to=finance@company.com, subject=Daily Report &reporting_date, attach=report.pdf);
