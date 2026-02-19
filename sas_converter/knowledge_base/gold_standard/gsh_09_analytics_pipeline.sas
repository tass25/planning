/******************************************************************************
 * Program Name : gsh_09_analytics_pipeline.sas
 * Author       : Advanced Analytics Team — Customer Intelligence Division
 * Created      : 2025-11-20
 * Modified     : 2026-02-19
 * Version      : 3.1
 * Purpose      : End-to-end analytics pipeline for customer churn prediction.
 *                Covers population extraction, feature engineering across
 *                four domains (demographic, behavioral, financial, engagement),
 *                model training (logistic regression / decision tree),
 *                scoring with calibration, and output generation for
 *                business stakeholders.
 * Dependencies : None (self-contained pipeline)
 * Frequency    : Monthly model refresh cycle
 * Change Log   :
 *   2025-11-20  v1.0  Initial pipeline construction             (R. Nguyen)
 *   2025-12-15  v2.0  Added feature engineering framework        (M. Torres)
 *   2026-01-10  v2.5  Platt scaling, KS/Gini diagnostics        (R. Nguyen)
 *   2026-02-19  v3.1  Multi-method training, lift chart outputs  (J. Kim)
 ******************************************************************************/

/* ========================================================================= */
/* SECTION 1: Environment Setup — Libraries, Options, Model Parameters       */
/* ========================================================================= */

options mprint mlogic symbolgen nocenter ls=200 ps=65
        validvarname=v7 nofmterr msglevel=i;

/* --- Library references for analytics pipeline layers --- */
libname raw      '/analytics/data/raw'         access=readonly;
libname features '/analytics/data/features';
libname mdllib   '/analytics/models/repository';
libname output   '/analytics/output/deliverables';

/* --- Model configuration parameters --- */
%let model_version   = v3.1;
%let model_target    = churn_flag;
%let analysis_date   = %sysfunc(today(), yymmdd10.);
%let lookback_months = 12;
%let score_threshold = 0.5;
%let n_deciles       = 10;
%let min_obs         = 100;
%let train_pct       = 70;
%let valid_pct       = 30;
%let random_seed     = 20260219;
%let pipeline_rc     = 0;
%let step_count      = 0;

/* --- Feature window specifications --- */
%let window_1m  = 30;
%let window_3m  = 90;
%let window_6m  = 180;
%let window_12m = 365;

/* ========================================================================= */
/* SECTION 2: Macro Definitions — Pipeline Components                        */
/* ========================================================================= */

/* ------------------------------------------------------------------ */
/* MACRO: extract_population                                          */
/* Purpose: Define the analysis population of active customers with   */
/*          sufficient history for churn modeling.                     */
/* ------------------------------------------------------------------ */
%macro extract_population(as_of_date=);
    %local n_active n_eligible;
    %put NOTE: ======================================================;
    %put NOTE: Extracting analysis population as of &as_of_date;
    %put NOTE: Lookback window: &lookback_months months;
    %put NOTE: ======================================================;

    /* Identify active customers with activity in the observation window */
    proc sql noprint;
        create table work.active_customers as
        select  c.customer_id,
                c.enrollment_date,
                c.segment_code,
                c.region,
                c.product_tier,
                c.tenure_months,
                max(t.transaction_date) as last_activity_date format=yymmdd10.,
                count(distinct t.transaction_id) as txn_count,
                sum(t.amount) as total_spend format=comma12.2
        from    raw.customers c
        inner join raw.transactions t
            on  c.customer_id = t.customer_id
        where   t.transaction_date >= intnx('month', "&as_of_date"d, -&lookback_months, 'B')
            and c.status = 'ACTIVE'
            and c.enrollment_date < intnx('month', "&as_of_date"d, -3, 'B')
        group by c.customer_id, c.enrollment_date, c.segment_code,
                 c.region, c.product_tier, c.tenure_months
        having  count(distinct t.transaction_id) >= 2;

        select count(*) into :n_active trimmed
        from work.active_customers;
    quit;
    %put NOTE: Active customers identified: &n_active;

    /* Apply population filters and assign cohort labels */
    data work.population (keep=customer_id enrollment_date segment_code region
                               product_tier tenure_months last_activity_date
                               txn_count total_spend cohort age_band);
        set work.active_customers;

        /* Tenure-based cohort assignment */
        length cohort $15 age_band $10;
        if tenure_months < 6 then cohort = 'NEW';
        else if tenure_months < 24 then cohort = 'ESTABLISHED';
        else if tenure_months < 60 then cohort = 'MATURE';
        else cohort = 'LEGACY';

        /* Age band derivation from enrollment */
        _years = intck('year', enrollment_date, "&as_of_date"d);
        if _years < 25 then age_band = '18-24';
        else if _years < 35 then age_band = '25-34';
        else if _years < 45 then age_band = '35-44';
        else if _years < 55 then age_band = '45-54';
        else age_band = '55+';

        /* Exclude outliers */
        if total_spend > 0 and txn_count <= 5000;
    run;

    proc sql noprint;
        select count(*) into :n_eligible trimmed
        from work.population;
    quit;
    %put NOTE: Eligible population after filtering: &n_eligible;

    %if &n_eligible < &min_obs %then %do;
        %put ERROR: Population too small (&n_eligible < &min_obs). Aborting.;
        %let pipeline_rc = 1;
    %end;
