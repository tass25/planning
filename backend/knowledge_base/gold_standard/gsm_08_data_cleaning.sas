/*****************************************************************************
 * Program: gsm_08_data_cleaning.sas
 * Purpose: Comprehensive data cleaning and validation pipeline
 * Author:  Data Quality Team
 * Date:    2026-02-19
 * Description:
 *   Validates, cleans, and standardizes customer account data through
 *   multiple passes: field validation, outlier detection, imputation,
 *   referential integrity checks, and metadata reporting.
 *****************************************************************************/

/* ------------------------------------------------------------------ */
/* Global settings and library references                             */
/* ------------------------------------------------------------------ */
options mprint mlogic nocenter validvarname=v7 ls=120 ps=60;

libname raw     'C:/data/cleaning/raw' access=readonly;
libname staging 'C:/data/cleaning/staging';
libname master  'C:/data/cleaning/master' access=readonly;
libname tgt     'C:/data/cleaning/output';

/* ------------------------------------------------------------------ */
/* Step 1: Comprehensive field validation                             */
/*   - Check for missing values, range violations, format issues      */
/*   - Use PRXMATCH for email and phone pattern validation            */
/* ------------------------------------------------------------------ */
data staging.validated (drop=rc_email rc_phone)
     staging.validation_errors (drop=rc_email rc_phone);
    set raw.customer_accounts;

    length validation_status $8 error_fields $200;
    validation_status = 'VALID';
    error_fields = '';

    /* Check required fields for missing values */
    if missing(customer_id) then do;
        validation_status = 'INVALID';
        error_fields = catx(', ', error_fields, 'customer_id:missing');
    end;
    if missing(first_name) or missing(last_name) then do;
        validation_status = 'INVALID';
        error_fields = catx(', ', error_fields, 'name:missing');
    end;

    /* Range checks for numeric fields */
    if not missing(age) and (age < 18 or age > 120) then do;
        validation_status = 'INVALID';
        error_fields = catx(', ', error_fields, 'age:out_of_range');
    end;
    if not missing(annual_income) and annual_income < 0 then do;
        validation_status = 'INVALID';
        error_fields = catx(', ', error_fields, 'income:negative');
    end;
    if not missing(credit_score) and (credit_score < 300 or credit_score > 850) then do;
        validation_status = 'INVALID';
        error_fields = catx(', ', error_fields, 'credit_score:out_of_range');
    end;

    /* Email format validation using regex */
    rc_email = prxmatch('/^[\w.+-]+@[\w-]+\.[\w.]+$/', strip(email));
    if not missing(email) and rc_email = 0 then do;
        validation_status = 'INVALID';
        error_fields = catx(', ', error_fields, 'email:bad_format');
    end;

    /* Phone number validation (must be 10 digits after stripping) */
    rc_phone = prxmatch('/^\d{10}$/', compress(phone, '-() '));
    if not missing(phone) and rc_phone = 0 then do;
        validation_status = 'INVALID';
        error_fields = catx(', ', error_fields, 'phone:bad_format');
    end;

    /* Date validation: registration must not be in the future */
    if not missing(registration_date) and registration_date > today() then do;
        validation_status = 'INVALID';
        error_fields = catx(', ', error_fields, 'registration_date:future');
    end;

    /* Route valid and invalid records to separate datasets */
    if validation_status = 'VALID' then output staging.validated;
    else output staging.validation_errors;
run;

/* ------------------------------------------------------------------ */
/* Step 2: Standardize multiple columns using ARRAY                   */
/*   - Uppercase text fields, trim whitespace                         */
/*   - Min-max normalize numeric scores to 0-1 scale                  */
/* ------------------------------------------------------------------ */
data staging.standardized;
    set staging.validated;

    /* Standardize character fields to uppercase trimmed */
    array char_fields{4} first_name last_name city state;
    do i = 1 to dim(char_fields);
        char_fields{i} = strip(upcase(char_fields{i}));
    end;

    /* Min-max normalization for numeric scores */
    array raw_scores{3} credit_score annual_income account_balance;
    array norm_scores{3} norm_credit norm_income norm_balance;
    array mins{3} _temporary_ (300 0 -50000);
    array maxs{3} _temporary_ (850 500000 1000000);
    do j = 1 to 3;
        if not missing(raw_scores{j}) then
            norm_scores{j} = (raw_scores{j} - mins{j}) / (maxs{j} - mins{j});
    end;

    /* Cap registration_date at today if somehow future */
    if not missing(registration_date) and registration_date > today() then
        registration_date = today();

    drop i j;
