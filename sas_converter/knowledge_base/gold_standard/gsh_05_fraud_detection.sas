/******************************************************************************
 * Program Name : gsh_05_fraud_detection.sas
 * Author       : Financial Crime Prevention Unit — Transaction Monitoring
 * Department   : Anti-Money Laundering & Fraud Analytics
 * Version      : 2.3
 * Created      : 2025-03-10
 * Modified     : 2026-02-19
 * Purpose      : Real-time transaction fraud detection system. Implements
 *                multi-layer fraud detection pipeline including feature
 *                engineering (velocity, amount, behavioral), rule-based
 *                screening (12 configurable rules), logistic regression
 *                scoring model, and automated alert generation with
 *                routing to BLOCK / REVIEW / PASS queues.
 * Input        : txn.transactions, txn.transaction_history,
 *                cust.customer_profiles, cust.account_details,
 *                mdl.model_coefficients, mdl.score_thresholds
 * Output       : alert.fraud_alerts, alert.blocked_transactions,
 *                alert.review_queue, alert.daily_fraud_metrics
 * Dependencies : fraud_utils.sas (shared fraud detection utilities)
 * Compliance   : PCI-DSS 3.2.1, BSA/AML, Reg E
 * Change Log   :
 *   2025-03-10  v1.0  Initial feature engineering pipeline     (M. Torres)
 *   2025-05-22  v1.1  Added rule engine with 6 rules            (M. Torres)
 *   2025-07-14  v1.2  Logistic regression scoring model         (S. Kim)
 *   2025-09-30  v1.5  Expanded to 12 rules, velocity windows   (M. Torres)
 *   2025-11-18  v2.0  Alert generation and routing              (S. Kim)
 *   2026-01-05  v2.2  Hash lookup for merchant blacklist        (M. Torres)
 *   2026-02-19  v2.3  Error handling and daily metrics          (S. Kim)
 ******************************************************************************/

/* ========================================================================= */
/* SECTION 1: Environment Setup and Library Definitions                      */
/* ========================================================================= */

options mprint symbolgen mlogic nocenter ls=150 ps=60
        validvarname=v7 nofmterr msglevel=i;

/* --- Transaction data library (current day + history) --- */
libname txn '/fraud/data/transactions'
            access=readonly;

/* --- Customer and account reference data --- */
libname cust '/fraud/data/customer'
             access=readonly;

/* --- Model artifacts: coefficients, thresholds, blacklists --- */
libname mdl '/fraud/models/production';

/* --- Alert output library --- */
libname alert '/fraud/output/alerts';

/* --- Global parameters for this fraud detection run --- */
%let run_id        = FR_%sysfunc(today(), yymmddn8.)_%sysfunc(time(), time5.);
%let process_date  = %sysfunc(today(), date9.);
%let score_version = LR_v2.3;
%let fraud_rc      = 0;
%let block_count   = 0;
%let review_count  = 0;
%let pass_count    = 0;
%let total_alerts  = 0;

/* Load shared fraud detection utility macros */
%include '/fraud/macros/fraud_utils.sas';

/* ========================================================================= */
/* SECTION 2: Feature Engineering Macro                                      */
/* ========================================================================= */

/*----------------------------------------------------------------------
  %MACRO feature_engineering
  Purpose: Build velocity-based and amount-based features for each
           transaction. Uses RETAIN for running accumulators, LAG for
           inter-transaction timing, and a %DO loop to compute features
           across multiple time windows (1h, 6h, 24h, 72h).
----------------------------------------------------------------------*/

