/******************************************************************************
 * Program Name   : gsh_15_complete_report.sas
 * Report ID      : RPT-EXEC-2026-Q1
 * Author         : Corporate Reporting Team — Executive Analytics Division
 * Distribution   : CEO, CFO, COO, VP Sales, VP HR, Board of Directors
 * Report Period  : Q1 FY2026 (January–March 2026)
 * Created        : 2026-01-15
 * Modified       : 2026-02-19
 * Version        : 3.0
 * Purpose        : Complete ODS reporting suite for executive management.
 *                  Generates multi-format (PDF, HTML, Excel) reports covering
 *                  executive summary, regional sales, workforce analytics,
 *                  financial statements, and appendix materials with
 *                  conditional formatting, traffic light KPI indicators,
 *                  and automated email distribution.
 * Dependencies   : report_templates.sas (shared formatting utilities)
 * Frequency      : Monthly / Quarterly
 * Change Log     :
 *   2026-01-15  v1.0  Initial report framework             (R. Nakamura)
 *   2026-01-28  v2.0  Added sales and HR sections           (S. Patel)
 *   2026-02-10  v2.5  Financial statements integration       (R. Nakamura)
 *   2026-02-19  v3.0  Full ODS suite with email delivery     (K. O'Brien)
 ******************************************************************************/

/* ========================================================================= */
/* SECTION 1: Environment Setup — Libraries, Options, Parameters             */
/* ========================================================================= */

/* --- Global options for report processing --- */
options mprint mlogic symbolgen nocenter ls=200 ps=65
        validvarname=v7 nofmterr msglevel=i nodate nonumber;

/* --- Library references for enterprise data sources --- */
libname sales   '/data/enterprise/sales'     access=readonly;
libname hr      '/data/enterprise/hr'        access=readonly;
libname finance '/data/enterprise/finance'   access=readonly;
libname rptout  '/reports/executive/output';

/* --- Report period and fiscal parameters --- */
%let report_period   = Q1-2026;
%let fiscal_year     = 2026;
%let report_format   = PDF;
%let period_start_dt = %sysfunc(mdy(1,1,2026));
%let period_end_dt   = %sysfunc(mdy(3,31,2026));
%let prior_start_dt  = %sysfunc(mdy(10,1,2025));
%let prior_end_dt    = %sysfunc(mdy(12,31,2025));
%let report_author   = R. Nakamura;
%let report_title    = Executive Management Report;
%let run_timestamp   = %sysfunc(datetime());
%let run_date        = %sysfunc(today(), yymmdd10.);

/* --- Distribution and delivery parameters --- */
%let dist_list       = ceo@corp.com cfo@corp.com coo@corp.com vp_sales@corp.com vp_hr@corp.com;
%let report_style    = journal;
%let output_path     = /reports/executive/output;
%let report_rc       = 0;
%let sections_done   = 0;

/* --- Load shared report formatting templates --- */
%include '/reports/shared/report_templates.sas';

/* ========================================================================= */
/* SECTION 2: Macro Definitions                                              */
/* ========================================================================= */

