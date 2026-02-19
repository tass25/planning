/******************************************************************************
 * Program Name : gsh_02_macro_framework.sas
 * Author       : Analytics Platform Team
 * Created      : 2025-11-20
 * Modified     : 2026-02-19
 * Purpose      : Reusable macro framework for standardized enterprise
 *                reporting. Provides parameterized macros for date range
 *                calculation, dynamic format creation, and multi-format
 *                report generation. Supports batch execution across
 *                multiple regions and periods.
 * Usage        : Invoked by quarterly, monthly, and ad-hoc report jobs.
 * Dependencies : None (self-contained macro library)
 * Change Log   :
 *   2025-11-20  v1.0  Initial framework                     (L. Torres)
 *   2025-12-15  v1.1  Added batch_reports macro              (L. Torres)
 *   2026-01-10  v1.2  Enhanced ODS output format support     (R. Kim)
 *   2026-02-19  v1.3  Parameter validation and error guards  (L. Torres)
 ******************************************************************************/

/* ========================================================================= */
/* SECTION 1: Environment Setup                                              */
/* ========================================================================= */

options mprint mlogic symbolgen nocenter ls=200 ps=65
        validvarname=v7 nofmterr;

/* --- Library references --- */
libname raw      '/data/analytics/raw'      access=readonly;
libname staging  '/data/analytics/staging';
libname mart     '/data/analytics/mart';
libname rptout   '/data/analytics/reports';
libname archive  '/data/analytics/archive';

/* Global configuration for this reporting run */
%let report_base_path = /data/analytics/output;
%let default_period   = QTR;
%let default_as_of    = %sysfunc(today(), yymmdd10.);
%let framework_rc     = 0;

/* ========================================================================= */
/* SECTION 2: Macro Definitions                                              */
/* ========================================================================= */

/* --------------------------------------------------------------------- */
/* MACRO: validate_params                                                 */
/*   Validates that all required parameters were supplied to a calling     */
/*   macro. Emits ERROR messages and sets &framework_rc for any missing    */
/*   required values. Uses COUNTW and SCAN for list iteration.             */
/* --------------------------------------------------------------------- */
%macro validate_params(macro_name=, required_params=);

    %local i n param_name param_val;

    %let n = %sysfunc(countw(&required_params, %str( )));

    %do i = 1 %to &n;
        %let param_name = %scan(&required_params, &i, %str( ));
        %let param_val  = &&&param_name;

        %if %length(&param_val) = 0 %then %do;
            %put ERROR: [&macro_name] Required parameter &param_name is missing or blank.;
            %let framework_rc = 1;
        %end;
    %end;

    %if &framework_rc ne 0 %then %do;
        %put ERROR: [&macro_name] Aborting due to missing required parameters.;
    %end;

%mend validate_params;

/* --------------------------------------------------------------------- */
/* MACRO: get_date_range                                                  */
/*   Calculates a date range (start and end) based on a period type       */
/*   relative to an as-of date. Returns values in global macro vars       */
/*   &range_start and &range_end. Uses %SYSFUNC(INTNX) and PUTN.         */
/*   Supported periods: MTH, QTR, YTD, YR, CUSTOM                        */
/* --------------------------------------------------------------------- */
%macro get_date_range(period=QTR, as_of=&default_as_of);

    %global range_start range_end range_label;
    %local as_of_sas;

    /* Convert as_of to SAS date numeric */
    %let as_of_sas = %sysfunc(inputn(&as_of, yymmdd10.));

    %if &period = MTH %then %do;
        %let range_start = %sysfunc(intnx(MONTH, &as_of_sas, 0, B), yymmdd10.);
        %let range_end   = %sysfunc(intnx(MONTH, &as_of_sas, 0, E), yymmdd10.);
        %let range_label = %sysfunc(putn(&as_of_sas, monyy7.));
    %end;
    %else %if &period = QTR %then %do;
        %let range_start = %sysfunc(intnx(QTR, &as_of_sas, 0, B), yymmdd10.);
        %let range_end   = %sysfunc(intnx(QTR, &as_of_sas, 0, E), yymmdd10.);
        %let range_label = Q%sysfunc(ceil(%sysfunc(month(&as_of_sas))/3))_%sysfunc(year(&as_of_sas));
    %end;
    %else %if &period = YTD %then %do;
        %let range_start = %sysfunc(intnx(YEAR, &as_of_sas, 0, B), yymmdd10.);
        %let range_end   = %sysfunc(putn(&as_of_sas, yymmdd10.));
        %let range_label = YTD_%sysfunc(year(&as_of_sas));
    %end;
    %else %if &period = YR %then %do;
        %let range_start = %sysfunc(intnx(YEAR, &as_of_sas, 0, B), yymmdd10.);
        %let range_end   = %sysfunc(intnx(YEAR, &as_of_sas, 0, E), yymmdd10.);
        %let range_label = FY_%sysfunc(year(&as_of_sas));
    %end;
    %else %do;
        %put ERROR: [get_date_range] Unsupported period type: &period;
        %let framework_rc = 1;
        %return;
    %end;

    %put NOTE: [get_date_range] Period=&period Start=&range_start End=&range_end Label=&range_label;

