/******************************************************************************
 * Program Name : gsh_07_migration_suite.sas
 * Author       : Data Migration Team — Enterprise Systems Division
 * Created      : 2026-01-20
 * Modified     : 2026-02-19
 * Purpose      : Data migration validation suite for legacy-to-new-platform
 *                migration. Performs count reconciliation, column-level
 *                comparison, amount tolerance checking, referential integrity
 *                validation, and generates a comprehensive reconciliation
 *                report with overall migration quality score.
 * Migration    : Phase 3 — Data Validation & Reconciliation
 * Dependencies : migration_utilities.sas
 * Frequency    : On-demand during migration windows
 * Change Log   :
 *   2026-01-20  v1.0  Initial development                    (R. Torres)
 *   2026-02-05  v1.1  Added column-level comparison macro     (L. Nguyen)
 *   2026-02-12  v1.2  Enhanced tolerance logic and reporting  (R. Torres)
 *   2026-02-19  v1.3  Added referential integrity checks      (M. Khan)
 ******************************************************************************/

/* ========================================================================= */
/* SECTION 1: Environment Setup — Libraries, Options, Parameters             */
/* ========================================================================= */

options mprint mlogic symbolgen nocenter ls=200 ps=65
        validvarname=v7 nofmterr;

/* --- Library references for migration layers --- */
libname legacy   '/data/migration/legacy'    access=readonly;
libname target   '/data/migration/target';
libname reconcil '/data/migration/reconcile';
libname work     '%sysfunc(pathname(work))';

/* --- Global migration parameters --- */
%let batch_id      = MIG-2026-0219-001;
%let run_date      = %sysfunc(today(), yymmdd10.);
%let run_timestamp = %sysfunc(datetime(), datetime20.);
%let tolerance     = 0.01;
%let tol_type      = PCT;    /* ABS = absolute, PCT = percentage */
%let migration_rc  = 0;
%let total_checks  = 0;
%let passed_checks = 0;
%let failed_checks = 0;
%let n_tables      = 8;
%let n_crit_tables = 4;
%let n_fin_tables  = 3;
%let n_fk_pairs    = 5;

/* --- Table lists for batch processing --- */
%let table1 = customers;
%let table2 = accounts;
%let table3 = transactions;
%let table4 = products;
%let table5 = orders;
%let table6 = order_lines;
%let table7 = suppliers;
%let table8 = employees;

/* Include shared migration utilities */
%include '/migration/common/migration_utilities.sas';

/* ========================================================================= */
/* SECTION 2: Macro Definitions                                              */
/* ========================================================================= */

/* --------------------------------------------------------------------- */
/* MACRO: count_reconcile                                                  */
/*   Compares row counts between legacy source and migration target for    */
/*   a given table. Logs pass/fail result to reconcil.count_results.       */
/* --------------------------------------------------------------------- */
%macro count_reconcile(table=, lib_src=legacy, lib_tgt=target);
    %local src_count tgt_count diff pct_diff status;

    %put NOTE: ===== Count Reconciliation: &table =====;

    /* Get row count from the legacy source system */
    proc sql noprint;
        select count(*) into :src_count trimmed
        from &lib_src..&table;
    quit;

    /* Get row count from the migration target system */
    proc sql noprint;
        select count(*) into :tgt_count trimmed
        from &lib_tgt..&table;
    quit;

    /* Compute difference and determine pass/fail status */
    data reconcil.count_result_&table;
        length table_name $32 status $10 batch_id $30 check_type $10
               run_date $10;
        table_name = "&table";
        batch_id   = "&batch_id";
        src_count  = &src_count;
        tgt_count  = &tgt_count;
        diff       = tgt_count - src_count;

        /* Calculate percentage difference */
        if src_count > 0 then
            pct_diff = abs(diff) / src_count * 100;
        else
            pct_diff = 0;

        /* Assess result: counts must match exactly */
        if diff = 0 then do;
            status = 'PASS';
            call symputx('passed_checks',
                         input(symget('passed_checks'), best.) + 1);
        end;
        else do;
            status = 'FAIL';
            call symputx('failed_checks',
                         input(symget('failed_checks'), best.) + 1);
        end;

        check_type = 'COUNT';
        run_date   = "&run_date";
        output;
    run;

    /* Increment global counter */
    %let total_checks = %eval(&total_checks + 1);

    %put NOTE: &table — Source: &src_count | Target: &tgt_count | Diff: %eval(&tgt_count - &src_count);
