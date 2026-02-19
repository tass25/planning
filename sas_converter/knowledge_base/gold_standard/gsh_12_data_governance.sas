/******************************************************************************
 * PROGRAM:     gsh_12_data_governance.sas
 * PURPOSE:     Enterprise data governance and quality framework
 * VERSION:     3.1.0
 * DATA STEWARD: M. Chen, CDMP — Chief Data Steward
 * DOMAIN:      Enterprise Data Quality Management
 * DESCRIPTION: Implements a comprehensive data governance framework that
 *              performs automated data profiling, completeness validation,
 *              business rule enforcement, cross-source consistency checks,
 *              and timeliness monitoring. Produces a weighted composite
 *              quality scorecard with ODS Excel reporting.
 * REVISION:    3.1.0 — Added cross-source consistency and timeliness checks
 * COPYRIGHT:   (c) 2026 Data Governance Office
 ******************************************************************************/

/* ============================================================================
   SECTION 1: ENVIRONMENT SETUP — Libraries and global parameters
   ============================================================================ */

/* Connect to source systems and quality output stores */
LIBNAME source '/data/enterprise/source'     ACCESS=READONLY;
LIBNAME dq     '/data/governance/quality';
LIBNAME meta   '/data/governance/metadata';
LIBNAME report '/data/governance/reports';

/* Global processing options */
OPTIONS MPRINT MLOGIC SYMBOLGEN COMPRESS=YES
        FULLSTIMER NOFMTERR MINOPERATOR;

/* --- Quality threshold parameters --- */
%LET completeness_threshold = 95;
%LET validity_threshold     = 98;
%LET consistency_threshold  = 99;
%LET freshness_max_days     = 3;
%LET run_date               = %SYSFUNC(TODAY(), DATE9.);
%LET run_datetime           = %SYSFUNC(DATETIME(), DATETIME20.);
%LET dq_version             = 3.1.0;
%LET steward_name           = M. Chen;
%LET domain_name            = Enterprise Data Quality;

/* --- Scorecard dimension weights (must sum to 1.0) --- */
%LET weight_completeness    = 0.30;
%LET weight_validity        = 0.30;
%LET weight_consistency     = 0.25;
%LET weight_timeliness      = 0.15;

/* ============================================================================
   SECTION 2: MACRO — profile_table
   Purpose: Automated data profiling for any table. Captures metadata
            (variable names, types, lengths), row counts, distinct counts
            per column, numeric distributions via PROC UNIVARIATE, and
            categorical frequency analysis via PROC FREQ.
            Results compiled into a standardized profile dataset.
   ============================================================================ */

