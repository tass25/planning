/*============================================================================*/
/* Program:    gsm_04_inventory_analysis.sas                                  */
/* Purpose:    Warehouse inventory analysis including days-of-supply,         */
/*             safety stock, reorder points, and executive summary            */
/* Author:     Supply Chain Analytics                                         */
/* Date:       2026-02-19                                                     */
/*============================================================================*/

/* Global options */
options nocenter nodate compress=yes;

/* Library references for warehouse data */
libname wh '/data/warehouse/inventory' access=readonly;
libname staging '/data/warehouse/staging';
libname tgt '/data/warehouse/reports';

/*--------------------------------------------------------------------*/
/* Step 1: Compute days-of-supply and reorder points                  */
/*--------------------------------------------------------------------*/
data staging.inventory_metrics;
    set wh.current_stock;

    /* Calculate average daily demand over trailing 90 days */
    if trailing_90d_demand > 0 then
        avg_daily_demand = trailing_90d_demand / 90;
    else
        avg_daily_demand = 0;

    /* Days of supply: how many days current stock can cover */
    if avg_daily_demand > 0 then
        days_of_supply = qty_on_hand / avg_daily_demand;
    else
        days_of_supply = 999;

    /* Lead time in days from supplier */
    lead_time_days = coalesce(supplier_lead_time, 14);

    /* Reorder point = demand during lead time + safety buffer */
    reorder_point = (avg_daily_demand * lead_time_days) * 1.20;

    /* Determine reorder flag */
    if qty_on_hand <= reorder_point then reorder_flag = 'Y';
    else reorder_flag = 'N';

    /* Compute inventory value */
    inventory_value = qty_on_hand * unit_cost;

    format unit_cost inventory_value dollar12.2
           days_of_supply 8.1;
run;

/*--------------------------------------------------------------------*/
/* Step 2: Calculate safety stock statistics by category              */
/*--------------------------------------------------------------------*/
proc means data=staging.inventory_metrics noprint nway;
    class product_category warehouse_id;
    var avg_daily_demand days_of_supply qty_on_hand inventory_value;
    output out=staging.safety_stock_stats(drop=_type_ _freq_)
        mean(avg_daily_demand)    = avg_demand
        std(avg_daily_demand)     = std_demand
        mean(days_of_supply)      = avg_dos
        sum(inventory_value)      = total_inv_value
        sum(qty_on_hand)          = total_qty;
run;

/*--------------------------------------------------------------------*/
/* Step 3: Identify stockout risks and overstock conditions           */
/*--------------------------------------------------------------------*/
proc sql;
    create table staging.stock_alerts as
    select
        i.sku_id,
        i.product_name,
        i.product_category,
        i.warehouse_id,
        i.qty_on_hand,
        i.days_of_supply,
        i.reorder_point,
        i.inventory_value,
        s.avg_demand,
        s.std_demand,
        /* Classify stock status */
        case
            when i.days_of_supply < 7 then 'CRITICAL_LOW'
            when i.days_of_supply < 14 then 'LOW_STOCK'
            when i.days_of_supply > 120 then 'OVERSTOCK'
            when i.days_of_supply > 90 then 'EXCESS'
            else 'NORMAL'
        end as stock_status,
        /* Estimated stockout date */
        case
            when i.avg_daily_demand > 0
            then today() + int(i.qty_on_hand / i.avg_daily_demand)
            else .
        end as est_stockout_date format=date9.
    from staging.inventory_metrics i
    inner join staging.safety_stock_stats s
        on i.product_category = s.product_category
        and i.warehouse_id = s.warehouse_id
    order by i.days_of_supply;
quit;

/*--------------------------------------------------------------------*/
/* Step 4: Build running inventory balance with RETAIN                */
/*--------------------------------------------------------------------*/
proc sort data=wh.inventory_movements
          out=staging.movements_sorted;
    by warehouse_id sku_id txn_date;
run;

data staging.running_balance;
    set staging.movements_sorted;
    by warehouse_id sku_id;

    retain running_qty 0;

    /* Reset balance at start of each SKU within warehouse */
    if first.sku_id then running_qty = 0;

    /* Apply movement: positive for receipts, negative for issues */
    if movement_type = 'RECEIPT' then running_qty = running_qty + movement_qty;
    else if movement_type = 'ISSUE' then running_qty = running_qty - movement_qty;
    else if movement_type = 'ADJUSTMENT' then running_qty = running_qty + movement_qty;

    /* Flag negative balance as data quality issue */
    if running_qty < 0 then negative_balance_flag = 'Y';
    else negative_balance_flag = 'N';

    format txn_date date9.;
run;

/*--------------------------------------------------------------------*/
/* Step 5: Prepare visualization dataset for trend charts             */
/*--------------------------------------------------------------------*/
data staging.viz_inventory_trend;
    set staging.running_balance;

    /* Derive time dimensions for charting */
    txn_month = intnx('month', txn_date, 0, 'beginning');
    txn_week  = intnx('week', txn_date, 0, 'beginning');

    /* Label for chart axis */
    length period_label $10;
    period_label = put(txn_month, monyy7.);

    format txn_month txn_week date9.;

    keep warehouse_id sku_id txn_date txn_month txn_week
         period_label running_qty movement_type;
run;

/*--------------------------------------------------------------------*/
/* Step 6: Executive summary report                                   */
/*--------------------------------------------------------------------*/
title1 'Inventory Analysis Executive Summary';
title2 'Stock Status and Reorder Recommendations';

proc report data=staging.stock_alerts nowd;
    where stock_status in ('CRITICAL_LOW', 'LOW_STOCK', 'OVERSTOCK');

    column warehouse_id product_category stock_status
           sku_id product_name qty_on_hand days_of_supply
           inventory_value;

    define warehouse_id / group 'Warehouse';
    define product_category / group 'Category';
    define stock_status / group 'Status';
    define sku_id / display 'SKU';
    define product_name / display 'Product';
    define qty_on_hand / analysis sum format=comma10. 'Qty On Hand';
    define days_of_supply / analysis mean format=8.1 'Avg DOS';
    define inventory_value / analysis sum format=dollar12.2 'Inv Value';

    break after warehouse_id / summarize suppress;
run;

title;