%macro feature_engineering(input_ds=, output_ds=, history_ds=);

    /* Step 1: Sort current transactions by account and timestamp */
    proc sort data=&input_ds out=work._txn_sorted;
        by account_id transaction_datetime;
    run;

    /* Step 2: Sort historical transactions for windowed join */
    proc sort data=&history_ds out=work._hist_sorted;
        by account_id transaction_datetime;
    run;

    /* Step 3: Combine current and historical for windowed features */
    data work._txn_combined;
        set work._hist_sorted(in=hist)
            work._txn_sorted(in=curr);
        by account_id transaction_datetime;
        is_current = curr;
    run;

    /* Step 4: Build features using RETAIN and LAG across accounts */
    data &output_ds(where=(is_current = 1));
        set work._txn_combined;
        by account_id;

        /* ---- Retained accumulators for velocity windows ---- */
        retain txn_count_1h txn_count_6h txn_count_24h txn_count_72h
               amt_sum_1h amt_sum_6h amt_sum_24h amt_sum_72h
               amt_max_1h amt_max_6h amt_max_24h amt_max_72h
               unique_merchants_24h distinct_countries_24h
               last_txn_datetime last_txn_amount
               acct_running_total acct_running_count;

        /* ---- LAG variables for inter-transaction gap ---- */
        lag_datetime = lag(transaction_datetime);
        lag_amount   = lag(transaction_amount);
        lag_merchant = lag(merchant_id);

        /* Reset all accumulators at the start of each account */
        if first.account_id then do;
            txn_count_1h  = 0; txn_count_6h  = 0;
            txn_count_24h = 0; txn_count_72h = 0;
            amt_sum_1h  = 0; amt_sum_6h  = 0;
            amt_sum_24h = 0; amt_sum_72h = 0;
            amt_max_1h  = 0; amt_max_6h  = 0;
            amt_max_24h = 0; amt_max_72h = 0;
            unique_merchants_24h   = 0;
            distinct_countries_24h = 0;
            last_txn_datetime = .;
            last_txn_amount   = .;
            acct_running_total = 0;
            acct_running_count = 0;
            lag_datetime = .;
            lag_amount   = .;
        end;

        /* Compute time difference in hours from previous transaction */
        if last_txn_datetime ne . then
            hours_since_last = intck('hour', last_txn_datetime,
                                     transaction_datetime);
        else
            hours_since_last = 999;

        /* ---- %DO loop: build windowed features for 1h, 6h, 24h, 72h ---- */
        %let window1 = 1;
        %let window2 = 6;
        %let window3 = 24;
        %let window4 = 72;

        %do i = 1 %to 4;
            /* Increment transaction count for this window */
            if hours_since_last <= &&window&i then
                txn_count_&&window&i = txn_count_&&window&i + 1;

            /* Accumulate transaction amount for this window */
            if hours_since_last <= &&window&i then
                amt_sum_&&window&i = amt_sum_&&window&i + transaction_amount;

            /* Track maximum single transaction in window */
            if hours_since_last <= &&window&i then
                amt_max_&&window&i = max(amt_max_&&window&i, transaction_amount);
        %end;

        /* ---- Derived ratio features ---- */
        if acct_running_count > 0 then
            avg_txn_amount = acct_running_total / acct_running_count;
        else
            avg_txn_amount = transaction_amount;

        /* Amount deviation from account historical average */
        if avg_txn_amount > 0 then
            amount_deviation = transaction_amount / avg_txn_amount;
        else
            amount_deviation = 1;

        /* Velocity ratio: 1-hour count relative to 24-hour count */
        if txn_count_24h > 0 then
            velocity_ratio_1_24 = txn_count_1h / txn_count_24h;
        else
            velocity_ratio_1_24 = 0;

        /* Same-merchant repeat flag within last hour */
        if lag_merchant = merchant_id and hours_since_last <= 1 then
            same_merchant_repeat = 1;
        else
            same_merchant_repeat = 0;

        /* Round-amount flag (amounts like 100, 200, 500, 1000) */
        if mod(transaction_amount, 100) = 0 and transaction_amount >= 100 then
            round_amount_flag = 1;
        else
            round_amount_flag = 0;

        /* Weekend / night transaction flag */
        txn_hour = hour(timepart(transaction_datetime));
        txn_dow  = weekday(datepart(transaction_datetime));
        if txn_dow in (1, 7) or txn_hour < 6 or txn_hour > 22 then
            off_hours_flag = 1;
        else
            off_hours_flag = 0;

        /* Update running accumulators for next iteration */
        acct_running_total = acct_running_total + transaction_amount;
        acct_running_count = acct_running_count + 1;
        last_txn_datetime  = transaction_datetime;
        last_txn_amount    = transaction_amount;

        /* Drop internal-only variables from output */
        drop lag_datetime lag_amount lag_merchant
             last_txn_datetime last_txn_amount
             acct_running_total acct_running_count
             is_current;
    run;

    /* Step 5: Merge customer profile features onto featured transactions */
    proc sort data=&output_ds;
        by account_id;
    run;

    data &output_ds;
        merge &output_ds(in=a)
              cust.customer_profiles(keep=account_id customer_segment
                   account_age_days avg_monthly_spend credit_score
                   country_code risk_rating
                   in=b);
        by account_id;
        if a;

        /* Compute account tenure risk: newer accounts are riskier */
        if account_age_days < 30 then tenure_risk = 3;
        else if account_age_days < 90 then tenure_risk = 2;
        else if account_age_days < 365 then tenure_risk = 1;
        else tenure_risk = 0;

        /* Spending anomaly: compare 24h total to daily average */
        if avg_monthly_spend > 0 then
            spend_anomaly = amt_sum_24h / (avg_monthly_spend / 30);
        else
            spend_anomaly = 0;
    run;

    %put NOTE: Feature engineering complete for &input_ds;

