/******************************************************************************
 * Program Name : gsh_03_warehouse_load.sas
 * Author       : Data Warehouse Engineering — Enterprise Data Platform
 * Created      : 2025-09-01
 * Modified     : 2026-02-19
 * Purpose      : Dimension and fact table loading pipeline for the enterprise
 *                data warehouse. Implements incremental extraction using
 *                watermark-based change tracking, SCD Type 2 dimension
 *                management, and surrogate key lookup for fact table loading.
 * Source System: OLTP via ODBC (Oracle), flat file supplements
 * Dependencies : etl_utilities.sas (shared extraction and audit macros)
 * Schedule     : Nightly at 02:00 (Autosys Job DWH-LOAD-001)
 * Change Log   :
 *   2025-09-01  v1.0  Initial warehouse load pipeline       (M. Garcia)
 *   2025-10-15  v1.1  Added SCD2 merge macro                (M. Garcia)
 *   2025-11-20  v1.2  Fact table loading with dim key lookup (K. Nguyen)
 *   2026-01-05  v1.3  Added watermark-based incremental load (M. Garcia)
 *   2026-02-19  v1.4  Error handling and rollback logging    (K. Nguyen)
 ******************************************************************************/

/* ========================================================================= */
/* SECTION 1: Environment Configuration                                      */
/* ========================================================================= */

options mprint mlogic symbolgen nocenter ls=200 ps=65
        validvarname=v7 nofmterr compress=binary;

/* --- Source system connection via ODBC --- */
libname srcdb odbc dsn='PROD_OLTP'
              schema=dbo
              access=readonly
              readbuff=10000;

/* --- Staging, warehouse, and control libraries --- */
libname staging '/dwh/staging';
libname whouse  '/dwh/warehouse';
libname tgt     '/dwh/target';
libname archive '/dwh/archive';
libname ctrl    '/dwh/control';

/* Global job control variables */
%let job_name      = DWH_NIGHTLY_LOAD;
%let job_run_id    = %sysfunc(putn(%sysfunc(datetime()), datetime20.));
%let job_status    = RUNNING;
%let job_rc        = 0;
%let process_dt    = %sysfunc(today(), yymmdd10.);
%let n_src_tables  = 5;

/* Load shared utility macros */
%include '/dwh/common/etl_utilities.sas';

/* ========================================================================= */
/* SECTION 2: Utility Macro Definitions                                      */
/* ========================================================================= */

/* --------------------------------------------------------------------- */
/* MACRO: extract_table                                                   */
/*   Extracts data from a source library into a staging dataset.          */
/*   Supports optional WHERE filter for incremental loads.                 */
/*   Uses %SYSFUNC(EXIST) to verify source, CALL SYMPUTX for counts.      */
/* --------------------------------------------------------------------- */
%macro extract_table(src_lib=, src_table=, tgt_ds=, filter=);

    %local src_exist row_count;

    %put NOTE: [extract_table] Extracting &src_lib..&src_table -> &tgt_ds;

    /* Validate source table exists */
    %let src_exist = %sysfunc(exist(&src_lib..&src_table));
    %if &src_exist = 0 %then %do;
        %put ERROR: [extract_table] Source &src_lib..&src_table does not exist.;
        %let job_rc = 1;
        %return;
    %end;

    /* Extract with optional filter condition */
    data &tgt_ds;
        set &src_lib..&src_table;
        %if %length(&filter) > 0 %then %do;
            where &filter;
        %end;

        /* Add extraction metadata */
        _extract_ts = datetime();
        _source_system = "&src_lib..&src_table";
        format _extract_ts datetime20.;
    run;

    /* Capture row count */
    data _null_;
        if 0 then set &tgt_ds nobs=_n;
        call symputx('row_count', _n, 'L');
        stop;
    run;

    %put NOTE: [extract_table] Extracted &row_count rows from &src_lib..&src_table;

    /* Log to control table */
    proc sql noprint;
        insert into ctrl.extraction_log
            (job_run_id, source_table, target_dataset, row_count,
             filter_applied, extract_timestamp)
        values
            ("&job_run_id", "&src_lib..&src_table", "&tgt_ds", &row_count,
             "&filter", %sysfunc(datetime()));
    quit;

%mend extract_table;