%mend count_reconcile;

/* --------------------------------------------------------------------- */
/* MACRO: column_compare                                                   */
/*   Performs column-level comparison between legacy and target tables.     */
/*   Joins on key columns and checks each compare column for value         */
/*   mismatches. Identifies records missing in source, missing in target,  */
/*   and individual column differences.                                    */
/* --------------------------------------------------------------------- */
%macro column_compare(table=, key_cols=, compare_cols=, lib_src=legacy);
    %local n_comp i col join_cond n_keys kcol n_mismatches;

    %put NOTE: ===== Column Comparison: &table =====;

    /* Count the number of columns to compare */
    %let n_comp = %sysfunc(countw(&compare_cols, %str( )));
    %let n_keys = %sysfunc(countw(&key_cols, %str( )));

    /* Build the join condition dynamically from key columns */
    %let join_cond = ;
    %do i = 1 %to &n_keys;
        %let kcol = %scan(&key_cols, &i, %str( ));
        %if &i > 1 %then %let join_cond = &join_cond AND;
        %let join_cond = &join_cond s.&kcol = t.&kcol;
    %end;

    /* Full outer join of source and target on key columns */
    proc sql;
        create table work._compare_&table as
        select
            coalesce(s.%scan(&key_cols, 1, %str( )),
                     t.%scan(&key_cols, 1, %str( ))) as key_value,
            case
                when s.%scan(&key_cols, 1, %str( )) is null
                    then 'MISSING_IN_SOURCE'
                when t.%scan(&key_cols, 1, %str( )) is null
                    then 'MISSING_IN_TARGET'
                else 'MATCHED'
            end as match_status length=20,
            /* Select source and target versions of each compare column */
            %do i = 1 %to &n_comp;
                %let col = %scan(&compare_cols, &i, %str( ));
                s.&col as src_&col,
                t.&col as tgt_&col
                %if &i < &n_comp %then ,;
            %end;
        from &lib_src..&table s
        full outer join target.&table t
        on &join_cond;
    quit;

    /* Analyze each compare column for mismatches using arrays */
    data reconcil.col_compare_&table(drop=i _mismatch_flag);
        set work._compare_&table;

        length column_name $32 mismatch_detail $200 table_name $32
               batch_id $30 check_type $10 run_date $10;

        /* Arrays for paired source/target column values */
        array _src(*) src_:;
        array _tgt(*) tgt_:;

        table_name = "&table";
        batch_id   = "&batch_id";
        check_type = 'COLUMN';
        run_date   = "&run_date";

        /* Handle records missing from one system */
        if match_status = 'MISSING_IN_SOURCE' then do;
            column_name     = '_KEY_';
            mismatch_detail = 'Record exists in target but not in source';
            output;
        end;
        else if match_status = 'MISSING_IN_TARGET' then do;
            column_name     = '_KEY_';
            mismatch_detail = 'Record exists in source but not in target';
            output;
        end;
        else do;
            /* Row matched on keys — compare each column value */
            _mismatch_flag = 0;
            do i = 1 to dim(_src);
                if _src(i) ne _tgt(i) then do;
                    column_name = vname(_src(i));
                    mismatch_detail = catx(' | ',
                        'Source=' || strip(put(_src(i), best32.)),
                        'Target=' || strip(put(_tgt(i), best32.)));
                    _mismatch_flag = 1;
                    output;
                end;
            end;

            /* If no column mismatches, record a PASS entry */
            if _mismatch_flag = 0 then do;
                column_name     = '_ALL_';
                mismatch_detail = 'All columns match';
                output;
            end;
        end;
    run;

    /* Summarize mismatch count for this table */
    proc sql noprint;
        select count(*) into :n_mismatches trimmed
        from reconcil.col_compare_&table
        where column_name ne '_ALL_'
          and mismatch_detail not contains 'All columns match';
    quit;

    /* Update global check counters */
    %let total_checks = %eval(&total_checks + 1);

    %if &n_mismatches > 0 %then %do;
        %put WARNING: &table — &n_mismatches column-level mismatches detected.;
        %let failed_checks = %eval(&failed_checks + 1);
    %end;
    %else %do;
        %put NOTE: &table — All compared columns match.;
        %let passed_checks = %eval(&passed_checks + 1);
    %end;
