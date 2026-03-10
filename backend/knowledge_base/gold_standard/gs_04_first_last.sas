/* gs_04 - DATA step with FIRST/LAST processing */
PROC SORT DATA=work.transactions;
    BY account_id transaction_date;
RUN;

DATA work.account_summary;
    SET work.transactions;
    BY account_id;
    RETAIN first_trans_date last_trans_date total_amount trans_count;

    IF FIRST.account_id THEN DO;
        first_trans_date = transaction_date;
        total_amount = 0;
        trans_count = 0;
    END;

    total_amount + amount;
    trans_count + 1;

    IF LAST.account_id THEN DO;
        last_trans_date = transaction_date;
        avg_amount = total_amount / trans_count;
        tenure_days = last_trans_date - first_trans_date;
        OUTPUT;
    END;

    FORMAT first_trans_date last_trans_date DATE9.
           total_amount avg_amount DOLLAR12.2;
RUN;
