/*****************************************************************************
 * Program:     gsm_20_audit_trail.sas
 * Purpose:     Automated change detection and audit trail generation
 * Author:      Data Governance Team
 * Created:     2026-02-19
 * Environment: SAS 9.4M5+
 * Description: Compares current vs. previous snapshots of monitored tables
 *              to detect INSERTs, UPDATEs, and DELETEs. Uses parameterized
 *              macro with loop-driven batch processing for multiple tables.
 *****************************************************************************/

/* ------------------------------------------------------------------ */
/* SECTION 1: Environment Setup                                        */
/* ------------------------------------------------------------------ */

/* Current production snapshot */
libname curr '/data/production/current' access=readonly;

/* Previous day snapshot for comparison */
libname prev '/data/production/previous' access=readonly;

/* Audit trail output library */
libname audit '/data/governance/audit_trail';

/* Staging library for intermediate results */
libname staging '/data/governance/staging';

/* Audit control parameters */
%let audit_date = %sysfunc(today(), date9.);
%let audit_user = %sysget(USERNAME);
%let log_level = DETAIL;

options mprint mlogic symbolgen nocenter;

/* ------------------------------------------------------------------ */
/* SECTION 2: Audit Detection Macro                                    */
/* ------------------------------------------------------------------ */

/* Macro to detect changes between current and previous snapshots */
%macro audit_table(table_name=, pk_col=);

    %put NOTE: =============================================;
    %put NOTE: Auditing table: &table_name;
    %put NOTE: Primary key: &pk_col;
    %put NOTE: Audit date: &audit_date;
    %put NOTE: =============================================;

    /* Step 1: Identify new records (INSERTs) - in current but not previous */
    proc sql;
        create table staging.ins_&table_name as
        select c.*,
               "INSERT" as change_type length=10,
               "&audit_date"d as audit_dt format=date9.
        from curr.&table_name as c
        left join prev.&table_name as p
            on c.&pk_col = p.&pk_col
        where p.&pk_col is null;
    quit;

    /* Step 2: Identify removed records (DELETEs) - in previous but not current */
    proc sql;
        create table staging.del_&table_name as
        select p.*,
               "DELETE" as change_type length=10,
               "&audit_date"d as audit_dt format=date9.
        from prev.&table_name as p
        left join curr.&table_name as c
            on p.&pk_col = c.&pk_col
        where c.&pk_col is null;
    quit;

    /* Step 3: Identify modified records (UPDATEs) via checksum comparison */
    proc sql;
        create table staging.upd_&table_name as
        select c.*,
               "UPDATE" as change_type length=10,
               "&audit_date"d as audit_dt format=date9.
        from curr.&table_name as c
        inner join prev.&table_name as p
            on c.&pk_col = p.&pk_col
        where md5(cats(of c.:)) ne md5(cats(of p.:));
    quit;

    /* Step 4: Combine all detected changes into unified audit log */
    data staging.changes_&table_name;
        set staging.ins_&table_name
            staging.del_&table_name
            staging.upd_&table_name;

        /* Add audit metadata */
        length table_source $50 audit_user $30;
        table_source = "&table_name";
        audit_user = "&audit_user";
        audit_seq = _n_;

        format audit_dt date9.;
    run;

    /* Conditional logging based on log level */
    %if &log_level = DETAIL %then %do;
        /* Detailed per-record logging */
        proc sql noprint;
            select count(*) into :n_ins trimmed
            from staging.ins_&table_name;
            select count(*) into :n_del trimmed
            from staging.del_&table_name;
            select count(*) into :n_upd trimmed
            from staging.upd_&table_name;
        quit;

        %put NOTE: &table_name audit results:;
        %put NOTE:   Inserts: &n_ins;
        %put NOTE:   Deletes: &n_del;
        %put NOTE:   Updates: &n_upd;
    %end;
    %else %do;
        /* Summary-only logging */
        proc sql noprint;
            select count(*) into :n_total trimmed
            from staging.changes_&table_name;
        quit;
        %put NOTE: &table_name - Total changes: &n_total;
    %end;

%mend audit_table;

/* ------------------------------------------------------------------ */
/* SECTION 3: Batch Audit via Loop                                     */
/* ------------------------------------------------------------------ */

/* Configure tables to monitor */
%let n_tables = 5;
%let tab1 = customer_master;  %let pk1 = customer_id;
%let tab2 = product_catalog;  %let pk2 = product_id;
%let tab3 = order_header;     %let pk3 = order_id;
%let tab4 = supplier_info;    %let pk4 = supplier_id;
%let tab5 = employee_roster;  %let pk5 = employee_id;

/* Driver macro: iterate over all monitored tables */
%macro run_audit_batch;
    %do t = 1 %to &n_tables;
        %put NOTE: --- Audit batch item &t of &n_tables ---;
        %audit_table(
            table_name = &&tab&t,
            pk_col     = &&pk&t
        );
    %end;
%mend run_audit_batch;

/* Execute the batch audit */
%run_audit_batch;

/* Open-code conditional: verify audit batch completed */
%if &syserr > 0 %then %do;
    %put ERROR: Audit batch encountered errors (SYSERR=&syserr);
    %put ERROR: Some tables may not have been audited;
%end;
%else %do;
    %put NOTE: Audit batch completed for all &n_tables tables;
%end;

/* ------------------------------------------------------------------ */
/* SECTION 4: Consolidated Audit Report                                */
/* ------------------------------------------------------------------ */

/* Merge all table-level change logs into master audit trail */
data audit.master_audit_trail;
    set staging.changes_customer_master
        staging.changes_product_catalog
        staging.changes_order_header
        staging.changes_supplier_info
        staging.changes_employee_roster;

    /* Global sequence number */
    master_seq = _n_;
run;

/* Change type distribution by table */
proc freq data=audit.master_audit_trail;
    title "Audit Trail Summary - &audit_date";
    tables table_source * change_type / nocum nopercent;
    tables change_type / nocum;
run;

/* Top tables by change volume */
proc sql;
    title "Change Volume by Table";
    select table_source,
           change_type,
           count(*) as change_count
    from audit.master_audit_trail
    group by table_source, change_type
    order by calculated change_count desc;
quit;

title;

/* ------------------------------------------------------------------ */
/* SECTION 5: Cleanup                                                  */
/* ------------------------------------------------------------------ */

libname curr clear;
libname prev clear;
libname staging clear;

%put NOTE: Audit trail generation completed at %sysfunc(datetime(), datetime20.);