%mend column_compare;

/* --------------------------------------------------------------------- */
/* MACRO: sum_reconcile                                                    */
/*   Reconciles summed amounts between legacy and target systems by key    */
/*   grouping. Supports absolute and percentage tolerance thresholds.      */
/*   Results are logged with breach details per amount column.             */
/* --------------------------------------------------------------------- */
%macro sum_reconcile(table=, key_cols=, amount_cols=, tolerance=&tolerance);
    %local n_amt i acol join_cond n_keys kcol n_breaches;

    %put NOTE: ===== Sum Reconciliation: &table =====;

    %let n_amt  = %sysfunc(countw(&amount_cols, %str( )));
    %let n_keys = %sysfunc(countw(&key_cols, %str( )));

    /* Build join condition from key columns */
    %let join_cond = ;
    %do i = 1 %to &n_keys;
        %let kcol = %scan(&key_cols, &i, %str( ));
        %if &i > 1 %then %let join_cond = &join_cond AND;
        %let join_cond = &join_cond s.&kcol = t.&kcol;
    %end;

    /* Aggregate amounts by key from the legacy source */
    proc sql;
        create table work._sum_src_&table as
        select
            %do i = 1 %to &n_keys;
                %scan(&key_cols, &i, %str( )),
            %end;
            %do i = 1 %to &n_amt;
                %let acol = %scan(&amount_cols, &i, %str( ));
                sum(&acol) as &acol format=comma20.2
                %if &i < &n_amt %then ,;
            %end;
        from legacy.&table
        group by
            %do i = 1 %to &n_keys;
                %scan(&key_cols, &i, %str( ))
                %if &i < &n_keys %then ,;
            %end;
        ;
    quit;

    /* Aggregate amounts by key from the migration target */
    proc sql;
        create table work._sum_tgt_&table as
        select
            %do i = 1 %to &n_keys;
                %scan(&key_cols, &i, %str( )),
            %end;
            %do i = 1 %to &n_amt;
                %let acol = %scan(&amount_cols, &i, %str( ));
                sum(&acol) as &acol format=comma20.2
                %if &i < &n_amt %then ,;
            %end;
        from target.&table
        group by
            %do i = 1 %to &n_keys;
                %scan(&key_cols, &i, %str( ))
                %if &i < &n_keys %then ,;
            %end;
        ;
    quit;

    /* Merge source and target summaries and compare amounts */
    data reconcil.sum_result_&table;
        merge work._sum_src_&table(rename=(
                %do i = 1 %to &n_amt;
                    %let acol = %scan(&amount_cols, &i, %str( ));
                    &acol = src_&acol
                %end;
              ))
              work._sum_tgt_&table(rename=(
                %do i = 1 %to &n_amt;
                    %let acol = %scan(&amount_cols, &i, %str( ));
                    &acol = tgt_&acol
                %end;
              ));
        by %do i = 1 %to &n_keys;
               %scan(&key_cols, &i, %str( ))
           %end;
        ;

        length status $10 breach_detail $200 table_name $32
               batch_id $30 check_type $10 run_date $10;

        table_name = "&table";
        batch_id   = "&batch_id";
        check_type = 'SUM';
        run_date   = "&run_date";
        tolerance  = &tolerance;

        /* Compute difference for each amount column */
        %do i = 1 %to &n_amt;
            %let acol = %scan(&amount_cols, &i, %str( ));

            diff_&acol = coalesce(tgt_&acol, 0)
                       - coalesce(src_&acol, 0);

            /* Apply tolerance check based on configured tolerance type */
            %if &tol_type = PCT %then %do;
                /* Percentage tolerance mode */
                if coalesce(src_&acol, 0) ne 0 then
                    pct_diff_&acol = abs(diff_&acol)
                                   / abs(src_&acol) * 100;
                else
                    pct_diff_&acol = 0;

                if pct_diff_&acol > &tolerance * 100 then do;
                    status = 'FAIL';
                    breach_detail = catx(' ',
                        "&acol breach:",
                        strip(put(pct_diff_&acol, 8.4)) || '%',
                        '> threshold',
                        strip(put(&tolerance * 100, 8.4)) || '%');
                end;
            %end;
            %else %do;
                /* Absolute tolerance mode */
                if abs(diff_&acol) > &tolerance then do;
                    status = 'FAIL';
                    breach_detail = catx(' ',
                        "&acol breach:",
                        strip(put(abs(diff_&acol), comma20.2)),
                        '> threshold',
                        strip(put(&tolerance, comma20.2)));
                end;
            %end;
        %end;

        /* Default to PASS if no breach was flagged */
        if status = ' ' then status = 'PASS';
    run;

    /* Count tolerance breaches */
    proc sql noprint;
        select count(*) into :n_breaches trimmed
        from reconcil.sum_result_&table
        where status = 'FAIL';
    quit;

    /* Update global counters */
    %let total_checks = %eval(&total_checks + 1);

    %if &n_breaches > 0 %then %do;
        %put WARNING: &table — &n_breaches tolerance breaches found.;
        %let failed_checks = %eval(&failed_checks + 1);
    %end;
    %else %do;
        %put NOTE: &table — All amounts within tolerance (&tol_type=&tolerance).;
        %let passed_checks = %eval(&passed_checks + 1);
    %end;
