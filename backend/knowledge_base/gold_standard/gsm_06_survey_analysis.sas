/*****************************************************************************
 * Program: gsm_06_survey_analysis.sas
 * Purpose: Analyze employee engagement survey data
 * Author:  Analytics Team
 * Date:    2026-02-19
 * Description:
 *   Processes raw survey responses, recodes Likert scales, computes
 *   composite engagement scores, and produces statistical analyses
 *   by demographic groups including chi-square tests and correlations.
 *****************************************************************************/

/* ------------------------------------------------------------------ */
/* Global settings and library references                             */
/* ------------------------------------------------------------------ */
options mprint mlogic symbolgen nocenter ls=120 ps=60;

libname raw     'C:/data/survey/raw' access=readonly;
libname staging 'C:/data/survey/staging';
libname tgt     'C:/data/survey/output';

/* ------------------------------------------------------------------ */
/* Step 1: Recode Likert scales and compute composite scores          */
/*   - Reverse-code negatively worded items (Q3, Q7, Q12)            */
/*   - Compute engagement, satisfaction, and leadership composites    */
/* ------------------------------------------------------------------ */
data staging.survey_scored;
    set raw.survey_responses;

    /* Reverse code negatively worded items (1->5, 2->4, etc.) */
    q3_r  = 6 - q3;
    q7_r  = 6 - q7;
    q12_r = 6 - q12;

    /* Engagement composite: average of Q1, Q2, Q3(reversed), Q4 */
    engagement_score = mean(q1, q2, q3_r, q4);

    /* Satisfaction composite: average of Q5, Q6, Q7(reversed), Q8 */
    satisfaction_score = mean(q5, q6, q7_r, q8);

    /* Leadership composite: average of Q9, Q10, Q11, Q12(reversed) */
    leadership_score = mean(q9, q10, q11, q12_r);

    /* Overall composite score */
    overall_score = mean(engagement_score, satisfaction_score, leadership_score);

    /* Categorize overall score into engagement tiers */
    length engagement_tier $15;
    if overall_score >= 4.0 then engagement_tier = 'Highly Engaged';
    else if overall_score >= 3.0 then engagement_tier = 'Engaged';
    else if overall_score >= 2.0 then engagement_tier = 'Neutral';
    else engagement_tier = 'Disengaged';

    /* Calculate response completeness */
    array all_q{12} q1-q12;
    n_answered = 0;
    do i = 1 to 12;
        if not missing(all_q{i}) then n_answered + 1;
    end;
    pct_complete = (n_answered / 12) * 100;

    format engagement_score satisfaction_score leadership_score
           overall_score 5.2 pct_complete 5.1;
    drop i;
run;

/* ------------------------------------------------------------------ */
/* Step 2: Response distributions with chi-square tests               */
/*   - Cross-tabulate engagement tier by department and tenure group  */
/* ------------------------------------------------------------------ */
proc freq data=staging.survey_scored;
    tables engagement_tier * department / chisq nocum nopercent expected;
    tables engagement_tier * tenure_group / chisq nocum;
    title 'Engagement Survey: Response Distributions';
run;

/* ------------------------------------------------------------------ */
/* Step 3: Group comparison - mean scores by department               */
/*   - Produce department-level aggregates with confidence limits     */
/* ------------------------------------------------------------------ */
proc means data=staging.survey_scored n mean std min max clm;
    class department;
    var engagement_score satisfaction_score leadership_score overall_score;
    output out=staging.dept_means
        mean(engagement_score)   = mean_engagement
        mean(satisfaction_score) = mean_satisfaction
        mean(leadership_score)   = mean_leadership
        mean(overall_score)      = mean_overall
        std(overall_score)       = std_overall
        n(overall_score)         = n_respondents;
    title 'Mean Scores by Department';
run;

/* ------------------------------------------------------------------ */
/* Step 4: Scale reliability - inter-item correlations                */
/*   - Examine correlations within each composite scale               */
/* ------------------------------------------------------------------ */
proc corr data=staging.survey_scored nosimple;
    var q1 q2 q3_r q4;
    title 'Engagement Scale: Inter-Item Correlations';
run;

proc corr data=staging.survey_scored nosimple;
    var q5 q6 q7_r q8;
    title 'Satisfaction Scale: Inter-Item Correlations';
run;

proc corr data=staging.survey_scored nosimple;
    var q9 q10 q11 q12_r;
    title 'Leadership Scale: Inter-Item Correlations';
run;

/* ------------------------------------------------------------------ */
/* Step 5: Demographic group summary via SQL                          */
/*   - Summarize composite scores and response rates by demographics  */
/* ------------------------------------------------------------------ */
proc sql;
    create table staging.demographic_summary as
    select
        department,
        tenure_group,
        gender,
        count(*) as n_respondents,
        mean(engagement_score) as avg_engagement format=5.2,
        mean(satisfaction_score) as avg_satisfaction format=5.2,
        mean(leadership_score) as avg_leadership format=5.2,
        mean(overall_score) as avg_overall format=5.2,
        mean(pct_complete) as avg_completion format=5.1,
        sum(case when engagement_tier = 'Highly Engaged' then 1 else 0 end)
            as n_highly_engaged,
        calculated n_highly_engaged / calculated n_respondents * 100
            as pct_highly_engaged format=5.1
    from staging.survey_scored
    group by department, tenure_group, gender
    having n_respondents >= 5
    order by department, tenure_group, gender;
quit;

/* ------------------------------------------------------------------ */
/* Step 6: Flag outlier respondents                                   */
/*   - Straight-line responding, low completion, extreme scores       */
/* ------------------------------------------------------------------ */
data tgt.survey_flagged;
    set staging.survey_scored;

    /* Flag low completion rate */
    flag_incomplete = (pct_complete < 50);

    /* Detect straight-line responding (zero variance in answers) */
    array items{12} q1-q12;
    _min = min(of items{*});
    _max = max(of items{*});
    flag_straightline = (_min = _max and not missing(_min));

    /* Flag extreme outliers on overall score */
    flag_outlier_low  = (overall_score < 1.5 and not missing(overall_score));
    flag_outlier_high = (overall_score > 4.8 and not missing(overall_score));

    /* Combined quality flag */
    flag_quality_concern = (flag_incomplete or flag_straightline
                           or flag_outlier_low or flag_outlier_high);

    /* Build quality notes for flagged respondents */
    length quality_notes $200;
    quality_notes = '';
    if flag_incomplete then
        quality_notes = catx('; ', quality_notes, 'Low completion');
    if flag_straightline then
        quality_notes = catx('; ', quality_notes, 'Straight-line responding');
    if flag_outlier_low then
        quality_notes = catx('; ', quality_notes, 'Extremely low scores');
    if flag_outlier_high then
        quality_notes = catx('; ', quality_notes, 'Extremely high scores');

    drop _min _max;
run;

/* End of survey analysis program */
