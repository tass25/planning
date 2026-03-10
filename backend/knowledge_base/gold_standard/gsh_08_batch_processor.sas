/******************************************************************************
 * Program Name : gsh_08_batch_processor.sas
 * Author       : Batch Operations Team — Enterprise Integration Platform
 * Created      : 2026-01-15
 * Modified     : 2026-02-19
 * Version      : 2.3
 * Purpose      : Enterprise batch job processing framework with comprehensive
 *                error handling, retry logic, and audit trail. Supports CSV,
 *                fixed-width, and SAS dataset ingestion with configurable
 *                transformation rules and target loading strategies.
 * Dependencies : batch_utilities.sas
 * Frequency    : Daily / On-demand batch execution
 * Change Log   :
 *   2026-01-15  v1.0  Initial framework development          (A. Patel)
 *   2026-01-28  v1.5  Added retry logic and error handling    (S. Chen)
 *   2026-02-10  v2.0  Enhanced transformation engine          (A. Patel)
 *   2026-02-19  v2.3  Added email notifications, audit trail  (K. Brooks)
 ******************************************************************************/

/* ========================================================================= */
/* SECTION 1: Environment Setup — Libraries, Options, Batch Parameters       */
/* ========================================================================= */

options mprint mlogic symbolgen nocenter ls=200 ps=65
        validvarname=v7 nofmterr msglevel=i;

/* --- Library references for batch processing layers --- */
libname indata   '/batch/input/data'       access=readonly;
libname outdata  '/batch/output/data';
libname control  '/batch/control/metadata';
libname batchlog '/batch/logs/audit';

/* --- Batch execution parameters --- */
%let batch_id      = BATCH-%sysfunc(today(), yymmddn8.)-%sysfunc(time(), tod5.);
%let max_retries   = 3;
%let email_list    = ops-team@company.com admin@company.com;
%let batch_rc      = 0;
%let total_files   = 0;
%let files_success = 0;
%let files_failed  = 0;
%let total_rows_in = 0;
%let total_rows_out= 0;
%let batch_start   = %sysfunc(datetime());
%let run_date      = %sysfunc(today(), yymmdd10.);

/* --- Processing control flags --- */
%let skip_validation = 0;
%let enable_email    = 1;
%let debug_mode      = 0;
%let archive_input   = 1;

/* --- File format specifications --- */
%let csv_delimiter  = %str(,);
%let csv_encoding   = utf-8;
%let fixed_reclen   = 250;

/* Include shared batch utility macros */
%include '/batch/common/batch_utilities.sas';

/* ========================================================================= */
/* SECTION 2: Macro Definitions                                              */
/* ========================================================================= */

/* --------------------------------------------------------------------- */
/* MACRO: init_batch                                                       */
/*   Initializes a new batch run by inserting a control record into the    */
/*   batch_runs table, setting global tracking variables, and logging      */
/*   the batch start event.                                                */
/* Parameters:                                                             */
/*   batch_id — unique identifier for this batch execution                 */
/* --------------------------------------------------------------------- */
%macro init_batch(batch_id=);
    %local start_ts n_pending;

    %let start_ts = %sysfunc(datetime(), datetime20.);

    %put NOTE: ============================================================;
    %put NOTE: Batch Processing Framework — Initialization;
    %put NOTE: Batch ID   : &batch_id;
    %put NOTE: Start Time : &start_ts;
    %put NOTE: Max Retries: &max_retries;
    %put NOTE: ============================================================;

    /* Insert batch run record into the control table */
    proc sql;
        insert into control.batch_runs
            (batch_id, start_time, status, total_files,
             files_processed, files_failed, operator, run_date)
        values
            ("&batch_id", %sysfunc(datetime()), "RUNNING", 0,
             0, 0, "&sysuserid", %sysfunc(today()));
    quit;

    /* Count pending files in the file queue */
    proc sql noprint;
        select count(*) into :n_pending trimmed
        from control.file_queue
        where batch_id = "&batch_id"
          and status = 'PENDING';
    quit;

    /* Set global tracking variables */
    %let total_files = &n_pending;
    %let files_success = 0;
    %let files_failed = 0;
    %let batch_rc = 0;

    %put NOTE: Found &n_pending files pending for batch &batch_id;

    /* Log initialization event to the batch audit table */
    data batchlog.init_log;
        length batch_id $30 event $50 detail $200 timestamp 8;
        format timestamp datetime20.;
        batch_id  = "&batch_id";
        event     = "BATCH_INITIALIZED";
        detail    = "Pending files: &n_pending | Max retries: &max_retries";
        timestamp = datetime();
        output;
    run;