/* ------------------------------------------------------------------ */
/* %setup_ods — Initialize ODS output destination based on format    */
/*   Parameters: format= (PDF|HTML|EXCEL), title=, style=            */
/*   Opens the appropriate ODS destination with formatting options    */
/* ------------------------------------------------------------------ */
%macro setup_ods(format=PDF, title=Executive Report, style=journal);
    %local output_file timestamp_str;
    %let timestamp_str = %sysfunc(putn(%sysfunc(datetime()), datetime15.));
    %let output_file   = &output_path./exec_report_&report_period._&timestamp_str;
    %put NOTE: ========================================================;
    %put NOTE: Setting up ODS output — Format: &format, Style: &style;
    %put NOTE: Output file: &output_file;
    %put NOTE: ========================================================;

    /* --- Select ODS destination based on format parameter --- */
    %if &format = PDF %then %do;
        ods pdf file="&output_file..pdf"
            style=&style
            bookmarkgen=yes
            pdftoc=3
            compress=9
            author="&report_author"
            title="&title — &report_period";
        ods pdf select all;
    %end;

    %if &format = HTML %then %do;
        ods html path="&output_path"
            file="exec_report_&report_period..html"
            style=&style
            contents="exec_report_&report_period._toc.html"
            frame="exec_report_&report_period._frame.html"
            headtext='<link rel="stylesheet" href="report_style.css">';
        ods html select all;
    %end;

    %if &format = EXCEL %then %do;
        ods excel file="&output_file..xlsx"
            style=&style
            options(sheet_name="Cover"
                    embedded_titles="yes"
                    embedded_footnotes="yes"
                    frozen_headers="yes");
        ods excel select all;
    %end;

    /* --- Set global titles and footnotes --- */
    title1 j=c bold height=14pt "&title";
    title2 j=c height=11pt "Period: &report_period | Fiscal Year: &fiscal_year";
    title3 j=c height=10pt "Prepared by: &report_author | Date: &run_date";
    footnote1 j=l "Confidential — For Executive Distribution Only";
    footnote2 j=r "Generated: &run_date at %sysfunc(putn(%sysfunc(time()), time8.))";
%mend setup_ods;

/* ------------------------------------------------------------------ */
/* %exec_summary — Executive summary with key financial KPIs         */
/*   Parameters: period= (report period identifier)                   */
/*   Outputs: work.exec_kpis, work.exec_period_change                */
/* ------------------------------------------------------------------ */
%macro exec_summary(period=);
    %local n_metrics;
    %put NOTE: ========================================================;
    %put NOTE: Generating Executive Summary — Period: &period;
    %put NOTE: ========================================================;

    /* --- Step 1: Extract key financial metrics from finance tables --- */
    proc sql noprint;
        create table work.exec_kpis as
        select  'Revenue'          as metric_name length=30,
                sum(revenue_amount)           as current_value format=comma20.2,
                sum(prior_revenue)            as prior_value   format=comma20.2,
                sum(budget_amount)            as budget_value  format=comma20.2
        from finance.income_statement
        where period = "&period"
        union all
        select  'EBITDA'           as metric_name,
                sum(ebitda_amount)            as current_value,
                sum(prior_ebitda)             as prior_value,
                sum(ebitda_budget)            as budget_value
        from finance.income_statement
        where period = "&period"
        union all
        select  'Net Income'       as metric_name,
                sum(net_income)               as current_value,
                sum(prior_net_income)         as prior_value,
                sum(ni_budget)                as budget_value
        from finance.income_statement
        where period = "&period"
        union all
        select  'Gross Margin %'   as metric_name,
                sum(gross_profit)/sum(revenue_amount) * 100 as current_value,
                sum(prior_gp)/sum(prior_revenue) * 100      as prior_value,
                sum(gp_budget)/sum(budget_amount) * 100     as budget_value
        from finance.income_statement
        where period = "&period";

        select count(*) into :n_metrics trimmed
        from work.exec_kpis;
    quit;

    %put NOTE: Extracted &n_metrics key performance indicators.;

    /* --- Step 2: Compute period-over-period changes --- */
    data work.exec_period_change;
        set work.exec_kpis;
        length trend $10 status $20;

        /* Calculate percentage change from prior period */
        if prior_value ne 0 then
            pct_change = ((current_value - prior_value) / abs(prior_value)) * 100;
        else
            pct_change = .;

        /* Calculate budget variance */
        if budget_value ne 0 then
            budget_var = ((current_value - budget_value) / abs(budget_value)) * 100;
        else
            budget_var = .;

        /* Assign trend indicator for direction arrow */
        if pct_change > 5 then trend = 'UP';
        else if pct_change < -5 then trend = 'DOWN';
        else trend = 'FLAT';

        /* Traffic light status based on budget performance */
        if budget_var >= 0 then status = 'GREEN';
        else if budget_var >= -5 then status = 'AMBER';
        else status = 'RED';

        format pct_change budget_var 8.1;
    run;

    /* --- Step 3: Executive KPI report with traffic light formatting --- */
    proc report data=work.exec_period_change nowd
        style(header)=[backgroundcolor=cx003366 foreground=white
                        font_weight=bold font_size=10pt];

        columns metric_name current_value prior_value pct_change
                budget_value budget_var status;

        define metric_name   / group   'Key Metric'         style=[font_weight=bold];
        define current_value / sum     'Current Period'     format=comma20.2;
        define prior_value   / sum     'Prior Period'       format=comma20.2;
        define pct_change    / display 'Change %'           format=8.1;
        define budget_value  / sum     'Budget'             format=comma20.2;
        define budget_var    / display 'Variance %'         format=8.1;
        define status        / display 'Status'             style=[font_weight=bold];

        /* --- Conditional formatting: traffic light cell styling --- */
        compute status;
            if status = 'GREEN' then
                call define(_col_, 'style',
                    'style=[backgroundcolor=cx90EE90 foreground=cx006400]');
            else if status = 'AMBER' then
                call define(_col_, 'style',
                    'style=[backgroundcolor=cxFFD700 foreground=cx8B4513]');
            else if status = 'RED' then
                call define(_col_, 'style',
                    'style=[backgroundcolor=cxFF6347 foreground=white]');
        endcomp;

        /* --- Summary line at bottom of report --- */
        compute after;
            line ' ';
            line "Report Period: &period | Generated: &run_date";
        endcomp;
    run;

    %let sections_done = %eval(&sections_done + 1);
    %put NOTE: Executive Summary complete. Sections done: &sections_done;
