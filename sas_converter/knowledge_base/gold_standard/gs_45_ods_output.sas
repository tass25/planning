/* gs_45 - ODS and global output management */
OPTIONS NODATE NONUMBER ORIENTATION=LANDSCAPE;
ODS LISTING CLOSE;
ODS HTML5 FILE='/output/dashboard.html' STYLE=HTMLBLUE;
ODS GRAPHICS ON / WIDTH=800px HEIGHT=400px;

TITLE1 'Executive Dashboard';
TITLE2 'Data as of %SYSFUNC(TODAY(), WORDDATE.)';

PROC SGPLOT DATA=work.kpi_data;
    VBAR month / RESPONSE=revenue STAT=SUM;
    YAXIS LABEL='Revenue' GRID;
RUN;

PROC TABULATE DATA=work.kpi_data;
    CLASS department month;
    VAR headcount budget_used;
    TABLE department, month * (headcount budget_used) * SUM;
RUN;

ODS HTML5 CLOSE;
ODS LISTING;
TITLE;