/* --------------------------------------------------------------------- */
/* MACRO: scd_type2_merge                                                 */
/*   Implements SCD Type 2 merge logic for dimension tables.               */
/*   Compares tracked columns between staging and existing dimension.      */
/*   Expires changed rows (current_flag='N', sets effective_to) and        */
/*   inserts new versions. Also inserts brand-new dimension members.       */
/*   Parameters:                                                           */
/*     dim         - Target dimension table in warehouse library           */
/*     stage       - Staging table with new/changed records                */
/*     natural_key - Natural business key column                           */
/*     tracked_cols - Space-separated list of SCD-tracked columns          */
/* --------------------------------------------------------------------- */
%macro scd_type2_merge(dim=, stage=, natural_key=, tracked_cols=);

    %local i n_cols col change_expr new_cnt upd_cnt unchanged_cnt;

    %put NOTE: [scd_type2_merge] Merging &stage into &dim on &natural_key;

    /* Build change detection expression from tracked columns */
    %let n_cols = %sysfunc(countw(&tracked_cols, %str( )));
    %let change_expr = ;
    %do i = 1 %to &n_cols;
        %let col = %scan(&tracked_cols, &i, %str( ));
        %if &i > 1 %then %let change_expr = &change_expr or ;
        %let change_expr = &change_expr (
            coalesce(strip(put(s.&col, best32.)), '') ne
            coalesce(strip(put(d.&col, best32.)), '')
        );
    %end;

    /* Classify records as NEW, CHANGED, or UNCHANGED */
    proc sql noprint;
        create table work._scd2_classified as
        select s.*,
               d.dim_key as _existing_key,
               case
                   when d.dim_key is null then 'NEW'
                   when &change_expr then 'CHANGED'
                   else 'UNCHANGED'
               end as _scd_action
        from &stage as s
        left join &dim (where=(current_flag = 'Y')) as d
            on s.&natural_key = d.&natural_key;

        /* Capture classification counts */
        select count(*) into :new_cnt trimmed
            from work._scd2_classified where _scd_action = 'NEW';
        select count(*) into :upd_cnt trimmed
            from work._scd2_classified where _scd_action = 'CHANGED';
        select count(*) into :unchanged_cnt trimmed
            from work._scd2_classified where _scd_action = 'UNCHANGED';
    quit;

    %put NOTE: [scd_type2_merge] New=&new_cnt Changed=&upd_cnt Unchanged=&unchanged_cnt;

    /* Step 1: Expire changed rows in the current dimension */
    %if &upd_cnt > 0 %then %do;
        proc sql;
            update &dim
            set current_flag = 'N',
                effective_to = "&process_dt"d,
                updated_by   = "&job_name",
                updated_ts   = %sysfunc(datetime())
            where current_flag = 'Y'
              and &natural_key in (
                  select &natural_key from work._scd2_classified
                  where _scd_action = 'CHANGED'
              );
        quit;
    %end;

    /* Step 2: Insert new versions for changed + new records */
    %if &new_cnt > 0 or &upd_cnt > 0 %then %do;
        proc sql;
            insert into &dim
            select monotonic() + (select coalesce(max(dim_key), 0) from &dim)
                       as dim_key,
                   s.*,
                   "&process_dt"d   as effective_from,
                   '31DEC9999'd     as effective_to,
                   'Y'              as current_flag,
                   "&job_name"      as created_by,
                   %sysfunc(datetime()) as created_ts,
                   .                as updated_by,
                   .                as updated_ts
            from work._scd2_classified (drop=_existing_key _scd_action) as s
            where s._scd_action in ('NEW', 'CHANGED');
        quit;
    %end;

    /* Log dimension load metrics */
    proc sql noprint;
        insert into ctrl.dimension_load_log
            (job_run_id, dimension_table, new_records, changed_records,
             unchanged_records, load_timestamp)
        values
            ("&job_run_id", "&dim", &new_cnt, &upd_cnt,
             &unchanged_cnt, %sysfunc(datetime()));
    quit;

    /* Cleanup */
    proc datasets lib=work nolist; delete _scd2_classified; quit;

%mend scd_type2_merge;