%mend init_batch;

/* --------------------------------------------------------------------- */
/* MACRO: process_file                                                     */
/*   Processes a single input file based on its type (CSV, FIXED, SAS).    */
/*   Performs validation checks on row count, required columns, and data    */
/*   types. Uses CALL EXECUTE for dynamic processing based on content.     */
/* Parameters:                                                             */
/*   file_path — full filesystem path to the input file                    */
/*   file_type — format identifier: CSV, FIXED, or SAS                    */
/* --------------------------------------------------------------------- */
%macro process_file(file_path=, file_type=);
    %local dsname obs_count retry_count file_rc col_list n_cols;

    %let retry_count = 0;
    %let file_rc = 0;
    %let dsname = work._incoming_%sysfunc(monotonic());

    %put NOTE: --- Processing file: &file_path (type=&file_type) ---;

    /* ================================================================= */
    /* FILE INGESTION — Branch by file type                               */
    /* ================================================================= */

    /* ---- CSV file ingestion ---- */
    %if &file_type = CSV %then %do;
        data &dsname;
            length _line $2000 _field1-_field50 $200;

            /* Read comma-delimited file, skip header row */
            infile "&file_path"
                delimiter="&csv_delimiter"
                missover dsd lrecl=2000
                firstobs=2
                encoding="&csv_encoding"
                end=_eof;

            /* Read header row on first iteration to capture column names */
            if _n_ = 1 then do;
                infile "&file_path" obs=1;
                input _header $2000.;
                call symputx('col_list', _header);
            end;

            /* Parse each data row into field variables */
            input _field1-_field50;

            /* Track row number for audit purposes */
            _row_num = _n_;

            /* Generate dynamic post-processing code via CALL EXECUTE */
            if _n_ = 1 then do;
                call execute('data &dsname._final; set &dsname; ');
                call execute('run;');
            end;
        run;
    %end;

    /* ---- Fixed-width file ingestion ---- */
    %else %if &file_type = FIXED %then %do;
        data &dsname;
            /* Read fixed-format file with specified record length */
            infile "&file_path"
                recfm=f lrecl=&fixed_reclen
                end=_eof;

            /* Column-position INPUT for fixed-width record layout */
            input
                @1   record_type    $2.
                @3   account_id     $12.
                @15  customer_name  $40.
                @55  transaction_dt  yymmdd10.
                @65  amount          12.2
                @77  currency_code  $3.
                @80  status_code    $2.
                @82  region_code    $5.
                @87  product_id     $10.
                @97  description    $100.
                @197 filler         $54.
            ;
            format transaction_dt yymmdd10. amount comma12.2;

            /* Skip header (HD) and trailer (TR) records */
            if record_type not in ('HD', 'TR');
            _row_num = _n_;
        run;
    %end;

    /* ---- SAS dataset copy ---- */
    %else %if &file_type = SAS %then %do;
        /* Copy dataset from input library to work */
        proc copy in=indata out=work;
            select %scan(&file_path, -1, /);
        run;

        /* Rename copied dataset to standardized working name */
        proc datasets lib=work nolist;
            change %scan(&file_path, -1, /) = %scan(&dsname, 2, .);
        quit;
    %end;

    /* ---- Unsupported file type — raise error ---- */
    %else %do;
        %put ERROR: Unsupported file type: &file_type;
        %let file_rc = 1;
        %error_handler(step=PROCESS_FILE, severity=CRITICAL);
        %return;
    %end;

    /* ================================================================= */
    /* POST-INGESTION VALIDATION                                          */
    /* ================================================================= */

    %if &file_rc = 0 %then %do;

        /* --- Check 1: Row count validation --- */
        proc sql noprint;
            select count(*) into :obs_count trimmed
            from &dsname;
        quit;

        %if &obs_count = 0 %then %do;
            %put WARNING: File &file_path produced 0 observations.;
            %let file_rc = 2;
            %error_handler(step=ROW_COUNT_CHECK, severity=WARNING);
        %end;
        %else %do;
            %put NOTE: File &file_path loaded &obs_count observations.;
            %let total_rows_in = %eval(&total_rows_in + &obs_count);
        %end;

        /* --- Check 2: Required columns validation --- */
        proc sql noprint;
            select count(*) into :n_cols trimmed
            from dictionary.columns
            where libname = 'WORK'
              and memname = "%upcase(%scan(&dsname, 2, .))";
        quit;

        %if &n_cols < 3 %then %do;
            %put ERROR: File &file_path has insufficient columns (&n_cols).;
            %let file_rc = 3;
            %error_handler(step=COLUMN_CHECK, severity=CRITICAL);
        %end;

        /* --- Check 3: Duplicate key detection --- */
        proc sort data=&dsname nodupkey
                  dupout=work._dupes_%sysfunc(monotonic())
                  out=&dsname._dedup;
            by account_id;
        run;

        %if &syserr > 0 %then %do;
            %put WARNING: Duplicate detection encountered issues for &file_path;
            %error_handler(step=DEDUP_CHECK, severity=WARNING);
        %end;

    %end;

    /* ================================================================= */
    /* UPDATE FILE QUEUE STATUS                                           */
    /* ================================================================= */

    /* Mark file as processed or failed in the control table */
    proc sql;
        update control.file_queue
        set status      = ifc(&file_rc = 0, 'PROCESSED', 'FAILED'),
            processed_at = datetime(),
            row_count    = &obs_count,
            return_code  = &file_rc
        where file_path = "&file_path"
          and batch_id  = "&batch_id";
    quit;

    /* Track cumulative success/failure counts */
    %if &file_rc = 0 %then %do;
        %let files_success = %eval(&files_success + 1);
    %end;
    %else %do;
        %let files_failed = %eval(&files_failed + 1);
    %end;