%mend feature_engineering;

/* ========================================================================= */
/* SECTION 3: Rule Engine Macro                                              */
/* ========================================================================= */

/*----------------------------------------------------------------------
  %MACRO rule_engine
  Purpose: Apply 12 configurable fraud detection rules to each
           transaction. Each rule assigns a risk score contribution
           and a rule-hit flag. Uses IF/THEN/ELSE cascading logic
           and PROC SQL with INTO: for aggregate rule hit counts.
----------------------------------------------------------------------*/

%macro rule_engine(input_ds=, output_ds=);

    data &output_ds;
        set &input_ds;

        /* Initialize rule hit flags and risk score accumulators */
        array rule_hit{12} rule_hit_1-rule_hit_12;
        do _r = 1 to 12;
            rule_hit{_r} = 0;
        end;
        rule_score = 0;
        rule_count = 0;

        /* --- Rule 1: High-value single transaction (> $5,000) --- */
        if transaction_amount > 5000 then do;
            rule_hit_1 = 1;
            rule_score = rule_score + 150;
            rule_count = rule_count + 1;
        end;

        /* --- Rule 2: Rapid-fire velocity (>5 txns in 1 hour) --- */
        if txn_count_1h > 5 then do;
            rule_hit_2 = 1;
            rule_score = rule_score + 200;
            rule_count = rule_count + 1;
        end;

        /* --- Rule 3: Amount deviation > 5x account average --- */
        if amount_deviation > 5 then do;
            rule_hit_3 = 1;
            rule_score = rule_score + 180;
            rule_count = rule_count + 1;
        end;

        /* --- Rule 4: Off-hours high-value transaction --- */
        if off_hours_flag = 1 and transaction_amount > 2000 then do;
            rule_hit_4 = 1;
            rule_score = rule_score + 120;
            rule_count = rule_count + 1;
        end;

        /* --- Rule 5: New account with large transaction --- */
        if tenure_risk >= 2 and transaction_amount > 1000 then do;
            rule_hit_5 = 1;
            rule_score = rule_score + 160;
            rule_count = rule_count + 1;
        end;

        /* --- Rule 6: Same merchant repeat within 1 hour --- */
        if same_merchant_repeat = 1 and txn_count_1h > 3 then do;
            rule_hit_6 = 1;
            rule_score = rule_score + 140;
            rule_count = rule_count + 1;
        end;

        /* --- Rule 7: Cross-border transaction with high amount --- */
        if country_code ne transaction_country
           and transaction_amount > 3000 then do;
            rule_hit_7 = 1;
            rule_score = rule_score + 170;
            rule_count = rule_count + 1;
        end;

        /* --- Rule 8: Round-amount structuring pattern --- */
        if round_amount_flag = 1 and txn_count_24h > 3 then do;
            rule_hit_8 = 1;
            rule_score = rule_score + 130;
            rule_count = rule_count + 1;
        end;

        /* --- Rule 9: 24-hour cumulative amount exceeds $10,000 (BSA/AML) --- */
        if amt_sum_24h > 10000 then do;
            rule_hit_9 = 1;
            rule_score = rule_score + 250;
            rule_count = rule_count + 1;
        end;

        /* --- Rule 10: Spending anomaly > 10x monthly average --- */
        if spend_anomaly > 10 then do;
            rule_hit_10 = 1;
            rule_score = rule_score + 190;
            rule_count = rule_count + 1;
        end;

        /* --- Rule 11: 72-hour velocity spike (>20 txns) --- */
        if txn_count_72h > 20 then do;
            rule_hit_11 = 1;
            rule_score = rule_score + 110;
            rule_count = rule_count + 1;
        end;

        /* --- Rule 12: High-risk customer with elevated activity --- */
        if risk_rating = 'HIGH' and txn_count_24h > 5
           and transaction_amount > 1000 then do;
            rule_hit_12 = 1;
            rule_score = rule_score + 220;
            rule_count = rule_count + 1;
        end;

        /* Cap combined rule score at 1000 */
        if rule_score > 1000 then rule_score = 1000;

        drop _r;
    run;

    /* Compute aggregate rule hit counts and store in macro variables */
    proc sql noprint;
        select sum(rule_hit_1),  sum(rule_hit_2),  sum(rule_hit_3),
               sum(rule_hit_4),  sum(rule_hit_5),  sum(rule_hit_6),
               sum(rule_hit_7),  sum(rule_hit_8),  sum(rule_hit_9),
               sum(rule_hit_10), sum(rule_hit_11), sum(rule_hit_12),
               sum(rule_count > 0)
        into :rule1_hits, :rule2_hits, :rule3_hits,
             :rule4_hits, :rule5_hits, :rule6_hits,
             :rule7_hits, :rule8_hits, :rule9_hits,
             :rule10_hits, :rule11_hits, :rule12_hits,
             :total_rule_hits
        from &output_ds;
    quit;

    /* Log rule hit summary to SAS log */
    %put NOTE: ---- Rule Engine Summary ----;
    %put NOTE: Rule 1  (High Value):          &rule1_hits hits;
    %put NOTE: Rule 2  (Rapid Velocity):      &rule2_hits hits;
    %put NOTE: Rule 3  (Amount Deviation):    &rule3_hits hits;
    %put NOTE: Rule 4  (Off-Hours High):      &rule4_hits hits;
    %put NOTE: Rule 5  (New Account Large):   &rule5_hits hits;
    %put NOTE: Rule 6  (Merchant Repeat):     &rule6_hits hits;
    %put NOTE: Rule 7  (Cross-Border):        &rule7_hits hits;
    %put NOTE: Rule 8  (Round Amount):        &rule8_hits hits;
    %put NOTE: Rule 9  (BSA Threshold):       &rule9_hits hits;
    %put NOTE: Rule 10 (Spend Anomaly):       &rule10_hits hits;
    %put NOTE: Rule 11 (72h Velocity):        &rule11_hits hits;
    %put NOTE: Rule 12 (High-Risk Customer):  &rule12_hits hits;
    %put NOTE: Total transactions with 1+ rule hits: &total_rule_hits;