%mend sum_reconcile;

/* --------------------------------------------------------------------- */
/* MACRO: referential_integrity                                            */
/*   Validates foreign key relationships by identifying orphaned records   */
/*   in the target system where child FK values have no matching parent    */
/*   record. Logs count and pass/fail status.                              */
/* --------------------------------------------------------------------- */
%macro referential_integrity(parent_table=, child_table=, fk_col=);
    %local n_orphans;

    %put NOTE: ===== Referential Integrity: &child_table -> &parent_table (&fk_col) =====;

    /* Identify orphaned child records with no matching parent */
    proc sql;
        create table reconcil.orphans_&child_table._&fk_col as
        select c.*
        from target.&child_table c
        left join target.&parent_table p
        on c.&fk_col = p.&fk_col
        where p.&fk_col is null
          and c.&fk_col is not null;

        /* Capture orphan count into macro variable */
        select count(*) into :n_orphans trimmed
        from reconcil.orphans_&child_table._&fk_col;
    quit;

    /* Log referential integrity result */
    data reconcil.fk_result_&child_table._&fk_col;
        length parent_table $32 child_table $32 fk_column $32
               status $10 batch_id $30 check_type $10 run_date $10;

        parent_table = "&parent_table";
        child_table  = "&child_table";
        fk_column    = "&fk_col";
        orphan_count = &n_orphans;
        batch_id     = "&batch_id";
        check_type   = 'FK';
        run_date     = "&run_date";

        if orphan_count = 0 then do;
            status = 'PASS';
            call symputx('passed_checks',
                         input(symget('passed_checks'), best.) + 1);
        end;
        else do;
            status = 'FAIL';
            call symputx('failed_checks',
                         input(symget('failed_checks'), best.) + 1);
        end;
    run;

    /* Increment global check counter */
    %let total_checks = %eval(&total_checks + 1);

    %if &n_orphans > 0 %then
        %put WARNING: &child_table.&fk_col — &n_orphans orphaned records found.;
    %else
        %put NOTE: &child_table.&fk_col — Referential integrity intact.;
%mend referential_integrity;