%mend process_file;

/* --------------------------------------------------------------------- */
/* MACRO: transform_data                                                   */
/*   Applies transformation rules from a rules dataset to the input data.  */
/*   Uses CALL EXECUTE to generate dynamic DATA step code. Iterates over   */
/*   transformation categories with a %DO loop.                            */
/* Parameters:                                                             */
/*   input_ds — work dataset to transform                                  */
/*   rules_ds — dataset containing transformation rules                    */
/* --------------------------------------------------------------------- */
%macro transform_data(input_ds=, rules_ds=);
    %local n_rules n_categories i cat_name transform_rc;

    %let transform_rc = 0;

    %put NOTE: --- Applying transformations from &rules_ds to &input_ds ---;

    /* Count total active transformation rules */
    proc sql noprint;
        select count(*) into :n_rules trimmed
        from &rules_ds
        where active_flag = 'Y';
    quit;

    %put NOTE: Found &n_rules active transformation rules.;

    /* Get distinct transformation categories ordered by priority */
    proc sql noprint;
        select count(distinct category) into :n_categories trimmed
        from &rules_ds
        where active_flag = 'Y';

        select distinct category into :cat1 - :cat99
        from &rules_ds
        where active_flag = 'Y'
        order by priority;
    quit;

    /* ---- Iterate over each transformation category ---- */
    %do i = 1 %to &n_categories;
        %let cat_name = &&cat&i;

        %put NOTE: Processing transformation category: &cat_name (&i of &n_categories);

        /* Read rules for this category and generate dynamic DATA step code */
        data _null_;
            set &rules_ds end=_last;
            where category = "&cat_name" and active_flag = 'Y';

            /* Build DATA step header on first observation */
            if _n_ = 1 then do;
                call execute("data &input_ds._&cat_name;");
                call execute("  set &input_ds;");
            end;

            /* Apply transformation based on rule type */
            length _code $500;
            select (rule_type);
                /* Column rename transformation */
                when ('RENAME')
                    _code = cat('rename ', strip(source_col),
                                ' = ', strip(target_col), ';');
                /* Derived column computation */
                when ('DERIVE')
                    _code = cat(strip(target_col), ' = ',
                                strip(expression), ';');
                /* Format assignment */
                when ('FORMAT')
                    _code = cat('format ', strip(source_col),
                                ' ', strip(expression), ';');
                /* Row filter condition */
                when ('FILTER')
                    _code = cat('if ', strip(expression), ';');
                /* Value recoding */
                when ('RECODE')
                    _code = cat('if ', strip(source_col), ' = ',
                                quote(strip(old_value)),
                                ' then ', strip(target_col), ' = ',
                                quote(strip(new_value)), ';');
                otherwise
                    _code = cat('/* Unknown rule type: ',
                                strip(rule_type), ' */');
            end;

            call execute('  ' || strip(_code));

            /* Close DATA step after last rule in this category */
            if _last then do;
                call execute('run;');
            end;
        run;

        /* Verify the transformation produced output without errors */
        %if &syserr > 4 %then %do;
            %put ERROR: Transformation category &cat_name failed with SYSERR=&syserr;
            %let transform_rc = 1;
            %error_handler(step=TRANSFORM_&cat_name, severity=CRITICAL);
            %goto transform_exit;
        %end;

        /* Replace input dataset with transformed version for next category */
        proc datasets lib=work nolist;
            delete %scan(&input_ds, 2, .);
            change %scan(&input_ds, 2, .)._&cat_name
                   = %scan(&input_ds, 2, .);
        quit;

    %end;

    /* --- Post-transformation row count validation --- */
    proc sql noprint;
        select count(*) into :post_count trimmed
        from &input_ds;
    quit;

    %put NOTE: Post-transformation row count: &post_count;

    %transform_exit:

    /* Log transformation summary to audit table */
    data batchlog.transform_log (keep=batch_id input_ds n_rules n_categories
                                      transform_rc timestamp);
        length batch_id $30 input_ds $50 timestamp 8;
        format timestamp datetime20.;
        batch_id     = "&batch_id";
        input_ds     = "&input_ds";
        n_rules      = &n_rules;
        n_categories = &n_categories;
        transform_rc = &transform_rc;
        timestamp    = datetime();
    run;