/* --------------------------------------------------------------------- */
/* MACRO: fact_load                                                       */
/*   Loads a fact table from staging data. Performs dimension key          */
/*   lookups to replace natural keys with surrogate keys. Calculates      */
/*   derived measures. Appends to the target fact table.                   */
/*   Parameters:                                                           */
/*     fact_table  - Target fact table in warehouse                        */
/*     stage_table - Staging table with transactional data                 */
/*     dim_keys    - Space-separated: natural_key=dim_table pairs          */
/*     measures    - Space-separated list of measure columns               */
/* --------------------------------------------------------------------- */
%macro fact_load(fact_table=, stage_table=, dim_keys=, measures=);

    %local i n_dims pair nat_key dim_tbl fact_count;

    %put NOTE: [fact_load] Loading &fact_table from &stage_table;

    %let n_dims = %sysfunc(countw(&dim_keys, %str( )));

    /* Build staging table with surrogate key lookups */
    proc sql noprint;
        create table work._fact_with_keys as
        select s.*
        %do i = 1 %to &n_dims;
            %let pair    = %scan(&dim_keys, &i, %str( ));
            %let nat_key = %scan(&pair, 1, =);
            %let dim_tbl = %scan(&pair, 2, =);
            , d&i..dim_key as &nat_key._key
        %end;
        from &stage_table as s
        %do i = 1 %to &n_dims;
            %let pair    = %scan(&dim_keys, &i, %str( ));
            %let nat_key = %scan(&pair, 1, =);
            %let dim_tbl = %scan(&pair, 2, =);
            left join &dim_tbl (where=(current_flag = 'Y')) as d&i
                on s.&nat_key = d&i..&nat_key
        %end;
        ;
    quit;

    /* Append to target fact table */
    proc sql noprint;
        insert into &fact_table
        select * from work._fact_with_keys;

        select count(*) into :fact_count trimmed
            from work._fact_with_keys;
    quit;

    %put NOTE: [fact_load] Loaded &fact_count rows into &fact_table;

    /* Log fact load metrics */
    proc sql noprint;
        insert into ctrl.fact_load_log
            (job_run_id, fact_table, rows_loaded, load_timestamp)
        values
            ("&job_run_id", "&fact_table", &fact_count, %sysfunc(datetime()));
    quit;

    proc datasets lib=work nolist; delete _fact_with_keys; quit;

%mend fact_load;

/* ========================================================================= */
/* SECTION 3: Watermark Retrieval — Get Last Successful Load Checkpoint      */
/* ========================================================================= */

proc sql noprint;
    select coalesce(max(watermark_value), '1900-01-01')
        into :last_watermark trimmed
    from ctrl.watermark_table
    where job_name = "&job_name"
      and status   = 'COMPLETE';
quit;

%put NOTE: [Watermark] Last successful watermark: &last_watermark;

/* ========================================================================= */
/* SECTION 4: Incremental Extraction Loop                                    */
/*   Iterates over source tables, extracting only rows modified since        */
/*   the last watermark timestamp.                                           */
/* ========================================================================= */

%macro extract_all_sources;
    %local i;

    /* Define extraction configuration as indexed arrays */
    %let ext_src1 = srcdb;  %let ext_tbl1 = customers;     %let ext_tgt1 = staging.stg_customers;
    %let ext_src2 = srcdb;  %let ext_tbl2 = products;      %let ext_tgt2 = staging.stg_products;
    %let ext_src3 = srcdb;  %let ext_tbl3 = orders;        %let ext_tgt3 = staging.stg_orders;
    %let ext_src4 = srcdb;  %let ext_tbl4 = order_lines;   %let ext_tgt4 = staging.stg_order_lines;
    %let ext_src5 = srcdb;  %let ext_tbl5 = suppliers;     %let ext_tgt5 = staging.stg_suppliers;

    %do i = 1 %to &n_src_tables;
        %put NOTE: [extract_all] Table &i of &n_src_tables: &&ext_tbl&i;
        %extract_table(
            src_lib   = &&ext_src&i,
            src_table = &&ext_tbl&i,
            tgt_ds    = &&ext_tgt&i,
            filter    = modified_date >= "&last_watermark"d
        );

        /* Check for extraction errors */
        %if &job_rc ne 0 %then %do;
            %put ERROR: [extract_all] Extraction failed at table &i (&&ext_tbl&i). Halting.;
            %return;
        %end;
    %end;

    %put NOTE: [extract_all] All &n_src_tables tables extracted successfully.;
%mend extract_all_sources;

%extract_all_sources;

/* Abort if extraction had errors */
%if &job_rc ne 0 %then %do;
    %put ERROR: Extraction phase failed. Aborting warehouse load.;
    %goto EXIT_PROGRAM;
%end;

/* ========================================================================= */
/* SECTION 5: Staging Transforms — Cleansing, Mapping, and Type Conversion   */
/* ========================================================================= */