%mend exec_summary;

/* ------------------------------------------------------------------ */
/* %sales_section — Regional sales analysis with pipeline metrics    */
/*   Parameters: region= (specific region name or ALL for iteration)  */
/*   Outputs: work.sales_pipeline, work.sales_quota, work.sales_chart */
/* ------------------------------------------------------------------ */
%macro sales_section(region=ALL);
    %local i n_regions reg;
    %put NOTE: ========================================================;
    %put NOTE: Generating Sales Section — Region: &region;
    %put NOTE: ========================================================;

    /* --- Step 1: Extract pipeline and bookings data via PROC SQL --- */
    proc sql noprint;
        create table work.sales_pipeline as
        select  s.region,
                s.product_line,
                s.sales_rep,
                sum(s.pipeline_value)     as pipeline       format=comma18.2,
                sum(s.bookings)           as bookings       format=comma18.2,
                sum(s.quota_amount)       as quota          format=comma18.2,
                count(distinct s.deal_id) as deal_count,
                sum(s.bookings) / sum(s.quota_amount) * 100
                                          as attainment_pct format=8.1
        from sales.opportunities s
        where s.close_date between &period_start_dt and &period_end_dt
            %if &region ne ALL %then
                and s.region = "&region";
        group by s.region, s.product_line, s.sales_rep
        order by s.region, attainment_pct desc;
    quit;

    /* --- Step 2: Product x Region cross-tabulation --- */
    proc tabulate data=work.sales_pipeline
        style=[font_size=9pt cellpadding=4];
        class region product_line;
        var bookings pipeline;
        table product_line='Product Line' all='Total',
              region='Region' * (bookings='Bookings'*sum*f=comma16.2
                                 pipeline='Pipeline'*sum*f=comma16.2)
              all='Grand Total' * (bookings='Bookings'*sum*f=comma16.2
                                   pipeline='Pipeline'*sum*f=comma16.2)
              / box='Sales Analysis';
    run;

    /* --- Step 3: Quota attainment calculation per rep --- */
    data work.sales_quota;
        set work.sales_pipeline;
        length performance_tier $15;

        /* Classify performance tier based on quota attainment */
        if attainment_pct >= 120 then performance_tier = 'Exceptional';
        else if attainment_pct >= 100 then performance_tier = 'On Target';
        else if attainment_pct >= 80 then performance_tier = 'Below Target';
        else performance_tier = 'At Risk';

        /* Flag sales reps needing management attention */
        needs_review = (attainment_pct < 70);
        format needs_review yesno.;
    run;

    /* --- Step 4: Regional detail iteration if ALL specified --- */
    %if &region = ALL %then %do;
        %let n_regions = 4;
        %do i = 1 %to &n_regions;
            %let reg = %scan(NORTH SOUTH EAST WEST, &i, %str( ));
            %put NOTE: Processing regional detail for &reg region;

            /* Regional summary statistics per product line */
            proc sql noprint;
                create table work.region_&reg as
                select  product_line,
                        sum(bookings)        as total_bookings  format=comma18.2,
                        sum(pipeline)        as total_pipeline  format=comma18.2,
                        sum(quota)           as total_quota     format=comma18.2,
                        mean(attainment_pct) as avg_attainment  format=8.1,
                        count(distinct sales_rep) as rep_count
                from work.sales_pipeline
                where region = "&reg"
                group by product_line;
            quit;
        %end;
    %end;

    /* --- Step 5: Prepare chart-ready dataset for PROC SGPLOT --- */
    data work.sales_chart;
        set work.sales_pipeline;
        /* Aggregate to region level for bar/line chart visualization */
        keep region bookings pipeline quota attainment_pct;
    run;

    /* Sort for chart readiness */
    proc sort data=work.sales_chart nodupkey;
        by region;
    run;

    %let sections_done = %eval(&sections_done + 1);
    %put NOTE: Sales Section complete. Sections done: &sections_done;