%MACRO profile_table(lib=, table=);

    %PUT NOTE: ========================================;
    %PUT NOTE: Profiling &lib..&table — started %SYSFUNC(TIME(), TIME8.);
    %PUT NOTE: ========================================;

    /* --- Step 2a: Capture variable metadata via PROC CONTENTS --- */
    PROC CONTENTS DATA=&lib..&table
                  OUT=work.contents_&table (KEEP=NAME TYPE LENGTH FORMAT LABEL NOBS)
                  NOPRINT;
    RUN;

    /* --- Step 2b: Row count and distinct count per column --- */
    PROC SQL NOPRINT;
        /* Total row count for the table */
        SELECT COUNT(*) INTO :total_rows TRIMMED
        FROM &lib..&table;

        /* Get list of all column names into macro variable */
        SELECT NAME INTO :col_list SEPARATED BY ' '
        FROM work.contents_&table;

        %LET n_cols = &SQLOBS;
    QUIT;

    /* Loop over each column to compute distinct value counts */
    %DO i = 1 %TO &n_cols;
        %LET col_name = %SCAN(&col_list, &i, %STR( ));

        PROC SQL NOPRINT;
            SELECT COUNT(DISTINCT &col_name) INTO :distinct_&col_name TRIMMED
            FROM &lib..&table;
        QUIT;
    %END;

    /* --- Step 2c: Numeric distribution statistics via PROC UNIVARIATE --- */
    PROC UNIVARIATE DATA=&lib..&table NOPRINT;
        VAR _NUMERIC_;
        OUTPUT OUT=work.univar_&table
            N=n NMISS=nmiss MEAN=mean STD=std
            MIN=min MAX=max MEDIAN=median
            Q1=q1 Q3=q3 P1=p1 P99=p99;
    RUN;

    /* --- Step 2d: Categorical frequency analysis via PROC FREQ --- */
    PROC FREQ DATA=&lib..&table NOPRINT;
        TABLES _CHARACTER_ / OUT=work.freq_&table
                             MISSING NOCUM;
    RUN;

    /* --- Step 2e: Compile profile into standardized format --- */
    DATA meta.profile_&table;
        LENGTH table_name $32 column_name $32 column_type $4
               total_rows 8 distinct_count 8 null_count 8
               profile_date 8 profiled_by $20;
        FORMAT profile_date DATE9.;

        SET work.contents_&table;

        table_name   = "&table";
        profile_date = TODAY();
        profiled_by  = "&steward_name";

        /* Map SAS type codes to labels */
        IF TYPE = 1 THEN column_type = 'NUM';
        ELSE column_type = 'CHAR';

        total_rows = &total_rows;

        /* Assign distinct count from macro variables */
        column_name    = NAME;
        distinct_count = INPUT(SYMGET('distinct_' || STRIP(NAME)), BEST.);

        /* Compute null count as total minus non-null distinct */
        null_count = total_rows - distinct_count;

        OUTPUT;
    RUN;

    %PUT NOTE: Profiling &lib..&table — completed. &n_cols columns, &total_rows rows.;

%MEND profile_table;

/* ============================================================================
   SECTION 3: MACRO — check_completeness
   Purpose: Validates required columns for null/blank values. Computes
            completeness percentage per column and flags failures against
            the configurable threshold. Uses %DO loop over required columns
            and PROC SQL to count nulls/blanks per column.
   ============================================================================ */

%MACRO check_completeness(lib=, table=, required_cols=);

    %PUT NOTE: ========================================;
    %PUT NOTE: Completeness check for &lib..&table;
    %PUT NOTE: Required columns: &required_cols;
    %PUT NOTE: ========================================;

    /* Count the number of required columns to iterate over */
    %LET n_req = %SYSFUNC(COUNTW(&required_cols, %STR( )));

    /* Initialize empty results table with correct structure */
    DATA work.completeness_&table;
        LENGTH table_name $32 column_name $32
               total_rows 8 non_null_count 8
               completeness_pct 8 threshold 8
               check_status $4 check_date 8;
        FORMAT completeness_pct 6.2 check_date DATE9.;
        STOP;
    RUN;

    /* --- Loop over each required column to check completeness --- */
    %DO j = 1 %TO &n_req;
        %LET req_col = %SCAN(&required_cols, &j, %STR( ));

        /* Count nulls and blanks for this column via PROC SQL */
        PROC SQL NOPRINT;
            SELECT COUNT(*) INTO :total_count TRIMMED
            FROM &lib..&table;

            SELECT COUNT(*) INTO :non_null_ct TRIMMED
            FROM &lib..&table
            WHERE &req_col IS NOT NULL
              AND &req_col NE '';
        QUIT;

        /* Compute completeness percentage and flag pass/fail */
        DATA work._comp_row;
            LENGTH table_name $32 column_name $32
                   total_rows 8 non_null_count 8
                   completeness_pct 8 threshold 8
                   check_status $4 check_date 8;
            FORMAT completeness_pct 6.2 check_date DATE9.;

            table_name      = "&table";
            column_name     = "&req_col";
            total_rows      = &total_count;
            non_null_count  = &non_null_ct;

            /* Calculate completeness as a percentage */
            IF total_rows > 0 THEN
                completeness_pct = (non_null_count / total_rows) * 100;
            ELSE
                completeness_pct = 0;

            threshold  = &completeness_threshold;
            check_date = TODAY();

            /* Flag pass or fail against configurable threshold */
            %IF %SYSEVALF(&non_null_ct / &total_count * 100) < &completeness_threshold %THEN %DO;
                check_status = 'FAIL';
                %PUT WARNING: Column &req_col in &table — completeness below threshold;
            %END;
            %ELSE %DO;
                check_status = 'PASS';
            %END;

            OUTPUT;
        RUN;

        /* Append this column result to the completeness results table */
        PROC APPEND BASE=work.completeness_&table
                    DATA=work._comp_row FORCE;
        RUN;

    %END;

    /* Store final completeness results in DQ library */
    DATA dq.completeness_&table;
        SET work.completeness_&table;
    RUN;

    %PUT NOTE: Completeness check for &table completed — &n_req columns checked.;

