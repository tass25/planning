/*****************************************************************************
 * Program:     gsm_18_macro_reporting.sas
 * Purpose:     Parameterized multi-region departmental reporting
 * Author:      Business Intelligence Team
 * Created:     2026-02-19
 * Environment: SAS 9.4M5+
 * Description: Generates formatted reports by region and department.
 *              Supports PDF/HTML output via conditional ODS selection.
 *              Loops over departments within each region for granular
 *              summary statistics and cross-tabulations.
 *****************************************************************************/

/* ------------------------------------------------------------------ */
/* SECTION 1: Environment Setup                                        */
/* ------------------------------------------------------------------ */

/* Data sources and output locations */
libname raw '/data/enterprise/raw' access=readonly;
libname staging '/data/enterprise/staging';
libname tgt '/data/reports/output';

/* Global options for reporting */
options mprint mlogic symbolgen nocenter nodate pageno=1;
options linesize=132 pagesize=60;

/* Report control parameters */
%let report_year = 2025;
%let dept_count = 4;
%let dept1 = SALES;
%let dept2 = MARKETING;
%let dept3 = OPERATIONS;
%let dept4 = FINANCE;

/* ------------------------------------------------------------------ */
/* SECTION 2: Include Common Format Definitions                        */
/* ------------------------------------------------------------------ */

/* Load shared format catalog and macro utilities */
%include '/data/enterprise/config/common_formats.sas';

/* ------------------------------------------------------------------ */
/* SECTION 3: Report Generation Macro                                  */
/* ------------------------------------------------------------------ */

/* Parameterized macro for region-level departmental reports */
%macro generate_report(region=, period=, output_format=PDF);

    %put NOTE: ================================================;
    %put NOTE: Generating report for region=&region period=&period;
    %put NOTE: Output format: &output_format;
    %put NOTE: ================================================;

    /* Conditional ODS destination based on output_format parameter */
    %if %upcase(&output_format) = PDF %then %do;
        ods pdf file="/data/reports/output/&region._&period._report.pdf"
            style=journal;
        %put NOTE: Using PDF output;
    %end;
    %else %if %upcase(&output_format) = HTML %then %do;
        ods html file="/data/reports/output/&region._&period._report.html"
            style=HTMLBlue;
        %put NOTE: Using HTML output;
    %end;
    %else %do;
        ods listing;
        %put NOTE: Using default listing output;
    %end;

    /* Filter source data for specified region and period */
    data staging.region_&region;
        set raw.enterprise_data;
        where region = "&region"
          and fiscal_year = &report_year
          and fiscal_period = "&period";

        /* Derive performance metrics */
        if target_amount > 0 then
            pct_achieved = (actual_amount / target_amount) * 100;
        else
            pct_achieved = 0;

        /* Flag underperformers */
        length perf_flag $15;
        if pct_achieved >= 100 then perf_flag = "EXCEEDS";
        else if pct_achieved >= 80 then perf_flag = "ON_TRACK";
        else perf_flag = "AT_RISK";
    run;

    /* Loop over each department within the region */
    %do d = 1 %to &dept_count;
        %let cur_dept = &&dept&d;

        %put NOTE: --- Processing department: &cur_dept ---;

        /* Departmental summary statistics */
        proc means data=staging.region_&region n mean sum min max maxdec=2;
            where department = "&cur_dept";
            title "Performance Summary: &region - &cur_dept (&period)";
            var actual_amount target_amount pct_achieved;
            output out=staging.stats_&region._&cur_dept
                n=n_records mean=avg_amount sum=total_amount;
        run;

        /* Departmental cross-tabulation */
        proc freq data=staging.region_&region;
            where department = "&cur_dept";
            title2 "Performance Distribution: &region - &cur_dept";
            tables perf_flag / nocum;
            tables perf_flag * fiscal_period / nocum nopercent;
        run;
    %end;

    /* Region-wide SQL summary across all departments */
    proc sql;
        title "Cross-Department Comparison: &region (&period)";
        select department,
               count(*) as n_employees,
               sum(actual_amount) as total_actual format=dollar15.2,
               sum(target_amount) as total_target format=dollar15.2,
               calculated total_actual / calculated total_target * 100
                   as overall_pct format=8.1
        from staging.region_&region
        group by department
        order by calculated overall_pct desc;
    quit;

    /* Close ODS destination */
    %if %upcase(&output_format) = PDF %then %do;
        ods pdf close;
    %end;
    %else %if %upcase(&output_format) = HTML %then %do;
        ods html close;
    %end;

    title;

%mend generate_report;

/* ------------------------------------------------------------------ */
/* SECTION 4: Region Configuration and Batch Execution                 */
/* ------------------------------------------------------------------ */

/* Define region parameters for batch reporting */
%let region_count = 3;
%let rgn1 = NORTH;  %let fmt1 = PDF;
%let rgn2 = SOUTH;  %let fmt2 = HTML;
%let rgn3 = WEST;   %let fmt3 = PDF;

/* Driver loop: generate reports for all configured regions */
%macro run_region_reports;
    %do r = 1 %to &region_count;
        %put NOTE: === Region &r of &region_count: &&rgn&r ===;
        %generate_report(
            region = &&rgn&r,
            period = Q4,
            output_format = &&fmt&r
        );
    %end;
%mend run_region_reports;

/* Execute batch report generation */
%run_region_reports;

/* Open-code conditional: verify report generation completed */
%if &syserr > 0 %then %do;
    %put ERROR: Report generation encountered errors (SYSERR=&syserr);
%end;
%else %do;
    %put NOTE: All regional reports generated successfully;
%end;

/* ------------------------------------------------------------------ */
/* SECTION 5: Executive Summary Across All Regions                     */
/* ------------------------------------------------------------------ */

/* Combine regional data for cross-region comparison */
proc sql;
    title "Executive Summary - All Regions Q4 &report_year";
    select region,
           department,
           count(*) as headcount,
           sum(actual_amount) as total_actual format=dollar15.2,
           avg(pct_achieved) as avg_achievement format=8.1
    from raw.enterprise_data
    where fiscal_year = &report_year
      and fiscal_period = "Q4"
    group by region, department
    order by region, department;
quit;

/* Performance flag distribution across all regions */
proc freq data=raw.enterprise_data;
    where fiscal_year = &report_year and fiscal_period = "Q4";
    title "Company-Wide Performance Distribution - Q4 &report_year";
    tables region * department / nocum nopercent;
run;

title;

/* ------------------------------------------------------------------ */
/* SECTION 6: Cleanup                                                  */
/* ------------------------------------------------------------------ */

libname raw clear;
libname staging clear;

%put NOTE: Report generation completed at %sysfunc(datetime(), datetime20.);
