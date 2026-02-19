/* gs_23 - PROC SQL with subqueries and CASE */
PROC SQL;
    CREATE TABLE work.employee_ranking AS
    SELECT e.employee_id,
           e.employee_name,
           e.department,
           e.salary,
           d.avg_dept_salary,
           CASE
               WHEN e.salary > d.avg_dept_salary * 1.2 THEN 'ABOVE_AVERAGE'
               WHEN e.salary < d.avg_dept_salary * 0.8 THEN 'BELOW_AVERAGE'
               ELSE 'AVERAGE'
           END AS salary_band,
           e.salary - d.avg_dept_salary AS salary_diff FORMAT=DOLLAR10.2
    FROM work.employees AS e
    INNER JOIN (
        SELECT department, MEAN(salary) AS avg_dept_salary
        FROM work.employees
        GROUP BY department
    ) AS d ON e.department = d.department
    ORDER BY e.department, e.salary DESC;

    SELECT department,
           COUNT(*) AS employee_count,
           MEAN(salary) AS avg_salary FORMAT=DOLLAR12.2
    FROM work.employees
    GROUP BY department;
QUIT;
