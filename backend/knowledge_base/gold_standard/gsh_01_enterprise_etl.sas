/******************************************************************************
 * Program Name : gsh_01_enterprise_etl.sas
 * Author       : Data Engineering Team — Financial Systems Division
 * Created      : 2026-01-15
 * Modified     : 2026-02-19
 * Purpose      : Enterprise ETL pipeline for the Financial Data Warehouse.
 *                Extracts data from raw source libraries, applies cleansing
 *                and business transformations, loads dimension and fact tables
 *                into the data mart layer using SCD Type 2 methodology.
 * Dependencies : common_macros.sas
 * Frequency    : Daily (scheduled via Control-M, Job ID FIN-DWH-001)
 * Change Log   :
 *   2026-01-15  v1.0  Initial development                    (J. Martin)
 *   2026-01-28  v1.1  Added SCD Type 2 dimension loading     (S. Chen)
 *   2026-02-10  v1.2  Enhanced error handling and audit trail (A. Patel)
 *   2026-02-19  v1.3  Added archival step and date dimension  (J. Martin)
 ******************************************************************************/

/* ========================================================================= */
/* SECTION 1: Environment Setup — Libraries, Options, and Includes           */
/* ========================================================================= */

options mprint mlogic symbolgen nocenter ls=200 ps=65
        validvarname=v7 nofmterr compress=binary;

/* --- Library references for each data layer --- */
libname raw      '/data/finance/raw'       access=readonly;
libname staging  '/data/finance/staging';
libname cleansed '/data/finance/cleansed';
libname mart     '/data/finance/mart';
libname archive  '/data/finance/archive';
libname tgt      '/data/finance/target';

/* Global macro variables for this run */
%let etl_run_id    = %sysfunc(putn(%sysfunc(datetime()), datetime20.));
%let process_date  = %sysfunc(today(), yymmdd10.);
%let valid_sources = 1;  /* Flag: set to 0 if any source validation fails */
%let etl_rc        = 0;  /* Return code accumulator */
%let n_sources     = 6;  /* Number of source tables to validate */

/* Include shared macro library */
%include '/etl/common/common_macros.sas';

/* ========================================================================= */
/* SECTION 2: Utility Macro Definitions                                      */
/* ========================================================================= */

/* --------------------------------------------------------------------- */
/* MACRO: check_source_data                                               */
/*   Validates that a source table exists and contains a minimum number   */
/*   of observations. Sets &valid_sources to 0 if validation fails.       */
/* --------------------------------------------------------------------- */
%macro check_source_data(lib=, table=, min_rows=100);

    %local dsid nobs rc table_exists;

    /* Check if the table exists in the library */
    %let table_exists = %sysfunc(exist(&lib..&table));

    %if &table_exists = 0 %then %do;
        %put ERROR: [check_source_data] Table &lib..&table does not exist.;
        %let valid_sources = 0;
        %return;
    %end;

    /* Open the dataset and retrieve observation count */
    %let dsid = %sysfunc(open(&lib..&table));
    %if &dsid > 0 %then %do;
        %let nobs = %sysfunc(attrn(&dsid, NOBS));
        %let rc   = %sysfunc(close(&dsid));

        %if &nobs < &min_rows %then %do;
            %put WARNING: [check_source_data] &lib..&table has only &nobs rows (minimum: &min_rows).;
            %let valid_sources = 0;
        %end;
        %else %do;
            %put NOTE: [check_source_data] &lib..&table validated OK — &nobs observations found.;
        %end;
    %end;
    %else %do;
        %put ERROR: [check_source_data] Unable to open &lib..&table — check permissions.;
        %let valid_sources = 0;
    %end;

%mend check_source_data;

/* --------------------------------------------------------------------- */
/* MACRO: log_step                                                        */
/*   Inserts an audit record into mart.etl_audit_log for traceability.    */
/*   Captures run ID, step name, status, row counts, and timestamp.       */
/* --------------------------------------------------------------------- */
%macro log_step(step_name=, status=OK, detail=, row_count=0);

    %local log_ts;
    %let log_ts = %sysfunc(datetime(), datetime20.);

    proc sql noprint;
        insert into mart.etl_audit_log
            (run_id, step_name, status, detail, row_count, log_timestamp)
        values
            ("&etl_run_id", "&step_name", "&status", "&detail",
             &row_count, "&log_ts");
    quit;

    %if &status = ERROR %then %do;
        %let etl_rc = 1;
        %put ERROR: [log_step] Step &step_name failed — &detail;
    %end;

