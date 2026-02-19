/* gs_07 - DATA step with output to multiple datasets */
DATA work.high_risk work.medium_risk work.low_risk;
    SET work.loan_applications;
    debt_ratio = total_debt / annual_income;
    IF credit_score < 580 OR debt_ratio > 0.50 THEN OUTPUT work.high_risk;
    ELSE IF credit_score < 700 OR debt_ratio > 0.35 THEN OUTPUT work.medium_risk;
    ELSE OUTPUT work.low_risk;
RUN;

PROC FREQ DATA=work.high_risk;
    TABLES loan_type * default_flag / CHISQ;
    TITLE 'High Risk Loan Distribution';
RUN;
