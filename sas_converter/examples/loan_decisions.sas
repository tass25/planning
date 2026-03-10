PROC SORT DATA=loan_applications;
BY applicant_id;
RUN;
PROC SORT DATA=credit_history;
BY applicant_id;
RUN;
DATA merged_applications;
MERGE loan_applications (IN=has_app) credit_history (IN=has_credit);
BY applicant_id;
IF has_app AND has_credit;
debt_to_income = monthly_debt / monthly_income;
credit_age_years = INTCK('YEAR', first_credit_date, TODAY());
RUN;
DATA loan_decisions;
SET merged_applications;
risk_score = 0;
IF credit_score >= 750 THEN risk_score = risk_score + 3;
ELSE IF credit_score >= 650 THEN risk_score = risk_score + 2;
ELSE IF credit_score >= 550 THEN risk_score = risk_score + 1;
IF debt_to_income < 0.30 THEN risk_score = risk_score + 2;
ELSE IF debt_to_income < 0.40 THEN risk_score = risk_score + 1;
IF credit_age_years >= 10 THEN risk_score = risk_score + 2;
ELSE IF credit_age_years >= 5 THEN risk_score = risk_score + 1;
IF risk_score >= 6 THEN decision = 'Approved';
ELSE IF risk_score >= 4 THEN decision = 'Manual Review';
ELSE decision = 'Denied';
IF decision = 'Approved' THEN interest_rate = 4.5;
ELSE IF decision = 'Manual Review' THEN interest_rate = 6.5;
ELSE interest_rate = .;
RUN;
PROC MEANS DATA=loan_decisions NOPRINT;
CLASS decision;
VAR loan_amount;
OUTPUT OUT=decision_summary
N=application_count
MEAN=avg_loan_amount
SUM=total_loan_volume;
RUN;
PROC EXPORT DATA=loan_decisions OUTFILE='/reports/loan_decisions.csv'
DBMS=CSV REPLACE;
RUN;