%MEND check_completeness;

/* ============================================================================
   SECTION 4: MACRO — check_validity
   Purpose: Validates data against business rules defined in a rules dataset.
            Reads each rule via SET, uses CALL EXECUTE to generate dynamic
            validation SQL, then loops over rules to count violations.
            Results aggregated into a quality scorecard.
   ============================================================================ */

%MACRO check_validity(lib=, table=, rules_ds=);

    %PUT NOTE: ========================================;
    %PUT NOTE: Validity check for &lib..&table;
    %PUT NOTE: Rules dataset: &rules_ds;
    %PUT NOTE: ========================================;

    /* --- Read the rules table and generate dynamic validation SQL --- */
    DATA _NULL_;
        SET &rules_ds END=last;

        /* Each observation contains a business rule definition */
        LENGTH rule_sql $500 rule_id $10 rule_desc $200
               target_column $32 rule_type $20;

        /* Generate CALL EXECUTE for each rule validation query */
        CALL EXECUTE('PROC SQL NOPRINT;');
        CALL EXECUTE('SELECT COUNT(*) INTO :violations_' || STRIP(rule_id));
        CALL EXECUTE(' TRIMMED FROM ' || "&lib..&table");
        CALL EXECUTE(' WHERE ' || STRIP(rule_condition) || ';');
        CALL EXECUTE('QUIT;');

        /* Track total number of rules for downstream loop */
        IF last THEN CALL SYMPUT('n_rules', STRIP(PUT(_N_, BEST.)));
    RUN;

    /* Initialize validity results table */
    DATA work.validity_&table;
        LENGTH table_name $32 rule_id $10 rule_desc $200
               target_column $32 rule_type $20
               total_rows 8 violation_count 8
               validity_pct 8 threshold 8
               check_status $4 check_date 8;
        FORMAT validity_pct 6.2 check_date DATE9.;
        STOP;
    RUN;

    /* --- Loop over rules to collect violation counts and score --- */
    %DO r = 1 %TO &n_rules;

        /* Read the r-th rule from the rules dataset */
        DATA work._rule_result;
            SET &rules_ds (FIRSTOBS=&r OBS=&r);

            LENGTH table_name $32 violation_count 8
                   validity_pct 8 threshold 8
                   check_status $4 check_date 8;
            FORMAT validity_pct 6.2 check_date DATE9.;

            table_name = "&table";
            check_date = TODAY();
            threshold  = &validity_threshold;

            /* Retrieve violation count from generated macro variable */
            violation_count = INPUT(SYMGET('violations_' || STRIP(rule_id)), BEST.);
        RUN;

        /* Get total row count for percentage calculation */
        PROC SQL NOPRINT;
            SELECT COUNT(*) INTO :rule_total TRIMMED
            FROM &lib..&table;
        QUIT;

        /* Compute validity percentage and determine pass/fail */
        DATA work._rule_result;
            SET work._rule_result;
            total_rows = &rule_total;

            /* Calculate validity percentage */
            IF total_rows > 0 THEN
                validity_pct = ((total_rows - violation_count) / total_rows) * 100;
            ELSE
                validity_pct = 0;

            /* Determine pass/fail status against threshold */
            IF validity_pct >= &validity_threshold THEN
                check_status = 'PASS';
            ELSE
                check_status = 'FAIL';
        RUN;

        /* Append to validity results */
        PROC APPEND BASE=work.validity_&table
                    DATA=work._rule_result FORCE;
        RUN;

    %END;

    /* Store validity results in DQ library */
    DATA dq.validity_&table;
        SET work.validity_&table;
    RUN;

    %PUT NOTE: Validity check for &table completed — &n_rules rules evaluated.;

