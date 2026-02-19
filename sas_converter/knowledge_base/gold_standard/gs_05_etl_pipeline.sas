/* gs_05 - Multiple DATA steps in ETL pipeline */
LIBNAME raw '/data/raw_feeds';
LIBNAME staging '/data/staging';

DATA staging.clean_claims;
    SET raw.insurance_claims;
    WHERE claim_date >= '01JAN2025'd;
    claim_amount = ABS(claim_amount);
    IF MISSING(policy_id) THEN DELETE;
    provider_code = UPCASE(STRIP(provider_code));
RUN;

DATA staging.categorized_claims;
    SET staging.clean_claims;
    LENGTH category $30;
    SELECT;
        WHEN (claim_amount > 50000) category = 'HIGH_VALUE';
        WHEN (claim_amount > 10000) category = 'MEDIUM_VALUE';
        OTHERWISE category = 'LOW_VALUE';
    END;
RUN;

DATA staging.enriched_claims;
    SET staging.categorized_claims;
    processing_date = TODAY();
    fiscal_quarter = QTR(claim_date);
    fiscal_year = YEAR(claim_date);
    FORMAT processing_date DATE9.;
RUN;
