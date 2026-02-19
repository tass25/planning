/*****************************************************************************
 * Program: gsm_07_time_series.sas
 * Purpose: Time series analysis for monthly retail sales data
 * Author:  Analytics Team
 * Date:    2026-02-19
 * Description:
 *   Analyzes monthly sales trends using lag functions for moving averages,
 *   performs year-over-year comparisons, date arithmetic with INTCK/INTNX,
 *   seasonal aggregation, and interpolation of missing periods.
 *****************************************************************************/

/* ------------------------------------------------------------------ */
/* Global settings and library references                             */
/* ------------------------------------------------------------------ */
options mprint mlogic nocenter ls=132 ps=60;

libname raw     'C:/data/timeseries/raw' access=readonly;
libname staging 'C:/data/timeseries/staging';
libname tgt     'C:/data/timeseries/output';

/* ------------------------------------------------------------------ */
/* Step 1: Moving averages using LAG functions                        */
/*   - Compute 3-month and 6-month moving averages for trend analysis */
/*   - Carry forward cumulative revenue with RETAIN                   */
/* ------------------------------------------------------------------ */
data staging.sales_moving_avg;
    set raw.monthly_sales;
    by region_id;

    retain cumulative_revenue 0;

    /* Reset cumulative counter at start of each region */
    if first.region_id then cumulative_revenue = 0;
    cumulative_revenue + net_revenue;

    /* Lag values for moving average calculation */
    lag1_rev = lag1(net_revenue);
    lag2_rev = lag2(net_revenue);
    lag3_rev = lag3(net_revenue);
    lag4_rev = lag4(net_revenue);
    lag5_rev = lag5(net_revenue);

    /* 3-month moving average (requires at least 3 data points) */
    if _n_ >= 3 then
        ma_3m = mean(net_revenue, lag1_rev, lag2_rev);

    /* 6-month moving average (requires at least 6 data points) */
    if _n_ >= 6 then
        ma_6m = mean(net_revenue, lag1_rev, lag2_rev,
                     lag3_rev, lag4_rev, lag5_rev);

    /* Month-over-month percent change */
    if not missing(lag1_rev) and lag1_rev > 0 then
        mom_change_pct = ((net_revenue - lag1_rev) / lag1_rev) * 100;

    /* Trend direction indicator */
    length trend_direction $10;
    if mom_change_pct > 5 then trend_direction = 'UP';
    else if mom_change_pct < -5 then trend_direction = 'DOWN';
    else if not missing(mom_change_pct) then trend_direction = 'STABLE';
    else trend_direction = 'N/A';

    format cumulative_revenue comma15.2
           ma_3m ma_6m comma12.2
           mom_change_pct 6.1;
run;

/* ------------------------------------------------------------------ */
/* Step 2: Interpolate missing months                                 */
/*   - Fill gaps in time series with linear interpolation             */
/*   - Detect date continuity breaks                                  */
/* ------------------------------------------------------------------ */
data staging.sales_interpolated;
    set staging.sales_moving_avg;
    by region_id sale_month;

    /* Track previous known value for interpolation */
    prev_rev = lag1(net_revenue);

    /* Simple carry-forward interpolation for missing values */
    if missing(net_revenue) and not missing(prev_rev) then do;
        net_revenue = prev_rev;
        interpolated_flag = 1;
    end;
    else interpolated_flag = 0;

    /* Check for month continuity gaps */
    expected_month = intnx('month', lag1(sale_month), 1, 'beginning');
    if not missing(expected_month) and sale_month ne expected_month then
        gap_detected = 1;
    else
        gap_detected = 0;

    format expected_month monyy7.;
run;

/* ------------------------------------------------------------------ */
/* Step 3: Year-over-year comparison via SQL                          */
/*   - Join current period to same period prior year                  */
/*   - Compute YoY change percentages for revenue and moving averages */
/* ------------------------------------------------------------------ */
proc sql;
    create table staging.yoy_comparison as
    select
        a.region_id,
        a.sale_month,
        year(a.sale_month) as current_year,
        a.net_revenue as current_revenue,
        b.net_revenue as prior_year_revenue,
        case
            when b.net_revenue > 0 then
                ((a.net_revenue - b.net_revenue) / b.net_revenue) * 100
            else .
        end as yoy_change_pct format=6.1,
        a.ma_3m as current_ma3,
        b.ma_3m as prior_year_ma3,
        a.cumulative_revenue
    from staging.sales_moving_avg a
    left join staging.sales_moving_avg b
        on a.region_id = b.region_id
        and a.sale_month = intnx('year', b.sale_month, 1, 'same')
    order by a.region_id, a.sale_month;
quit;

/* ------------------------------------------------------------------ */
/* Step 4: Date arithmetic - compute fiscal periods and intervals     */
/*   - Fiscal year begins in July                                     */
/*   - Calculate fiscal quarter, days in month, daily average revenue */
/* ------------------------------------------------------------------ */
data staging.sales_fiscal;
    set staging.yoy_comparison;

    /* Fiscal year starts in July */
    fiscal_year_start = intnx('year.7', sale_month, 0, 'beginning');
    fiscal_year = year(fiscal_year_start);

    /* Fiscal quarter within fiscal year */
    months_into_fy = intck('month', fiscal_year_start, sale_month);
    fiscal_quarter = floor(months_into_fy / 3) + 1;

    /* Calendar days in the sales month */
    month_start = intnx('month', sale_month, 0, 'beginning');
    month_end   = intnx('month', sale_month, 0, 'end');
    days_in_month = intck('day', month_start, month_end) + 1;

    /* Daily average revenue */
    if days_in_month > 0 then
        daily_avg_revenue = current_revenue / days_in_month;

    /* Months elapsed since baseline date */
    months_since_start = intck('month', '01JAN2020'd, sale_month);

    /* Revenue per day of month for normalization */
    if days_in_month > 0 then
        normalized_revenue = (current_revenue / days_in_month) * 30;

    format fiscal_year_start month_start month_end date9.
           daily_avg_revenue normalized_revenue comma10.2;
run;

/* ------------------------------------------------------------------ */
/* Step 5: Seasonal aggregation with CLASS statement                  */
/*   - Summarize revenue metrics by fiscal year and quarter           */
/*   - Produce seasonal performance summary for reporting             */
/* ------------------------------------------------------------------ */
proc means data=staging.sales_fiscal n mean sum std median;
    class fiscal_year fiscal_quarter;
    var current_revenue daily_avg_revenue yoy_change_pct;
    output out=tgt.seasonal_summary
        mean(current_revenue)  = avg_revenue
        sum(current_revenue)   = total_revenue
        mean(yoy_change_pct)   = avg_yoy_change
        std(current_revenue)   = std_revenue
        n(current_revenue)     = n_months;
    title 'Seasonal Revenue Summary by Fiscal Year and Quarter';
run;

/* End of time series analysis program */