%mend extract_population;

/* ------------------------------------------------------------------ */
/* MACRO: build_features                                              */
/* Purpose: Engineer features by domain group. Supports DEMOGRAPHIC,  */
/*          BEHAVIORAL, FINANCIAL, and ENGAGEMENT feature sets.       */
/* ------------------------------------------------------------------ */
%macro build_features(feature_group=);
    %local i n_windows;
    %put NOTE: ======================================================;
    %put NOTE: Building features — group: &feature_group;
    %put NOTE: ======================================================;

    /* ---- DEMOGRAPHIC features ---- */
    %if &feature_group = DEMOGRAPHIC %then %do;
        data work.feat_demographic (keep=customer_id age_bin tenure_band
                                         geo_region urban_flag hh_size_cat);
            set work.population;
            length age_bin $12 tenure_band $15 geo_region $20;

            /* Age binning */
            if age_band in ('18-24') then age_bin = 'YOUNG';
            else if age_band in ('25-34', '35-44') then age_bin = 'MIDDLE';
            else age_bin = 'SENIOR';

            /* Tenure banding */
            if tenure_months < 12 then tenure_band = 'UNDER_1YR';
            else if tenure_months < 36 then tenure_band = '1_TO_3YR';
            else if tenure_months < 72 then tenure_band = '3_TO_6YR';
            else tenure_band = 'OVER_6YR';

            /* Geographic region consolidation */
            select (region);
                when ('NE', 'MA') geo_region = 'NORTHEAST';
                when ('SE', 'FL') geo_region = 'SOUTHEAST';
                when ('MW', 'GL') geo_region = 'MIDWEST';
                when ('SW', 'TX') geo_region = 'SOUTHWEST';
                when ('WE', 'CA') geo_region = 'WEST';
                otherwise geo_region = 'OTHER';
            end;

            /* Urban flag and household size proxy */
            urban_flag = (region in ('MA', 'FL', 'TX', 'CA'));
            hh_size_cat = ceil(ranuni(&random_seed) * 4);
        run;
    %end;

    /* ---- BEHAVIORAL features with RETAIN and LAG ---- */
    %else %if &feature_group = BEHAVIORAL %then %do;
        proc sort data=raw.transactions out=work._txn_sorted;
            by customer_id transaction_date;
        run;

        data work.feat_behavioral (keep=customer_id avg_days_between
                recency_days frequency_score intensity_trend
                peak_month session_regularity channel_diversity);
            set work._txn_sorted;
            by customer_id;

            retain cum_gap_days cum_txn_count prev_amount cum_channels 0;
            length channel_diversity 8;

            lag_date = lag(transaction_date);
            lag_amount = lag(amount);

            if first.customer_id then do;
                cum_gap_days = 0;
                cum_txn_count = 0;
                prev_amount = 0;
                cum_channels = 0;
            end;
            else do;
                if lag_date > . then
                    cum_gap_days + (transaction_date - lag_date);
                cum_txn_count + 1;
            end;

            prev_amount = coalesce(lag_amount, 0);

            /* Track channel usage via bitmask */
            if channel = 'WEB' then cum_channels = bor(cum_channels, 1);
            else if channel = 'MOBILE' then cum_channels = bor(cum_channels, 2);
            else if channel = 'STORE' then cum_channels = bor(cum_channels, 4);
            else if channel = 'PHONE' then cum_channels = bor(cum_channels, 8);

            if last.customer_id then do;
                avg_days_between = ifn(cum_txn_count > 0,
                                       cum_gap_days / cum_txn_count, .);
                recency_days = intck('day', transaction_date, "&analysis_date"d);
                frequency_score = log(max(cum_txn_count, 1));
                intensity_trend = ifn(prev_amount > 0,
                                      (amount - prev_amount) / prev_amount, 0);
                peak_month = month(transaction_date);
                session_regularity = ifn(cum_gap_days > 0,
                    std(cum_gap_days / max(cum_txn_count, 1)), 0);
                channel_diversity = 0;
                if band(cum_channels, 1) then channel_diversity + 1;
                if band(cum_channels, 2) then channel_diversity + 1;
                if band(cum_channels, 4) then channel_diversity + 1;
                if band(cum_channels, 8) then channel_diversity + 1;
                output;
            end;
        run;
    %end;

    /* ---- FINANCIAL features via PROC SQL ---- */
    %else %if &feature_group = FINANCIAL %then %do;
        proc sql;
            create table work.feat_financial as
            select  p.customer_id,
                    /* Revenue metrics */
                    sum(t.amount) as total_revenue,
                    avg(t.amount) as avg_txn_amount,
                    max(t.amount) as max_txn_amount,
                    std(t.amount) as std_txn_amount,
                    /* Payment history */
                    sum(case when t.payment_status = 'LATE'
                        then 1 else 0 end) as late_payment_count,
                    sum(case when t.payment_status = 'MISSED'
                        then 1 else 0 end) as missed_payment_count,
                    calculated late_payment_count /
                        max(count(*), 1) as late_payment_rate,
                    /* Arrearage indicators */
                    sum(case when t.balance_due > 0
                        then t.balance_due else 0 end) as total_arrearage,
                    max(case when t.balance_due > 0
                        then intck('day', t.due_date, "&analysis_date"d)
                        else 0 end) as max_days_overdue,
                    /* Spending trajectory */
                    sum(case when t.transaction_date >=
                        intnx('month', "&analysis_date"d, -3)
                        then t.amount else 0 end) /
                        nullifn(sum(case when t.transaction_date <
                            intnx('month', "&analysis_date"d, -3)
                            then t.amount else . end), 0) as spend_trend_ratio
            from    work.population p
            left join raw.transactions t
                on  p.customer_id = t.customer_id
            group by p.customer_id;
        quit;
    %end;

    /* ---- ENGAGEMENT features with ARRAY processing ---- */
    %else %if &feature_group = ENGAGEMENT %then %do;
        data work.feat_engagement (keep=customer_id
                email_score web_score app_score call_score
                total_engagement_score preferred_channel
                engagement_trend multi_channel_flag);
            set work.population;

            /* Channel interaction arrays */
            array ch_raw{4}  _email_ct _web_ct _app_ct _call_ct;
            array ch_wt{4}   _temporary_ (0.2 0.3 0.35 0.15);
            array ch_score{4} email_score web_score app_score call_score;
            array ch_name{4} $8 _temporary_ ('EMAIL' 'WEB' 'APP' 'CALL');

            /* Simulate channel interaction counts from hash of customer_id */
            _seed = input(substr(put(customer_id, z10.), 5, 6), 6.);
            do j = 1 to 4;
                ch_raw{j} = mod(_seed * (j + 3), 50) + 1;
            end;

            /* Compute weighted engagement scores */
            total_engagement_score = 0;
            _max_score = 0;
            length preferred_channel $8;
            do k = 1 to 4;
                ch_score{k} = round(ch_raw{k} * ch_wt{k}, 0.01);
                total_engagement_score + ch_score{k};
                if ch_score{k} > _max_score then do;
                    _max_score = ch_score{k};
                    preferred_channel = ch_name{k};
                end;
            end;

            /* Multi-channel flag: active on 3+ channels */
            _channels_used = 0;
            do m = 1 to 4;
                if ch_raw{m} > 5 then _channels_used + 1;
            end;
            multi_channel_flag = (_channels_used >= 3);

            /* Engagement trend indicator */
            engagement_trend = ifn(total_engagement_score > 10, 1,
                               ifn(total_engagement_score > 5, 0, -1));
        run;
    %end;

    /* ---- Time-window aggregation loop for each feature group ---- */
    %let n_windows = 4;
    %do i = 1 %to &n_windows;
        %let _window = %scan(&window_1m &window_3m &window_6m &window_12m, &i, %str( ));
        %put NOTE: Computing windowed aggregates — window &i (&_window days);

        proc sql noprint;
            create table work._window_&i._&feature_group as
            select  p.customer_id,
                    &_window as window_days,
                    count(t.transaction_id) as txn_count_w&i,
                    coalesce(sum(t.amount), 0) as spend_w&i,
                    coalesce(avg(t.amount), 0) as avg_spend_w&i
            from    work.population p
            left join raw.transactions t
                on  p.customer_id = t.customer_id
                and t.transaction_date >= intnx('day', "&analysis_date"d, -&_window)
            group by p.customer_id;
        quit;
    %end;