%mend log_step;

/* --------------------------------------------------------------------- */
/* MACRO: load_dimension                                                  */
/*   Implements SCD Type 2 dimension loading with effective dating.        */
/*   Compares staging rows against existing dimension, expires changed     */
/*   records and inserts new versions with current effective dates.         */
/*   Parameters:                                                           */
/*     dim_table   - Target dimension table (e.g., mart.customer_dim)      */
/*     src_table   - Staging source table                                  */
/*     natural_key - Business key column(s) for matching                   */
/*     scd_type    - SCD type (1 or 2); default 2                          */
/* --------------------------------------------------------------------- */
%macro load_dimension(dim_table=, src_table=, natural_key=, scd_type=2);

    %local src_count new_count upd_count;

    %put NOTE: [load_dimension] Loading &dim_table from &src_table (SCD Type &scd_type).;

    /* Step 1: Identify new and changed records via left join */
    proc sql noprint;
        create table work._dim_changes as
        select s.*,
               d.dim_surrogate_key,
               d.effective_from as existing_eff_from,
               case
                   when d.dim_surrogate_key is null then 'NEW'
                   else 'UPDATE'
               end as _change_type
        from &src_table as s
        left join &dim_table (where=(current_flag = 'Y')) as d
            on s.&natural_key = d.&natural_key;

        select count(*) into :src_count trimmed from &src_table;
        select count(*) into :new_count trimmed
            from work._dim_changes where _change_type = 'NEW';
        select count(*) into :upd_count trimmed
            from work._dim_changes where _change_type = 'UPDATE';
    quit;

    %put NOTE: [load_dimension] Source=&src_count New=&new_count Updated=&upd_count;

    %if &scd_type = 2 %then %do;

        /* Step 2a: Expire changed records in the dimension */
        proc sql;
            update &dim_table
            set current_flag   = 'N',
                effective_to   = "&process_date"d
            where current_flag = 'Y'
              and &natural_key in (
                  select &natural_key from work._dim_changes
                  where _change_type = 'UPDATE'
              );
        quit;

        /* Step 2b: Insert new versions of changed and genuinely new records */
        proc sql;
            insert into &dim_table
            select monotonic()   as dim_surrogate_key,
                   s.*,
                   "&process_date"d  as effective_from,
                   '31DEC9999'd      as effective_to,
                   'Y'               as current_flag
            from work._dim_changes as s;
        quit;

    %end;
    %else %do;

        /* SCD Type 1: Simple overwrite of existing rows */
        proc sql;
            delete from &dim_table
            where &natural_key in (
                select &natural_key from work._dim_changes
            );

            insert into &dim_table
            select * from work._dim_changes;
        quit;

    %end;

    %log_step(step_name=load_dim_&dim_table, status=OK,
              detail=New=&new_count Updated=&upd_count, row_count=&src_count);

    /* Clean up temp table */
    proc datasets lib=work nolist; delete _dim_changes; quit;

%mend load_dimension;

/* ========================================================================= */
/* SECTION 3: Source Validation Loop                                         */
/*   Iterates over all expected source tables and validates each one.        */
/* ========================================================================= */

%macro validate_all_sources;
    %local i;

    /* Define source tables as indexed macro variable arrays */
    %let src_lib1 = raw;   %let src_tbl1 = customers;
    %let src_lib2 = raw;   %let src_tbl2 = products;
    %let src_lib3 = raw;   %let src_tbl3 = transactions;
    %let src_lib4 = raw;   %let src_tbl4 = accounts;
    %let src_lib5 = raw;   %let src_tbl5 = fx_rates;
    %let src_lib6 = raw;   %let src_tbl6 = calendar;

    %do i = 1 %to &n_sources;
        %put NOTE: Validating source &i of &n_sources: &&src_lib&i...&&src_tbl&i;
        %check_source_data(lib=&&src_lib&i, table=&&src_tbl&i, min_rows=10);
    %end;

    %put NOTE: [validate_all_sources] Validation complete. valid_sources=&valid_sources;