%mend rule_engine;

/* ========================================================================= */
/* SECTION 4: Score Model Macro                                              */
/* ========================================================================= */

/*----------------------------------------------------------------------
  %MACRO score_model
  Purpose: Apply logistic regression model coefficients to the feature
           vector. Computes log-odds, converts to probability via the
           logistic function, and normalizes to a 0-1000 fraud score.
           Blends rule score with model score using configurable weights.
----------------------------------------------------------------------*/

%macro score_model(input_ds=, output_ds=, coeff_ds=);

    /* Load model coefficients from reference table into macro variables */
    data _null_;
        set &coeff_ds;
        call symput(compress('coeff_' || variable_name),
                     put(coefficient, best12.));
    run;

    /* Apply logistic regression scoring to each transaction */
    data &output_ds;
        set &input_ds;

        /* ---- Compute log-odds (linear predictor) ---- */
        log_odds = &coeff_intercept
            + &coeff_txn_count_1h       * txn_count_1h
            + &coeff_txn_count_24h      * txn_count_24h
            + &coeff_amt_sum_24h        * (amt_sum_24h / 1000)
            + &coeff_amount_deviation   * amount_deviation
            + &coeff_velocity_ratio     * velocity_ratio_1_24
            + &coeff_off_hours          * off_hours_flag
            + &coeff_tenure_risk        * tenure_risk
            + &coeff_spend_anomaly      * min(spend_anomaly, 20)
            + &coeff_round_amount       * round_amount_flag
            + &coeff_same_merchant      * same_merchant_repeat;

        /* ---- Convert log-odds to probability via logistic function ---- */
        fraud_probability = 1 / (1 + exp(-log_odds));

        /* ---- Normalize probability to 0-1000 scale ---- */
        model_score = round(fraud_probability * 1000);

        /* Cap model score at boundaries */
        if model_score < 0 then model_score = 0;
        if model_score > 1000 then model_score = 1000;

        /* ---- Blend model score with rule score (60/40 weight) ---- */
        blended_score = round(0.6 * model_score + 0.4 * rule_score);

        /* Apply minimum floor: any rule hit guarantees score >= 100 */
        if rule_count > 0 and blended_score < 100 then
            blended_score = 100;

        /* Apply override: 3+ rules triggered guarantees score >= 500 */
        if rule_count >= 3 then
            blended_score = max(blended_score, 500);

        /* Final score capping */
        if blended_score > 1000 then blended_score = 1000;

        /* Score confidence band classification */
        length score_confidence $10;
        if fraud_probability >= 0.8 then score_confidence = 'VERY_HIGH';
        else if fraud_probability >= 0.5 then score_confidence = 'HIGH';
        else if fraud_probability >= 0.2 then score_confidence = 'MEDIUM';
        else score_confidence = 'LOW';

        /* Add scoring metadata */
        length score_model_version $20;
        score_model_version = "&score_version";
        score_timestamp     = datetime();
        format score_timestamp datetime20.;
    run;

    %put NOTE: Model scoring complete using version &score_version;