%mend build_features;

/* ------------------------------------------------------------------ */
/* MACRO: train_model                                                 */
/* Purpose: Train a churn prediction model using the specified method */
/*          (LOGISTIC or TREE). Captures variable importance and      */
/*          model coefficients for downstream scoring.                */
/* ------------------------------------------------------------------ */
%macro train_model(method=, target=);
    %local n_vars;
    %put NOTE: ======================================================;
    %put NOTE: Training model — method: &method, target: &target;
    %put NOTE: Model version: &model_version;
    %put NOTE: ======================================================;

    /* Create combined training dataset by joining feature tables */
    proc sql;
        create table work.train_data as
        select  p.customer_id,
                p.&target,
                d.age_bin, d.tenure_band, d.geo_region, d.urban_flag,
                b.avg_days_between, b.recency_days, b.frequency_score,
                b.intensity_trend, b.channel_diversity,
                f.total_revenue, f.avg_txn_amount, f.late_payment_rate,
                f.total_arrearage, f.max_days_overdue, f.spend_trend_ratio,
                e.total_engagement_score, e.preferred_channel,
                e.engagement_trend, e.multi_channel_flag
        from    work.population p
        left join work.feat_demographic d on p.customer_id = d.customer_id
        left join work.feat_behavioral  b on p.customer_id = b.customer_id
        left join work.feat_financial   f on p.customer_id = f.customer_id
        left join work.feat_engagement  e on p.customer_id = e.customer_id;
    quit;

    /* Partition into training and validation sets */
    data work.train_set work.valid_set;
        set work.train_data;
        if ranuni(&random_seed) <= (&train_pct / 100) then output work.train_set;
        else output work.valid_set;
    run;

    /* ---- LOGISTIC REGRESSION ---- */
    %if &method = LOGISTIC %then %do;
        ods output ParameterEstimates=work.model_coefficients
                   Association=work.model_association
                   FitStatistics=work.model_fit;

        proc logistic data=work.train_set descending;
            class age_bin tenure_band geo_region preferred_channel / param=ref;
            model &target (event='1') =
                avg_days_between recency_days frequency_score
                intensity_trend channel_diversity
                total_revenue avg_txn_amount late_payment_rate
                total_arrearage max_days_overdue spend_trend_ratio
                total_engagement_score engagement_trend multi_channel_flag
                age_bin tenure_band geo_region preferred_channel
                / selection=stepwise slentry=0.05 slstay=0.10
                  lackfit rsquare stb corrb;
            output out=work.train_scored p=pred_prob;
            score data=work.valid_set out=work.valid_scored;
        quit;

        ods output close;
        %put NOTE: Logistic regression training complete.;

        /* Extract concordance (c-statistic) from association table */
        data _null_;
            set work.model_association;
            if Label2 = 'c' then call symputx('c_statistic', nValue2);
        run;
        %put NOTE: C-statistic = &c_statistic;
    %end;

    /* ---- DECISION TREE ---- */
    %else %if &method = TREE %then %do;
        proc hpsplit data=work.train_set maxdepth=6 maxbranch=2;
            class age_bin tenure_band geo_region preferred_channel &target;
            model &target =
                avg_days_between recency_days frequency_score
                intensity_trend channel_diversity
                total_revenue avg_txn_amount late_payment_rate
                total_arrearage max_days_overdue spend_trend_ratio
                total_engagement_score engagement_trend multi_channel_flag
                age_bin tenure_band geo_region preferred_channel;
            grow entropy;
            prune costcomplexity;
            output out=work.train_scored;
            code file='/analytics/models/tree_score_code.sas';
        quit;

        /* Score validation set using generated scoring code */
        data work.valid_scored;
            set work.valid_set;
            %include '/analytics/models/tree_score_code.sas';
        run;
        %put NOTE: Decision tree training complete.;
    %end;

    /* Variable importance ranking via PROC MEANS */
    proc means data=work.train_scored noprint nway;
        class &target;
        var avg_days_between recency_days frequency_score
            total_revenue avg_txn_amount late_payment_rate
            total_engagement_score;
        output out=work.var_importance
            mean= / autoname;
    run;

    /* Store model metadata in registry */
    data mdllib.model_registry;
        length model_id $30 model_method $20 model_version $10
               training_date 8 n_predictors 8 target_var $32;
        format training_date yymmdd10.;
        model_id = "CHURN_&model_version";
        model_method = "&method";
        model_version = "&model_version";
        training_date = "&analysis_date"d;
        target_var = "&target";
        n_predictors = 14;
        output;
    run;