%mend sales_section;

/* ------------------------------------------------------------------ */
/* %hr_section — Workforce analytics: headcount, turnover, diversity */
/*   Outputs: work.hr_headcount, work.hr_diversity, work.hr_comp,    */
/*            work.hr_new_hires, work.hr_departures                   */
/* ------------------------------------------------------------------ */
%macro hr_section;
    %local total_hc turnover_rate n_hires n_departures;
    %put NOTE: ========================================================;
    %put NOTE: Generating HR / Workforce Analytics Section;
    %put NOTE: ========================================================;

    /* --- Step 1: Compute headcount and turnover rates --- */
    data work.hr_headcount;
        set hr.employee_roster end=eof;
        where employment_status = 'ACTIVE'
           or (termination_date between &period_start_dt and &period_end_dt);

        /* Calculate employee tenure in months and years */
        tenure_months = intck('month', hire_date, &period_end_dt);
        tenure_years  = tenure_months / 12;

        /* Flag turnover within the reporting period */
        if employment_status = 'TERMINATED' and
           termination_date between &period_start_dt and &period_end_dt
        then is_turnover = 1;
        else is_turnover = 0;

        /* Retain running totals for headcount and turnover counts */
        retain active_count 0 turnover_count 0;
        if employment_status = 'ACTIVE' then active_count + 1;
        if is_turnover then turnover_count + 1;

        /* On last record, compute turnover rate and store in macro vars */
        if eof then do;
            turnover_rate = (turnover_count / active_count) * 100;
            call symputx('total_hc', active_count);
            call symputx('turnover_rate', put(turnover_rate, 8.2));
        end;

        format tenure_years 5.1 turnover_rate 8.2;
    run;

    %put NOTE: Total headcount: &total_hc | Turnover rate: &turnover_rate pct;

    /* --- Step 2: Diversity metrics via PROC FREQ --- */
    proc freq data=work.hr_headcount noprint;
        where employment_status = 'ACTIVE';
        tables gender              / out=work.hr_div_gender;
        tables ethnicity           / out=work.hr_div_ethnicity;
        tables department * gender / out=work.hr_div_dept_gender;
    run;

    /* Combine diversity dimension tables into single reporting dataset */
    data work.hr_diversity;
        length category $30 value $50;
        set work.hr_div_gender    (in=a rename=(gender=value))
            work.hr_div_ethnicity (in=b rename=(ethnicity=value));
        if a then category = 'Gender';
        if b then category = 'Ethnicity';
        pct = percent;
        format pct 8.1;
        keep category value count pct;
    run;

    /* --- Step 3: Compensation analysis via PROC MEANS --- */
    proc means data=work.hr_headcount noprint
        where=(employment_status = 'ACTIVE');
        class department job_level;
        var base_salary total_compensation;
        output out=work.hr_comp
            mean(base_salary)=avg_salary
            median(base_salary)=med_salary
            min(base_salary)=min_salary
            max(base_salary)=max_salary
            mean(total_compensation)=avg_total_comp
            n(base_salary)=emp_count;
    run;

    /* --- Step 4: New hires and departures via PROC SQL --- */
    proc sql noprint;
        /* New hires within the reporting period */
        create table work.hr_new_hires as
        select employee_id, employee_name, department, job_title,
               hire_date, base_salary
        from hr.employee_roster
        where hire_date between &period_start_dt and &period_end_dt
        order by department, hire_date;

        select count(*) into :n_hires trimmed
        from work.hr_new_hires;

        /* Departures within the reporting period */
        create table work.hr_departures as
        select employee_id, employee_name, department, job_title,
               termination_date, termination_reason, tenure_months
        from work.hr_headcount
        where is_turnover = 1
        order by department, termination_date;

        select count(*) into :n_departures trimmed
        from work.hr_departures;
    quit;

    %put NOTE: New hires: &n_hires | Departures: &n_departures;
    %let sections_done = %eval(&sections_done + 1);
    %put NOTE: HR Section complete. Sections done: &sections_done;