%mend get_date_range;

/* --------------------------------------------------------------------- */
/* MACRO: create_format                                                   */
/*   Dynamically creates a SAS format from a lookup dataset using         */
/*   PROC FORMAT CNTLIN= option. Builds a CNTLIN-compatible dataset       */
/*   from the specified data, start column, and label column.             */
/* --------------------------------------------------------------------- */
%macro create_format(fmtname=, data=, start_col=, label_col=, type=C);

    %validate_params(macro_name=create_format,
                     required_params=fmtname data start_col label_col);
    %if &framework_rc ne 0 %then %return;

    /* Build CNTLIN dataset */
    data work._fmt_cntlin;
        set &data (keep=&start_col &label_col) end=_last;

        retain fmtname "&fmtname" type "&type";

        rename &start_col = start
               &label_col = label;

        /* Track record count for logging */
        _n + 1;
        if _last then
            call symputx('_fmt_count', _n, 'L');
    run;

    /* Generate the format */
    proc format cntlin=work._fmt_cntlin;
    run;

    %put NOTE: [create_format] Format $&fmtname created with &_fmt_count entries.;

    proc datasets lib=work nolist; delete _fmt_cntlin; quit;

%mend create_format;

/* --------------------------------------------------------------------- */
/* MACRO: standard_report                                                 */
/*   Generates a standardized report for a given input dataset.           */
/*   Supports HTML, PDF, and RTF output. Iterates over analysis vars,     */
/*   runs PROC MEANS for summary statistics, PROC SQL for top-N,          */
/*   and CALL SYMPUT to capture summary values for titles.                 */
/*   Parameters:                                                           */
/*     report_name   - Name identifier for the output files               */
/*     input_ds      - Input dataset (libname.dataset)                    */
/*     class_vars    - Classification variable(s) for grouping            */
/*     analysis_vars - Space-separated list of numeric analysis vars      */
/*     output_fmt    - Output format: HTML, PDF, or RTF                   */
/*     where_clause  - Optional filter condition                          */
/* --------------------------------------------------------------------- */
%macro standard_report(report_name=, input_ds=, class_vars=, analysis_vars=,
                       output_fmt=HTML, where_clause=1=1);

    %local i n_vars current_var total_obs grand_mean;

    %validate_params(macro_name=standard_report,
                     required_params=report_name input_ds class_vars analysis_vars);
    %if &framework_rc ne 0 %then %return;

    %let n_vars = %sysfunc(countw(&analysis_vars, %str( )));

    %put NOTE: [standard_report] Generating &report_name with &n_vars analysis variables.;
    %put NOTE: [standard_report] Output format: &output_fmt;

    /* Get total observation count and first variable grand mean via DATA step */
    data _null_;
        set &input_ds end=_last;
        where &where_clause;
        retain _count 0 _sum 0;
        _count + 1;
        _sum + %scan(&analysis_vars, 1, %str( ));
        if _last then do;
            call symputx('total_obs', _count, 'G');
            if _count > 0 then
                call symputx('grand_mean', put(_sum / _count, best12.), 'G');
            else
                call symputx('grand_mean', '0', 'G');
        end;
    run;

    %put NOTE: [standard_report] Total observations: &total_obs  Grand mean: &grand_mean;

    /* --- Select output destination based on format parameter --- */
    %if %upcase(&output_fmt) = HTML %then %do;
        ods html file="&report_base_path/&report_name..html"
                 style=HTMLBlue;
    %end;
    %else %if %upcase(&output_fmt) = PDF %then %do;
        ods pdf file="&report_base_path/&report_name..pdf"
                style=Printer;
    %end;
    %else %if %upcase(&output_fmt) = RTF %then %do;
        ods rtf file="&report_base_path/&report_name..rtf"
                style=RTF bodytitle;
    %end;
    %else %do;
        %put ERROR: [standard_report] Unsupported output format: &output_fmt;
        %let framework_rc = 1;
        %return;
    %end;

    title1 "Enterprise Report: &report_name";
    title2 "Period: &range_label (&range_start to &range_end)";
    title3 "Generated: &default_as_of — Total Records: &total_obs";
    footnote "Confidential — Internal Use Only";

    /* --- Iterate over each analysis variable for individual summaries --- */
    %do i = 1 %to &n_vars;
        %let current_var = %scan(&analysis_vars, &i, %str( ));

        title4 "Analysis Variable: &current_var (&i of &n_vars)";

        /* PROC MEANS for descriptive statistics */
        proc means data=&input_ds n mean std min q1 median q3 max maxdec=2;
            where &where_clause;
            class &class_vars;
            var &current_var;
            output out=work._summary_&current_var
                   n=n mean=avg std=std_dev min=min_val max=max_val;
        run;

        /* PROC SQL for top-10 records by this variable */
        proc sql outobs=10;
            title5 "Top 10 Records by &current_var";
            select &class_vars,
                   &current_var,
                   &current_var / &grand_mean as index_to_mean format=percent8.1
            from &input_ds
            where &where_clause
            order by &current_var descending;
        quit;

    %end;

    /* --- Cross-tabulation summary across all analysis variables --- */
    proc sql;
        create table rptout.&report_name._summary as
        select &class_vars,
               count(*) as record_count,
               %do i = 1 %to &n_vars;
                   %let current_var = %scan(&analysis_vars, &i, %str( ));
                   mean(&current_var) as avg_&current_var,
                   sum(&current_var)  as total_&current_var
                   %if &i < &n_vars %then ,;
               %end;
        from &input_ds
        where &where_clause
        group by &class_vars
        order by record_count descending;
    quit;

    /* Close ODS destination */
    %if %upcase(&output_fmt) = HTML %then %do; ods html close; %end;
    %else %if %upcase(&output_fmt) = PDF %then %do; ods pdf close; %end;
    %else %if %upcase(&output_fmt) = RTF %then %do; ods rtf close; %end;

    title; footnote;

    %put NOTE: [standard_report] Report &report_name generated successfully (&output_fmt).;

    /* Clean up per-variable summary tables */
    proc datasets lib=work nolist;
        %do i = 1 %to &n_vars;
            %let current_var = %scan(&analysis_vars, &i, %str( ));
            delete _summary_&current_var;
        %end;
    quit;