%mend score_model;

/* ========================================================================= */
/* SECTION 5: Alert Generation Macro                                         */
/* ========================================================================= */

/*----------------------------------------------------------------------
  %MACRO alert_generation
  Purpose: Route scored transactions into BLOCK, REVIEW, or PASS
           queues based on configurable score thresholds. Creates
           alert records with priority, assigned analyst queue,
           and SLA deadlines for investigation.
----------------------------------------------------------------------*/

%macro alert_generation(input_ds=, block_ds=, review_ds=, pass_ds=,
                        alert_ds=, block_threshold=750,
                        review_threshold=400);

    /* Store configurable thresholds */
    %let _blk_thresh = &block_threshold;
    %let _rev_thresh = &review_threshold;

    /* Route transactions to appropriate queues based on blended score */
    data &block_ds &review_ds &pass_ds;
        set &input_ds;

        length alert_action $10 alert_priority $8
               analyst_queue $20 sla_deadline 8;
        format sla_deadline datetime20.;

        /* ---- BLOCK: immediate transaction block (score >= 750) ---- */
        if blended_score >= &_blk_thresh then do;
            alert_action   = 'BLOCK';
            alert_priority = 'CRITICAL';
            analyst_queue  = 'FRAUD_TIER1';
            sla_deadline   = datetime() + 3600;   /* 1-hour SLA */
            output &block_ds;
        end;

        /* ---- REVIEW: manual review required (score >= 400) ---- */
        else if blended_score >= &_rev_thresh then do;
            alert_action   = 'REVIEW';
            if blended_score >= 600 then alert_priority = 'HIGH';
            else alert_priority = 'MEDIUM';
            analyst_queue  = 'FRAUD_TIER2';
            sla_deadline   = datetime() + 14400;  /* 4-hour SLA */
            output &review_ds;
        end;

        /* ---- PASS: no action required (score < 400) ---- */
        else do;
            alert_action   = 'PASS';
            alert_priority = 'LOW';
            analyst_queue  = 'NONE';
            sla_deadline   = .;
            output &pass_ds;
        end;
    run;

    /* Create consolidated alert log combining BLOCK and REVIEW */
    data &alert_ds;
        set &block_ds(in=blk)
            &review_ds(in=rev);

        length alert_id $30;
        alert_id = catx('_', 'ALT', put(today(), yymmddn8.),
                         put(_n_, z6.));
        alert_run_id   = "&run_id";
        alert_datetime = datetime();
        format alert_datetime datetime20.;
    run;

    /* Capture queue counts via CALL SYMPUT for downstream reporting */
    data _null_;
        set &block_ds nobs=_nblk;
        if _n_ = 1 then call symput('block_count',
                                     strip(put(_nblk, best.)));
        stop;
    run;

    data _null_;
        set &review_ds nobs=_nrev;
        if _n_ = 1 then call symput('review_count',
                                     strip(put(_nrev, best.)));
        stop;
    run;

    data _null_;
        set &pass_ds nobs=_npass;
        if _n_ = 1 then call symput('pass_count',
                                     strip(put(_npass, best.)));
        stop;
    run;

    %let total_alerts = %eval(&block_count + &review_count);

    %put NOTE: ---- Alert Generation Summary ----;
    %put NOTE: BLOCK  transactions: &block_count;
    %put NOTE: REVIEW transactions: &review_count;
    %put NOTE: PASS   transactions: &pass_count;
    %put NOTE: Total alerts generated: &total_alerts;

