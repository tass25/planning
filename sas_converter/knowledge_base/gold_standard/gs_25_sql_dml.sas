/* gs_25 - PROC SQL with INSERT, UPDATE, DELETE */
PROC SQL;
    CREATE TABLE work.audit_log (
        log_id NUM,
        action CHAR(20),
        table_name CHAR(50),
        record_count NUM,
        run_date NUM FORMAT=DATETIME20.
    );

    INSERT INTO work.audit_log
    VALUES (1, 'LOAD', 'customer_master', 15234, %SYSFUNC(DATETIME()));

    UPDATE work.customer_master
    SET status = 'INACTIVE',
        update_date = TODAY()
    WHERE last_activity_date < INTNX('MONTH', TODAY(), -12);

    DELETE FROM work.temp_staging
    WHERE load_date < TODAY() - 30;

    SELECT action, table_name, record_count
    FROM work.audit_log
    ORDER BY run_date DESC;
QUIT;
