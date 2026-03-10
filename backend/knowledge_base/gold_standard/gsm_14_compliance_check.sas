/******************************************************************************
 * Program: gsm_14_compliance_check.sas
 * Purpose: Regulatory compliance validation for financial transactions
 *          Applies business rules, cross-references regulatory tables,
 *          categorizes violations, and generates remediation records
 * Author:  Compliance Operations Team
 * Date:    2026-02-19
 ******************************************************************************/

/* --- Library references for compliance data --- */
libname raw     '/data/compliance/raw';
libname staging '/data/compliance/staging';
libname tgt     '/data/compliance/target';

options mprint nocenter;

/* -----------------------------------------------------------------------
   STEP 1: Apply regulatory validation rules to transactions
   Checks: AML thresholds, KYC completeness, sanctions screening
   ----------------------------------------------------------------------- */
data staging.validated_transactions;
    set raw.financial_transactions;
    length violation_code $10 violation_desc $80 rule_id $8;

    violation_flag = 0;
    violation_code = '';
    violation_desc = '';
    rule_id = '';

    /* Rule R001: Currency Transaction Report threshold */
    if transaction_amount >= 10000 and ctr_filed = 'N' then do;
        violation_flag = 1;
        violation_code = 'AML-001';
        violation_desc = 'Transaction >= $10,000 without CTR filing';
        rule_id = 'R001';
        output;
    end;

    /* Rule R002: Structuring detection - multiple near-threshold txns */
    if transaction_amount >= 8000 and transaction_amount < 10000
       and daily_txn_count >= 3 then do;
        violation_flag = 1;
        violation_code = 'AML-002';
        violation_desc = 'Potential structuring: multiple near-threshold transactions';
        rule_id = 'R002';
        output;
    end;

    /* Rule R003: KYC documentation completeness */
    if kyc_verified = 'N' and account_age_days > 30 then do;
        violation_flag = 1;
        violation_code = 'KYC-001';
        violation_desc = 'KYC verification incomplete after 30-day grace period';
        rule_id = 'R003';
        output;
    end;

    /* Rule R004: High-risk country without enhanced due diligence */
    if high_risk_country = 'Y' and edd_completed = 'N' then do;
        violation_flag = 1;
        violation_code = 'KYC-002';
        violation_desc = 'High-risk jurisdiction without enhanced due diligence';
        rule_id = 'R004';
        output;
    end;

    /* Rule R005: Dormant account sudden activity */
    if days_since_last_txn > 365 and transaction_amount > 5000 then do;
        violation_flag = 1;
        violation_code = 'SAR-001';
        violation_desc = 'Dormant account reactivation with significant transaction';
        rule_id = 'R005';
        output;
    end;

    /* Non-violation records also output */
    if violation_flag = 0 then output;
run;

/* -----------------------------------------------------------------------
   STEP 2: Cross-reference against regulatory lookup tables
   ----------------------------------------------------------------------- */
proc sql;
    create table staging.enriched_violations as
    select v.*,
           s.sanction_type,
           s.sanction_date,
           s.sanctioning_body,
           r.regulation_name,
           r.penalty_range,
           r.reporting_deadline_days
    from staging.validated_transactions as v
    left join raw.sanctions_list as s
        on v.counterparty_id = s.entity_id
    left join raw.regulation_lookup as r
        on substr(v.violation_code, 1, 3) = r.regulation_prefix
    where v.violation_flag = 1;
quit;

/* -----------------------------------------------------------------------
   STEP 3: Categorize violations by severity level
   ----------------------------------------------------------------------- */
data staging.violation_severity;
    set staging.enriched_violations;
    length severity $10;

    /* Severity based on violation type and amount */
    if sanction_type ne '' then do;
        severity = 'CRITICAL';
        priority_score = 100;
    end;
    else if violation_code in ('AML-001','AML-002')
            and transaction_amount >= 50000 then do;
        severity = 'HIGH';
        priority_score = 80;
    end;
    else if violation_code in ('AML-001','AML-002') then do;
        severity = 'MEDIUM';
        priority_score = 50;
    end;
    else if violation_code in ('KYC-001','KYC-002') then do;
        severity = 'MEDIUM';
        priority_score = 40;
    end;
    else do;
        severity = 'LOW';
        priority_score = 20;
    end;

    /* Escalation deadline */
    escalation_date = today() + reporting_deadline_days;
    format escalation_date date9.;
run;

/* -----------------------------------------------------------------------
   STEP 4: Violation summary statistics
   ----------------------------------------------------------------------- */
proc freq data=staging.violation_severity;
    tables severity * violation_code / out=staging.violation_summary nocum nopercent;
    tables severity / out=staging.severity_counts nocum;
run;

/* -----------------------------------------------------------------------
   STEP 5: Generate remediation action records
   ----------------------------------------------------------------------- */
data tgt.remediation_actions;
    set staging.violation_severity;
    length action_required $100 assigned_team $30 status $15;

    /* Assign remediation actions based on violation type */
    if violation_code = 'AML-001' then do;
        action_required = 'File CTR with FinCEN within 15 days';
        assigned_team = 'BSA_COMPLIANCE';
    end;
    else if violation_code = 'AML-002' then do;
        action_required = 'Review for SAR filing; investigate structuring pattern';
        assigned_team = 'AML_INVESTIGATIONS';
    end;
    else if violation_code = 'KYC-001' then do;
        action_required = 'Complete KYC verification or freeze account';
        assigned_team = 'CUSTOMER_OPS';
    end;
    else if violation_code = 'KYC-002' then do;
        action_required = 'Perform enhanced due diligence review';
        assigned_team = 'EDD_TEAM';
    end;
    else do;
        action_required = 'Review and document findings';
        assigned_team = 'COMPLIANCE_OPS';
    end;

    status = 'OPEN';
    created_date = today();
    format created_date date9.;
run;

/* -----------------------------------------------------------------------
   STEP 6: Compliance exceptions report
   ----------------------------------------------------------------------- */
title 'Compliance Exceptions Report - Critical and High Severity';
proc print data=tgt.remediation_actions noobs label;
    where severity in ('CRITICAL','HIGH');
    var transaction_id violation_code severity transaction_amount
        action_required assigned_team escalation_date;
    label transaction_id     = 'Transaction ID'
          violation_code     = 'Violation'
          severity           = 'Severity'
          transaction_amount = 'Amount'
          action_required    = 'Required Action'
          assigned_team      = 'Team'
          escalation_date    = 'Deadline';
    format transaction_amount dollar12.2;
run;
title;
