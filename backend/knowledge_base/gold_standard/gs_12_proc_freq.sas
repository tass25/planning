/* gs_12 - PROC FREQ with multiple tables */
PROC FREQ DATA=work.patient_visits;
    TABLES gender * diagnosis / NOROW NOCOL NOPERCENT;
    TABLES visit_type / OUT=work.visit_counts;
    TABLES insurance_type * visit_type / CHISQ EXPECTED;
    WHERE visit_date >= '01JAN2025'd;
RUN;
