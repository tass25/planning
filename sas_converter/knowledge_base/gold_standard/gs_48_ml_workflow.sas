/* gs_48 - Machine learning workflow */
OPTIONS MPRINT;
LIBNAME ml '/data/ml_project';

/* Prep and feature engineering */
DATA work.features;
    SET ml.raw_features;
    ARRAY nums{*} _NUMERIC_;
    DO i = 1 TO DIM(nums);
        IF MISSING(nums{i}) THEN nums{i} = 0;
    END;
    log_income = LOG(income + 1);
    age_squared = age ** 2;
    interactions = age * years_employed;
    DROP i;
RUN;

/* Train-test split */
PROC SURVEYSELECT DATA=work.features OUT=work.split
    METHOD=SRS SAMPRATE=0.7 SEED=42 OUTALL;
RUN;

DATA work.train work.test;
    SET work.split;
    IF selected = 1 THEN OUTPUT work.train;
    ELSE OUTPUT work.test;
RUN;

/* Model training */
PROC LOGISTIC DATA=work.train OUTMODEL=work.model_store DESCENDING;
    MODEL target = log_income age_squared interactions
                   credit_score debt_ratio / SELECTION=STEPWISE;
    SCORE DATA=work.test OUT=work.scored;
RUN;

/* Evaluate */
PROC FREQ DATA=work.scored;
    TABLES target * I_target / SENSPEC;
    TITLE 'Confusion Matrix';
RUN;