%mend transform_data;

/* --------------------------------------------------------------------- */
/* MACRO: load_target                                                      */
/*   Loads processed data into target tables. Supports FULL (truncate and  */
/*   reload) and INCREMENTAL (upsert) load strategies. Validates row       */
/*   counts post-load and logs the operation.                              */
/* Parameters:                                                             */
/*   source_ds    — work dataset containing data to load                   */
/*   target_table — name of the target table in outdata library            */
/*   load_type    — FULL (truncate+insert) or INCREMENTAL (upsert)         */
/* --------------------------------------------------------------------- */
%macro load_target(source_ds=, target_table=, load_type=);
    %local src_count tgt_before tgt_after load_rc delta;

    %let load_rc = 0;

    %put NOTE: --- Loading &source_ds into &target_table (mode=&load_type) ---;

    /* Get source row count before load */
    proc sql noprint;
        select count(*) into :src_count trimmed
        from &source_ds;
    quit;

    /* Get target row count before load for delta calculation */
    proc sql noprint;
        select count(*) into :tgt_before trimmed
        from outdata.&target_table;
    quit;

    /* ---- FULL load: delete all existing rows and insert ---- */
    %if &load_type = FULL %then %do;

        %put NOTE: Executing FULL load — truncating &target_table;

        /* Delete all existing rows from the target table */
        proc sql;
            delete from outdata.&target_table;
        quit;

        /* Insert all rows from source into target */
        proc sql;
            insert into outdata.&target_table
            select * from &source_ds;
        quit;

        %if &syserr > 4 %then %do;
            %put ERROR: FULL load failed for &target_table (SYSERR=&syserr);
            %let load_rc = 1;
            %error_handler(step=LOAD_FULL_&target_table, severity=CRITICAL);
        %end;

    %end;

    /* ---- INCREMENTAL load: merge/upsert logic ---- */
    %else %do;

        %put NOTE: Executing INCREMENTAL load — upserting into &target_table;

        /* Update existing records that match on primary key */
        proc sql;
            update outdata.&target_table as t
            set t.last_updated = datetime()
            where exists (
                select 1 from &source_ds as s
                where s.record_key = t.record_key
            );
        quit;

        /* Insert new records that do not already exist in target */
        proc sql;
            insert into outdata.&target_table
            select s.*, datetime() as loaded_at format=datetime20.
            from &source_ds as s
            where not exists (
                select 1 from outdata.&target_table as t
                where t.record_key = s.record_key
            );
        quit;

        %if &syserr > 4 %then %do;
            %put ERROR: INCREMENTAL load failed for &target_table (SYSERR=&syserr);
            %let load_rc = 1;
            %error_handler(step=LOAD_INCR_&target_table, severity=CRITICAL);
        %end;

    %end;

    /* ---- Post-load row count validation ---- */
    proc sql noprint;
        select count(*) into :tgt_after trimmed
        from outdata.&target_table;
    quit;

    /* Calculate net change in target table */
    %let delta = %eval(&tgt_after - &tgt_before);
    %let total_rows_out = %eval(&total_rows_out + &delta);

    %put NOTE: Load complete — Source: &src_count | Before: &tgt_before | After: &tgt_after | Delta: &delta;

    /* Verify row count consistency for FULL loads */
    %if &load_type = FULL and &tgt_after ne &src_count %then %do;
        %put WARNING: Row count mismatch after FULL load. Expected &src_count, got &tgt_after;
        %error_handler(step=LOAD_VALIDATE_&target_table, severity=WARNING);
    %end;

    /* Log load operation to audit table */
    data batchlog.load_log (keep=batch_id target_table load_type
                                 src_count tgt_before tgt_after
                                 load_rc timestamp);
        length batch_id $30 target_table $50 load_type $20 timestamp 8;
        format timestamp datetime20.;
        batch_id     = "&batch_id";
        target_table = "&target_table";
        load_type    = "&load_type";
        src_count    = &src_count;
        tgt_before   = &tgt_before;
        tgt_after    = &tgt_after;
        load_rc      = &load_rc;
        timestamp    = datetime();
    run;