%mend validate_all_sources;

/* Execute the validation loop */
%validate_all_sources;

/* ========================================================================= */
/* SECTION 4: Early Exit Check                                               */
/*   Abort the pipeline if any source validation failed.                     */
/* ========================================================================= */

%if &valid_sources = 0 %then %do;
    %log_step(step_name=VALIDATION, status=ERROR,
              detail=One or more source tables failed validation);
    %put ERROR: ETL pipeline aborted due to source validation failure.;
    endsas;
%end;

%log_step(step_name=VALIDATION, status=OK, detail=All 6 sources validated);

/* ========================================================================= */
/* SECTION 5: Customer Dimension — Extract and Transform                     */
/* ========================================================================= */

data staging.customer_stg (drop=_:);
    set raw.customers;

    /* Standardize name fields */
    first_name = propcase(strip(first_name));
    last_name  = propcase(strip(last_name));
    full_name  = catx(' ', first_name, last_name);

    /* Derive customer age band from date of birth */
    if not missing(date_of_birth) then do;
        _age = intck('YEAR', date_of_birth, "&process_date"d);
        select;
            when (_age < 25)           age_band = '18-24';
            when (25 <= _age < 35)     age_band = '25-34';
            when (35 <= _age < 45)     age_band = '35-44';
            when (45 <= _age < 55)     age_band = '45-54';
            when (55 <= _age < 65)     age_band = '55-64';
            otherwise                  age_band = '65+';
        end;
    end;
    else do;
        age_band = 'Unknown';
    end;

    /* Clean and validate email address */
    email = lowcase(strip(email));
    if index(email, '@') = 0 then email = '';

    /* Map state to sales region */
    length region $20;
    select (upcase(state));
        when ('NY','NJ','CT','MA','PA') region = 'Northeast';
        when ('IL','OH','MI','WI','MN') region = 'Midwest';
        when ('TX','FL','GA','NC','VA') region = 'South';
        when ('CA','WA','OR','AZ','CO') region = 'West';
        otherwise                       region = 'Other';
    end;

    /* Record metadata */
    load_date     = "&process_date"d;
    source_system = 'CORE_BANKING';
    format load_date yymmdd10.;
run;

%log_step(step_name=CUSTOMER_EXTRACT, status=OK,
          detail=Customer staging table created);

/* ========================================================================= */
/* SECTION 6: Customer Deduplication via PROC SQL                            */
/* ========================================================================= */

proc sql;
    create table staging.customer_dedup as
    select a.*
    from staging.customer_stg as a
    inner join (
        select customer_id,
               min(monotonic()) as first_row
        from staging.customer_stg
        group by customer_id
    ) as b
        on a.customer_id = b.customer_id
    order by a.customer_id;

    /* Capture dedup metrics */
    select count(distinct customer_id) into :dedup_count trimmed
        from staging.customer_dedup;
quit;

%put NOTE: [Dedup] Unique customers retained: &dedup_count;
%log_step(step_name=CUSTOMER_DEDUP, status=OK,
          detail=&dedup_count unique customers, row_count=&dedup_count);

/* ========================================================================= */
/* SECTION 7: Dimension Loading — Invoke SCD Type 2 Macros                   */
/* ========================================================================= */

/* Load customer dimension with SCD Type 2 history tracking */
%load_dimension(dim_table=mart.customer_dim,
                src_table=staging.customer_dedup,
                natural_key=customer_id, scd_type=2);

/* Load product dimension with SCD Type 2 */
%load_dimension(dim_table=mart.product_dim,
                src_table=staging.product_stg,
                natural_key=product_id, scd_type=2);

/* Load date/calendar dimension — SCD Type 1 (overwrite) since dates are static */
%load_dimension(dim_table=mart.date_dim,
                src_table=staging.calendar_stg,
                natural_key=calendar_date, scd_type=1);