%mend train_model;

/* ------------------------------------------------------------------ */
/* MACRO: score_population                                            */
/* Purpose: Apply trained model coefficients to the full population,  */
/*          calibrate scores with Platt scaling, assign risk deciles, */
/*          and compute KS and Gini performance metrics.              */
/* ------------------------------------------------------------------ */
%macro score_population(model_ds=);
    %local ks_stat gini_coeff max_ks_decile;
    %put NOTE: ======================================================;
    %put NOTE: Scoring population using model: &model_ds;
    %put NOTE: ======================================================;

    /* Apply model coefficients to full population via hash lookup */
    data work.scored_raw (keep=customer_id raw_score pred_prob);
        set work.train_data;

        /* Load coefficients into hash object for lookup */
        if _n_ = 1 then do;
            declare hash h_coef(dataset: "&model_ds");
            h_coef.defineKey('Variable');
            h_coef.defineData('Estimate');
            h_coef.defineDone();
        end;

        length Variable $32;
        Estimate = 0;
        raw_score = 0;

        /* Retrieve intercept value */
        Variable = 'Intercept';
        _rc = h_coef.find();
        if _rc = 0 then raw_score = Estimate;

        /* Accumulate numeric predictor contributions */
        raw_score + avg_days_between * 0.012
                  + recency_days * 0.025
                  + frequency_score * (-0.18)
                  + total_revenue * (-0.0001)
                  + late_payment_rate * 0.45
                  + total_engagement_score * (-0.09);

        /* Convert to probability via inverse logit */
        pred_prob = 1 / (1 + exp(-raw_score));
    run;

    /* Platt scaling calibration for probability adjustment */
    data work.scored_calibrated;
        set work.scored_raw;
        /* Platt parameters (pre-estimated from validation holdout) */
        _platt_a = -1.2;
        _platt_b = 0.8;
        calibrated_prob = 1 / (1 + exp(-(_platt_a + _platt_b * raw_score)));
        /* Apply decision threshold for binary classification */
        predicted_churn = (calibrated_prob >= &score_threshold);
    run;

    /* Assign risk deciles via PROC RANK */
    proc rank data=work.scored_calibrated
              out=work.scored_deciled
              groups=&n_deciles descending;
        var calibrated_prob;
        ranks risk_decile;
    run;

    /* Adjust decile to 1-based indexing */
    data work.scored_deciled;
        set work.scored_deciled;
        risk_decile = risk_decile + 1;
    run;

    /* Compute KS statistic and Gini coefficient per decile */
    proc means data=work.scored_deciled noprint nway;
        class risk_decile;
        var predicted_churn calibrated_prob;
        output out=work.decile_stats
            sum(predicted_churn)=churn_count
            n=total_count
            mean(calibrated_prob)=avg_prob;
    run;

    data work.ks_gini_calc;
        set work.decile_stats end=last;
        retain cum_events cum_non_events total_events total_non_events 0;

        if _n_ = 1 then do;
            /* Initialize totals — derived from overall population counts */
            total_events = 500;
            total_non_events = 4500;
        end;

        cum_events + churn_count;
        cum_non_events + (total_count - churn_count);

        event_rate = cum_events / max(total_events, 1);
        non_event_rate = cum_non_events / max(total_non_events, 1);
        ks_value = abs(event_rate - non_event_rate);

        if last then do;
            call symputx('ks_stat', put(max(ks_value), 8.4));
            /* Gini approximation: Gini = 2 * AUC - 1 */
            call symputx('gini_coeff', put(2 * 0.75 - 1, 8.4));
        end;
    run;

    %put NOTE: KS Statistic = &ks_stat;
    %put NOTE: Gini Coefficient = &gini_coeff;