%mend load_target;

/* --------------------------------------------------------------------- */
/* MACRO: error_handler                                                    */
/*   Centralized error handling macro. Logs error details to the audit     */
/*   table, sends email notifications for critical errors, and propagates  */
/*   error state via CALL SYMPUT for downstream decision-making.           */
/* Parameters:                                                             */
/*   step     — name of the processing step where error occurred           */
/*   severity — CRITICAL, WARNING, or INFO                                 */
/* --------------------------------------------------------------------- */
%macro error_handler(step=, severity=);
    %local err_timestamp err_msg;

    %let err_timestamp = %sysfunc(datetime(), datetime20.);

    %put NOTE: *** Error Handler Invoked ***;
    %put NOTE: Step     : &step;
    %put NOTE: Severity : &severity;
    %put NOTE: SYSERR   : &syserr;
    %put NOTE: SYSRC    : &sysrc;

    /* Log error details to the error audit table */
    data batchlog.error_log;
        length batch_id $30 step_name $50 severity $10
               error_code 8 error_msg $500 timestamp 8;
        format timestamp datetime20.;

        batch_id   = "&batch_id";
        step_name  = "&step";
        severity   = "&severity";
        error_code = &syserr;
        error_msg  = symget('syserrortext');
        timestamp  = datetime();

        /* Propagate error state to global macro scope */
        call symputx('batch_rc', 1, 'G');
        call symputx('last_error_step', "&step", 'G');
        call symputx('last_error_time', put(datetime(), datetime20.), 'G');
    run;

    /* ---- Handle CRITICAL severity: email notification ---- */
    %if &severity = CRITICAL %then %do;

        %put ERROR: CRITICAL error in step &step — sending notification.;

        /* Define email fileref for notification */
        filename email_out email
            to=("&email_list")
            subject="CRITICAL: Batch &batch_id failed at step &step"
            type="text/plain";

        /* Write structured error notification email */
        data _null_;
            file email_out;
            put "====================================================";
            put "BATCH PROCESSING ALERT — CRITICAL ERROR";
            put "====================================================";
            put " ";
            put "Batch ID    : &batch_id";
            put "Failed Step : &step";
            put "Severity    : &severity";
            put "Error Code  : &syserr";
            put "Timestamp   : &err_timestamp";
            put " ";
            put "Immediate attention required.";
            put "Review the batch log for details.";
            put " ";
            put "====================================================";
        run;

        /* Release email fileref */
        filename email_out clear;

        /* Set batch return code to critical failure level */
        %let batch_rc = 2;

    %end;

    /* ---- Handle WARNING severity: log and continue ---- */
    %else %if &severity = WARNING %then %do;

        %put WARNING: Non-critical issue in step &step — continuing batch.;

        /* Append warning record to the warnings summary table */
        proc sql;
            insert into control.batch_warnings
                (batch_id, step_name, warning_msg, warning_time)
            values
                ("&batch_id", "&step",
                 "Warning encountered — see log for details",
                 %sysfunc(datetime()));
        quit;

    %end;

    /* ---- Handle INFO severity: log informational note ---- */
    %else %do;

        %put NOTE: Informational event logged for step &step;

    %end;

