/******************************************************************************
 * Program: gsm_13_sales_dashboard.sas
 * Purpose: Sales performance dashboard data preparation
 *          Builds denormalized sales fact table, computes attainment metrics,
 *          and generates KPI summary for executive dashboard consumption
 * Author:  Sales Analytics Team
 * Date:    2026-02-19
 ******************************************************************************/

/* --- Library references for sales data warehouse --- */
libname raw     '/data/sales/raw';
libname staging '/data/sales/staging';
libname tgt     '/data/sales/target';

options mprint nocenter yearcutoff=2020;

/* --- ODS and report formatting setup --- */
ods listing close;
ods html path='/reports/sales' file='dashboard_data.html' style=plateau;
title1 'Sales Performance Dashboard';
title2 "Reporting Period: &sysdate9";

/* -----------------------------------------------------------------------
   STEP 1: Sales data enrichment - territory mapping and quota assignment
   ----------------------------------------------------------------------- */
data staging.enriched_sales;
    set raw.sales_transactions;
    length territory $20 region $15;

    /* Map sales rep to territory based on state */
    if state in ('CA','OR','WA','NV','AZ') then territory = 'WEST';
    else if state in ('TX','OK','LA','AR','NM') then territory = 'SOUTH_CENTRAL';
    else if state in ('NY','NJ','CT','MA','PA') then territory = 'NORTHEAST';
    else if state in ('IL','OH','MI','WI','MN') then territory = 'MIDWEST';
    else territory = 'OTHER';

    /* Assign region from territory */
    if territory in ('WEST') then region = 'PACIFIC';
    else if territory in ('SOUTH_CENTRAL') then region = 'CENTRAL';
    else if territory in ('NORTHEAST') then region = 'EAST';
    else if territory in ('MIDWEST') then region = 'CENTRAL';
    else region = 'UNASSIGNED';

    /* Revenue calculations */
    net_revenue = gross_amount - discount_amount;
    margin_pct = (net_revenue - cost_amount) / net_revenue;

    /* Fiscal quarter assignment */
    fiscal_qtr = ceil(month(sale_date) / 3);
    fiscal_year = year(sale_date);

    format net_revenue cost_amount dollar12.2 margin_pct percent8.1;
run;

/* -----------------------------------------------------------------------
   STEP 2: Build denormalized sales fact table with multiple JOINs
   ----------------------------------------------------------------------- */
proc sql;
    create table staging.sales_fact as
    select e.transaction_id,
           e.sale_date,
           e.rep_id,
           r.rep_name,
           r.hire_date,
           e.territory,
           e.region,
           e.fiscal_year,
           e.fiscal_qtr,
           p.product_name,
           p.product_category,
           p.product_line,
           c.customer_name,
           c.customer_segment,
           c.industry,
           e.net_revenue,
           e.margin_pct,
           q.quarterly_quota
    from staging.enriched_sales as e
    inner join raw.sales_reps as r
        on e.rep_id = r.rep_id
    inner join raw.products as p
        on e.product_id = p.product_id
    inner join raw.customers as c
        on e.customer_id = c.customer_id
    left join raw.quotas as q
        on e.rep_id = q.rep_id
        and e.fiscal_year = q.fiscal_year
        and e.fiscal_qtr = q.fiscal_qtr;
quit;

/* -----------------------------------------------------------------------
   STEP 3: Regional rollup using PROC MEANS with CLASS
   ----------------------------------------------------------------------- */
proc means data=staging.sales_fact
           sum mean n noprint;
    class region territory fiscal_qtr;
    var net_revenue margin_pct;
    output out=staging.regional_rollup
        sum(net_revenue)=total_revenue
        mean(margin_pct)=avg_margin
        n(net_revenue)=deal_count;
run;

/* -----------------------------------------------------------------------
   STEP 4: Compute attainment percentages and performance bands
   ----------------------------------------------------------------------- */
proc sort data=staging.sales_fact;
    by rep_id fiscal_year fiscal_qtr;
run;

data staging.rep_attainment;
    set staging.sales_fact;
    by rep_id fiscal_year fiscal_qtr;
    retain qtd_revenue;

    /* Accumulate revenue within rep-quarter */
    if first.fiscal_qtr then qtd_revenue = 0;
    qtd_revenue + net_revenue;

    /* Output one record per rep per quarter */
    if last.fiscal_qtr then do;
        if quarterly_quota > 0 then
            attainment_pct = qtd_revenue / quarterly_quota;
        else
            attainment_pct = .;

        /* Performance band assignment */
        length perf_band $15;
        if attainment_pct >= 1.50 then perf_band = 'EXCEPTIONAL';
        else if attainment_pct >= 1.00 then perf_band = 'ON_TARGET';
        else if attainment_pct >= 0.75 then perf_band = 'DEVELOPING';
        else perf_band = 'AT_RISK';

        format attainment_pct percent8.1 qtd_revenue dollar12.2;
        output;
    end;
run;

/* -----------------------------------------------------------------------
   STEP 5: Rep performance quartiles using PROC RANK
   ----------------------------------------------------------------------- */
proc rank data=staging.rep_attainment
          out=staging.rep_ranked
          groups=4;
    var attainment_pct;
    ranks attainment_quartile;
run;

/* -----------------------------------------------------------------------
   STEP 6: KPI summary dataset for dashboard consumption
   ----------------------------------------------------------------------- */
data tgt.dashboard_kpis;
    set staging.rep_ranked end=eof;
    length kpi_name $30;

    /* Running accumulators */
    retain total_rev quota_sum reps_above reps_below rep_count 0;
    total_rev + qtd_revenue;
    quota_sum + quarterly_quota;
    rep_count + 1;
    if attainment_pct >= 1.0 then reps_above + 1;
    else reps_below + 1;

    if eof then do;
        kpi_name = 'OVERALL_ATTAINMENT';
        kpi_value = total_rev / quota_sum;
        output;

        kpi_name = 'PCT_REPS_ON_TARGET';
        kpi_value = reps_above / rep_count;
        output;

        kpi_name = 'TOTAL_REVENUE';
        kpi_value = total_rev;
        output;

        kpi_name = 'REP_COUNT';
        kpi_value = rep_count;
        output;
    end;

    keep kpi_name kpi_value;
    format kpi_value comma16.2;
run;

ods html close;
ods listing;
title;
