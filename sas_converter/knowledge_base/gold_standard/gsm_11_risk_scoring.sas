/******************************************************************************
 * Program: gsm_11_risk_scoring.sas
 * Purpose: Credit risk scoring model for loan applications
 *          Computes individual risk factors, benchmarks against population,
 *          applies scorecard-based bucketing, and enforces policy cutoffs.
 * Author:  Risk Analytics Team
 * Date:    2026-02-19
 ******************************************************************************/

/* --- Library references for risk data environment --- */
libname raw     '/data/risk/raw';
libname staging '/data/risk/staging';
libname tgt     '/data/risk/target';

options mprint symbolgen nocenter;

/* -----------------------------------------------------------------------
   STEP 1: Compute individual risk factors from application data
   Loan-to-Value (LTV), Debt-to-Income (DTI), credit utilization
   ----------------------------------------------------------------------- */
data staging.risk_factors;
    set raw.loan_applications;
    length risk_flag $1;

    /* Loan-to-Value ratio */
    if property_value > 0 then
        ltv_ratio = loan_amount / property_value;
    else
        ltv_ratio = .;

    /* Debt-to-Income ratio */
    if gross_income > 0 then
        dti_ratio = (monthly_debt + (loan_amount / 360)) / (gross_income / 12);
    else
        dti_ratio = .;

    /* Credit utilization rate */
    if credit_limit > 0 then
        credit_util = outstanding_balance / credit_limit;
    else
        credit_util = .;

    /* Payment history score (0-100 scale) */
    payment_score = 100 - (missed_payments * 15) - (late_payments_30d * 5);
    if payment_score < 0 then payment_score = 0;

    /* Flag records with missing critical data */
    if ltv_ratio = . or dti_ratio = . then
        risk_flag = 'M';
    else
        risk_flag = 'V';

    format ltv_ratio dti_ratio credit_util percent8.2;
run;

/* -----------------------------------------------------------------------
   STEP 2: Population benchmarks for risk factor distributions
   ----------------------------------------------------------------------- */
proc means data=staging.risk_factors
           n mean std p25 median p75 p90 p95
           noprint;
    where risk_flag = 'V';
    var ltv_ratio dti_ratio credit_util payment_score;
    output out=staging.population_benchmarks
        mean=avg_ltv avg_dti avg_util avg_payment
        std=std_ltv std_dti std_util std_payment
        p90=p90_ltv p90_dti p90_util p90_payment;
run;

/* -----------------------------------------------------------------------
   STEP 3: Join application data with credit bureau records
   ----------------------------------------------------------------------- */
proc sql;
    create table staging.enriched_applications as
    select a.application_id,
           a.applicant_id,
           a.ltv_ratio,
           a.dti_ratio,
           a.credit_util,
           a.payment_score,
           b.fico_score,
           b.bankruptcy_flag,
           b.inquiries_6m,
           b.oldest_tradeline_months,
           b.derogatory_count,
           coalesce(b.fico_score, 0) as fico_adj
    from staging.risk_factors as a
    left join raw.credit_bureau as b
        on a.applicant_id = b.applicant_id
    where a.risk_flag = 'V';
quit;

/* -----------------------------------------------------------------------
   STEP 4: Risk bucketing using scorecard approach (SELECT/WHEN)
   Assign points based on characteristic ranges
   ----------------------------------------------------------------------- */
data staging.risk_scored;
    set staging.enriched_applications;
    length risk_bucket $12;

    /* LTV score component */
    select;
        when (ltv_ratio <= 0.60) ltv_points = 40;
        when (ltv_ratio <= 0.75) ltv_points = 30;
        when (ltv_ratio <= 0.85) ltv_points = 20;
        when (ltv_ratio <= 0.95) ltv_points = 10;
        otherwise                ltv_points = 0;
    end;

    /* DTI score component */
    select;
        when (dti_ratio <= 0.28) dti_points = 30;
        when (dti_ratio <= 0.36) dti_points = 20;
        when (dti_ratio <= 0.43) dti_points = 10;
        otherwise                dti_points = 0;
    end;

    /* FICO score component */
    select;
        when (fico_adj >= 760) fico_points = 50;
        when (fico_adj >= 700) fico_points = 35;
        when (fico_adj >= 660) fico_points = 20;
        when (fico_adj >= 620) fico_points = 10;
        otherwise              fico_points = 0;
    end;

    /* Total raw score */
    raw_score = ltv_points + dti_points + fico_points;

    /* Assign risk bucket */
    select;
        when (raw_score >= 100) risk_bucket = 'PRIME';
        when (raw_score >= 70)  risk_bucket = 'NEAR_PRIME';
        when (raw_score >= 40)  risk_bucket = 'SUBPRIME';
        otherwise               risk_bucket = 'DEEP_SUB';
    end;
run;

/* -----------------------------------------------------------------------
   STEP 5: Apply logistic regression coefficients for PD estimation
   Coefficients pre-estimated from historical default model
   ----------------------------------------------------------------------- */
data staging.pd_estimates;
    set staging.risk_scored;

    /* Model intercept and coefficients */
    _intercept = -3.258;
    _beta_ltv  =  2.145;
    _beta_dti  =  1.873;
    _beta_fico = -0.0042;
    _beta_util =  0.952;
    _beta_inq  =  0.187;

    /* Linear predictor (log-odds) */
    logit = _intercept
          + _beta_ltv  * ltv_ratio
          + _beta_dti  * dti_ratio
          + _beta_fico * fico_adj
          + _beta_util * credit_util
          + _beta_inq  * inquiries_6m;

    /* Probability of default */
    prob_default = 1 / (1 + exp(-logit));

    /* Expected loss given default assumption */
    lgd = 0.40;
    expected_loss = prob_default * lgd * loan_amount;

    drop _intercept _beta_: logit;
    format prob_default percent8.4 expected_loss dollar12.2;
run;

/* -----------------------------------------------------------------------
   STEP 6: Apply policy overrides and final credit decision
   ----------------------------------------------------------------------- */
data tgt.final_decisions;
    set staging.pd_estimates;
    length decision $10 override_reason $50;

    /* Default decision based on PD threshold */
    if prob_default <= 0.03 then decision = 'APPROVE';
    else if prob_default <= 0.08 then decision = 'REVIEW';
    else decision = 'DECLINE';

    /* Policy overrides */
    override_reason = '';
    if bankruptcy_flag = 'Y' then do;
        decision = 'DECLINE';
        override_reason = 'Active bankruptcy on file';
    end;
    else if fico_adj < 580 then do;
        decision = 'DECLINE';
        override_reason = 'FICO below minimum threshold';
    end;
    else if ltv_ratio > 0.97 then do;
        decision = 'DECLINE';
        override_reason = 'LTV exceeds maximum policy limit';
    end;
    else if dti_ratio > 0.50 then do;
        decision = 'REVIEW';
        override_reason = 'DTI exceeds guideline maximum';
    end;

    decision_date = today();
    format decision_date date9.;
run;