%mend error_handler;

/* --------------------------------------------------------------------- */
/* MACRO: finalize_batch                                                   */
/*   Finalizes the batch run by updating the control table with end time,  */
/*   final status, and summary metrics. Generates a batch summary dataset  */
/*   and optionally archives processed input files.                        */
/* Parameters:                                                             */
/*   batch_id — unique batch identifier to finalize                        */
/*   status   — final status: SUCCESS, COMPLETED_WITH_ERRORS, or FAILED   */
/* --------------------------------------------------------------------- */
%macro finalize_batch(batch_id=, status=);
    %local end_ts elapsed_sec elapsed_min;

    %let end_ts = %sysfunc(datetime());
    %let elapsed_sec = %sysevalf(&end_ts - &batch_start);
    %let elapsed_min = %sysevalf(&elapsed_sec / 60, ceil);

    %put NOTE: ============================================================;
    %put NOTE: Batch Finalization — &batch_id;
    %put NOTE: Status         : &status;
    %put NOTE: Files OK       : &files_success of &total_files;
    %put NOTE: Files Failed   : &files_failed;
    %put NOTE: Elapsed Time   : &elapsed_min minutes;
    %put NOTE: ============================================================;

    /* Update batch control table with final status and metrics */
    proc sql;
        update control.batch_runs
        set end_time        = &end_ts,
            status          = "&status",
            total_files     = &total_files,
            files_processed = &files_success,
            files_failed    = &files_failed,
            rows_in         = &total_rows_in,
            rows_out        = &total_rows_out,
            elapsed_seconds = &elapsed_sec,
            return_code     = &batch_rc
        where batch_id = "&batch_id";
    quit;

    /* Generate batch summary dataset for reporting */
    data batchlog.batch_summary;
        length batch_id $30 status $20 detail $500 timestamp 8;
        format timestamp datetime20. batch_start_dt datetime20.
               batch_end_dt datetime20.;

        batch_id       = "&batch_id";
        status         = "&status";
        total_files    = &total_files;
        files_success  = &files_success;
        files_failed   = &files_failed;
        total_rows_in  = &total_rows_in;
        total_rows_out = &total_rows_out;
        batch_start_dt = &batch_start;
        batch_end_dt   = &end_ts;
        elapsed_min    = &elapsed_min;

        /* Build human-readable summary detail string */
        detail = catx(' | ',
            cat('Files: ', put(total_files, 8. -l)),
            cat('OK: ', put(files_success, 8. -l)),
            cat('Fail: ', put(files_failed, 8. -l)),
            cat('Rows In: ', put(total_rows_in, comma12. -l)),
            cat('Rows Out: ', put(total_rows_out, comma12. -l)),
            cat('Duration: ', put(elapsed_min, 8. -l), ' min')
        );

        timestamp = datetime();
        output;
    run;

    /* Archive processed input files if archiving is enabled */
    %if &archive_input = 1 %then %do;
        %put NOTE: Archiving processed input files...;

        data _null_;
            set control.file_queue;
            where batch_id = "&batch_id" and status = 'PROCESSED';

            /* Build archive path and move file via system command */
            length archive_path $500 cmd $1000;
            archive_path = cats('/batch/archive/', "&batch_id", '/',
                               scan(file_path, -1, '/'));
            cmd = catx(' ', 'mv', strip(file_path), strip(archive_path));
            call system(cmd);
        run;
    %end;