%mend standard_report;

/* --------------------------------------------------------------------- */
/* MACRO: batch_reports                                                   */
/*   Executes standard_report for each region in a list. Iterates         */
/*   using %DO with COUNTW/SCAN. Uses region-specific data filtering      */
/*   and calls get_date_range for period setup. Supports conditional       */
/*   inclusion of a year-over-year comparison section.                     */
/* --------------------------------------------------------------------- */
%macro batch_reports(region_list=, period=QTR, as_of=&default_as_of,
                     output_fmt=HTML, include_yoy=N);

    %local i n_regions current_region;

    %validate_params(macro_name=batch_reports,
                     required_params=region_list);
    %if &framework_rc ne 0 %then %return;

    /* Calculate date range for this batch */
    %get_date_range(period=&period, as_of=&as_of);

    %let n_regions = %sysfunc(countw(&region_list, %str( )));
    %put NOTE: [batch_reports] Processing &n_regions regions for period &range_label.;

    /* --- Main region iteration loop --- */
    %do i = 1 %to &n_regions;
        %let current_region = %scan(&region_list, &i, %str( ));
        %put NOTE: [batch_reports] Region &i of &n_regions: &current_region;

        /* Extract region-specific data for the date range */
        data staging.region_&current_region;
            set raw.sales_data;
            where region = "&current_region"
              and transaction_date between "&range_start"d and "&range_end"d;
        run;

        /* Generate the standard report for this region */
        %standard_report(
            report_name   = &current_region._&range_label,
            input_ds      = staging.region_&current_region,
            class_vars    = product_category department,
            analysis_vars = revenue units_sold margin_pct,
            output_fmt    = &output_fmt,
            where_clause  = 1=1
        );

        /* --- Optional year-over-year comparison section --- */
        %if %upcase(&include_yoy) = Y %then %do;
            %put NOTE: [batch_reports] Including YoY comparison for &current_region;

            /* Get prior year range */
            %local py_start py_end;
            %let py_start = %sysfunc(intnx(YEAR, %sysfunc(inputn(&range_start, yymmdd10.)), -1, S), yymmdd10.);
            %let py_end   = %sysfunc(intnx(YEAR, %sysfunc(inputn(&range_end, yymmdd10.)), -1, S), yymmdd10.);

            /* Build YoY comparison dataset */
            proc sql;
                create table staging.yoy_&current_region as
                select cy.product_category,
                       cy.revenue           as cy_revenue,
                       py.revenue           as py_revenue,
                       cy.revenue - py.revenue as revenue_change,
                       case when py.revenue > 0
                            then (cy.revenue - py.revenue) / py.revenue
                            else . end       as revenue_pct_change format=percent8.1
                from (
                    select product_category,
                           sum(revenue) as revenue
                    from raw.sales_data
                    where region = "&current_region"
                      and transaction_date between "&range_start"d and "&range_end"d
                    group by product_category
                ) as cy
                left join (
                    select product_category,
                           sum(revenue) as revenue
                    from raw.sales_data
                    where region = "&current_region"
                      and transaction_date between "&py_start"d and "&py_end"d
                    group by product_category
                ) as py
                    on cy.product_category = py.product_category
                order by revenue_change descending;
            quit;
        %end;

        /* Clean up region staging data */
        proc datasets lib=staging nolist;
            delete region_&current_region;
            %if %upcase(&include_yoy) = Y %then %do;
                delete yoy_&current_region;
            %end;
        quit;

    %end;  /* End region loop */

    %put NOTE: [batch_reports] Batch complete. &n_regions regions processed.;