%MEND check_validity;

/* ============================================================================
   SECTION 5: MACRO — check_consistency
   Purpose: Compares two data sources on a shared key to find discrepancies.
            Uses PROC SQL FULL JOIN and a DATA step to classify records
            as match, mismatch, missing_left, or missing_right.
            PROC MEANS computes the overall match rate.
   ============================================================================ */

%MACRO check_consistency(src1=, src2=, key=, compare_cols=);

    %PUT NOTE: ========================================;
    %PUT NOTE: Consistency check: &src1 vs &src2;
    %PUT NOTE: Key: &key | Compare columns: &compare_cols;
    %PUT NOTE: ========================================;

    /* Count comparison columns for loop processing */
    %LET n_compare = %SYSFUNC(COUNTW(&compare_cols, %STR( )));

    /* --- Full outer join to detect all discrepancies --- */
    PROC SQL;
        CREATE TABLE work.consistency_raw AS
        SELECT COALESCE(a.&key, b.&key) AS &key,
               /* Include comparison columns from both left and right sources */
               %DO c = 1 %TO &n_compare;
                   %LET comp_col = %SCAN(&compare_cols, &c, %STR( ));
                   a.&comp_col AS left_&comp_col,
                   b.&comp_col AS right_&comp_col,
               %END;
               /* Classification logic for match status */
               CASE
                   WHEN a.&key IS NULL THEN 'MISSING_LEFT'
                   WHEN b.&key IS NULL THEN 'MISSING_RIGHT'
                   WHEN 1=1
                       %DO c = 1 %TO &n_compare;
                           %LET comp_col = %SCAN(&compare_cols, &c, %STR( ));
                           AND a.&comp_col = b.&comp_col
                       %END;
                   THEN 'MATCH'
                   ELSE 'MISMATCH'
               END AS match_status LENGTH=15
        FROM &src1 AS a
        FULL JOIN &src2 AS b
            ON a.&key = b.&key;
    QUIT;

    /* --- Classify and enrich discrepancy records via DATA step --- */
    DATA work.consistency_detail (KEEP=&key match_status
                                       mismatch_columns check_date)
         work.consistency_mismatches (WHERE=(match_status='MISMATCH'));

        LENGTH match_status $15 mismatch_columns $500 check_date 8;
        FORMAT check_date DATE9.;

        SET work.consistency_raw;
        check_date = TODAY();

        /* Build list of mismatched columns for diagnosis */
        mismatch_columns = '';
        %DO c = 1 %TO &n_compare;
            %LET comp_col = %SCAN(&compare_cols, &c, %STR( ));
            IF left_&comp_col NE right_&comp_col THEN
                mismatch_columns = CATX(', ', mismatch_columns, "&comp_col");
        %END;

        OUTPUT work.consistency_detail;
        IF match_status = 'MISMATCH' THEN OUTPUT work.consistency_mismatches;
    RUN;

    /* --- Compute match rate statistics via PROC MEANS --- */
    PROC MEANS DATA=work.consistency_detail NOPRINT NWAY;
        CLASS match_status;
        OUTPUT OUT=work.consistency_stats (DROP=_TYPE_ _FREQ_)
               N=record_count;
    RUN;

    /* --- Calculate overall match rate via PROC SQL --- */
    PROC SQL NOPRINT;
        SELECT SUM(CASE WHEN match_status='MATCH' THEN 1 ELSE 0 END) /
               COUNT(*) * 100 FORMAT=6.2
        INTO :match_rate TRIMMED
        FROM work.consistency_detail;
    QUIT;

    /* Store consistency results in DQ library */
    DATA dq.consistency_%SCAN(&src1, 2, .)_%SCAN(&src2, 2, .);
        SET work.consistency_detail;
        match_rate = &match_rate;
    RUN;

    %PUT NOTE: Consistency check complete. Match rate: &match_rate.%;

