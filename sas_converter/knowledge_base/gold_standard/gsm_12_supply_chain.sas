/******************************************************************************
 * Program: gsm_12_supply_chain.sas
 * Purpose: Supply chain analytics - lead time analysis, supplier performance,
 *          backorder tracking, safety stock computation and ABC classification
 * Author:  Supply Chain Analytics Team
 * Date:    2026-02-19
 ******************************************************************************/

/* --- Library references for supply chain data --- */
libname raw     '/data/supplychain/raw';
libname staging '/data/supplychain/staging';
libname tgt     '/data/supplychain/target';

options mprint nocenter;

/* -----------------------------------------------------------------------
   STEP 1: Compute lead times and delivery reliability per supplier
   ----------------------------------------------------------------------- */
data staging.delivery_metrics;
    set raw.purchase_orders;
    where order_status = 'DELIVERED';

    /* Actual lead time in calendar days */
    lead_time_days = delivery_date - order_date;

    /* Promised vs actual delivery variance */
    delivery_variance = delivery_date - promised_date;

    /* On-time flag: delivered on or before promised date */
    if delivery_variance <= 0 then on_time = 1;
    else on_time = 0;

    /* Quality acceptance flag */
    if qty_accepted >= qty_ordered * 0.95 then quality_pass = 1;
    else quality_pass = 0;

    format delivery_date order_date promised_date date9.;
run;

/* -----------------------------------------------------------------------
   STEP 2: Aggregate supplier performance metrics
   ----------------------------------------------------------------------- */
proc sql;
    create table staging.supplier_scorecard as
    select s.supplier_id,
           s.supplier_name,
           s.supplier_region,
           count(*) as total_orders,
           avg(d.lead_time_days) as avg_lead_time,
           std(d.lead_time_days) as std_lead_time,
           sum(d.on_time) / count(*) as otd_rate format=percent8.1,
           sum(d.quality_pass) / count(*) as quality_rate format=percent8.1,
           sum(d.qty_accepted * d.unit_cost) as total_spend format=dollar12.2
    from staging.delivery_metrics as d
    inner join raw.suppliers as s
        on d.supplier_id = s.supplier_id
    group by s.supplier_id, s.supplier_name, s.supplier_region
    having count(*) >= 5;
quit;

/* -----------------------------------------------------------------------
   STEP 3: Track backorder accumulation using RETAIN
   ----------------------------------------------------------------------- */
proc sort data=raw.inventory_transactions out=work.inv_sorted;
    by product_id transaction_date;
run;

data staging.backorder_tracking;
    set work.inv_sorted;
    by product_id;
    retain running_backorder 0;

    /* Reset accumulator at start of each product */
    if first.product_id then running_backorder = 0;

    /* Accumulate backorders: positive = demand, negative = receipt */
    if transaction_type = 'DEMAND' then
        running_backorder = running_backorder + quantity;
    else if transaction_type = 'RECEIPT' then
        running_backorder = max(0, running_backorder - quantity);

    /* Flag critical backorder levels */
    if running_backorder > reorder_point then
        backorder_alert = 'CRITICAL';
    else if running_backorder > 0 then
        backorder_alert = 'WARNING';
    else
        backorder_alert = 'OK';
run;

/* -----------------------------------------------------------------------
   STEP 4: Safety stock computation using demand variability
   ----------------------------------------------------------------------- */
proc means data=raw.daily_demand
           mean std noprint;
    by product_id;
    var daily_qty;
    output out=staging.demand_stats
        mean=avg_daily_demand
        std=std_daily_demand;
run;

/* -----------------------------------------------------------------------
   STEP 5: ABC classification across product categories using arrays
   ----------------------------------------------------------------------- */
data tgt.product_classification;
    set staging.demand_stats;

    /* Service level z-score (95% = 1.645) */
    z_score = 1.645;
    avg_lead_time = 14;
    std_lead_time = 3;

    /* Safety stock formula */
    safety_stock = z_score * sqrt(
        (avg_lead_time * std_daily_demand**2) +
        (avg_daily_demand**2 * std_lead_time**2)
    );

    reorder_point = (avg_daily_demand * avg_lead_time) + safety_stock;

    /* ABC classification thresholds by category */
    array rev_pct{3} _temporary_ (0.80 0.95 1.00);
    array abc_label{3} $1 _temporary_ ('A' 'B' 'C');

    /* Assign ABC class based on cumulative revenue percentage */
    length abc_class $1;
    if cumulative_rev_pct <= rev_pct{1} then abc_class = abc_label{1};
    else if cumulative_rev_pct <= rev_pct{2} then abc_class = abc_label{2};
    else abc_class = abc_label{3};

    /* Set review frequency based on ABC class */
    array review_days{3} _temporary_ (7 14 30);
    if abc_class = 'A' then review_cycle = review_days{1};
    else if abc_class = 'B' then review_cycle = review_days{2};
    else review_cycle = review_days{3};

    format safety_stock reorder_point comma10.;
    drop z_score avg_lead_time std_lead_time;
run;

/* -----------------------------------------------------------------------
   STEP 6: Generate exception report for critical items
   ----------------------------------------------------------------------- */
proc sort data=tgt.product_classification
          out=work.exceptions;
    by abc_class descending safety_stock;
    where abc_class = 'A' and safety_stock > 1000;
run;

title 'Supply Chain Exception Report - High Safety Stock A-Items';
proc print data=work.exceptions noobs label;
    var product_id abc_class avg_daily_demand safety_stock reorder_point review_cycle;
    label product_id       = 'Product'
          abc_class        = 'ABC Class'
          avg_daily_demand = 'Avg Daily Demand'
          safety_stock     = 'Safety Stock'
          reorder_point    = 'Reorder Point'
          review_cycle     = 'Review (Days)';
run;
title;