%mend batch_reports;

/* ========================================================================= */
/* SECTION 3: Data Preparation — Lookup Formats and Base Data                */
/* ========================================================================= */

/* Create dynamic format for product category labels */
data staging.product_lookup;
    set raw.product_master (keep=product_code product_description);
run;

%create_format(fmtname=PRODLBL,
               data=staging.product_lookup,
               start_col=product_code,
               label_col=product_description,
               type=C);

/* Create dynamic format for department labels */
data staging.dept_lookup;
    set raw.department_master (keep=dept_code dept_name);
run;

%create_format(fmtname=DEPTLBL,
               data=staging.dept_lookup,
               start_col=dept_code,
               label_col=dept_name,
               type=C);

/* ========================================================================= */
/* SECTION 4: Main Reporting Execution — Quarterly Regional Reports          */
/* ========================================================================= */

/* Set up date range for this quarter */
%get_date_range(period=QTR, as_of=&default_as_of);

/* Execute batch reports for all five major sales regions */
%batch_reports(
    region_list = Northeast Midwest South West International,
    period      = QTR,
    as_of       = &default_as_of,
    output_fmt  = HTML,
    include_yoy = Y
);

/* ========================================================================= */
/* SECTION 5: Consolidated Summary — Cross-Region Aggregation                */
/* ========================================================================= */