%mend alert_generation;

/* ========================================================================= */
/* SECTION 6: Main Program Execution                                         */
/* ========================================================================= */

%put NOTE: ===== Fraud Detection Pipeline Started =====;
%put NOTE: Run ID:       &run_id;
%put NOTE: Process Date: &process_date;

/* --- Step 1: Run feature engineering --- */
%feature_engineering(
    input_ds   = txn.transactions,
    output_ds  = work.txn_featured,
    history_ds = txn.transaction_history
);

/* Error check after feature engineering */
%if &syserr > 0 %then %do;
    %let fraud_rc = 1;
    %put ERROR: Feature engineering failed with syserr=&syserr;
    %goto fraud_exit;
%end;

/* --- Step 2: Run rule engine --- */
%rule_engine(
    input_ds  = work.txn_featured,
    output_ds = work.txn_ruled
);

/* Error check after rule engine */
%if &syserr > 0 %then %do;
    %let fraud_rc = 2;
    %put ERROR: Rule engine failed with syserr=&syserr;
    %goto fraud_exit;
%end;

/* --- Step 3: Score transactions with logistic regression model --- */
%score_model(
    input_ds  = work.txn_ruled,
    output_ds = work.txn_scored,
    coeff_ds  = mdl.model_coefficients
);

/* Error check after model scoring */
%if &syserr > 0 %then %do;
    %let fraud_rc = 3;
    %put ERROR: Model scoring failed with syserr=&syserr;
    %goto fraud_exit;
%end;

/* --- Step 4: Generate alerts and route to queues --- */
%alert_generation(
    input_ds         = work.txn_scored,
    block_ds         = alert.blocked_transactions,
    review_ds        = alert.review_queue,
    pass_ds          = work.passed_transactions,
    alert_ds         = alert.fraud_alerts,
    block_threshold  = 750,
    review_threshold = 400
);

/* Error check after alert generation */
%if &syserr > 0 %then %do;
    %let fraud_rc = 4;
    %put ERROR: Alert generation failed with syserr=&syserr;
    %goto fraud_exit;
%end;

/* ========================================================================= */
/* SECTION 7: Daily Fraud Metrics Dashboard                                  */
/* ========================================================================= */

/* Generate daily summary metrics aggregated by transaction date */
proc sql;
    create table alert.daily_fraud_metrics as
    select
        datepart(transaction_datetime)
            as txn_date format=date9.,
        count(*)
            as total_transactions,
        sum(case when alert_action = 'BLOCK'  then 1 else 0 end)
            as blocked_count,
        sum(case when alert_action = 'REVIEW' then 1 else 0 end)
            as review_count,
        sum(case when alert_action = 'PASS'   then 1 else 0 end)
            as passed_count,
        sum(case when rule_count > 0 then 1 else 0 end)
            as rule_hit_count,
        avg(blended_score)
            as avg_fraud_score format=8.2,
        max(blended_score)
            as max_fraud_score,
        sum(transaction_amount)
            as total_amount format=dollar20.2,
        sum(case when alert_action = 'BLOCK'
            then transaction_amount else 0 end)
            as blocked_amount format=dollar20.2,
        calculated blocked_count
            / calculated total_transactions * 100
            as block_rate format=8.4,
        calculated rule_hit_count
            / calculated total_transactions * 100
            as rule_hit_rate format=8.4
    from work.txn_scored
    group by calculated txn_date
    order by calculated txn_date;
quit;

