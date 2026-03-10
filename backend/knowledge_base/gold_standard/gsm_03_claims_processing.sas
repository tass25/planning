/*============================================================================*/
/* Program:    gsm_03_claims_processing.sas                                   */
/* Purpose:    Insurance claims intake processing including validation,       */
/*             deduplication, provider enrichment, and reserving              */
/* Author:     Claims Analytics Unit                                          */
/* Date:       2026-02-19                                                     */
/*============================================================================*/

/* Processing options */
options nocenter nodate compress=yes msglevel=i;

/* Source and target library definitions */
libname raw '/data/claims/intake' access=readonly;
libname staging '/data/claims/staging';
libname provider '/data/reference/providers' access=readonly;
libname tgt '/data/claims/processed';

/*--------------------------------------------------------------------*/
/* Step 1: Validate incoming claims - apply business rules            */
/*--------------------------------------------------------------------*/
data staging.claims_validated
     staging.claims_rejected(keep=claim_id reject_reason submit_date);
    set raw.claims_intake;

    length reject_reason $100 claim_category $20;
    reject_flag = 0;
    reject_reason = '';

    /* Rule 1: Claim ID must be present */
    if missing(claim_id) then do;
        reject_reason = 'Missing claim ID';
        reject_flag = 1;
    end;

    /* Rule 2: Policy must be active at time of service */
    if policy_end_date < service_date then do;
        reject_reason = catx(' | ', reject_reason, 'Policy expired before service');
        reject_flag = 1;
    end;

    /* Rule 3: Claim amount must be positive and within limits */
    if claim_amount <= 0 then do;
        reject_reason = catx(' | ', reject_reason, 'Non-positive claim amount');
        reject_flag = 1;
    end;
    if claim_amount > 1000000 then do;
        reject_reason = catx(' | ', reject_reason, 'Amount exceeds $1M threshold');
        reject_flag = 1;
    end;

    /* Rule 4: Service date cannot be in the future */
    if service_date > today() then do;
        reject_reason = catx(' | ', reject_reason, 'Future service date');
        reject_flag = 1;
    end;

    /* Rule 5: Provider NPI must be 10 digits */
    if length(strip(provider_npi)) ne 10 then do;
        reject_reason = catx(' | ', reject_reason, 'Invalid provider NPI length');
        reject_flag = 1;
    end;

    /* Categorize claim by type */
    if claim_type in ('INPATIENT', 'IP') then claim_category = 'INPATIENT';
    else if claim_type in ('OUTPATIENT', 'OP') then claim_category = 'OUTPATIENT';
    else if claim_type in ('PHARMACY', 'RX') then claim_category = 'PHARMACY';
    else if claim_type in ('DENTAL', 'DN') then claim_category = 'DENTAL';
    else claim_category = 'OTHER';

    /* Route to appropriate output */
    if reject_flag = 1 then output staging.claims_rejected;
    else output staging.claims_validated;

    format service_date policy_end_date submit_date date9.
           claim_amount dollar12.2;
run;

/*--------------------------------------------------------------------*/
/* Step 2: Sort and deduplicate validated claims (FIRST. logic)       */
/*--------------------------------------------------------------------*/
proc sort data=staging.claims_validated;
    by claim_id descending submit_date;
run;

data staging.claims_deduped;
    set staging.claims_validated;
    by claim_id;

    /* Keep only the most recent submission per claim */
    if first.claim_id;

    /* Calculate days from service to submission */
    days_to_submit = submit_date - service_date;

    /* Flag late submissions (> 90 days) */
    if days_to_submit > 90 then late_submit_flag = 'Y';
    else late_submit_flag = 'N';
run;

/*--------------------------------------------------------------------*/
/* Step 3: Enrich claims with provider master data                    */
/*--------------------------------------------------------------------*/
proc sql;
    create table staging.claims_enriched as
    select
        c.claim_id,
        c.policy_id,
        c.member_id,
        c.service_date,
        c.claim_amount,
        c.claim_category,
        c.days_to_submit,
        c.late_submit_flag,
        p.provider_name,
        p.provider_specialty,
        p.network_status,
        p.state_code as provider_state,
        /* Apply in-network vs out-of-network discount */
        case
            when p.network_status = 'IN_NETWORK'
            then c.claim_amount * 0.80
            when p.network_status = 'OUT_OF_NETWORK'
            then c.claim_amount * 0.60
            else c.claim_amount
        end as allowed_amount
    from staging.claims_deduped c
    left join provider.provider_master p
        on c.provider_npi = p.provider_npi
    order by c.claim_id;
quit;

/*--------------------------------------------------------------------*/
/* Step 4: Compute reserve amounts based on claim characteristics     */
/*--------------------------------------------------------------------*/
data tgt.claims_reserved;
    set staging.claims_enriched;

    length reserve_category $15;

    /* Base reserve is allowed amount */
    reserve_amount = allowed_amount;

    /* Adjust reserves based on claim category */
    if claim_category = 'INPATIENT' then do;
        reserve_factor = 1.25;
        reserve_category = 'HIGH';
    end;
    else if claim_category = 'OUTPATIENT' then do;
        reserve_factor = 1.10;
        reserve_category = 'STANDARD';
    end;
    else if claim_category = 'PHARMACY' then do;
        reserve_factor = 1.05;
        reserve_category = 'LOW';
    end;
    else do;
        reserve_factor = 1.15;
        reserve_category = 'STANDARD';
    end;

    /* Apply reserve factor */
    reserve_amount = reserve_amount * reserve_factor;

    /* Additional IBNR adjustment for late submissions */
    if late_submit_flag = 'Y' then
        reserve_amount = reserve_amount * 1.10;

    format claim_amount allowed_amount reserve_amount dollar12.2
           service_date date9.;
run;

/*--------------------------------------------------------------------*/
/* Step 5: Print exception report for rejected claims                 */
/*--------------------------------------------------------------------*/
title1 'Claims Processing Exception Report';
title2 'Rejected Claims Summary';

proc print data=staging.claims_rejected noobs label;
    var claim_id submit_date reject_reason;
    label claim_id      = 'Claim ID'
          submit_date   = 'Submit Date'
          reject_reason = 'Rejection Reason(s)';
run;

title;
