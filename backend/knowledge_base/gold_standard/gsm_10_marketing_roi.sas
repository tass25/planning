/*****************************************************************************
 * Program: gsm_10_marketing_roi.sas
 * Purpose: Marketing campaign ROI analysis and performance reporting
 * Author:  Marketing Analytics Team
 * Date:    2026-02-19
 * Description:
 *   Computes campaign-level costs, conversions, and revenue attribution.
 *   Calculates channel ROI across 12 months, ranks campaign performance,
 *   and produces an executive dashboard dataset.
 *****************************************************************************/

/* ------------------------------------------------------------------ */
/* Global settings and library references                             */
/* ------------------------------------------------------------------ */
options mprint mlogic nocenter ls=132 ps=60;

libname raw     'C:/data/marketing/raw' access=readonly;
libname staging 'C:/data/marketing/staging';
libname tgt     'C:/data/marketing/output';

/* ------------------------------------------------------------------ */
/* Step 1: Compute campaign-level costs and conversions               */
/*   - Aggregate spend, impressions, clicks, and conversions          */
/*   - Calculate click-through rate and cost per acquisition          */
/* ------------------------------------------------------------------ */
data staging.campaign_metrics;
    set raw.campaign_daily_stats;
    by campaign_id;

    retain total_spend total_impressions total_clicks total_conversions 0;

    /* Reset accumulators at start of each campaign */
    if first.campaign_id then do;
        total_spend = 0;
        total_impressions = 0;
        total_clicks = 0;
        total_conversions = 0;
    end;

    /* Accumulate daily metrics */
    total_spend + daily_spend;
    total_impressions + daily_impressions;
    total_clicks + daily_clicks;
    total_conversions + daily_conversions;

    /* Output summary row at end of each campaign */
    if last.campaign_id then do;
        /* Click-through rate */
        if total_impressions > 0 then
            ctr = (total_clicks / total_impressions) * 100;
        else ctr = 0;

        /* Cost per click */
        if total_clicks > 0 then
            cpc = total_spend / total_clicks;
        else cpc = .;

        /* Cost per acquisition */
        if total_conversions > 0 then
            cpa = total_spend / total_conversions;
        else cpa = .;

        format total_spend cpc cpa dollar12.2
               total_impressions total_clicks total_conversions comma12.
               ctr 6.2;
        output;
    end;
run;

/* ------------------------------------------------------------------ */
/* Step 2: Join campaigns with revenue attribution (multi-touch)      */
/*   - Link campaign touches to downstream revenue events             */
/*   - Apply linear multi-touch attribution model                     */
/* ------------------------------------------------------------------ */
proc sql;
    create table staging.campaign_revenue as
    select
        c.campaign_id,
        c.campaign_name,
        c.channel,
        c.total_spend,
        c.total_conversions,
        count(distinct t.customer_id) as attributed_customers,
        sum(t.touch_weight * r.revenue_amount) as attributed_revenue format=dollar15.2,
        /* ROI calculation: (revenue - cost) / cost */
        case
            when c.total_spend > 0 then
                (calculated attributed_revenue - c.total_spend) / c.total_spend * 100
            else .
        end as campaign_roi format=8.1,
        /* Revenue per conversion */
        case
            when c.total_conversions > 0 then
                calculated attributed_revenue / c.total_conversions
            else .
        end as revenue_per_conversion format=dollar10.2
    from staging.campaign_metrics c
    left join raw.touchpoint_log t
        on c.campaign_id = t.campaign_id
    left join raw.revenue_events r
        on t.customer_id = r.customer_id
        and t.touch_date <= r.purchase_date
        and r.purchase_date <= t.touch_date + 30
    group by c.campaign_id, c.campaign_name, c.channel,
             c.total_spend, c.total_conversions
    order by calculated campaign_roi desc;
quit;