/* Rule effectiveness analysis: hits and true blocks per rule */
proc sql;
    create table work.rule_effectiveness as
    select 'Rule_01_High_Value'       as rule_name length=30,
           sum(rule_hit_1)            as hits,
           sum(rule_hit_1 * (alert_action = 'BLOCK')) as true_blocks
    from work.txn_scored
    union all
    select 'Rule_02_Rapid_Velocity',
           sum(rule_hit_2),
           sum(rule_hit_2 * (alert_action = 'BLOCK'))
    from work.txn_scored
    union all
    select 'Rule_03_Amount_Deviation',
           sum(rule_hit_3),
           sum(rule_hit_3 * (alert_action = 'BLOCK'))
    from work.txn_scored
    union all
    select 'Rule_04_Off_Hours',
           sum(rule_hit_4),
           sum(rule_hit_4 * (alert_action = 'BLOCK'))
    from work.txn_scored
    union all
    select 'Rule_05_New_Account',
           sum(rule_hit_5),
           sum(rule_hit_5 * (alert_action = 'BLOCK'))
    from work.txn_scored
    union all
    select 'Rule_06_Merchant_Repeat',
           sum(rule_hit_6),
           sum(rule_hit_6 * (alert_action = 'BLOCK'))
    from work.txn_scored
    union all
    select 'Rule_07_Cross_Border',
           sum(rule_hit_7),
           sum(rule_hit_7 * (alert_action = 'BLOCK'))
    from work.txn_scored
    union all
    select 'Rule_08_Round_Amount',
           sum(rule_hit_8),
           sum(rule_hit_8 * (alert_action = 'BLOCK'))
    from work.txn_scored
    union all
    select 'Rule_09_BSA_Threshold',
           sum(rule_hit_9),
           sum(rule_hit_9 * (alert_action = 'BLOCK'))
    from work.txn_scored
    union all
    select 'Rule_10_Spend_Anomaly',
           sum(rule_hit_10),
           sum(rule_hit_10 * (alert_action = 'BLOCK'))
    from work.txn_scored
    union all
    select 'Rule_11_72h_Velocity',
           sum(rule_hit_11),
           sum(rule_hit_11 * (alert_action = 'BLOCK'))
    from work.txn_scored
    union all
    select 'Rule_12_HighRisk_Cust',
           sum(rule_hit_12),
           sum(rule_hit_12 * (alert_action = 'BLOCK'))
    from work.txn_scored;
quit;

/* Score distribution report */
proc means data=work.txn_scored
           n mean std min p25 median p75 p90 p95 p99 max;
    var blended_score model_score rule_score
        transaction_amount fraud_probability;
    title 'Fraud Detection - Score Distribution Summary';
run;
title;

/* ========================================================================= */
/* SECTION 8: Error Handling and Completion                                   */
/* ========================================================================= */

%fraud_exit:

%if &fraud_rc ne 0 %then %do;
    %put ERROR: ==================================================;
    %put ERROR: Fraud Detection Pipeline FAILED;
    %put ERROR: Return Code: &fraud_rc;
    %put ERROR: Run ID:      &run_id;
    %put ERROR: ==================================================;

    /* Write error log record to alert library */
    data alert.pipeline_errors;
        length run_id $40 error_step $30 error_code 8
               error_message $200;
        run_id        = "&run_id";
        error_step    = "STEP_&fraud_rc";
        error_code    = &fraud_rc;
        error_message = "Pipeline failed at step &fraud_rc - syserr=&syserr";
        error_datetime = datetime();
        format error_datetime datetime20.;
    run;
%end;

%else %do;
    %put NOTE: ==================================================;
    %put NOTE: Fraud Detection Pipeline COMPLETED SUCCESSFULLY;
    %put NOTE: Run ID:        &run_id;
    %put NOTE: Process Date:  &process_date;
    %put NOTE: Blocked:       &block_count transactions;
    %put NOTE: Review:        &review_count transactions;
    %put NOTE: Passed:        &pass_count transactions;
    %put NOTE: Total Alerts:  &total_alerts;
    %put NOTE: ==================================================;

    /* Write completion flag file for downstream batch scheduler */
    data _null_;
        file '/fraud/output/alerts/completion_flag.txt';
        put "RUN_ID=&run_id";
        put "STATUS=SUCCESS";
        put "PROCESS_DATE=&process_date";
        put "BLOCK_COUNT=&block_count";
        put "REVIEW_COUNT=&review_count";
        put "PASS_COUNT=&pass_count";
        put "COMPLETION_TIME=" datetime() datetime20.;
    run;
%end;

/* ========================================================================= */
/* SECTION 9: Cleanup                                                        */
/* ========================================================================= */

/* Delete intermediate work datasets */
proc datasets lib=work nolist;
    delete _txn_sorted _hist_sorted _txn_combined
           txn_featured txn_ruled txn_scored
           passed_transactions rule_effectiveness;
quit;

/* Reset OPTIONS to defaults */
options nomprint nomlogic nosymbolgen;

%put NOTE: ===== Fraud Detection Pipeline Ended =====;
%put NOTE: Timestamp: %sysfunc(datetime(), datetime20.);