%MEND check_consistency;

/* ============================================================================
   SECTION 6: MACRO — check_timeliness
   Purpose: Checks data freshness by computing the lag between the most
            recent record date and the current date. Uses PROC SQL to get
            max date, DATA step with %SYSFUNC to compute lag, and flags
            stale data when lag exceeds max_lag_days.
   ============================================================================ */

%MACRO check_timeliness(lib=, table=, date_col=, max_lag_days=);

    %PUT NOTE: ========================================;
    %PUT NOTE: Timeliness check for &lib..&table;
    %PUT NOTE: Date column: &date_col | Max lag: &max_lag_days days;
    %PUT NOTE: ========================================;

    /* --- Get the most recent date value via PROC SQL --- */
    PROC SQL NOPRINT;
        SELECT MAX(&date_col) FORMAT=DATE9. INTO :max_date TRIMMED
        FROM &lib..&table;

        SELECT COUNT(*) INTO :table_rows TRIMMED
        FROM &lib..&table;
    QUIT;

    /* --- Compute lag and determine freshness status via DATA step --- */
    DATA dq.timeliness_&table;
        LENGTH table_name $32 date_column $32
               max_date 8 current_date 8 lag_days 8
               max_allowed_lag 8 freshness_status $10
               check_date 8 total_rows 8;
        FORMAT max_date DATE9. current_date DATE9. check_date DATE9.;

        table_name      = "&table";
        date_column     = "&date_col";
        max_date        = INPUT("&max_date", DATE9.);
        current_date    = TODAY();
        check_date      = TODAY();
        max_allowed_lag = &max_lag_days;
        total_rows      = &table_rows;

        /* Calculate the lag in days using INTCK */
        lag_days = INTCK('DAY', max_date, current_date);

        /* Flag as STALE if lag exceeds maximum allowed days */
        %IF %SYSEVALF(%SYSFUNC(TODAY()) - %SYSFUNC(INPUTN(&max_date, DATE9.)) > &max_lag_days) %THEN %DO;
            freshness_status = 'STALE';
            %PUT WARNING: &table is STALE — &date_col lag exceeds &max_lag_days days;
        %END;
        %ELSE %DO;
            freshness_status = 'CURRENT';
        %END;

        OUTPUT;
    RUN;

    %PUT NOTE: Timeliness check for &table completed. Max date: &max_date;

%MEND check_timeliness;

/* ============================================================================
   SECTION 7: MACRO — dq_scorecard
   Purpose: Compiles all quality check results into a weighted composite
            score. Uses PROC SQL to aggregate dimension scores, DATA step
            to compute the weighted composite, PROC REPORT for formatted
            scorecard, and ODS Excel for output distribution.
   ============================================================================ */

