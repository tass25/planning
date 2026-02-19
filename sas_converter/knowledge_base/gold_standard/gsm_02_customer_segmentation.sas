/*============================================================================*/
/* Program:    gsm_02_customer_segmentation.sas                               */
/* Purpose:    Customer RFM segmentation for marketing analytics              */
/*             Computes Recency, Frequency, Monetary scores and segments      */
/* Author:     Marketing Analytics Team                                       */
/* Date:       2026-02-19                                                     */
/*============================================================================*/

/* Global options */
options nocenter nodate mprint;

/* Library references */
libname raw '/data/crm/raw' access=readonly;
libname staging '/data/crm/staging';
libname tgt '/data/crm/analytics';

/*--------------------------------------------------------------------*/
/* Step 1: Compute RFM base metrics from transaction history          */
/*--------------------------------------------------------------------*/
data staging.rfm_base;
    set raw.customer_transactions
        (where=(order_date >= '01JAN2024'd));

    /* Keep only completed orders */
    if order_status = 'COMPLETE';

    /* Calculate days since last purchase (recency) */
    recency_days = today() - order_date;

    /* Revenue after returns and discounts */
    net_revenue = (quantity * unit_price) - discount_amount;
    if net_revenue < 0 then net_revenue = 0;

    format order_date date9. net_revenue dollar12.2;

    keep customer_id order_id order_date recency_days
         net_revenue quantity product_category;
run;

/* Sort for aggregation */
proc sort data=staging.rfm_base;
    by customer_id;
run;

/*--------------------------------------------------------------------*/
/* Step 2: Aggregate RFM metrics per customer                         */
/*--------------------------------------------------------------------*/
proc sql;
    create table staging.rfm_metrics as
    select
        customer_id,
        min(recency_days) as recency,
        count(distinct order_id) as frequency,
        sum(net_revenue) as monetary,
        mean(net_revenue) as avg_order_value,
        max(order_date) as last_order_date format=date9.,
        count(distinct product_category) as category_breadth
    from staging.rfm_base
    group by customer_id
    having frequency >= 1;
quit;

/*--------------------------------------------------------------------*/
/* Step 3: Assign RFM quintile ranks using PROC RANK                  */
/*--------------------------------------------------------------------*/
proc rank data=staging.rfm_metrics
          out=staging.rfm_ranked groups=5;
    var recency frequency monetary;
    ranks r_rank f_rank m_rank;
run;

/* Invert recency rank: lower recency = better (more recent) */
data staging.rfm_scored;
    set staging.rfm_ranked;

    /* Recency: 0=most recent quintile, 4=oldest - invert to 1-5 */
    r_score = 5 - r_rank;

    /* Frequency and Monetary: higher is better, shift to 1-5 */
    f_score = f_rank + 1;
    m_score = m_rank + 1;

    /* Composite RFM score (weighted) */
    rfm_composite = (r_score * 0.35) + (f_score * 0.35) + (m_score * 0.30);

    /* Create RFM cell code (e.g., "5-4-3") */
    length rfm_cell $10;
    rfm_cell = catx('-', r_score, f_score, m_score);
run;

/*--------------------------------------------------------------------*/
/* Step 4: Assign customer segment labels based on RFM scores         */
/*--------------------------------------------------------------------*/
data tgt.customer_segments;
    set staging.rfm_scored;

    length segment_name $30 segment_code $5;

    /* Classify customers into business segments */
    select;
        when (r_score >= 4 and f_score >= 4 and m_score >= 4) do;
            segment_name = 'Champions';
            segment_code = 'CHAMP';
        end;
        when (r_score >= 4 and f_score >= 3) do;
            segment_name = 'Loyal Customers';
            segment_code = 'LOYAL';
        end;
        when (r_score >= 4 and f_score <= 2) do;
            segment_name = 'New Customers';
            segment_code = 'NEW';
        end;
        when (r_score >= 3 and m_score >= 3) do;
            segment_name = 'Potential Loyalists';
            segment_code = 'POTLYL';
        end;
        when (r_score <= 2 and f_score >= 3) do;
            segment_name = 'At Risk';
            segment_code = 'ATRSK';
        end;
        when (r_score <= 2 and f_score <= 2 and m_score <= 2) do;
            segment_name = 'Hibernating';
            segment_code = 'HIBER';
        end;
        otherwise do;
            segment_name = 'Need Attention';
            segment_code = 'NTATN';
        end;
    end;

    format monetary avg_order_value dollar12.2
           rfm_composite 5.2;
run;

/*--------------------------------------------------------------------*/
/* Step 5: Summarize segment distribution                             */
/*--------------------------------------------------------------------*/
title 'Customer Segment Distribution';

proc freq data=tgt.customer_segments;
    tables segment_name / nocum out=staging.segment_dist;
run;

/*--------------------------------------------------------------------*/
/* Step 6: Profile each segment with descriptive statistics           */
/*--------------------------------------------------------------------*/
proc means data=tgt.customer_segments n mean median std min max;
    class segment_name;
    var recency frequency monetary avg_order_value
        category_breadth rfm_composite;
    output out=tgt.segment_profiles(drop=_type_ _freq_)
        mean(recency) = avg_recency
        mean(frequency) = avg_frequency
        mean(monetary) = avg_monetary
        mean(rfm_composite) = avg_rfm_score;
run;

title;
