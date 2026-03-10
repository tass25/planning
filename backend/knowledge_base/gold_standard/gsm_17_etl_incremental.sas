/*****************************************************************************
 * Program:     gsm_17_etl_incremental.sas
 * Purpose:     Incremental ETL load with watermark tracking
 * Author:      ETL Development Team
 * Created:     2026-02-19
 * Environment: SAS 9.4M5+
 * Description: Implements delta-load ETL pattern using high-water-mark
 *              timestamps. Supports both initial and incremental loads
 *              for multiple source tables via parameterized macro.
 *****************************************************************************/

/* ------------------------------------------------------------------ */
/* SECTION 1: Environment Setup                                        */
/* ------------------------------------------------------------------ */

/* Source operational database */
libname raw '/data/source/operational' access=readonly;

/* ETL staging area */
libname staging '/data/etl/staging';

/* Target data warehouse */
libname tgt '/data/warehouse/target';

/* ETL control table library */
libname ctl '/data/etl/control';

/* Control parameters */
%let etl_run_id = %sysfunc(datetime(), datetime20.);
%let batch_size = 50000;
%let default_watermark = 01JAN2020;

options mprint mlogic symbolgen compress=yes;

/* ------------------------------------------------------------------ */
/* SECTION 2: Incremental Load Macro Definition                        */
/* ------------------------------------------------------------------ */

/* Macro for delta-load with watermark-based change detection */
%macro incremental_load(src_lib=, src_table=, tgt_lib=, tgt_table=,
                        key_col=, ts_col=modified_dt);

    %put NOTE: ================================================;
    %put NOTE: Processing &src_lib..&src_table -> &tgt_lib..&tgt_table;
    %put NOTE: Key: &key_col | Timestamp column: &ts_col;
    %put NOTE: ================================================;

    /* Retrieve last successful watermark from control table */
    %local watermark delta_count;
    %let watermark = ;
    proc sql noprint;
        select put(max(watermark_ts), datetime20.)
            into :watermark trimmed
        from ctl.etl_watermarks
        where table_name = "&tgt_table";
    quit;

    /* Determine load type based on watermark existence */
    %if &watermark = %then %do;
        /* ------- INITIAL LOAD: no prior watermark found ------- */
        %put NOTE: No watermark found - performing INITIAL LOAD for &tgt_table;

        data staging.delta_&tgt_table;
            set &src_lib..&src_table;
            /* Add ETL tracking metadata */
            etl_load_dt = datetime();
            etl_run_id = "&etl_run_id";
            etl_load_type = "INITIAL";
            format etl_load_dt datetime20.;
        run;
    %end;
    %else %do;
        /* ------- INCREMENTAL LOAD: extract only changed records ------- */
        %put NOTE: Watermark &watermark found - INCREMENTAL LOAD for &tgt_table;

        data staging.delta_&tgt_table;
            set &src_lib..&src_table;
            where &ts_col > input("&watermark", datetime20.);
            /* Add ETL tracking metadata */
            etl_load_dt = datetime();
            etl_run_id = "&etl_run_id";
            etl_load_type = "INCREMENTAL";
            format etl_load_dt datetime20.;
        run;
    %end;

    /* Count extracted delta records */
    proc sql noprint;
        select count(*) into :delta_count trimmed
        from staging.delta_&tgt_table;
    quit;

    %put NOTE: Extracted &delta_count records for &tgt_table;

    /* Upsert: remove stale rows then insert fresh delta */
    proc sql;
        delete from &tgt_lib..&tgt_table
        where &key_col in (
            select &key_col from staging.delta_&tgt_table
        );

        insert into &tgt_lib..&tgt_table
        select * from staging.delta_&tgt_table;
    quit;

    /* Update watermark control table */
    proc sql;
        insert into ctl.etl_watermarks
            (table_name, watermark_ts, records_loaded, load_type, load_dt)
        select "&tgt_table",
               max(&ts_col),
               &delta_count,
               case when "&watermark" = ""
                    then "INITIAL" else "INCREMENTAL" end,
               datetime()
        from staging.delta_&tgt_table;
    quit;

    %put NOTE: Watermark updated for &tgt_table;

%mend incremental_load;

/* ------------------------------------------------------------------ */
/* SECTION 3: Batch Processing via Loop                                */
/* ------------------------------------------------------------------ */

/* Table configuration for batch ETL */
%let table_count = 4;
%let tbl1_src = customers;  %let tbl1_tgt = dim_customer;  %let tbl1_key = customer_id;
%let tbl2_src = products;   %let tbl2_tgt = dim_product;   %let tbl2_key = product_id;
%let tbl3_src = orders;     %let tbl3_tgt = fact_orders;   %let tbl3_key = order_id;
%let tbl4_src = shipments;  %let tbl4_tgt = fact_shipping; %let tbl4_key = shipment_id;

/* Driver macro: loop over configured tables and invoke ETL */
%macro run_etl_batch;
    %do i = 1 %to &table_count;
        %put NOTE: --- Processing table &i of &table_count ---;

        %incremental_load(
            src_lib   = raw,
            src_table = &&tbl&i._src,
            tgt_lib   = tgt,
            tgt_table = &&tbl&i._tgt,
            key_col   = &&tbl&i._key,
            ts_col    = modified_dt
        );
    %end;
%mend run_etl_batch;

/* Execute batch ETL */
%run_etl_batch;

/* ------------------------------------------------------------------ */
/* SECTION 4: Post-Load Error Check                                    */
/* ------------------------------------------------------------------ */

/* Open-code conditional: verify batch completed without errors */
%if &syserr > 0 %then %do;
    %put ERROR: ETL batch failed (SYSERR=&syserr). Halting validation.;
    data staging.etl_error_log;
        length process $50 error_msg $200;
        process = "INCREMENTAL_ETL";
        error_msg = "Batch failed with SYSERR=&syserr";
        error_dt = datetime();
        format error_dt datetime20.;
    run;
%end;
%else %do;
    %put NOTE: ETL batch completed without errors;
%end;

/* ------------------------------------------------------------------ */
/* SECTION 5: Load Summary Record                                      */
/* ------------------------------------------------------------------ */

/* Create audit record for this ETL run */
data tgt.etl_load_summary;
    length batch_id $30 load_status $20;
    batch_id = "&etl_run_id";
    load_dt = datetime();
    tables_processed = &table_count;
    load_status = "COMPLETE";
    format load_dt datetime20.;
run;

/* ------------------------------------------------------------------ */
/* SECTION 6: Post-Load Validation                                     */
/* ------------------------------------------------------------------ */

/* Validate target table row counts after load */
proc sql;
    title "Post-Load Target Table Counts";
    select "dim_customer" as table_name, count(*) as row_count
        from tgt.dim_customer
    union all
    select "dim_product", count(*)
        from tgt.dim_product
    union all
    select "fact_orders", count(*)
        from tgt.fact_orders
    union all
    select "fact_shipping", count(*)
        from tgt.fact_shipping;
quit;

title;

/* ------------------------------------------------------------------ */
/* SECTION 7: Cleanup                                                  */
/* ------------------------------------------------------------------ */

/* Remove staging delta tables */
proc datasets lib=staging nolist;
    delete delta_dim_customer
           delta_dim_product
           delta_fact_orders
           delta_fact_shipping;
quit;

libname raw clear;
libname staging clear;

%put NOTE: ETL batch completed at %sysfunc(datetime(), datetime20.);
