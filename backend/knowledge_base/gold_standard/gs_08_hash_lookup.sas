/* gs_08 - DATA step with hash object lookup */
DATA work.enriched_sales;
    LENGTH region_name $40 manager $30;
    IF _N_ = 1 THEN DO;
        DECLARE HASH h(dataset: 'work.region_lookup');
        h.DEFINEKEY('region_code');
        h.DEFINEDATA('region_name', 'manager');
        h.DEFINEDONE();
    END;

    SET work.daily_sales;
    rc = h.FIND();
    IF rc NE 0 THEN DO;
        region_name = 'UNKNOWN';
        manager = 'UNASSIGNED';
    END;
    DROP rc;
RUN;
