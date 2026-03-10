/*============================================================================*/
/* Program:    gsm_05_employee_report.sas                                     */
/* Purpose:    Employee compensation and tenure analysis with formatted       */
/*             HTML report output for HR leadership                           */
/* Author:     HR Analytics Team                                              */
/* Date:       2026-02-19                                                     */
/*============================================================================*/

/* Processing options */
options nocenter nodate pageno=1 fmtsearch=(work);

/* Library references */
libname hr '/data/hr/master' access=readonly;
libname staging '/data/hr/staging';
libname tgt '/data/hr/reports';

/* Report titles */
title1 'Human Resources Workforce Analysis';
title2 'Compensation and Tenure Report';
title3 "Report Date: &sysdate9";

/*--------------------------------------------------------------------*/
/* Step 1: Compute employee tenure and age metrics                    */
/*--------------------------------------------------------------------*/
data staging.employee_derived;
    set hr.employee_master
        (where=(employment_status = 'ACTIVE'));

    /* Calculate current age in years */
    age_years = intck('year', date_of_birth, today());

    /* Adjust if birthday hasn't occurred yet this year */
    if intnx('year', date_of_birth, age_years, 'sameday') > today() then
        age_years = age_years - 1;

    /* Calculate tenure in complete years */
    tenure_years = intck('year', hire_date, today());

    /* Tenure in months for finer granularity */
    tenure_months = intck('month', hire_date, today());

    /* Years until retirement (assuming age 65) */
    retirement_date = intnx('year', date_of_birth, 65, 'sameday');
    years_to_retire = intck('year', today(), retirement_date);
    if years_to_retire < 0 then years_to_retire = 0;

    /* Compute midpoint ratio (salary vs grade midpoint) */
    if grade_midpoint > 0 then
        compa_ratio = annual_salary / grade_midpoint;
    else
        compa_ratio = .;

    format hire_date date_of_birth retirement_date date9.
           annual_salary grade_midpoint dollar12.2
           compa_ratio 6.3;
run;

/*--------------------------------------------------------------------*/
/* Step 2: Define custom formats for reporting                        */
/*--------------------------------------------------------------------*/
proc format;
    /* Salary band format */
    value sal_band
        low   -< 40000   = 'Under $40K'
        40000 -< 60000   = '$40K-$60K'
        60000 -< 80000   = '$60K-$80K'
        80000 -< 100000  = '$80K-$100K'
        100000-< 150000  = '$100K-$150K'
        150000- high      = '$150K+';

    /* Tenure group format */
    value tenure_grp
        low -< 1   = 'Less than 1 yr'
        1   -< 3   = '1-2 years'
        3   -< 5   = '3-4 years'
        5   -< 10  = '5-9 years'
        10  -< 20  = '10-19 years'
        20  - high = '20+ years';

    /* Age bracket format */
    value age_bracket
        low -< 25  = 'Under 25'
        25  -< 35  = '25-34'
        35  -< 45  = '35-44'
        45  -< 55  = '45-54'
        55  - high = '55+';
run;

/*--------------------------------------------------------------------*/
/* Step 3: Join employees with department and manager details         */
/*--------------------------------------------------------------------*/
proc sql;
    create table tgt.employee_detail as
    select
        e.employee_id,
        e.first_name,
        e.last_name,
        e.age_years,
        e.tenure_years,
        e.annual_salary,
        e.compa_ratio,
        e.years_to_retire,
        e.job_grade,
        d.department_name,
        d.division_name,
        d.cost_center,
        m.first_name as mgr_first_name,
        m.last_name as mgr_last_name
    from staging.employee_derived e
    left join hr.department_master d
        on e.department_id = d.department_id
    left join hr.employee_master m
        on e.manager_id = m.employee_id
    order by d.department_name, e.last_name;
quit;

/*--------------------------------------------------------------------*/
/* Step 4: Cross-tabulation by department and job grade               */
/*--------------------------------------------------------------------*/
proc tabulate data=tgt.employee_detail format=comma10.;
    class department_name job_grade;
    var annual_salary tenure_years;

    table department_name='Department' all='Total',
          job_grade='Grade' * (annual_salary='Salary' * (n mean)
                               tenure_years='Tenure' * mean)
          all='All Grades' * (annual_salary='Salary' * (n mean)
                              tenure_years='Tenure' * mean);
run;

/*--------------------------------------------------------------------*/
/* Step 5: Compensation analysis by department                        */
/*--------------------------------------------------------------------*/
proc means data=tgt.employee_detail n mean median std min max;
    class department_name;
    var annual_salary compa_ratio tenure_years years_to_retire;
    output out=tgt.comp_summary(drop=_type_ _freq_)
        mean(annual_salary) = avg_salary
        median(annual_salary) = med_salary
        mean(compa_ratio) = avg_compa_ratio
        mean(tenure_years) = avg_tenure
        n(employee_id) = headcount;
run;

/*--------------------------------------------------------------------*/
/* Step 6: Generate HTML report output                                */
/*--------------------------------------------------------------------*/
ods html file='/reports/hr/workforce_analysis.html'
         style=seaside;

proc print data=tgt.comp_summary noobs label;
    var department_name headcount avg_salary med_salary
        avg_compa_ratio avg_tenure;
    label department_name = 'Department'
          headcount       = 'Headcount'
          avg_salary      = 'Avg Salary'
          med_salary      = 'Median Salary'
          avg_compa_ratio = 'Avg Compa-Ratio'
          avg_tenure      = 'Avg Tenure (Yrs)';
    format avg_salary med_salary dollar12.2
           avg_compa_ratio 6.3
           avg_tenure 5.1;
run;

ods html close;

title;