/* ------------------------------------------------------------------ */
/* Step 3: Calculate channel ROI across 12 months using ARRAYS        */
/*   - Monthly revenue and cost arrays per channel                    */
/*   - Compute rolling and cumulative ROI by channel                  */
/* ------------------------------------------------------------------ */
data staging.channel_monthly_roi;
    set raw.channel_monthly_data;
    by channel;

    /* Monthly revenue and cost arrays */
    array rev{12} rev_m01-rev_m12;
    array cost{12} cost_m01-cost_m12;
    array roi{12} roi_m01-roi_m12;
    array cum_rev{12} _temporary_;
    array cum_cost{12} _temporary_;

    /* Compute monthly ROI and cumulative figures */
    do m = 1 to 12;
        if cost{m} > 0 then
            roi{m} = ((rev{m} - cost{m}) / cost{m}) * 100;
        else
            roi{m} = .;

        /* Cumulative */
        if m = 1 then do;
            cum_rev{m} = rev{m};
            cum_cost{m} = cost{m};
        end;
        else do;
            cum_rev{m} = cum_rev{m-1} + rev{m};
            cum_cost{m} = cum_cost{m-1} + cost{m};
        end;
    end;

    /* Annual totals */
    annual_revenue = sum(of rev{*});
    annual_cost = sum(of cost{*});
    if annual_cost > 0 then
        annual_roi = ((annual_revenue - annual_cost) / annual_cost) * 100;
    else annual_roi = .;

    /* Break-even month: first month where cumulative ROI >= 0 */
    breakeven_month = .;
    do m = 1 to 12;
        if cum_cost{m} > 0 and cum_rev{m} >= cum_cost{m}
           and missing(breakeven_month) then
            breakeven_month = m;
    end;

    format annual_revenue annual_cost dollar15.2
           annual_roi 8.1;
    drop m;
run;

/* ------------------------------------------------------------------ */
/* Step 4: Campaign performance summary statistics                    */
/* ------------------------------------------------------------------ */
proc means data=staging.campaign_revenue n mean std median min max;
    class channel;
    var total_spend attributed_revenue campaign_roi
        total_conversions revenue_per_conversion;
    output out=staging.performance_summary
        mean(campaign_roi)          = avg_roi
        mean(total_spend)           = avg_spend
        mean(attributed_revenue)    = avg_revenue
        sum(attributed_revenue)     = total_attributed_rev
        n(campaign_id)              = n_campaigns;
    title 'Campaign Performance Summary by Channel';
run;

/* ------------------------------------------------------------------ */
/* Step 5: Campaign tiering with PROC RANK                            */
/*   - Rank campaigns by ROI into quartile tiers                      */
/* ------------------------------------------------------------------ */
proc rank data=staging.campaign_revenue
          out=staging.campaign_ranked groups=4;
    var campaign_roi;
    ranks roi_quartile;
run;

/* Assign tier labels based on rank */
data staging.campaign_tiered;
    set staging.campaign_ranked;

    length campaign_tier $12;
    select (roi_quartile);
        when (3) campaign_tier = 'PLATINUM';
        when (2) campaign_tier = 'GOLD';
        when (1) campaign_tier = 'SILVER';
        when (0) campaign_tier = 'BRONZE';
        otherwise campaign_tier = 'UNRANKED';
    end;
run;

/* ------------------------------------------------------------------ */
/* Step 6: Executive dashboard output dataset                         */
/*   - Final summary with KPIs for leadership review                  */
/* ------------------------------------------------------------------ */
data tgt.executive_dashboard;
    set staging.campaign_tiered;

    /* Key performance indicators for dashboard */
    length kpi_status $10;
    if campaign_roi >= 200 then kpi_status = 'EXCEEDS';
    else if campaign_roi >= 100 then kpi_status = 'ON TARGET';
    else if campaign_roi >= 0 then kpi_status = 'BELOW';
    else kpi_status = 'AT RISK';

    /* Efficiency score: composite of CPA, CTR, and ROI */
    if not missing(campaign_roi) then
        efficiency_score = (campaign_roi / 100) * 0.5
                         + (total_conversions / max(total_spend, 1)) * 0.3
                         + (attributed_revenue / max(total_spend, 1)) * 0.2;

    /* Flag top performers for increased investment */
    recommend_increase = (campaign_tier = 'PLATINUM' and kpi_status = 'EXCEEDS');

    format efficiency_score 6.3;
run;

/* End of marketing ROI analysis program */