%mend hr_section;

/* ------------------------------------------------------------------ */
/* %finance_section — Financial statements: income, balance sheet,   */
/*   budget variance with formatted P&L and YTD accumulation          */
/*   Outputs: work.income_stmt, work.balance_sheet, work.ytd_accum,  */
/*            work.budget_variance                                     */
/* ------------------------------------------------------------------ */
%macro finance_section;
    %local n_line_items total_revenue total_expenses;
    %put NOTE: ========================================================;
    %put NOTE: Generating Finance Section — Fiscal Year: &fiscal_year;
    %put NOTE: ========================================================;

    /* --- Step 1: Income statement line items via PROC SQL --- */
    proc sql noprint;
        create table work.income_stmt as
        select  line_item_id,
                line_item_name,
                line_item_category,
                display_order,
                indent_level,
                sum(case when period = "&report_period"
                    then amount else 0 end)     as current_amount
                    format=comma20.2,
                sum(case when period = "&report_period"
                    then budget else 0 end)     as budget_amount
                    format=comma20.2,
                sum(amount)                     as ytd_amount
                    format=comma20.2,
                sum(budget)                     as ytd_budget
                    format=comma20.2
        from finance.gl_detail
        where fiscal_year = &fiscal_year
          and line_item_category in ('REVENUE','COGS','OPEX','OTHER_INCOME',
                                     'INTEREST','TAX')
        group by line_item_id, line_item_name, line_item_category,
                 display_order, indent_level
        order by display_order;

        select count(*) into :n_line_items trimmed
        from work.income_stmt;

        select sum(current_amount) into :total_revenue trimmed
        from work.income_stmt
        where line_item_category = 'REVENUE';

        select sum(current_amount) into :total_expenses trimmed
        from work.income_stmt
        where line_item_category in ('COGS','OPEX');
    quit;

    %put NOTE: Income statement: &n_line_items line items processed.;

    /* --- Step 2: Balance sheet computations (assets, liabilities, equity) --- */
    data work.balance_sheet;
        set finance.trial_balance end=eof;
        where fiscal_year = &fiscal_year
          and period = "&report_period";

        length section $20;

        /* Classify accounts into balance sheet sections */
        if account_type in ('CASH','AR','INVENTORY','PREPAID','OTHER_CA')
            then section = 'Current Assets';
        else if account_type in ('PPE','INTANGIBLE','INVESTMENT','OTHER_NCA')
            then section = 'Non-Current Assets';
        else if account_type in ('AP','ACCRUED','ST_DEBT','OTHER_CL')
            then section = 'Current Liabilities';
        else if account_type in ('LT_DEBT','PENSION','DEFERRED_TAX','OTHER_NCL')
            then section = 'Non-Current Liabilities';
        else if account_type in ('COMMON','RETAINED','AOCI','TREASURY')
            then section = 'Equity';

        /* Compute net amounts based on normal balances */
        if section in ('Current Assets','Non-Current Assets') then
            net_amount = debit_balance - credit_balance;
        else
            net_amount = credit_balance - debit_balance;

        /* Running totals using RETAIN for balance sheet equation check */
        retain total_assets 0 total_liabilities 0 total_equity 0;
        if section in ('Current Assets','Non-Current Assets') then
            total_assets + net_amount;
        else if section in ('Current Liabilities','Non-Current Liabilities') then
            total_liabilities + net_amount;
        else if section = 'Equity' then
            total_equity + net_amount;

        /* On last record, validate Assets = Liabilities + Equity */
        if eof then do;
            bs_difference = total_assets - total_liabilities - total_equity;
            if abs(bs_difference) > 0.01 then
                put 'WARNING: Balance sheet out of balance by '
                    bs_difference comma20.2;
        end;

        format net_amount total_assets total_liabilities total_equity
               bs_difference comma20.2;
    run;

    /* --- Step 3: Formatted P&L report with indentation levels --- */
    proc report data=work.income_stmt nowd
        style(header)=[backgroundcolor=cx003366 foreground=white font_weight=bold];

        columns display_order indent_level line_item_name
                current_amount budget_amount ytd_amount ytd_budget;

        define display_order   / order noprint;
        define indent_level    / display noprint;
        define line_item_name  / display 'Line Item'
            style=[font_size=9pt];
        define current_amount  / sum 'Current Period' format=comma20.2;
        define budget_amount   / sum 'Budget'         format=comma20.2;
        define ytd_amount      / sum 'YTD Actual'     format=comma20.2;
        define ytd_budget      / sum 'YTD Budget'     format=comma20.2;

        /* Apply indentation styling based on hierarchy level */
        compute line_item_name;
            if indent_level = 0 then
                call define(_col_, 'style',
                    'style=[font_weight=bold backgroundcolor=cxE8E8E8]');
            else if indent_level = 1 then
                call define(_col_, 'style',
                    'style=[indent=15pt]');
            else if indent_level = 2 then
                call define(_col_, 'style',
                    'style=[indent=30pt font_style=italic]');
        endcomp;

        /* Highlight negative variances in red */
        compute current_amount;
            if current_amount.sum < 0 then
                call define(_col_, 'style',
                    'style=[foreground=red]');
        endcomp;

        rbreak after / summarize
            style=[font_weight=bold backgroundcolor=cx003366 foreground=white];
    run;

    /* --- Step 4: YTD accumulation with RETAIN for running totals --- */
    data work.ytd_accum;
        set finance.monthly_actuals;
        where fiscal_year = &fiscal_year;
        by line_item_id;

        retain ytd_running 0;

        /* Reset YTD accumulator at start of each line item group */
        if first.line_item_id then ytd_running = 0;
        ytd_running + monthly_amount;

        /* Calculate YTD variance against prorated annual budget */
        months_elapsed  = month(period_date);
        prorated_budget = (annual_budget / 12) * months_elapsed;
        ytd_variance    = ytd_running - prorated_budget;
        ytd_var_pct     = (ytd_variance / prorated_budget) * 100;

        format ytd_running prorated_budget ytd_variance comma20.2
               ytd_var_pct 8.1;
    run;

    /* --- Step 5: Budget vs actual variance analysis --- */
    proc sql noprint;
        create table work.budget_variance as
        select  a.line_item_category,
                a.line_item_name,
                a.current_amount,
                a.budget_amount,
                a.current_amount - a.budget_amount as variance
                    format=comma20.2,
                case when a.budget_amount ne 0 then
                    (a.current_amount - a.budget_amount) /
                    abs(a.budget_amount) * 100
                else . end                         as var_pct
                    format=8.1,
                case when calculated var_pct > 5 then 'FAVORABLE'
                     when calculated var_pct < -5 then 'UNFAVORABLE'
                     else 'ON_TRACK' end           as var_status length=15
        from work.income_stmt a
        order by abs(calculated variance) desc;
    quit;

    %let sections_done = %eval(&sections_done + 1);
    %put NOTE: Finance Section complete. Sections done: &sections_done;