/* ========================================================================= */
/* SECTION 8: Fact Table Extraction — Transactions with Multi-Source Merge    */
/* ========================================================================= */

data staging.fact_transactions
     staging.fact_txn_rejects;

    merge raw.transactions  (in=a)
          raw.accounts      (in=b keep=account_id account_type currency_code)
          raw.fx_rates      (in=c keep=currency_code fx_rate_to_usd);
    by account_id;

    if a;  /* Keep only rows with a transaction record */

    /* Convert to base currency (USD) */
    if currency_code ne 'USD' and not missing(fx_rate_to_usd) then
        amount_usd = amount * fx_rate_to_usd;
    else
        amount_usd = amount;

    /* Classify transaction type into broad category */
    length txn_category $15;
    select (upcase(transaction_type));
        when ('DEP','XFER_IN','INT_CREDIT')  txn_category = 'INFLOW';
        when ('WDR','XFER_OUT','FEE','TAX')  txn_category = 'OUTFLOW';
        otherwise                             txn_category = 'OTHER';
    end;

    /* Derive fiscal period attributes */
    fiscal_year    = year(transaction_date);
    fiscal_quarter = ceil(month(transaction_date) / 3);
    fiscal_month   = month(transaction_date);

    /* Data quality check — reject incomplete records */
    _valid = 1;
    if missing(amount) then _valid = 0;
    if missing(transaction_date) then _valid = 0;
    if missing(account_id) then _valid = 0;

    if _valid = 0 then output staging.fact_txn_rejects;
    else output staging.fact_transactions;

    drop _valid;
run;

%log_step(step_name=FACT_EXTRACT, status=OK,
          detail=Transaction fact staging and rejects created);

/* ========================================================================= */
/* SECTION 9: Fact Aggregation — Daily Account Summaries via PROC SQL        */
/* ========================================================================= */

proc sql;
    create table staging.daily_account_summary as
    select t.account_id,
           t.transaction_date,
           t.account_type,
           sum(case when t.txn_category = 'INFLOW'
                    then t.amount_usd else 0 end)   as total_inflow,
           sum(case when t.txn_category = 'OUTFLOW'
                    then t.amount_usd else 0 end)   as total_outflow,
           sum(t.amount_usd)                        as net_amount,
           count(*)                                 as txn_count,
           min(t.amount_usd)                        as min_txn_amount,
           max(t.amount_usd)                        as max_txn_amount
    from staging.fact_transactions as t
    group by t.account_id, t.transaction_date, t.account_type
    order by t.account_id, t.transaction_date;
quit;

%log_step(step_name=DAILY_SUMMARY, status=OK,
          detail=Daily account summaries aggregated);

/* ========================================================================= */
/* SECTION 10: Running Balances with RETAIN                                  */
/* ========================================================================= */

data mart.account_balances;
    set staging.daily_account_summary;
    by account_id transaction_date;

    retain running_balance   0
           cumulative_inflow  0
           cumulative_outflow 0
           days_active        0;

    /* Reset accumulators for each new account */
    if first.account_id then do;
        running_balance    = 0;
        cumulative_inflow  = 0;
        cumulative_outflow = 0;
        days_active        = 0;
    end;

    /* Accumulate running totals */
    running_balance    = running_balance + net_amount;
    cumulative_inflow  = cumulative_inflow + total_inflow;
    cumulative_outflow = cumulative_outflow + abs(total_outflow);
    days_active + 1;

    /* Derived metrics */
    if cumulative_inflow > 0 then
        outflow_ratio = cumulative_outflow / cumulative_inflow;
    else
        outflow_ratio = .;

    avg_daily_net = running_balance / days_active;

    /* Flag accounts with concerning patterns */
    length balance_flag $10;
    if running_balance < 0 then balance_flag = 'NEGATIVE';
    else if running_balance < 1000 then balance_flag = 'LOW';
    else balance_flag = 'NORMAL';

    format running_balance cumulative_inflow cumulative_outflow
           avg_daily_net dollar15.2;
run;