/* Build a summary-of-summaries across all regions */
proc sql;
    create table mart.quarterly_summary as
    select 'ALL_REGIONS'           as region,
           a.product_category,
           sum(a.record_count)     as total_records,
           sum(a.total_revenue)    as total_revenue format=dollar15.2,
           avg(a.avg_revenue)      as weighted_avg_revenue format=dollar12.2,
           sum(a.total_units_sold) as total_units,
           avg(a.avg_margin_pct)   as avg_margin format=percent8.1
    from (
        select * from rptout.Northeast_&range_label._summary
        union all
        select * from rptout.Midwest_&range_label._summary
        union all
        select * from rptout.South_&range_label._summary
        union all
        select * from rptout.West_&range_label._summary
        union all
        select * from rptout.International_&range_label._summary
    ) as a
    group by a.product_category
    order by total_revenue descending;
quit;

/* Generate a consolidated executive report */
%standard_report(
    report_name   = Executive_Consolidated_&range_label,
    input_ds      = mart.quarterly_summary,
    class_vars    = product_category,
    analysis_vars = total_revenue total_units avg_margin,
    output_fmt    = PDF,
    where_clause  = 1=1
);

/* ========================================================================= */
/* SECTION 6: Trend Analysis — Rolling Quarterly Metrics                     */
/* ========================================================================= */

data mart.rolling_trends;
    set mart.quarterly_summary;
    by product_category;

    retain q1_revenue q2_revenue q3_revenue q4_revenue 0
           quarter_idx 0;

    /* Reset for each product category */
    if first.product_category then do;
        q1_revenue  = 0;
        q2_revenue  = 0;
        q3_revenue  = 0;
        q4_revenue  = 0;
        quarter_idx = 0;
    end;

    quarter_idx + 1;

    /* Store quarter-specific revenue */
    select (quarter_idx);
        when (1) q1_revenue = total_revenue;
        when (2) q2_revenue = total_revenue;
        when (3) q3_revenue = total_revenue;
        when (4) q4_revenue = total_revenue;
        otherwise;
    end;

    /* Compute rolling average on last record per category */
    if last.product_category then do;
        rolling_avg_revenue = mean(q1_revenue, q2_revenue, q3_revenue, q4_revenue);
        revenue_volatility  = std(q1_revenue, q2_revenue, q3_revenue, q4_revenue);

        /* Flag high-volatility categories */
        length volatility_flag $10;
        if revenue_volatility > rolling_avg_revenue * 0.3 then
            volatility_flag = 'HIGH';
        else if revenue_volatility > rolling_avg_revenue * 0.15 then
            volatility_flag = 'MEDIUM';
        else
            volatility_flag = 'LOW';

        output;
    end;

    format q1_revenue q2_revenue q3_revenue q4_revenue
           rolling_avg_revenue revenue_volatility dollar15.2;
run;

/* ========================================================================= */
/* SECTION 7: Reporting Metadata and Cleanup                                 */
/* ========================================================================= */

/* Store report execution metadata */
proc sql;
    insert into mart.report_execution_log
        (report_date, period, range_start, range_end,
         regions_processed, output_format, status, run_timestamp)
    values
        ("&default_as_of"d, "&default_period", "&range_start"d, "&range_end"d,
         5, "HTML+PDF", "COMPLETE", %sysfunc(datetime()));
quit;

/* Clean up staging datasets */
proc datasets lib=staging nolist;
    delete product_lookup dept_lookup;
quit;

/* Final status messages */
%if &framework_rc ne 0 %then %do;
    %put WARNING: Macro framework completed with errors. Review log for details.;
    %put WARNING: framework_rc = &framework_rc;
%end;
%else %do;
    %put NOTE: Macro framework completed successfully. All reports generated.;
%end;

options nomprint nomlogic nosymbolgen;

%put NOTE: ===== gsh_02_macro_framework.sas completed at %sysfunc(datetime(), datetime20.) =====;
