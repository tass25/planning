/******************************************************************************
 * Program: gsm_15_ab_testing.sas
 * Purpose: A/B testing analysis pipeline for digital experiments
 *          Defines test groups, computes summary statistics, tests for
 *          significance, and generates experiment conclusion reports
 * Author:  Product Analytics Team
 * Date:    2026-02-19
 ******************************************************************************/

/* --- Library references for experiment data --- */
libname raw     '/data/experiments/raw';
libname staging '/data/experiments/staging';
libname tgt     '/data/experiments/target';

options mprint nocenter;

/* -----------------------------------------------------------------------
   STEP 1: Define test/control groups from assignment log
   ----------------------------------------------------------------------- */
data staging.experiment_groups;
    set raw.assignment_log;
    where experiment_id = 'EXP-2026-042';
    length group_label $10;

    /* Validate group assignment */
    if group_code = 'T' then group_label = 'TEST';
    else if group_code = 'C' then group_label = 'CONTROL';
    else delete;

    /* Compute days since exposure */
    exposure_days = today() - assignment_date;

    /* Only include users with sufficient observation window */
    if exposure_days >= 14;

    /* Flag users with valid conversion events */
    if conversion_date ne . then do;
        converted = 1;
        days_to_convert = conversion_date - assignment_date;
    end;
    else do;
        converted = 0;
        days_to_convert = .;
    end;

    /* Revenue attribution */
    if revenue = . then revenue = 0;

    format assignment_date conversion_date date9.;
run;

/* -----------------------------------------------------------------------
   STEP 2: Compute group summary statistics
   ----------------------------------------------------------------------- */
proc means data=staging.experiment_groups
           n mean std stderr min max noprint;
    class group_label;
    var converted revenue days_to_convert;
    output out=staging.group_stats
        n=n_users
        mean(converted)=conversion_rate
        mean(revenue)=avg_revenue
        std(converted)=std_conversion
        std(revenue)=std_revenue
        stderr(converted)=se_conversion
        stderr(revenue)=se_revenue;
run;

/* -----------------------------------------------------------------------
   STEP 3: Statistical significance testing
   ----------------------------------------------------------------------- */
proc ttest data=staging.experiment_groups
           alpha=0.05;
    class group_label;
    var converted revenue;
    ods output ttests=staging.ttest_results
              statistics=staging.ttest_stats;
run;

/* -----------------------------------------------------------------------
   STEP 4: Compute lift and confidence intervals via SQL
   ----------------------------------------------------------------------- */
proc sql;
    create table staging.lift_analysis as
    select t.group_label,
           t.conversion_rate,
           t.avg_revenue,
           t.n_users,
           t.se_conversion,
           t.se_revenue,
           /* Conversion lift vs control */
           case when t.group_label = 'TEST' then
               (t.conversion_rate - c.conversion_rate) / c.conversion_rate
           else 0 end as conversion_lift format=percent8.2,
           /* Revenue lift vs control */
           case when t.group_label = 'TEST' then
               (t.avg_revenue - c.avg_revenue) / c.avg_revenue
           else 0 end as revenue_lift format=percent8.2,
           /* 95% CI lower bound for conversion difference */
           case when t.group_label = 'TEST' then
               (t.conversion_rate - c.conversion_rate)
               - 1.96 * sqrt(t.se_conversion**2 + c.se_conversion**2)
           else 0 end as conv_ci_lower,
           /* 95% CI upper bound for conversion difference */
           case when t.group_label = 'TEST' then
               (t.conversion_rate - c.conversion_rate)
               + 1.96 * sqrt(t.se_conversion**2 + c.se_conversion**2)
           else 0 end as conv_ci_upper
    from staging.group_stats(where=(_type_=1)) as t,
         staging.group_stats(where=(_type_=1 and group_label='CONTROL')) as c;
quit;

/* -----------------------------------------------------------------------
   STEP 5: Flag winners/losers and compute minimum detectable effect
   ----------------------------------------------------------------------- */
data staging.experiment_decision;
    set staging.lift_analysis;
    where group_label = 'TEST';
    length winner_flag $12 decision $20;

    /* Merge with t-test p-value */
    set staging.ttest_results(where=(variable='converted') keep=variable probt);

    /* Statistical significance check */
    if probt < 0.05 then do;
        stat_significant = 1;
        if conversion_lift > 0 then do;
            winner_flag = 'TEST_WINS';
            decision = 'LAUNCH';
        end;
        else do;
            winner_flag = 'CONTROL_WINS';
            decision = 'REVERT';
        end;
    end;
    else do;
        stat_significant = 0;
        winner_flag = 'INCONCLUSIVE';
        decision = 'EXTEND_OR_STOP';
    end;

    /* Minimum Detectable Effect (MDE) for the given sample size */
    /* MDE = 2.8 * sqrt(p*(1-p) / n) for 80% power, alpha=0.05 */
    baseline_rate = conversion_rate
                  - (conversion_lift * conversion_rate / (1 + conversion_lift));
    mde = 2.8 * sqrt(baseline_rate * (1 - baseline_rate) / n_users);

    format mde percent8.4 probt pvalue6.4;
run;

/* -----------------------------------------------------------------------
   STEP 6: Experiment conclusion report dataset
   ----------------------------------------------------------------------- */
data tgt.experiment_report;
    length experiment_id $20 metric_name $30 metric_value 8
           conclusion $100;

    set staging.experiment_decision;

    experiment_id = 'EXP-2026-042';
    report_date = today();

    /* Output key metrics as name-value pairs */
    metric_name = 'CONVERSION_LIFT';
    metric_value = conversion_lift;
    conclusion = catx(' ', 'Conversion lift:', put(conversion_lift, percent8.2),
                       '| p-value:', put(probt, pvalue6.4));
    output;

    metric_name = 'REVENUE_LIFT';
    metric_value = revenue_lift;
    conclusion = catx(' ', 'Revenue lift:', put(revenue_lift, percent8.2));
    output;

    metric_name = 'SAMPLE_SIZE';
    metric_value = n_users;
    conclusion = catx(' ', 'Test group size:', put(n_users, comma10.));
    output;

    metric_name = 'MDE';
    metric_value = mde;
    conclusion = catx(' ', 'Minimum Detectable Effect:', put(mde, percent8.4));
    output;

    metric_name = 'DECISION';
    metric_value = (decision = 'LAUNCH');
    conclusion = catx(' ', 'Final decision:', decision, '| Winner:', winner_flag);
    output;

    keep experiment_id report_date metric_name metric_value conclusion;
    format report_date date9.;
run;