/* --- Customer staging transforms --- */
data staging.stg_customers_clean (drop=_:);
    set staging.stg_customers;

    /* Standardize name fields */
    first_name = propcase(strip(first_name));
    last_name  = propcase(strip(last_name));

    /* Null handling for optional fields */
    if missing(phone) then phone = 'N/A';
    if missing(email) then email = 'N/A';

    /* Status code mapping */
    length customer_status $15;
    select (upcase(status_code));
        when ('A')  customer_status = 'ACTIVE';
        when ('I')  customer_status = 'INACTIVE';
        when ('S')  customer_status = 'SUSPENDED';
        when ('C')  customer_status = 'CLOSED';
        otherwise   customer_status = 'UNKNOWN';
    end;

    /* Type conversion for date fields stored as strings */
    if not missing(registration_date_str) then
        registration_date = input(registration_date_str, yymmdd10.);
    else
        registration_date = .;
    format registration_date yymmdd10.;

    /* Geography enrichment */
    length country_name $50;
    select (upcase(country_code));
        when ('US') country_name = 'United States';
        when ('CA') country_name = 'Canada';
        when ('GB') country_name = 'United Kingdom';
        when ('DE') country_name = 'Germany';
        when ('FR') country_name = 'France';
        otherwise   country_name = 'Other';
    end;
run;

/* --- Product staging transforms --- */
data staging.stg_products_clean (drop=_:);
    set staging.stg_products;

    /* Null handling */
    if missing(unit_cost) then unit_cost = 0;
    if missing(list_price) then list_price = 0;

    /* Derive margin percentage */
    if list_price > 0 then
        margin_pct = (list_price - unit_cost) / list_price;
    else
        margin_pct = 0;

    /* Product category standardization */
    category = propcase(strip(category));
    subcategory = propcase(strip(subcategory));

    format margin_pct percent8.1;
run;

/* ========================================================================= */
/* SECTION 6: Deduplication via PROC SORT                                    */
/* ========================================================================= */

proc sort data=staging.stg_customers_clean
          out=staging.stg_customers_dedup nodupkey;
    by customer_id;
run;

proc sort data=staging.stg_products_clean
          out=staging.stg_products_dedup nodupkey;
    by product_id;
run;

proc sort data=staging.stg_orders
          out=staging.stg_orders_dedup nodupkey;
    by order_id;
run;

/* ========================================================================= */
/* SECTION 7: Dimension Loading — SCD Type 2 Merge                          */
/* ========================================================================= */

/* Load customer dimension */
%scd_type2_merge(
    dim         = whouse.dim_customer,
    stage       = staging.stg_customers_dedup,
    natural_key = customer_id,
    tracked_cols = first_name last_name email phone customer_status country_name
);

/* Load product dimension */
%scd_type2_merge(
    dim         = whouse.dim_product,
    stage       = staging.stg_products_dedup,
    natural_key = product_id,
    tracked_cols = category subcategory unit_cost list_price margin_pct
);

/* Load supplier dimension */
%scd_type2_merge(
    dim         = whouse.dim_supplier,
    stage       = staging.stg_suppliers,
    natural_key = supplier_id,
    tracked_cols = supplier_name contact_name city state country_code
);

/* ========================================================================= */
/* SECTION 8: Dimension Key Lookup — Resolve Surrogate Keys for Facts        */
/* ========================================================================= */

proc sql;
    create table staging.orders_with_keys as
    select o.*,
           dc.dim_key  as customer_dim_key,
           dp.dim_key  as product_dim_key,
           ds.dim_key  as supplier_dim_key,
           dd.dim_key  as date_dim_key
    from staging.stg_orders_dedup as o
    left join whouse.dim_customer (where=(current_flag = 'Y')) as dc
        on o.customer_id = dc.customer_id
    left join staging.stg_order_lines as ol
        on o.order_id = ol.order_id
    left join whouse.dim_product (where=(current_flag = 'Y')) as dp
        on ol.product_id = dp.product_id
    left join whouse.dim_supplier (where=(current_flag = 'Y')) as ds
        on ol.supplier_id = ds.supplier_id
    left join whouse.dim_date as dd
        on o.order_date = dd.calendar_date;
quit;

/* Identify orphaned keys — orders without dimension matches */
proc sql;
    create table staging.orphan_keys as
    select order_id,
           case when customer_dim_key is null then 'CUSTOMER' else '' end as missing_customer,
           case when product_dim_key is null then 'PRODUCT' else '' end as missing_product,
           case when date_dim_key is null then 'DATE' else '' end as missing_date
    from staging.orders_with_keys
    where customer_dim_key is null
       or product_dim_key is null
       or date_dim_key is null;

    select count(*) into :orphan_count trimmed from staging.orphan_keys;
quit;

%if &orphan_count > 0 %then %do;
    %put WARNING: [Key Lookup] &orphan_count orders have missing dimension keys.;
    %put WARNING: [Key Lookup] Check staging.orphan_keys for details.;
%end;

/* ========================================================================= */
/* SECTION 9: Fact Table Loading                                             */
/* ========================================================================= */