%mend finance_section;

/* ------------------------------------------------------------------ */
/* %appendix — Supporting tables: top customers, AR aging, notes     */
/*   Outputs: work.top_customers, rptout (AR aging print),           */
/*            work.methodology                                        */
/* ------------------------------------------------------------------ */
%macro appendix;
    %put NOTE: ========================================================;
    %put NOTE: Generating Appendix — Supporting Tables and Notes;
    %put NOTE: ========================================================;

    /* --- Appendix A: Top 20 customers by revenue --- */
    proc sql outobs=20;
        create table work.top_customers as
        select  c.customer_id,
                c.customer_name,
                c.industry_segment,
                sum(s.revenue_amount)    as total_revenue   format=comma18.2,
                count(distinct s.order_id) as order_count,
                max(s.order_date)        as last_order_date format=yymmdd10.,
                sum(s.revenue_amount) /
                    (select sum(revenue_amount)
                     from sales.order_detail
                     where order_date between &period_start_dt
                                         and &period_end_dt) * 100
                                         as revenue_share   format=8.1
        from sales.order_detail s
        inner join sales.customer_master c
            on s.customer_id = c.customer_id
        where s.order_date between &period_start_dt and &period_end_dt
        group by c.customer_id, c.customer_name, c.industry_segment
        order by total_revenue desc;
    quit;

    /* --- Appendix B: Open AR aging report --- */
    proc print data=finance.ar_open_items noobs label
        style(header)=[backgroundcolor=cx003366 foreground=white];
        where open_balance > 0;
        var customer_name invoice_id invoice_date due_date
            open_balance aging_bucket days_past_due;
        label customer_name  = 'Customer'
              invoice_id     = 'Invoice #'
              invoice_date   = 'Invoice Date'
              due_date       = 'Due Date'
              open_balance   = 'Open Balance'
              aging_bucket   = 'Aging Bucket'
              days_past_due  = 'Days Past Due';
        sum open_balance;
    run;

    /* --- Appendix C: Methodology notes and assumptions --- */
    data work.methodology;
        length section $50 description $500;
        section = 'Revenue Recognition';
        description = 'Revenue is recognized per ASC 606 at point of delivery for product sales and ratably over the service period for subscriptions.';
        output;
        section = 'EBITDA Calculation';
        description = 'EBITDA excludes stock-based compensation, restructuring charges, and one-time items per the company Non-GAAP policy.';
        output;
        section = 'Headcount Methodology';
        description = 'Headcount reflects active employees as of period end. Contractors and temporary staff are excluded from the count.';
        output;
        section = 'Regional Allocation';
        description = 'Shared services costs are allocated to regions based on headcount-weighted revenue contribution ratios.';
        output;
        section = 'Budget Variance';
        description = 'Favorable variances (actuals exceeding budget for revenue, below budget for expenses) are shown in green.';
        output;
    run;

    %let sections_done = %eval(&sections_done + 1);
    %put NOTE: Appendix complete. Sections done: &sections_done;