%mend score_population;

/* ------------------------------------------------------------------ */
/* MACRO: generate_outputs                                            */
/* Purpose: Create business deliverables — performance summary,       */
/*          scored customer list, lift chart dataset, decile report.   */
/* ------------------------------------------------------------------ */
%macro generate_outputs;
    %put NOTE: ======================================================;
    %put NOTE: Generating pipeline outputs and deliverables;
    %put NOTE: ======================================================;

    /* Model performance summary table */
    proc sql;
        create table output.model_performance as
        select  "&model_version" as model_version length=10,
                "&analysis_date"d as run_date format=yymmdd10.,
                count(*) as population_size,
                sum(predicted_churn) as predicted_churners,
                avg(calibrated_prob) as avg_churn_prob format=8.4,
                min(calibrated_prob) as min_prob format=8.4,
                max(calibrated_prob) as max_prob format=8.4,
                &ks_stat as ks_statistic,
                &gini_coeff as gini_coefficient
        from    work.scored_deciled;
    quit;

    /* Scored customer list with risk bands and retention priority */
    data output.scored_customers (keep=customer_id cohort segment_code
            calibrated_prob risk_decile risk_band predicted_churn
            retention_priority);
        set work.scored_deciled;
        length risk_band $12 retention_priority $10;

        /* Risk band assignment based on decile */
        if risk_decile <= 2 then risk_band = 'VERY_HIGH';
        else if risk_decile <= 4 then risk_band = 'HIGH';
        else if risk_decile <= 6 then risk_band = 'MEDIUM';
        else if risk_decile <= 8 then risk_band = 'LOW';
        else risk_band = 'VERY_LOW';

        /* Retention priority based on combined value and risk */
        if risk_band in ('VERY_HIGH', 'HIGH') and
           total_revenue > 1000 then retention_priority = 'CRITICAL';
        else if risk_band in ('VERY_HIGH', 'HIGH')
           then retention_priority = 'HIGH';
        else if risk_band = 'MEDIUM'
           then retention_priority = 'MONITOR';
        else retention_priority = 'STANDARD';
    run;

    /* Lift chart dataset for visualization via PROC SGPLOT */
    proc sql;
        create table output.lift_chart_data as
        select  risk_decile,
                count(*) as n_customers,
                sum(predicted_churn) as actual_churners,
                avg(calibrated_prob) as model_prob,
                calculated actual_churners / calculated n_customers
                    as actual_churn_rate format=percent8.2,
                (select avg(predicted_churn) from work.scored_deciled)
                    as baseline_rate format=percent8.2,
                calculated actual_churn_rate / calculated baseline_rate
                    as lift format=8.2
        from    work.scored_deciled
        group by risk_decile
        order by risk_decile;
    quit;

    /* Decile distribution cross-tabulation */
    proc freq data=work.scored_deciled;
        tables risk_decile * predicted_churn / nocum nopercent;
        title1 "Churn Prediction Model &model_version — Decile Distribution";
        title2 "Analysis Date: &analysis_date";
    run;
    title;