run;

/* ------------------------------------------------------------------ */
/* Step 3: Data profiling - missing value frequency analysis          */
/* ------------------------------------------------------------------ */
proc freq data=staging.standardized;
    tables age credit_score annual_income email phone state
           / missing nocum nopercent;
    title 'Data Profiling: Missing Value Report';
run;

/* ------------------------------------------------------------------ */
/* Step 4: Outlier detection using PROC UNIVARIATE                    */
/*   - Compute percentile-based boundaries for key numeric fields     */
/* ------------------------------------------------------------------ */
proc univariate data=staging.standardized;
    var annual_income credit_score account_balance age;
    id customer_id;
    output out=staging.outlier_stats
        pctlpts  = 1 5 25 50 75 95 99
        pctlpre  = income_ credit_ balance_ age_
        pctlname = p01 p05 p25 p50 p75 p95 p99;
    title 'Outlier Detection: Univariate Statistics';
run;

/* ------------------------------------------------------------------ */
/* Step 5: Impute missing values                                      */
/*   - Median for numeric, regression estimate for income, zip lookup */
/* ------------------------------------------------------------------ */
data tgt.customer_cleaned;
    set staging.standardized;

    /* Impute missing age with pre-calculated median */
    if missing(age) then do;
        age = 42;
        age_imputed = 1;
    end;
    else age_imputed = 0;

    /* Impute missing income using credit_score regression estimate */
    if missing(annual_income) then do;
        if not missing(credit_score) then
            annual_income = 15000 + (credit_score - 300) * 180;
        else
            annual_income = 55000; /* fallback to overall median */
        income_imputed = 1;
    end;
    else income_imputed = 0;

    /* Impute missing state from zip code prefix */
    if missing(state) and not missing(zip_code) then do;
        zip_prefix = substr(put(zip_code, z5.), 1, 3);
        if zip_prefix in ('100','101','102') then state = 'NY';
        else if zip_prefix in ('900','901','902') then state = 'CA';
        else if zip_prefix in ('600','601','602') then state = 'IL';
        else if zip_prefix in ('770','771','772') then state = 'TX';
        state_imputed = 1;
    end;
    else state_imputed = 0;
run;

/* ------------------------------------------------------------------ */
/* Step 6: Referential integrity checks against master tables         */
/*   - Identify orphan records and invalid reference codes            */
/* ------------------------------------------------------------------ */
proc sql;
    /* Find customers not in master customer list */
    create table staging.orphan_records as
    select a.customer_id, a.first_name, a.last_name,
           'NOT_IN_MASTER' as integrity_issue
    from tgt.customer_cleaned a
    left join master.customer_master b
        on a.customer_id = b.customer_id
    where b.customer_id is null;

    /* Find invalid state codes */
    create table staging.invalid_states as
    select a.customer_id, a.state,
           'INVALID_STATE' as integrity_issue
    from tgt.customer_cleaned a
    left join master.state_reference b
        on a.state = b.state_code
    where a.state is not null
      and b.state_code is null;

    /* Summary count of integrity issues */
    title 'Referential Integrity Summary';
    select 'Orphan Records' as issue_type,
           count(*) as issue_count
    from staging.orphan_records
    union all
    select 'Invalid States',
           count(*)
    from staging.invalid_states;
quit;

/* ------------------------------------------------------------------ */
/* Step 7: Metadata report for cleaned output dataset                 */
/* ------------------------------------------------------------------ */
proc contents data=tgt.customer_cleaned
              out=staging.metadata_report noprint;
run;

/* End of data cleaning pipeline */