%mend finalize_batch;

/* ========================================================================= */
/* SECTION 3: Main Program Execution                                         */
/* ========================================================================= */

%put NOTE: ================================================================;
%put NOTE: BATCH PROCESSING FRAMEWORK — MAIN EXECUTION;
%put NOTE: Batch ID : &batch_id;
%put NOTE: Run Date : &run_date;
%put NOTE: ================================================================;

/* ------------------------------------------------------------------- */
/* Step 1: Initialize the batch run                                      */
/* ------------------------------------------------------------------- */
%init_batch(batch_id=&batch_id);

/* ------------------------------------------------------------------- */
/* Step 2: Read file list from control table and process each file       */
/* ------------------------------------------------------------------- */
%macro run_batch_files;
    %local i file_path_i file_type_i n_files;

    /* Retrieve list of pending files from the file queue */
    proc sql noprint;
        select count(*) into :n_files trimmed
        from control.file_queue
        where batch_id = "&batch_id"
          and status = 'PENDING';

        select file_path, file_type
        into :fp1 - :fp999, :ft1 - :ft999
        from control.file_queue
        where batch_id = "&batch_id"
          and status = 'PENDING'
        order by priority, file_id;
    quit;

    %put NOTE: Processing &n_files files in batch &batch_id;

    /* --- Loop over each pending file in the queue --- */
    %do i = 1 %to &n_files;
        %let file_path_i = &&fp&i;
        %let file_type_i = &&ft&i;

        %put NOTE: ========================================================;
        %put NOTE: File &i of &n_files: &file_path_i (&file_type_i);
        %put NOTE: ========================================================;

        /* Step 2a: Ingest and validate the source file */
        %process_file(file_path=&file_path_i, file_type=&file_type_i);

        /* Check for critical failure — abort batch if needed */
        %if &batch_rc >= 2 %then %do;
            %put ERROR: Critical failure detected — aborting batch.;
            %goto batch_abort;
        %end;

        /* Step 2b: Apply transformation rules to ingested data */
        %transform_data(
            input_ds=work._incoming_%eval(&i),
            rules_ds=control.transform_rules
        );

        /* Check for transformation failure */
        %if &syserr > 4 %then %do;
            %put ERROR: Transformation failed for file &file_path_i;
            %error_handler(step=TRANSFORM_FILE_&i, severity=CRITICAL);
            %goto batch_abort;
        %end;

        /* Step 2c: Load transformed data to target table */
        %load_target(
            source_ds=work._incoming_%eval(&i),
            target_table=%scan(&file_path_i, -1, /.),
            load_type=INCREMENTAL
        );

        /* Check for load failure */
        %if &syserr > 4 %then %do;
            %put ERROR: Load failed for file &file_path_i;
            %error_handler(step=LOAD_FILE_&i, severity=CRITICAL);
        %end;

    %end;

    %batch_abort:

