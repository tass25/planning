/* gs_19 - PROC SUMMARY with multiple output stats */
PROC SUMMARY DATA=work.transactions NWAY;
    CLASS customer_segment product_category;
    VAR transaction_amount quantity discount_pct;
    OUTPUT OUT=work.segment_summary (DROP=_TYPE_ _FREQ_)
        SUM(transaction_amount) = total_revenue
        MEAN(transaction_amount) = avg_order_value
        SUM(quantity) = total_units
        MEAN(discount_pct) = avg_discount
        N(transaction_amount) = order_count;
RUN;

DATA work.segment_kpis;
    SET work.segment_summary;
    revenue_per_unit = total_revenue / total_units;
    IF avg_discount > 0.15 THEN discount_flag = 'HIGH';
    ELSE discount_flag = 'NORMAL';
RUN;