%mend appendix;

/* ------------------------------------------------------------------ */
/* %close_ods — Finalize ODS output and log report metadata          */
/*   Closes active ODS destinations and records generation metadata   */
/*   to the report output library for audit trail purposes            */
/* ------------------------------------------------------------------ */
%macro close_ods;
    %put NOTE: ========================================================;
    %put NOTE: Closing ODS Output and Logging Report Metadata;
    %put NOTE: ========================================================;

    /* --- Clear titles and footnotes before closing --- */
    title;
    footnote;

    /* --- Close the active ODS destination --- */
    %if &report_format = PDF %then %do;
        ods pdf close;
    %end;
    %if &report_format = HTML %then %do;
        ods html close;
    %end;
    %if &report_format = EXCEL %then %do;
        ods excel close;
    %end;

    /* --- Log report generation metadata for audit trail --- */
    data rptout.report_log;
        length report_id $20 report_name $60 format $10 author $30
               status $15 distribution $200;
        report_id     = "RPT-EXEC-&report_period";
        report_name   = "&report_title";
        format        = "&report_format";
        author        = "&report_author";
        generated_dt  = datetime();
        sections_cnt  = &sections_done;
        status        = ifc(&report_rc = 0, 'SUCCESS', 'ERROR');
        distribution  = "&dist_list";
        run_duration  = datetime() - &run_timestamp;
        format generated_dt datetime20. run_duration time8.;
    run;

    %put NOTE: Report metadata logged to rptout.report_log;