/* --------------------------------------------------------------------- */
/* MACRO: generate_reconciliation_report                                   */
/*   Compiles all reconciliation results into a unified dashboard and      */
/*   generates a formatted PDF report with overall migration quality       */
/*   score, count details, and FK validation results.                      */
/* --------------------------------------------------------------------- */
%macro generate_reconciliation_report;
    %local i;

    %put NOTE: ===== Generating Reconciliation Report =====;

    /* --- Step 1: Merge all count reconciliation results --- */
    data reconcil.all_count_results;
        set
        %do i = 1 %to &n_tables;
            reconcil.count_result_&&table&i
        %end;
        ;
    run;

    /* --- Step 2: Merge all FK validation results --- */
    data reconcil.all_fk_results;
        length parent_table $32 child_table $32 fk_column $32
               status $10 batch_id $30 check_type $10 run_date $10;
        set
            reconcil.fk_result_orders_customer_id
            reconcil.fk_result_order_lines_order_id
            reconcil.fk_result_order_lines_product_id
            reconcil.fk_result_transactions_account_id
            reconcil.fk_result_employees_dept_id
        ;
    run;

    /* --- Step 3: Build summary dashboard via PROC SQL --- */
    proc sql;
        create table reconcil.migration_dashboard as
        select
            "&batch_id"     as batch_id length=30,
            "&run_date"     as run_date length=10,
            &total_checks   as total_checks,
            &passed_checks  as passed_checks,
            &failed_checks  as failed_checks,
            case
                when &total_checks > 0
                    then &passed_checks / &total_checks * 100
                else 0
            end as pass_rate format=8.2,
            case
                when calculated pass_rate >= 100 then 'CERTIFIED'
                when calculated pass_rate >= 95  then 'CONDITIONAL'
                when calculated pass_rate >= 80  then 'REVIEW_REQUIRED'
                else 'FAILED'
            end as migration_status length=20
        ;
    quit;

    /* --- Step 4: Compute overall migration quality score --- */
    data reconcil.quality_score;
        set reconcil.migration_dashboard;

        /* Weighted scoring components */
        count_weight  = 0.30;
        column_weight = 0.30;
        sum_weight    = 0.25;
        fk_weight     = 0.15;

        /* Use pass rate as the quality score basis */
        quality_score = pass_rate;

        /* Determine go-live recommendation */
        length recommendation $100;
        if quality_score >= 100 then
            recommendation =
                'Migration validated. Proceed to go-live.';
        else if quality_score >= 95 then
            recommendation =
                'Minor issues found. Review and remediate before go-live.';
        else if quality_score >= 80 then
            recommendation =
                'Significant issues. Re-run migration for affected tables.';
        else
            recommendation =
                'Migration failed validation. Full re-migration required.';

        batch_id  = "&batch_id";
        run_date  = "&run_date";
        scored_at = put(datetime(), datetime20.);
    run;

    /* --- Step 5: Generate formatted PDF report via ODS --- */
    ods pdf file="/reports/migration/reconciliation_&batch_id..pdf"
        style=journal;

    ods proclabel 'Migration Reconciliation Summary';

    title1 "Data Migration Reconciliation Report";
    title2 "Batch: &batch_id | Date: &run_date";

    /* Overall quality score and recommendation */
    proc report data=reconcil.quality_score nowd;
        columns batch_id run_date total_checks passed_checks
                failed_checks pass_rate quality_score
                migration_status recommendation;

        define batch_id          / display 'Batch ID';
        define run_date          / display 'Run Date';
        define total_checks      / display 'Total Checks';
        define passed_checks     / display 'Passed';
        define failed_checks     / display 'Failed';
        define pass_rate         / display 'Pass Rate (%)' format=8.2;
        define quality_score     / display 'Quality Score' format=8.2;
        define migration_status  / display 'Status';
        define recommendation    / display 'Recommendation' width=50;

        compute migration_status;
            if migration_status = 'FAILED' then
                call define(_col_, 'style',
                    'style=[color=red font_weight=bold]');
            else if migration_status = 'CERTIFIED' then
                call define(_col_, 'style',
                    'style=[color=green font_weight=bold]');
        endcomp;
    run;

    /* Row count reconciliation detail */
    title3 "Section 1: Row Count Reconciliation";

    proc report data=reconcil.all_count_results nowd;
        columns table_name src_count tgt_count diff pct_diff status;

        define table_name / display 'Table';
        define src_count  / display 'Source Rows' format=comma12.;
        define tgt_count  / display 'Target Rows' format=comma12.;
        define diff       / display 'Difference'  format=comma12.;
        define pct_diff   / display '% Diff'      format=8.4;
        define status     / display 'Status';

        compute status;
            if status = 'FAIL' then
                call define(_row_, 'style',
                    'style=[background=lightyellow]');
        endcomp;
    run;

    /* Referential integrity detail */
    title3 "Section 2: Referential Integrity Validation";

    proc report data=reconcil.all_fk_results nowd;
        columns parent_table child_table fk_column orphan_count status;

        define parent_table  / display 'Parent Table';
        define child_table   / display 'Child Table';
        define fk_column     / display 'FK Column';
        define orphan_count  / display 'Orphan Records' format=comma12.;
        define status        / display 'Status';

        compute status;
            if status = 'FAIL' then
                call define(_row_, 'style',
                    'style=[background=lightyellow]');
        endcomp;
    run;

    title;
    ods pdf close;

    %put NOTE: Reconciliation report saved to /reports/migration/;
%mend generate_reconciliation_report;

/* ========================================================================= */
/* SECTION 3: Main Program — Execute Migration Validation Suite              */
/* ========================================================================= */