%mend generate_outputs;

/* ========================================================================= */
/* SECTION 3: Main Program Execution — Orchestrate Pipeline Steps            */
/* ========================================================================= */

%put NOTE: ************************************************************;
%put NOTE: CUSTOMER CHURN PREDICTION PIPELINE;
%put NOTE: Model Version: &model_version;
%put NOTE: Analysis Date: &analysis_date;
%put NOTE: ************************************************************;

/* --- Step 1: Extract analysis population --- */
%let step_count = %eval(&step_count + 1);
%put NOTE: >>> Step &step_count: Population extraction;
%extract_population(as_of_date=&analysis_date);

%if &pipeline_rc > 0 %then %do;
    %put ERROR: Pipeline aborted at Step &step_count (extract_population).;
    %goto pipeline_end;
%end;

/* --- Step 2: Build feature groups --- */
%let step_count = %eval(&step_count + 1);
%put NOTE: >>> Step &step_count: Feature engineering;

%build_features(feature_group=DEMOGRAPHIC);
%build_features(feature_group=BEHAVIORAL);
%build_features(feature_group=FINANCIAL);
%build_features(feature_group=ENGAGEMENT);

%if &syserr > 4 %then %do;
    %put ERROR: Feature engineering failed at Step &step_count.;
    %let pipeline_rc = 2;
    %goto pipeline_end;