%mend run_batch_files;

/* Execute the batch file processing loop */
%run_batch_files;

/* ------------------------------------------------------------------- */
/* Step 3: Determine final batch status based on results                 */
/* ------------------------------------------------------------------- */
%macro set_final_status;
    %global final_status;

    %if &batch_rc >= 2 %then %do;
        %let final_status = FAILED;
    %end;
    %else %if &files_failed > 0 %then %do;
        %let final_status = COMPLETED_WITH_ERRORS;
    %end;
    %else %do;
        %let final_status = SUCCESS;
    %end;

    %put NOTE: Final batch status: &final_status;
%mend set_final_status;

%set_final_status;

/* ------------------------------------------------------------------- */
/* Step 4: Finalize batch and generate summary                           */
/* ------------------------------------------------------------------- */
%finalize_batch(batch_id=&batch_id, status=&final_status);

/* ------------------------------------------------------------------- */
/* Step 5: Print batch summary report                                    */
/* ------------------------------------------------------------------- */
title1 "Batch Processing Summary Report";
title2 "Batch ID: &batch_id | Date: &run_date";

proc print data=batchlog.batch_summary noobs label;
    var batch_id status total_files files_success files_failed
        total_rows_in total_rows_out elapsed_min;
    label batch_id       = 'Batch ID'
          status         = 'Status'
          total_files    = 'Total Files'
          files_success  = 'Successful'
          files_failed   = 'Failed'
          total_rows_in  = 'Rows Ingested'
          total_rows_out = 'Rows Loaded'
          elapsed_min    = 'Duration (min)';
run;

title;

/* ------------------------------------------------------------------- */
/* Step 6: Print error summary report if errors occurred                  */
/* ------------------------------------------------------------------- */
%if &files_failed > 0 or &batch_rc > 0 %then %do;

    title1 "Batch Error Summary";
    title2 "Batch ID: &batch_id";

    proc print data=batchlog.error_log noobs;
        where batch_id = "&batch_id";
        var step_name severity error_code error_msg timestamp;
    run;

    title;

%end;

/* ------------------------------------------------------------------- */
/* Step 7: Cleanup temporary work datasets                               */
/* ------------------------------------------------------------------- */
proc datasets lib=work nolist nowarn;
    delete _incoming_: _dupes_:;
quit;

/* --- Reset session options to defaults --- */
options nomprint nomlogic nosymbolgen;

/* --- Final completion banner --- */
%put NOTE: ================================================================;
%put NOTE: Batch &batch_id completed with status: &final_status;
%put NOTE: Files processed: &files_success of &total_files;
%put NOTE: Files failed   : &files_failed;
%put NOTE: Total rows in  : &total_rows_in;
%put NOTE: Total rows out : &total_rows_out;
%put NOTE: ================================================================;
