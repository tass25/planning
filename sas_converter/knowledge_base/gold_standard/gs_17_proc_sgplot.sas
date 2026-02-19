/* gs_17 - PROC SGPLOT and PROC SGPANEL for visualization */
PROC SGPLOT DATA=work.monthly_metrics;
    SERIES X=month Y=revenue / GROUP=region LINEATTRS=(THICKNESS=2);
    XAXIS LABEL='Month' GRID;
    YAXIS LABEL='Revenue ($)' GRID;
    TITLE 'Monthly Revenue by Region';
RUN;

PROC SGPANEL DATA=work.survey_results;
    PANELBY department / COLUMNS=3;
    VBAR satisfaction / RESPONSE=count STAT=SUM;
    ROWAXIS LABEL='Count';
    COLAXIS LABEL='Satisfaction Score';
RUN;