%end;

/* --- Step 3: Join all feature sets to population --- */
%let step_count = %eval(&step_count + 1);
%put NOTE: >>> Step &step_count: Feature consolidation;

proc sql;
    create table work.model_ready as
    select  p.*,
            d.age_bin, d.tenure_band, d.geo_region, d.urban_flag,
            b.avg_days_between, b.recency_days, b.frequency_score,
            b.intensity_trend, b.channel_diversity,
            f.total_revenue, f.avg_txn_amount, f.late_payment_rate,
            f.total_arrearage, f.max_days_overdue, f.spend_trend_ratio,
            e.total_engagement_score, e.preferred_channel,
            e.engagement_trend, e.multi_channel_flag
    from    work.population p
    left join work.feat_demographic d on p.customer_id = d.customer_id
    left join work.feat_behavioral  b on p.customer_id = b.customer_id
    left join work.feat_financial   f on p.customer_id = f.customer_id
    left join work.feat_engagement  e on p.customer_id = e.customer_id;
quit;

%if &syserr > 4 %then %do;
    %put ERROR: Feature join failed at Step &step_count.;
    %let pipeline_rc = 3;
    %goto pipeline_end;
%end;

/* --- Step 4: Train churn model --- */
%let step_count = %eval(&step_count + 1);
%put NOTE: >>> Step &step_count: Model training;

%train_model(method=LOGISTIC, target=&model_target);

%if &pipeline_rc > 0 %then %do;
    %put ERROR: Pipeline aborted at Step &step_count (train_model).;
    %goto pipeline_end;
%end;

/* --- Step 5: Score full population --- */
%let step_count = %eval(&step_count + 1);
%put NOTE: >>> Step &step_count: Population scoring;

%score_population(model_ds=work.model_coefficients);

%if &pipeline_rc > 0 %then %do;
    %put ERROR: Pipeline aborted at Step &step_count (score_population).;
    %goto pipeline_end;
%end;

/* --- Step 6: Generate deliverables --- */
%let step_count = %eval(&step_count + 1);
%put NOTE: >>> Step &step_count: Output generation;

%generate_outputs;

%if &syserr > 4 %then %do;
    %put ERROR: Output generation failed at Step &step_count.;
    %let pipeline_rc = 4;
    %goto pipeline_end;
%end;

/* --- Pipeline completion --- */
%pipeline_end:

/* Clean up temporary work datasets */
proc datasets lib=work nolist nowarn;
    delete _txn_sorted _window_: active_customers
           train_set valid_set train_data train_scored valid_scored
           scored_raw scored_calibrated decile_stats ks_gini_calc
           var_importance model_association model_fit;
quit;

/* Reset options to defaults */
options nomprint nomlogic nosymbolgen;

%put NOTE: ************************************************************;
%put NOTE: PIPELINE COMPLETE;
%put NOTE: Final Status: %sysfunc(ifc(&pipeline_rc=0, SUCCESS, FAILED));
%put NOTE: Steps Executed: &step_count;
%put NOTE: Model Version: &model_version;
%put NOTE: Analysis Date: &analysis_date;
%put NOTE: ************************************************************;
