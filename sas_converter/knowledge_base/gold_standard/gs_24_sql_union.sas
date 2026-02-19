/* gs_24 - PROC SQL with UNION and set operations */
PROC SQL;
    CREATE TABLE work.all_contacts AS
    SELECT customer_id AS contact_id,
           customer_name AS name,
           email,
           'CUSTOMER' AS contact_type
    FROM work.customers
    WHERE active_flag = 1

    UNION ALL

    SELECT vendor_id AS contact_id,
           vendor_name AS name,
           vendor_email AS email,
           'VENDOR' AS contact_type
    FROM work.vendors
    WHERE status = 'ACTIVE'

    UNION ALL

    SELECT employee_id AS contact_id,
           employee_name AS name,
           work_email AS email,
           'EMPLOYEE' AS contact_type
    FROM work.employees
    WHERE termination_date IS NULL

    ORDER BY contact_type, name;
QUIT;
