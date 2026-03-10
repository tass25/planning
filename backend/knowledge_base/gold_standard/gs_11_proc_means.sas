/* gs_11 - PROC MEANS with CLASS and OUTPUT */
TITLE 'Descriptive Statistics by Department';

PROC MEANS DATA=work.employee_perf N MEAN STD MIN MAX MAXDEC=2;
    CLASS department;
    VAR salary performance_score years_experience;
    OUTPUT OUT=work.dept_stats
        MEAN=avg_salary avg_perf avg_exp
        STD=std_salary std_perf std_exp;
RUN;

TITLE;
