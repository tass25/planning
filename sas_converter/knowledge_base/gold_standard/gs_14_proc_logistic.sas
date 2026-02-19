/* gs_14 - PROC LOGISTIC for binary classification */
DATA work.model_data;
    SET work.credit_apps;
    IF MISSING(income) OR MISSING(credit_score) THEN DELETE;
    log_income = LOG(income);
    high_debt = (debt_ratio > 0.4);
RUN;

PROC LOGISTIC DATA=work.model_data DESCENDING PLOTS=ROC;
    CLASS employment_type (REF='FULL_TIME') / PARAM=REF;
    MODEL default_flag = log_income credit_score high_debt
                         employment_type years_employed / SELECTION=STEPWISE
                         SLENTRY=0.05 SLSTAY=0.10;
    OUTPUT OUT=work.scored_apps P=prob_default;
    TITLE 'Credit Default Logistic Regression';
RUN;
