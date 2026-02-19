/* gs_47 - Data quality pipeline with multiple block types */
%INCLUDE 'macros/dq_framework.sas';

OPTIONS MPRINT;
LIBNAME staging '/data/staging';

/* Step 1: Load and initial clean */
DATA work.raw_claims;
    SET staging.insurance_claims;
    WHERE NOT MISSING(claim_id);
    claim_amount = ABS(claim_amount);
    IF claim_date > TODAY() THEN claim_date = .;
RUN;

/* Step 2: Statistical profiling */
PROC MEANS DATA=work.raw_claims N NMISS MEAN STD MIN MAX Q1 Q3;
    VAR claim_amount deductible copay;
    OUTPUT OUT=work.claim_profile;
RUN;

/* Step 3: Outlier detection */
PROC SQL;
    CREATE TABLE work.outliers AS
    SELECT claim_id, claim_amount, provider_id
    FROM work.raw_claims
    WHERE claim_amount > (SELECT MEAN(claim_amount) + 3 * STD(claim_amount)
                          FROM work.raw_claims)
    ORDER BY claim_amount DESC;
QUIT;

/* Step 4: Flag and output */
DATA staging.validated_claims staging.rejected_claims;
    MERGE work.raw_claims (IN=a)
          work.outliers (IN=b KEEP=claim_id);
    BY claim_id;
    IF a;
    IF b THEN DO;
        reject_reason = 'OUTLIER';
        OUTPUT staging.rejected_claims;
    END;
    ELSE OUTPUT staging.validated_claims;
RUN;

%dq_summary_report(valid=staging.validated_claims, rejected=staging.rejected_claims);