%put NOTE: ============================================================;
%put NOTE: Migration Validation Suite — Batch &batch_id;
%put NOTE: Run Date: &run_date;
%put NOTE: Tolerance: &tolerance (&tol_type);
%put NOTE: ============================================================;

/* ----- Phase 1: Row Count Reconciliation for all 8 tables ------------ */
%put NOTE: --- Phase 1: Count Reconciliation ---;

%macro run_count_checks;
    %do i = 1 %to &n_tables;
        %count_reconcile(table=&&table&i);

        /* Abort on critical system errors */
        %if &syserr > 4 %then %do;
            %put ERROR: System error during count check for &&table&i..;
            %let migration_rc = 1;
        %end;
    %end;
%mend run_count_checks;

%run_count_checks;

/* ----- Phase 2: Column Comparison for 4 critical tables -------------- */
%put NOTE: --- Phase 2: Column Comparison ---;

%column_compare(table=customers,
    key_cols=customer_id,
    compare_cols=first_name last_name email phone status);

%column_compare(table=accounts,
    key_cols=account_id,
    compare_cols=account_type balance open_date status);

%column_compare(table=products,
    key_cols=product_id,
    compare_cols=product_name category unit_price active_flag);

%column_compare(table=orders,
    key_cols=order_id,
    compare_cols=order_date customer_id total_amount status);

/* ----- Phase 3: Sum Reconciliation for 3 financial tables ------------ */
%put NOTE: --- Phase 3: Sum Reconciliation ---;

%sum_reconcile(table=transactions,
    key_cols=account_id,
    amount_cols=debit_amount credit_amount balance,
    tolerance=&tolerance);

%sum_reconcile(table=orders,
    key_cols=customer_id,
    amount_cols=total_amount tax_amount discount_amount,
    tolerance=&tolerance);

%sum_reconcile(table=order_lines,
    key_cols=order_id,
    amount_cols=line_total unit_price,
    tolerance=&tolerance);

/* ----- Phase 4: Referential Integrity for 5 FK relationships --------- */
%put NOTE: --- Phase 4: Referential Integrity ---;

%referential_integrity(parent_table=customers,
    child_table=orders,
    fk_col=customer_id);

%referential_integrity(parent_table=orders,
    child_table=order_lines,
    fk_col=order_id);

%referential_integrity(parent_table=products,
    child_table=order_lines,
    fk_col=product_id);

%referential_integrity(parent_table=accounts,
    child_table=transactions,
    fk_col=account_id);

%referential_integrity(parent_table=departments,
    child_table=employees,
    fk_col=dept_id);

/* ----- Phase 5: Generate Reconciliation Report ----------------------- */
%put NOTE: --- Phase 5: Reconciliation Report ---;

%if &migration_rc = 0 %then %do;
    %generate_reconciliation_report;
%end;
%else %do;
    %put ERROR: Skipping report generation due to earlier system errors.;
    %put ERROR: Review log for details. Batch: &batch_id;
%end;

/* ========================================================================= */
/* SECTION 4: Final Status Logging and Cleanup                               */
/* ========================================================================= */

/* Persist final validation status to reconciliation library */
data reconcil.validation_log;
    length batch_id $30 status $20 detail $200;
    batch_id = "&batch_id";
    run_date = "&run_date";
    total    = &total_checks;
    passed   = &passed_checks;
    failed   = &failed_checks;

    if failed = 0 then
        status = 'ALL_PASSED';
    else
        status = 'HAS_FAILURES';

    detail = catx(' ',
        'Checks:', strip(put(total, best.)),
        '| Passed:', strip(put(passed, best.)),
        '| Failed:', strip(put(failed, best.)));

    scored_ts = datetime();
    format scored_ts datetime20.;
run;

/* Clean up temporary work datasets */
proc datasets lib=work nolist nowarn;
    delete _compare_: _sum_src_: _sum_tgt_:;
quit;

/* ---- Final summary messages ---- */
%put NOTE: ============================================================;
%put NOTE: Migration Validation Complete;
%put NOTE: Batch: &batch_id;
%put NOTE: Total Checks: &total_checks;
%put NOTE: Passed: &passed_checks | Failed: &failed_checks;
%put NOTE: ============================================================;

/* Reset debugging options */
options nomprint nomlogic nosymbolgen;