/* Prepare order fact staging with calculated measures */
data staging.fact_orders_stage;
    set staging.orders_with_keys;
    where customer_dim_key is not null;   /* Exclude orphans */

    /* Calculate derived measures */
    if quantity > 0 and unit_price > 0 then do;
        line_total     = quantity * unit_price;
        discount_amt   = line_total * coalesce(discount_pct, 0);
        net_amount     = line_total - discount_amt;
        tax_amount     = net_amount * coalesce(tax_rate, 0);
        gross_amount   = net_amount + tax_amount;
    end;
    else do;
        line_total   = 0;
        discount_amt = 0;
        net_amount   = 0;
        tax_amount   = 0;
        gross_amount = 0;
    end;

    format line_total discount_amt net_amount tax_amount gross_amount dollar15.2;
run;

/* Load order fact table */
%fact_load(
    fact_table  = whouse.fact_orders,
    stage_table = staging.fact_orders_stage,
    dim_keys    = customer_id=whouse.dim_customer product_id=whouse.dim_product,
    measures    = quantity unit_price line_total discount_amt net_amount
);

/* Load returns fact table */
%fact_load(
    fact_table  = whouse.fact_returns,
    stage_table = staging.stg_returns,
    dim_keys    = customer_id=whouse.dim_customer product_id=whouse.dim_product,
    measures    = return_quantity refund_amount
);

/* ========================================================================= */
/* SECTION 10: Watermark Update — Record This Run's Checkpoint               */
/* ========================================================================= */

data ctrl.watermark_update;
    length job_name $50 watermark_value $30 status $15;
    job_name        = "&job_name";
    watermark_value = "&process_dt";
    status          = "COMPLETE";
    update_ts       = datetime();
    format update_ts datetime20.;
    output;
run;

proc append base=ctrl.watermark_table data=ctrl.watermark_update force;
run;

%put NOTE: [Watermark] Updated watermark to &process_dt;

/* ========================================================================= */
/* SECTION 11: Error Detection and Rollback Logging                          */
/* ========================================================================= */

%if &syserr ne 0 or &job_rc ne 0 %then %do;
    %let job_status = FAILED;

    %put ERROR: Warehouse load encountered errors. SYSERR=&syserr JOB_RC=&job_rc;

    /* Log error details to control table */
    proc sql noprint;
        insert into ctrl.error_log
            (job_run_id, job_name, error_code, error_message, error_timestamp)
        values
            ("&job_run_id", "&job_name", &syserr,
             "Warehouse load failed — review SAS log for details",
             %sysfunc(datetime()));
    quit;

    /* Write error flag file for monitoring */
    data _null_;
        file '/dwh/flags/load_error.flag';
        put "JOB_RUN_ID=&job_run_id";
        put "JOB_NAME=&job_name";
        put "ERROR_TIME=%sysfunc(datetime(), datetime20.)";
        put "SYSERR=&syserr";
        put "JOB_RC=&job_rc";
    run;
%end;
%else %do;
    %let job_status = COMPLETE;
    %put NOTE: Warehouse load completed successfully.;
%end;

/* ========================================================================= */
/* SECTION 12: Job Status Update and Final Cleanup                           */
/* ========================================================================= */

proc sql;
    insert into ctrl.job_status_log
        (job_run_id, job_name, job_status, process_date,
         start_time, end_time, tables_processed)
    values
        ("&job_run_id", "&job_name", "&job_status", "&process_dt"d,
         input("&job_run_id", datetime20.), %sysfunc(datetime()), &n_src_tables);
quit;

/* Clean up all staging datasets */
proc datasets lib=staging nolist;
    delete stg_customers stg_customers_clean stg_customers_dedup
           stg_products stg_products_clean stg_products_dedup
           stg_orders stg_orders_dedup stg_order_lines stg_suppliers
           stg_returns orders_with_keys orphan_keys
           fact_orders_stage;
quit;

proc datasets lib=work nolist; kill; quit;

/* Final notification via CALL EXECUTE */
data _null_;
    if "&job_status" = "FAILED" then do;
        call execute('%nrstr(%put ERROR: ===== DWH LOAD FAILED =====;)');
        call execute(cats(
            '%nrstr(filename _email email to=("dwh-ops@company.com") ',
            'subject="DWH LOAD FAILURE: ', "&process_dt", '";)'
        ));
    end;
    else do;
        call execute('%nrstr(%put NOTE: ===== DWH LOAD COMPLETE =====;)');
    end;
run;

%EXIT_PROGRAM:

options nomprint nomlogic nosymbolgen;

%put NOTE: ===== gsh_03_warehouse_load.sas finished at %sysfunc(datetime(), datetime20.) =====;
%put NOTE: ===== Job Status: &job_status =====;
