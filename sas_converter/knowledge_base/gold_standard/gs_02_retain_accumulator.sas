/* gs_02 - DATA step with RETAIN and accumulator logic */
DATA work.running_totals;
    SET work.sales_data;
    BY region;
    RETAIN cumulative_sales 0;
    IF FIRST.region THEN cumulative_sales = 0;
    cumulative_sales + sales_amount;
    pct_of_target = cumulative_sales / target_amount * 100;
    FORMAT cumulative_sales DOLLAR12.2 pct_of_target 6.1;
RUN;

DATA work.flagged_accounts;
    SET work.running_totals;
    LENGTH flag $20;
    IF pct_of_target >= 100 THEN flag = 'TARGET_MET';
    ELSE IF pct_of_target >= 75 THEN flag = 'ON_TRACK';
    ELSE flag = 'AT_RISK';
RUN;
