/*****************************************************************************
 * Program:     gsm_19_longitudinal.sas
 * Purpose:     Longitudinal panel analysis across multiple survey waves
 * Author:      Survey Analytics Team
 * Created:     2026-02-19
 * Environment: SAS 9.4M5+
 * Description: Processes multiple survey waves using parameterized macros.
 *              Computes wave-level statistics, builds cross-wave panel,
 *              and calculates longitudinal change metrics using LAG.
 *****************************************************************************/

/* ------------------------------------------------------------------ */
/* SECTION 1: Environment Setup                                        */
/* ------------------------------------------------------------------ */

/* Panel survey data library */
libname raw '/data/survey/raw' access=readonly;

/* Staging and analysis output */
libname staging '/data/survey/staging';
libname tgt '/data/survey/analysis';

/* Wave configuration */
%let total_waves = 4;
%let wave1_date = 01JAN2024;
%let wave2_date = 01APR2024;
%let wave3_date = 01JUL2024;
%let wave4_date = 01OCT2024;

options mprint mlogic symbolgen nocenter;

/* ------------------------------------------------------------------ */
/* SECTION 2: Wave Processing Macro                                    */
/* ------------------------------------------------------------------ */

/* Macro to extract and summarize a single survey wave */
%macro process_wave(wave_num=, wave_date=);

    %put NOTE: =============================================;
    %put NOTE: Processing Wave &wave_num (date: &wave_date);
    %put NOTE: =============================================;

    /* Check if wave data exists before processing */
    %let dsid = %sysfunc(open(raw.survey_responses));
    %if &dsid = 0 %then %do;
        %put WARNING: Cannot open raw.survey_responses for wave &wave_num;
        %put WARNING: Skipping wave &wave_num processing;
        %goto wave_exit;
    %end;
    %let rc = %sysfunc(close(&dsid));

    /* Extract respondents for this specific wave */
    data staging.wave_&wave_num;
        set raw.survey_responses;
        where wave_id = &wave_num
          and response_date >= "&wave_date"d;

        /* Derive composite satisfaction score */
        satisfaction_score = mean(of q1_rating q2_rating q3_rating
                                    q4_rating q5_rating);

        /* Classification of engagement level */
        length engagement $15;
        if satisfaction_score >= 4.0 then engagement = "HIGH";
        else if satisfaction_score >= 2.5 then engagement = "MODERATE";
        else engagement = "LOW";

        /* Track completion rate */
        array questions{5} q1_rating q2_rating q3_rating
                           q4_rating q5_rating;
        items_answered = 0;
        do j = 1 to 5;
            if questions{j} > 0 then items_answered + 1;
        end;
        completion_pct = (items_answered / 5) * 100;

        wave_label = "Wave &wave_num";
        format response_date date9.;
        drop j;
    run;

    /* Wave-level descriptive statistics */
    proc means data=staging.wave_&wave_num
               n mean std min max median maxdec=2;
        title "Wave &wave_num Summary Statistics";
        var satisfaction_score completion_pct
            q1_rating q2_rating q3_rating q4_rating q5_rating;
        output out=staging.stats_wave_&wave_num
            n=n_respondents
            mean=avg_satisfaction
            std=sd_satisfaction;
    run;

    %wave_exit:
    %put NOTE: Wave &wave_num processing complete;

%mend process_wave;

/* ------------------------------------------------------------------ */
/* SECTION 3: Process All Waves via Loop                               */
/* ------------------------------------------------------------------ */

/* Driver macro to iterate over all configured waves */
%macro run_all_waves;
    %do w = 1 %to &total_waves;
        %process_wave(
            wave_num = &w,
            wave_date = &&wave&w._date
        );
    %end;
%mend run_all_waves;

/* Execute wave processing */
%run_all_waves;

/* Open-code conditional: verify all waves processed */
%if &syserr > 0 %then %do;
    %put ERROR: Wave processing encountered errors (SYSERR=&syserr);
    %put ERROR: Longitudinal panel may be incomplete;
%end;
%else %do;
    %put NOTE: All &total_waves waves processed successfully;
%end;

/* ------------------------------------------------------------------ */
/* SECTION 4: Build Longitudinal Panel                                 */
/* ------------------------------------------------------------------ */

/* Join all waves into a single panel dataset keyed by respondent */
proc sql;
    create table staging.longitudinal_panel as
    select coalesce(w1.respondent_id, w2.respondent_id,
                    w3.respondent_id, w4.respondent_id)
               as respondent_id,
           w1.satisfaction_score as score_w1,
           w2.satisfaction_score as score_w2,
           w3.satisfaction_score as score_w3,
           w4.satisfaction_score as score_w4,
           w1.engagement as engage_w1,
           w4.engagement as engage_w4,
           /* Participation tracking */
           (w1.respondent_id is not null) as in_wave1,
           (w2.respondent_id is not null) as in_wave2,
           (w3.respondent_id is not null) as in_wave3,
           (w4.respondent_id is not null) as in_wave4
    from staging.wave_1 as w1
    full join staging.wave_2 as w2
        on w1.respondent_id = w2.respondent_id
    full join staging.wave_3 as w3
        on coalesce(w1.respondent_id, w2.respondent_id)
           = w3.respondent_id
    full join staging.wave_4 as w4
        on coalesce(w1.respondent_id, w2.respondent_id,
                    w3.respondent_id) = w4.respondent_id
    order by calculated respondent_id;
quit;

/* ------------------------------------------------------------------ */
/* SECTION 5: Longitudinal Change Analysis                             */
/* ------------------------------------------------------------------ */

/* Compute wave-over-wave changes using LAG function */
data tgt.wave_changes;
    set staging.longitudinal_panel;

    /* Count number of waves each respondent participated in */
    waves_participated = sum(in_wave1, in_wave2, in_wave3, in_wave4);

    /* Calculate overall trajectory */
    if score_w1 > 0 and score_w4 > 0 then
        overall_change = score_w4 - score_w1;
    else
        overall_change = .;

    /* Classify trajectory */
    length trajectory $15;
    if overall_change > 0.5 then trajectory = "IMPROVING";
    else if overall_change < -0.5 then trajectory = "DECLINING";
    else if overall_change ne . then trajectory = "STABLE";
    else trajectory = "INSUFFICIENT";

    /* Flag attrition risk: participated in wave 1 but not wave 4 */
    if in_wave1 = 1 and in_wave4 = 0 then attrition_flag = 1;
    else attrition_flag = 0;

    format overall_change 8.2;
run;

/* Trajectory distribution report */
proc freq data=tgt.wave_changes;
    title "Respondent Trajectory Distribution";
    tables trajectory / nocum;
    tables trajectory * waves_participated / nocum nopercent;
run;

title;

/* ------------------------------------------------------------------ */
/* SECTION 6: Cleanup                                                  */
/* ------------------------------------------------------------------ */

libname raw clear;
libname staging clear;

%put NOTE: Longitudinal analysis completed at %sysfunc(datetime(), datetime20.);