%log_step(step_name=RUNNING_BALANCE, status=OK,
          detail=Account running balances computed);

/* ========================================================================= */
/* SECTION 11: Executive Summary via PROC SQL                                */
/* ========================================================================= */

proc sql;
    create table mart.executive_summary as
    select b.account_type,
           b.balance_flag,
           count(distinct b.account_id)  as account_count,
           sum(b.running_balance)        as total_balance,
           avg(b.running_balance)        as avg_balance,
           sum(b.cumulative_inflow)      as total_inflows,
           sum(b.cumulative_outflow)     as total_outflows,
           avg(b.outflow_ratio)          as avg_outflow_ratio
    from mart.account_balances as b
    where b.transaction_date = (
        select max(transaction_date) from mart.account_balances
    )
    group by b.account_type, b.balance_flag
    order by b.account_type, b.balance_flag;
quit;

%log_step(step_name=EXEC_SUMMARY, status=OK,
          detail=Executive summary table generated);

/* ========================================================================= */
/* SECTION 12: Error Detection and Conditional Handling                      */
/* ========================================================================= */

%if &syserr ne 0 or &etl_rc ne 0 %then %do;
    %put ERROR: ETL pipeline encountered errors. syserr=&syserr etl_rc=&etl_rc;

    %log_step(step_name=ERROR_HANDLER, status=ERROR,
              detail=Pipeline errors detected — review log);

    /* Write error flag file for downstream job monitoring */
    data _null_;
        file '/data/finance/flags/etl_error.flag';
        put "ETL_RUN_ID=&etl_run_id";
        put "ERROR_TIME=%sysfunc(datetime(), datetime20.)";
        put "SYSERR=&syserr";
        put "ETL_RC=&etl_rc";
    run;

    /* Send error notification via email */
    filename mymail email
        to=('dw-ops@company.com')
        subject="ETL FAILURE: gsh_01_enterprise_etl — &process_date"
        type='text/plain';
    data _null_;
        file mymail;
        put "The Financial DWH ETL pipeline failed on &process_date.";
        put "Run ID : &etl_run_id";
        put "SYSERR : &syserr";
        put "ETL_RC : &etl_rc";
        put "Please review the SAS log for details.";
    run;
    filename mymail clear;
%end;
%else %do;
    %put NOTE: ETL pipeline completed successfully. No errors detected.;
%end;

/* ========================================================================= */
/* SECTION 13: Archival — Move Aged Data to Archive Library                  */
/* ========================================================================= */

data archive.transactions_%sysfunc(compress(&process_date, -)) (compress=yes);
    set raw.transactions;
    where transaction_date <= "&process_date"d - 365;

    /* Add archive metadata */
    archive_date   = "&process_date"d;
    archive_run_id = "&etl_run_id";
    format archive_date yymmdd10.;
run;

/* Remove archived records from the active raw layer */
proc sql;
    delete from raw.transactions
    where transaction_date <= "&process_date"d - 365;
quit;

%log_step(step_name=ARCHIVAL, status=OK,
          detail=Historical transactions archived and purged from raw);

/* ========================================================================= */
/* SECTION 14: Final Cleanup and Audit Trail                                 */
/* ========================================================================= */

/* Clear intermediate staging datasets */
proc datasets lib=staging nolist;
    delete customer_stg
           customer_dedup
           fact_transactions
           fact_txn_rejects
           daily_account_summary;
quit;

/* Record final pipeline completion in audit log */
%log_step(step_name=PIPELINE_COMPLETE, status=OK,
          detail=All ETL steps completed successfully);

/* Write completion flag for downstream batch scheduler */
data _null_;
    file '/data/finance/flags/etl_complete.flag';
    put "ETL_RUN_ID=&etl_run_id";
    put "COMPLETION_TIME=%sysfunc(datetime(), datetime20.)";
    put "PROCESS_DATE=&process_date";
    put "STATUS=SUCCESS";
run;

/* Reset options to defaults */
options nomprint nomlogic nosymbolgen;

%put NOTE: ===== gsh_01_enterprise_etl.sas completed at %sysfunc(datetime(), datetime20.) =====;