%MACRO dq_scorecard;

    %PUT NOTE: ========================================;
    %PUT NOTE: Building DQ Scorecard — &run_date;
    %PUT NOTE: ========================================;

    /* --- Aggregate completeness dimension scores via PROC SQL --- */
    PROC SQL;
        CREATE TABLE work.score_completeness AS
        SELECT 'COMPLETENESS' AS dimension LENGTH=20,
               AVG(completeness_pct) AS dimension_score FORMAT=6.2,
               SUM(CASE WHEN check_status='FAIL' THEN 1 ELSE 0 END) AS fail_count,
               COUNT(*) AS total_checks,
               &weight_completeness AS weight
        FROM dq.completeness_customers
        OUTER UNION CORR
        SELECT 'COMPLETENESS', AVG(completeness_pct),
               SUM(CASE WHEN check_status='FAIL' THEN 1 ELSE 0 END),
               COUNT(*), &weight_completeness
        FROM dq.completeness_transactions
        OUTER UNION CORR
        SELECT 'COMPLETENESS', AVG(completeness_pct),
               SUM(CASE WHEN check_status='FAIL' THEN 1 ELSE 0 END),
               COUNT(*), &weight_completeness
        FROM dq.completeness_products
        OUTER UNION CORR
        SELECT 'COMPLETENESS', AVG(completeness_pct),
               SUM(CASE WHEN check_status='FAIL' THEN 1 ELSE 0 END),
               COUNT(*), &weight_completeness
        FROM dq.completeness_accounts
        OUTER UNION CORR
        SELECT 'COMPLETENESS', AVG(completeness_pct),
               SUM(CASE WHEN check_status='FAIL' THEN 1 ELSE 0 END),
               COUNT(*), &weight_completeness
        FROM dq.completeness_orders;
    QUIT;

    /* --- Aggregate validity dimension scores via PROC SQL --- */
    PROC SQL;
        CREATE TABLE work.score_validity AS
        SELECT 'VALIDITY' AS dimension LENGTH=20,
               AVG(validity_pct) AS dimension_score FORMAT=6.2,
               SUM(CASE WHEN check_status='FAIL' THEN 1 ELSE 0 END) AS fail_count,
               COUNT(*) AS total_checks,
               &weight_validity AS weight
        FROM dq.validity_customers
        OUTER UNION CORR
        SELECT 'VALIDITY', AVG(validity_pct),
               SUM(CASE WHEN check_status='FAIL' THEN 1 ELSE 0 END),
               COUNT(*), &weight_validity
        FROM dq.validity_transactions
        OUTER UNION CORR
        SELECT 'VALIDITY', AVG(validity_pct),
               SUM(CASE WHEN check_status='FAIL' THEN 1 ELSE 0 END),
               COUNT(*), &weight_validity
        FROM dq.validity_products;
    QUIT;

    /* --- Combine all dimension scores into a single table --- */
    DATA work.dq_dimensions;
        SET work.score_completeness
            work.score_validity;
    RUN;

    /* --- Add consistency scores via PROC SQL INSERT --- */
    PROC SQL;
        INSERT INTO work.dq_dimensions
        SELECT 'CONSISTENCY' AS dimension,
               match_rate AS dimension_score,
               CASE WHEN match_rate < &consistency_threshold THEN 1 ELSE 0 END
                   AS fail_count,
               1 AS total_checks,
               &weight_consistency AS weight
        FROM dq.consistency_customers_ext_customers;
    QUIT;

    /* --- Add timeliness scores via DATA step --- */
    DATA work.timeliness_scores;
        SET dq.timeliness_customers
            dq.timeliness_transactions
            dq.timeliness_orders
            dq.timeliness_accounts;

        LENGTH dimension $20;
        dimension = 'TIMELINESS';

        /* Score based on freshness status — degrade if stale */
        IF freshness_status = 'CURRENT' THEN dimension_score = 100;
        ELSE dimension_score = MAX(0, 100 - (lag_days - max_allowed_lag) * 10);

        weight       = &weight_timeliness;
        fail_count   = (freshness_status = 'STALE');
        total_checks = 1;
    RUN;

    /* Append timeliness to combined dimensions */
    PROC APPEND BASE=work.dq_dimensions
                DATA=work.timeliness_scores (KEEP=dimension dimension_score
                     fail_count total_checks weight) FORCE;
    RUN;

    /* --- Compute weighted composite score via DATA step --- */
    DATA work.composite_score;
        SET work.dq_dimensions END=last;

        RETAIN weighted_sum 0 weight_sum 0
               total_fails 0 total_checks_all 0;

        weighted_sum     + (dimension_score * weight);
        weight_sum       + weight;
        total_fails      + fail_count;
        total_checks_all + total_checks;

        IF last THEN DO;
            composite_score = weighted_sum / weight_sum;
            overall_status  = IFC(composite_score >= 90, 'EXCELLENT',
                              IFC(composite_score >= 75, 'GOOD',
                              IFC(composite_score >= 60, 'FAIR', 'POOR')));
            scorecard_date  = TODAY();
            FORMAT scorecard_date DATE9. composite_score 6.2;
            OUTPUT;
        END;
    RUN;

    /* --- Generate formatted scorecard report via PROC REPORT --- */
    PROC REPORT DATA=work.dq_dimensions NOWD
                STYLE(HEADER)=[BACKGROUNDCOLOR=steelblue COLOR=white];
        COLUMNS dimension dimension_score fail_count total_checks weight;
        DEFINE dimension       / GROUP 'Quality Dimension';
        DEFINE dimension_score / ANALYSIS MEAN 'Score (%)' FORMAT=6.2;
        DEFINE fail_count      / ANALYSIS SUM 'Failures';
        DEFINE total_checks    / ANALYSIS SUM 'Total Checks';
        DEFINE weight          / DISPLAY 'Weight' FORMAT=4.2;

        COMPUTE AFTER;
            LINE ' ';
            LINE 'Data Governance Scorecard — Generated &run_date';
            LINE 'Framework Version: &dq_version';
        ENDCOMP;
    RUN;

    /* --- ODS Excel output for distribution to stakeholders --- */
    ODS EXCEL FILE="/data/governance/reports/dq_scorecard_&run_date..xlsx"
             STYLE=SEASIDE
             OPTIONS(SHEET_NAME='DQ Scorecard'
                     EMBEDDED_TITLES='YES');

        /* Print composite score summary */
        PROC PRINT DATA=work.composite_score NOOBS LABEL;
            TITLE 'Enterprise Data Quality Composite Score';
            TITLE2 "Run Date: &run_date | Framework: &dq_version";
        RUN;

        /* Print dimension-level detail */
        PROC PRINT DATA=work.dq_dimensions NOOBS LABEL;
            TITLE 'Quality Dimension Detail';
        RUN;

    ODS EXCEL CLOSE;

    /* Store scorecard history in report library */
    DATA report.dq_scorecard_history;
        SET report.dq_scorecard_history
            work.composite_score;
    RUN;

    %PUT NOTE: DQ Scorecard generated successfully.;
    %PUT NOTE: Report saved to /data/governance/reports/;

