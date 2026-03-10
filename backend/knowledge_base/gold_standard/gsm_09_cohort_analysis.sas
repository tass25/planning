/*****************************************************************************
 * Program: gsm_09_cohort_analysis.sas
 * Purpose: Clinical cohort analysis for treatment outcome study
 * Author:  Biostatistics Team
 * Date:    2026-02-19
 * Description:
 *   Defines patient cohorts based on inclusion/exclusion criteria,
 *   constructs age-sex matched pairs, computes follow-up duration,
 *   and analyzes treatment outcomes with baseline characteristics.
 *****************************************************************************/

/* ------------------------------------------------------------------ */
/* Global settings and library references                             */
/* ------------------------------------------------------------------ */
options mprint mlogic nocenter ls=120 ps=60;

libname raw     'C:/data/clinical/raw' access=readonly;
libname staging 'C:/data/clinical/staging';
libname tgt     'C:/data/clinical/output';

/* ------------------------------------------------------------------ */
/* Step 1: Define cohort inclusion/exclusion criteria                  */
/*   - Include adults 18+ with diagnosis code in target range         */
/*   - Exclude patients with prior treatment or missing consent       */
/* ------------------------------------------------------------------ */
data staging.eligible_patients;
    set raw.patient_registry;

    /* Inclusion criteria */
    age_at_index = intck('year', date_of_birth, index_date);
    include_age = (age_at_index >= 18 and age_at_index <= 85);
    include_diagnosis = (primary_dx_code in ('E11.0','E11.1','E11.2',
                                             'E11.3','E11.4','E11.5'));
    include_enrollment = (enrollment_start <= index_date
                         and enrollment_end >= index_date + 365);

    /* Exclusion criteria */
    exclude_prior_tx = (prior_treatment_flag = 1);
    exclude_no_consent = (informed_consent ne 'Y');
    exclude_comorbidity = (charlson_index > 6);

    /* Apply all criteria */
    if include_age and include_diagnosis and include_enrollment
       and not exclude_prior_tx and not exclude_no_consent
       and not exclude_comorbidity;

    /* Assign treatment group based on treatment_arm variable */
    length cohort_group $10;
    if treatment_arm = 1 then cohort_group = 'TREATMENT';
    else if treatment_arm = 0 then cohort_group = 'CONTROL';
    else cohort_group = 'UNKNOWN';

    /* Age group for matching */
    length age_group $10;
    if age_at_index < 30 then age_group = '18-29';
    else if age_at_index < 45 then age_group = '30-44';
    else if age_at_index < 60 then age_group = '45-59';
    else if age_at_index < 75 then age_group = '60-74';
    else age_group = '75-85';

    format index_date enrollment_start enrollment_end date9.;
run;

/* ------------------------------------------------------------------ */
/* Step 2: Build matched cohort pairs using age-sex matching          */
/*   - Match each treatment patient with a control of same age/sex   */
/*   - Use 1:1 greedy matching via SQL                               */
/* ------------------------------------------------------------------ */
proc sql;
    /* Create matched pairs: treatment to control on age_group + gender */
    create table staging.matched_cohort as
    select
        t.patient_id as treatment_id,
        c.patient_id as control_id,
        t.age_group,
        t.gender,
        t.age_at_index as treatment_age,
        c.age_at_index as control_age,
        abs(t.age_at_index - c.age_at_index) as age_diff
    from staging.eligible_patients t
    inner join staging.eligible_patients c
        on t.age_group = c.age_group
        and t.gender = c.gender
        and t.cohort_group = 'TREATMENT'
        and c.cohort_group = 'CONTROL'
    group by t.patient_id
    having age_diff = min(age_diff)
    order by t.patient_id;

    /* Count matched vs unmatched */
    title 'Cohort Matching Summary';
    select cohort_group,
           count(*) as n_patients
    from staging.eligible_patients
    group by cohort_group;
quit;

/* ------------------------------------------------------------------ */
/* Step 3: Compute follow-up duration with RETAIN                     */
/*   - Track cumulative days at risk per patient                      */
/*   - Flag censoring events                                          */
/* ------------------------------------------------------------------ */
data staging.followup;
    set raw.patient_encounters;
    by patient_id encounter_date;

    retain days_at_risk 0 first_encounter_date;

    /* Reset at start of each patient */
    if first.patient_id then do;
        days_at_risk = 0;
        first_encounter_date = encounter_date;
    end;

    /* Accumulate days since previous encounter */
    if not first.patient_id then
        days_at_risk + intck('day', lag1(encounter_date), encounter_date);

    /* Total follow-up from first to current encounter */
    total_followup_days = intck('day', first_encounter_date, encounter_date);

    /* Censor at 365 days or study end date */
    study_end = '31DEC2025'd;
    if encounter_date > study_end then do;
        censored = 1;
        total_followup_days = intck('day', first_encounter_date, study_end);
    end;
    else censored = 0;

    /* Flag outcome event (primary endpoint) */
    outcome_event = (outcome_code in ('HOSP','ER','DEATH'));

    format first_encounter_date encounter_date study_end date9.;
run;

/* ------------------------------------------------------------------ */
/* Step 4: Outcome analysis using PROC FREQ                           */
/*   - Chi-square test for outcome events by treatment group          */
/* ------------------------------------------------------------------ */
proc freq data=staging.followup;
    where last.patient_id;
    tables cohort_group * outcome_event / chisq relrisk nocum;
    title 'Outcome Event Rates by Treatment Group';
run;

/* ------------------------------------------------------------------ */
/* Step 5: Baseline characteristics table                             */
/*   - Summarize demographics and clinical measures by cohort group   */
/* ------------------------------------------------------------------ */
proc means data=staging.eligible_patients n mean std median min max;
    class cohort_group;
    var age_at_index charlson_index baseline_hba1c baseline_bmi
        systolic_bp diastolic_bp;
    output out=tgt.baseline_characteristics
        mean(age_at_index)    = mean_age
        mean(charlson_index)  = mean_charlson
        mean(baseline_hba1c)  = mean_hba1c
        mean(baseline_bmi)    = mean_bmi
        std(age_at_index)     = sd_age
        std(baseline_hba1c)   = sd_hba1c
        n(age_at_index)       = n_patients;
    title 'Baseline Characteristics by Cohort';
run;

/* ------------------------------------------------------------------ */
/* Step 6: Compute hazard indicators                                  */
/*   - Create time-to-event dataset with hazard rate estimates        */
/* ------------------------------------------------------------------ */
data tgt.hazard_indicators;
    set staging.followup;
    by patient_id;

    /* Keep only the last record per patient */
    if last.patient_id;

    /* Compute hazard rate estimate (events / person-time) */
    person_years = total_followup_days / 365.25;
    if person_years > 0 then
        hazard_rate = outcome_event / person_years;
    else
        hazard_rate = .;

    /* Risk category based on follow-up and outcome */
    length risk_category $12;
    if outcome_event = 1 and total_followup_days <= 90 then
        risk_category = 'HIGH';
    else if outcome_event = 1 then
        risk_category = 'MODERATE';
    else if censored = 1 then
        risk_category = 'CENSORED';
    else
        risk_category = 'LOW';

    format hazard_rate 8.4 person_years 6.2;
run;

/* End of cohort analysis program */