%mend close_ods;

/* ========================================================================= */
/* SECTION 3: Main Program Execution                                         */
/* ========================================================================= */

%put NOTE: ============================================================;
%put NOTE: EXECUTIVE MANAGEMENT REPORT SUITE v3.0;
%put NOTE: Period: &report_period | Format: &report_format;
%put NOTE: Author: &report_author | Date: &run_date;
%put NOTE: ============================================================;

/* --- Step 1: Initialize ODS output destination --- */
%setup_ods(format=&report_format, title=&report_title, style=&report_style);

/* --- Step 2: Generate report sections in sequence --- */
%exec_summary(period=&report_period);

%sales_section(region=ALL);

%hr_section;

%finance_section;

%appendix;

/* --- Step 3: Close ODS and log report metadata --- */
%close_ods;

/* --- Step 4: Retrieve email distribution for delivery --- */
proc sql noprint;
    select trim(distribution) into :email_list separated by ' '
    from rptout.report_log
    where report_id = "RPT-EXEC-&report_period";
quit;

/* --- Step 5: Error handling and final status reporting --- */
%if &report_rc ne 0 %then %do;
    %put ERROR: Report generation failed with return code &report_rc;
    %put ERROR: Review log for details. Sections completed: &sections_done;

    /* Log error details to persistent error table */
    data rptout.report_errors;
        length report_id $20 error_msg $200 error_dt 8;
        report_id = "RPT-EXEC-&report_period";
        error_msg = "Generation failed at section &sections_done";
        error_dt  = datetime();
        format error_dt datetime20.;
    run;
%end;
%else %do;
    %put NOTE: Report generation completed successfully.;
    %put NOTE: All &sections_done sections generated without errors.;
%end;

/* --- Cleanup temporary work datasets --- */
proc datasets lib=work nolist nowarn;
    delete exec_kpis exec_period_change
           sales_pipeline sales_quota sales_chart
           region_NORTH region_SOUTH region_EAST region_WEST
           hr_headcount hr_diversity hr_div_gender hr_div_ethnicity
           hr_div_dept_gender hr_comp hr_new_hires hr_departures
           income_stmt balance_sheet ytd_accum budget_variance
           top_customers methodology;
quit;

/* --- Reset options to defaults --- */
options nomprint nomlogic nosymbolgen;

%put NOTE: ============================================================;
%put NOTE: EXECUTIVE REPORT SUITE COMPLETE;
%put NOTE: Period: &report_period;
%put NOTE: Status: %sysfunc(ifc(&report_rc=0, SUCCESS, FAILED));
%put NOTE: Report delivered to distribution list;
%put NOTE: ============================================================;