%MEND dq_scorecard;

/* ============================================================================
   SECTION 8: MAIN PROGRAM — Execute all quality checks
   Runs all governance checks in sequence: profiling, completeness,
   validity, consistency, timeliness, and scorecard generation.
   ============================================================================ */

/* --- 8a: Profile 5 source tables --- */
%PUT NOTE: ============================================================;
%PUT NOTE: PHASE 1 — DATA PROFILING;
%PUT NOTE: ============================================================;

%profile_table(lib=source, table=customers);
%profile_table(lib=source, table=transactions);
%profile_table(lib=source, table=products);
%profile_table(lib=source, table=accounts);
%profile_table(lib=source, table=orders);

/* --- 8b: Completeness checks for 5 tables --- */
%PUT NOTE: ============================================================;
%PUT NOTE: PHASE 2 — COMPLETENESS CHECKS;
%PUT NOTE: ============================================================;

%check_completeness(lib=source, table=customers,
    required_cols=customer_id name email phone address);
%check_completeness(lib=source, table=transactions,
    required_cols=txn_id customer_id amount txn_date status);
%check_completeness(lib=source, table=products,
    required_cols=product_id product_name category price);
%check_completeness(lib=source, table=accounts,
    required_cols=account_id customer_id account_type open_date balance);
%check_completeness(lib=source, table=orders,
    required_cols=order_id customer_id order_date total_amount ship_date);

/* --- 8c: Validity checks for 3 tables with business rule sets --- */
%PUT NOTE: ============================================================;
%PUT NOTE: PHASE 3 — BUSINESS RULE VALIDATION;
%PUT NOTE: ============================================================;

%check_validity(lib=source, table=customers,
    rules_ds=meta.rules_customers);
%check_validity(lib=source, table=transactions,
    rules_ds=meta.rules_transactions);
%check_validity(lib=source, table=products,
    rules_ds=meta.rules_products);

/* --- 8d: Consistency checks for 2 cross-source comparisons --- */
%PUT NOTE: ============================================================;
%PUT NOTE: PHASE 4 — CROSS-SOURCE CONSISTENCY;
%PUT NOTE: ============================================================;

