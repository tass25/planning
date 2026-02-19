/*============================================================================*/
/* Program:    gsm_01_financial_summary.sas                                   */
/* Purpose:    Quarterly financial transaction summary and account             */
/*             classification for regulatory reporting                        */
/* Author:     Data Engineering Team                                          */
/* Date:       2026-02-19                                                     */
/*============================================================================*/

/* Set global options for reporting */
options nocenter nodate pageno=1 linesize=132 pagesize=60;
options compress=yes nofmterr;

/* Define library references for source and target schemas */
libname raw '/data/finance/raw' access=readonly;
libname staging '/data/finance/staging';
libname tgt '/data/finance/reporting';

/*--------------------------------------------------------------------*/
/* Step 1: Clean and validate raw financial transactions              */
/*--------------------------------------------------------------------*/
data staging.txn_clean;
    set raw.transactions
        (where=(txn_date between '01JAN2025'd and '31DEC2025'd));

    /* Standardize transaction amounts */
    if txn_amount = . then txn_amount = 0;

    if txn_amount < 0 then do;
        txn_type = 'DEBIT';
        abs_amount = abs(txn_amount);
    end;
    else do;
        txn_type = 'CREDIT';
        abs_amount = txn_amount;
    end;

    /* Derive quarter from transaction date */
    txn_quarter = qtr(txn_date);
    txn_year = year(txn_date);
    quarter_label = cats('Q', txn_quarter, '_', txn_year);

    /* Remove invalid account numbers */
    if account_id = '' then delete;
    if length(account_id) < 8 then delete;

    /* Flag high-value transactions for compliance review */
    if abs_amount > 100000 then high_value_flag = 'Y';
    else high_value_flag = 'N';

    /* Compute account age in days */
    days_since_open = txn_date - account_open_date;

    format txn_date account_open_date date9.
           txn_amount abs_amount dollar15.2;
run;

/*--------------------------------------------------------------------*/
/* Step 2: Sort transactions by account and quarter                   */
/*--------------------------------------------------------------------*/
proc sort data=staging.txn_clean
          out=staging.txn_sorted;
    by account_id txn_quarter;
run;

/*--------------------------------------------------------------------*/
/* Step 3: Quarterly aggregate statistics per account                 */
/*--------------------------------------------------------------------*/
proc means data=staging.txn_sorted noprint nway;
    class account_id txn_quarter quarter_label;
    var abs_amount days_since_open;
    output out=staging.quarterly_stats(drop=_type_ _freq_)
        sum(abs_amount)   = total_amount
        mean(abs_amount)  = avg_amount
        max(abs_amount)   = max_amount
        min(abs_amount)   = min_amount
        n(abs_amount)     = txn_count
        mean(days_since_open) = avg_account_age;
run;

/*--------------------------------------------------------------------*/
/* Step 4: Join with account master and compute utilization ratios    */
/*--------------------------------------------------------------------*/
proc sql;
    create table staging.account_summary as
    select
        q.account_id,
        q.txn_quarter,
        q.quarter_label,
        q.total_amount,
        q.avg_amount,
        q.txn_count,
        a.credit_limit,
        a.account_type,
        a.branch_code,
        a.relationship_manager,
        /* Utilization ratio: total spend vs credit limit */
        case
            when a.credit_limit > 0
            then q.total_amount / a.credit_limit
            else .
        end as utilization_ratio,
        /* Average transaction size */
        case
            when q.txn_count > 0
            then q.total_amount / q.txn_count
            else 0
        end as avg_txn_size
    from staging.quarterly_stats q
    left join raw.account_master a
        on q.account_id = a.account_id
    order by q.account_id, q.txn_quarter;
quit;

/*--------------------------------------------------------------------*/
/* Step 5: Categorize accounts as performing or non-performing        */
/*--------------------------------------------------------------------*/
data tgt.account_classification;
    set staging.account_summary;

    length performance_category $20 risk_tier $10;

    /* Classify based on utilization and transaction frequency */
    if utilization_ratio = . then performance_category = 'UNSCORED';
    else if utilization_ratio > 0.9 then performance_category = 'HIGH_RISK';
    else if utilization_ratio > 0.7 then performance_category = 'WATCH_LIST';
    else if utilization_ratio > 0.3 then performance_category = 'PERFORMING';
    else performance_category = 'LOW_USAGE';

    /* Assign risk tier for regulatory reporting */
    select (performance_category);
        when ('HIGH_RISK')   risk_tier = 'TIER_3';
        when ('WATCH_LIST')  risk_tier = 'TIER_2';
        when ('PERFORMING')  risk_tier = 'TIER_1';
        when ('LOW_USAGE')   risk_tier = 'TIER_1';
        otherwise            risk_tier = 'TIER_UNK';
    end;

    /* Calculate composite risk score */
    risk_score = (utilization_ratio * 0.4) +
                 (min(txn_count / 100, 1) * 0.3) +
                 (min(total_amount / 500000, 1) * 0.3);

    format utilization_ratio risk_score percent8.2
           total_amount avg_amount dollar15.2;
run;

/*--------------------------------------------------------------------*/
/* Step 6: Generate formatted executive report                        */
/*--------------------------------------------------------------------*/
title1 'Quarterly Financial Summary Report';
title2 'Account Performance Classification';

proc report data=tgt.account_classification nowd;
    column branch_code performance_category account_id
           total_amount utilization_ratio risk_score;

    define branch_code / group 'Branch';
    define performance_category / group 'Category';
    define account_id / group 'Account ID';
    define total_amount / analysis sum format=dollar15.2 'Total Amount';
    define utilization_ratio / analysis mean format=percent8.2 'Avg Utilization';
    define risk_score / analysis mean format=8.4 'Risk Score';

    break after branch_code / summarize suppress;
    rbreak after / summarize;
run;

footnote1 'Source: Finance Data Warehouse | Confidential';
title;
footnote;
