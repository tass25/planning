/*****************************************************************************
 * Program:     gsm_16_data_reconciliation.sas
 * Purpose:     Data reconciliation between Source A (ERP) and Source B (DW)
 * Author:      Data Quality Team
 * Created:     2026-02-19
 * Environment: SAS 9.4M5+
 * Description: Compares records across two source systems to identify
 *              discrepancies. Uses parameterized macro for reusable
 *              reconciliation logic with conditional error handling.
 *****************************************************************************/

/* ------------------------------------------------------------------ */
/* SECTION 1: Environment Setup                                        */
/* ------------------------------------------------------------------ */

/* Source system A - ERP operational data */
libname src_a '/data/erp/extracts' access=readonly;

/* Source system B - data warehouse */
libname src_b '/data/warehouse/current' access=readonly;

/* Staging library for intermediate results */
libname staging '/data/staging/reconciliation';

/* Reporting library */
libname rpt '/data/reports/recon';

/* Control parameters */
%let recon_date = %sysfunc(today(), date9.);
%let max_disc = 1000;

options mprint mlogic symbolgen nocenter;

/* ------------------------------------------------------------------ */
/* SECTION 2: Reconciliation Macro                                     */
/* ------------------------------------------------------------------ */

/* Parameterized macro to compare a single table across two sources */
%macro reconcile_table(src_a=, src_b=, keys=, table_name=);

    %put NOTE: =============================================;
    %put NOTE: Reconciling &table_name;
    %put NOTE: Source A: &src_a | Source B: &src_b | Key: &keys;
    %put NOTE: =============================================;

    /* Count records in each source */
    proc sql noprint;
        select count(*) into :cnt_a trimmed from &src_a;
        select count(*) into :cnt_b trimmed from &src_b;
    quit;

    %put NOTE: &table_name counts - A: &cnt_a | B: &cnt_b;

    /* Identify records in A but not in B */
    proc sql;
        create table staging.miss_b_&table_name as
        select a.*,
               "&table_name" as table_name length=50,
               "MISSING_FROM_B" as disc_type length=30
        from &src_a as a
        left join &src_b as b
            on a.&keys = b.&keys
        where b.&keys is null;
    quit;

    /* Identify records in B but not in A */
    proc sql;
        create table staging.miss_a_&table_name as
        select b.*,
               "&table_name" as table_name length=50,
               "MISSING_FROM_A" as disc_type length=30
        from &src_b as b
        left join &src_a as a
            on b.&keys = a.&keys
        where a.&keys is null;
    quit;

    /* Combine all discrepancies for this table */
    data staging.recon_&table_name;
        set staging.miss_b_&table_name
            staging.miss_a_&table_name;

        length source_system $20 recon_status $20;
        if disc_type = "MISSING_FROM_B" then
            source_system = "SOURCE_A_ONLY";
        else
            source_system = "SOURCE_B_ONLY";

        recon_status = "UNRESOLVED";
        recon_dt = today();
        format recon_dt date9.;
    run;

    /* Log discrepancy count */
    proc sql noprint;
        select count(*) into :n_disc trimmed
        from staging.recon_&table_name;
    quit;

    %put NOTE: &table_name discrepancies found: &n_disc;

%mend reconcile_table;

/* ------------------------------------------------------------------ */
/* SECTION 3: Execute Reconciliation for Key Tables                    */
/* ------------------------------------------------------------------ */

/* Reconcile customer master data */
%reconcile_table(
    src_a = src_a.customers,
    src_b = src_b.dim_customer,
    keys  = customer_id,
    table_name = customers
);

/* Reconcile order transactions */
%reconcile_table(
    src_a = src_a.orders,
    src_b = src_b.fact_orders,
    keys  = order_id,
    table_name = orders
);

/* Reconcile product catalog */
%reconcile_table(
    src_a = src_a.products,
    src_b = src_b.dim_product,
    keys  = product_id,
    table_name = products
);

/* ------------------------------------------------------------------ */
/* SECTION 4: Error Handling                                            */
/* ------------------------------------------------------------------ */

/* Open-code conditional: check for reconciliation errors */
%if &syserr > 0 %then %do;
    %put ERROR: Reconciliation failed (SYSERR=&syserr);
    data staging.recon_error_log;
        length process_name $50 error_message $200;
        process_name = "DATA_RECONCILIATION";
        error_message = "Process failed with SYSERR=&syserr";
        error_dt = datetime();
        format error_dt datetime20.;
    run;
%end;
%else %do;
    %put NOTE: All reconciliation steps completed without errors;
%end;

/* ------------------------------------------------------------------ */
/* SECTION 5: Consolidated Discrepancy Report                          */
/* ------------------------------------------------------------------ */

/* Merge all table-level results into consolidated dataset */
data rpt.consolidated_recon;
    set staging.recon_customers
        staging.recon_orders
        staging.recon_products;

    /* Assign severity level based on discrepancy type */
    length severity $10;
    if disc_type = "MISSING_FROM_A" then
        severity = "HIGH";
    else
        severity = "MEDIUM";
run;

/* Cross-table count summary via SQL */
proc sql;
    title "Reconciliation Count Summary - &recon_date";
    select table_name,
           disc_type,
           count(*) as discrepancy_count
    from rpt.consolidated_recon
    group by table_name, disc_type
    order by table_name, disc_type;
quit;

/* Severity distribution */
proc freq data=rpt.consolidated_recon;
    title "Discrepancy Severity Distribution";
    tables severity * table_name / nocum nopercent;
run;

/* Detailed listing of discrepancies */
proc print data=rpt.consolidated_recon(obs=&max_disc) noobs;
    title "Discrepancy Detail Report (Top &max_disc)";
    var table_name disc_type source_system recon_status recon_dt;
run;

title;

/* ------------------------------------------------------------------ */
/* SECTION 6: Cleanup                                                  */
/* ------------------------------------------------------------------ */

libname src_a clear;
libname src_b clear;

%put NOTE: Reconciliation completed at %sysfunc(datetime(), datetime20.);