%check_consistency(src1=source.customers, src2=meta.ext_customers,
    key=customer_id, compare_cols=name email phone);
%check_consistency(src1=source.accounts, src2=meta.ext_accounts,
    key=account_id, compare_cols=account_type balance status);

/* --- 8e: Timeliness checks for 4 tables --- */
%PUT NOTE: ============================================================;
%PUT NOTE: PHASE 5 — DATA FRESHNESS CHECKS;
%PUT NOTE: ============================================================;

%check_timeliness(lib=source, table=customers,
    date_col=last_update_dt, max_lag_days=7);
%check_timeliness(lib=source, table=transactions,
    date_col=txn_date, max_lag_days=1);
%check_timeliness(lib=source, table=orders,
    date_col=order_date, max_lag_days=2);
%check_timeliness(lib=source, table=accounts,
    date_col=last_activity_dt, max_lag_days=3);

/* --- 8f: Generate DQ Scorecard --- */
%PUT NOTE: ============================================================;
%PUT NOTE: PHASE 6 — DQ SCORECARD GENERATION;
%PUT NOTE: ============================================================;

%dq_scorecard;

/* --- 8g: Error handling — Compile and print all failures --- */
%PUT NOTE: ============================================================;
%PUT NOTE: PHASE 7 — FAILURE SUMMARY;
%PUT NOTE: ============================================================;

/* Combine all completeness failure records for review */
DATA work.all_failures;
    LENGTH source_check $30 table_name $32 detail $200
           check_status $4 check_date 8;
    FORMAT check_date DATE9.;

    /* Gather completeness failures from all 5 tables */
    SET dq.completeness_customers (IN=a WHERE=(check_status='FAIL'))
        dq.completeness_transactions (IN=b WHERE=(check_status='FAIL'))
        dq.completeness_products (IN=c WHERE=(check_status='FAIL'))
        dq.completeness_accounts (IN=d WHERE=(check_status='FAIL'))
        dq.completeness_orders (IN=e WHERE=(check_status='FAIL'));

    IF a OR b OR c OR d OR e THEN source_check = 'COMPLETENESS';
    detail = CATX(' | ', 'Column:', column_name,
                  'Completeness:', PUT(completeness_pct, 6.2));
RUN;

/* Gather validity failures from all 3 tables */
DATA work.validity_failures;
    LENGTH source_check $30 table_name $32 detail $200
           check_status $4 check_date 8;
    FORMAT check_date DATE9.;

    SET dq.validity_customers (IN=a WHERE=(check_status='FAIL'))
        dq.validity_transactions (IN=b WHERE=(check_status='FAIL'))
        dq.validity_products (IN=c WHERE=(check_status='FAIL'));

    source_check = 'VALIDITY';
    detail = CATX(' | ', 'Rule:', rule_id,
                  'Violations:', PUT(violation_count, BEST.));
RUN;

/* Append validity failures to combined failure table */
PROC APPEND BASE=work.all_failures
            DATA=work.validity_failures FORCE;
RUN;

/* Print failure summary report to log and output */
TITLE 'DATA GOVERNANCE FRAMEWORK — FAILURE SUMMARY';
TITLE2 "Run Date: &run_date | Framework Version: &dq_version";
TITLE3 "Data Steward: &steward_name | Domain: &domain_name";

PROC PRINT DATA=work.all_failures NOOBS LABEL;
    VAR source_check table_name detail check_status check_date;
    LABEL source_check = 'Check Type'
          table_name   = 'Table'
          detail       = 'Details'
          check_status = 'Status'
          check_date   = 'Date';
RUN;

TITLE;

/* --- Final program status log --- */
%PUT NOTE: ============================================================;
%PUT NOTE: Data Governance Framework execution complete.;
%PUT NOTE: Run date: &run_date;
%PUT NOTE: Framework version: &dq_version;
%PUT NOTE: Steward: &steward_name;
%PUT NOTE: Domain: &domain_name;
%PUT NOTE: ============================================================;

/* End of gsh_12_data_governance.sas */
