/* ==========================================================================
   Target: ~150 Lines of mixed Data Steps, Procedures, Macros, and Globals
   ========================================================================== */

/* 1. GLOBAL CONFIGURATION & ENVIRONMENT SETUP */
%LET env = PRODUCTION;
%LET process_date = %SYSFUNC(today(), date9.);
%LET threshold = 5000;

OPTIONS NODATE NONUMBER MPRINT;

LIBNAME raw_src "/data/raw/source_systems";
LIBNAME staging "/data/staging/temp_storage";
LIBNAME final   "/data/production/final_tables";

FILENAME log_out "/logs/migration_audit.txt";

/* 2. MACRO DEFINITION BLOCK: DATA CLEANING ENGINE */
%MACRO preprocess_finance_data(in_ds, out_ds);
    /* Identify and partition boundary: Start of nested DATA step */
    DATA &out_ds (DROP=err_code);
        SET &in_ds;
        
        /* String manipulation to test regex complexity */
        customer_name = UPCASE(STRIP(name));
        account_id = COMPRESS(account_id, '-');
        
        /* Logic check for conditional boundaries */
        IF balance < 0 THEN DO;
            status = 'OVERDRAWN';
            flag = 1;
        END;
        ELSE IF balance = 0 THEN status = 'EMPTY';
        ELSE status = 'ACTIVE';
        
        /* Date arithmetic */
        days_since_active = today() - last_transaction_dt;
        
        IF days_since_active > 365 THEN account_type = 'DORMANT';
        ELSE account_type = 'CURRENT';
        
        LABEL status = "Account Status Indicator"
              account_type = "Activity Classification";
    RUN; /* End of partitioned DATA block */

    PROC SORT DATA=&out_ds;
        BY account_id descending days_since_active;
    RUN;
%MEND preprocess_finance_data;

/* 3. PROCEDURE SQL BLOCK: COMPLEX JOIN & QUIT BOUNDARY */
/* This tests if the partitioner correctly identifies QUIT instead of RUN */
PROC SQL;
    CREATE TABLE staging.joined_master AS
    SELECT 
        a.account_id,
        a.status,
        b.region,
        b.manager_id,
        SUM(a.balance) AS total_balance
    FROM staging.cleaned_accounts AS a
    LEFT JOIN raw_src.region_map AS b
    ON a.region_code = b.code
    WHERE a.balance > &threshold
    GROUP BY 1, 2, 3, 4
    ORDER BY total_balance DESC;
QUIT;

/* 4. DATA STEP WITH IN-LINE DATALINES */
/* Tests if the partitioner handles internal data blocks correctly */
DATA work.manual_adjustments;
    INPUT Account_ID $ Adjustment_Amt Type $;
    DATALINES;
    ACC100 250.00 REBATE
    ACC205 -50.25 FEE
    ACC309 1000.00 BONUS
    ACC412 -15.00 CHARGE
    ;
RUN;

/* 5. ANALYTICAL PROCEDURE BLOCK: PROC MEANS */
PROC MEANS DATA=staging.joined_master N MEAN STD MIN MAX;
    CLASS region status;
    VAR total_balance;
    OUTPUT OUT=work.summary_stats
        MEAN=avg_balance
        SUM=total_regional_val;
RUN;

/* 6. MACRO CALLS & ITERATIVE LOGIC */
%preprocess_finance_data(raw_src.daily_ledger, staging.cleaned_accounts);

/* 7. FORMAT DEFINITIONS */
PROC FORMAT;
    VALUE $grade
        'OVERDRAWN' = 'Red'
        'ACTIVE'    = 'Green'
        'DORMANT'   = 'Yellow'
        OTHER       = 'Gray';
RUN;

/* 8. PROCEDURE REG: STATISTICAL MODELING */
/* Testing for scientific/modeling stack conversion (Statsmodels/Scikit-learn) */
PROC REG DATA=staging.joined_master;
    MODEL total_balance = region_code manager_id / SELECTION=STEPWISE;
    TITLE "Predictive Model for Account Value";
RUN;


/* 9. DATA STEP WITH MULTIPLE SET STATEMENTS */
DATA final.monthly_report;
    MERGE staging.joined_master (IN=a)
          work.manual_adjustments (IN=b);
    BY Account_ID;
    
    IF a; /* Preserve primary records */
    
    IF b THEN total_balance = total_balance + Adjustment_Amt;
    
    MONTH = "%SUBSTR(&process_date, 3, 3)";
    YEAR  = "%SUBSTR(&process_date, 6, 4)";
    
    FORMAT status $grade.;
RUN;

/* 10. FINAL EXPORT AND CLEANUP */
PROC EXPORT DATA=final.monthly_report
    OUTFILE="/output/migration_validation_&process_date..csv"
    DBMS=CSV REPLACE;
RUN;

%LET cleanup_flag = 1;
DATA _NULL_;
    IF &cleanup_flag = 1 THEN DO;
        PUT "MIGRATION PARTITIONING TEST COMPLETE: %SYSFUNC(datetime(), datetime20.)";
    END;
RUN;

/* 11. REPEATED PATTERNS TO FILL VOLUME */
/* Additional steps to ensure file length for stress testing */

PROC FREQ DATA=final.monthly_report;
    TABLES region * status / NOCOL NOPERCENT;
RUN;

PROC PRINT DATA=work.summary_stats (OBS=10);
    TITLE "Top 10 Summary Statistics Preview";
RUN;

/* End of Partitioning Test Script */