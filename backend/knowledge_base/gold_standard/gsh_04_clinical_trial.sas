/******************************************************************************
 * Program Name : gsh_04_clinical_trial.sas
 * Author       : Biostatistics Department — Clinical Data Sciences
 * Study        : XYZ-301 Phase III Randomized Controlled Trial
 * Protocol     : XYZ-301-GLOBAL
 * Created      : 2025-06-15
 * Modified     : 2026-02-19
 * Purpose      : End-to-end clinical trial analysis pipeline for Phase III
 *                study XYZ-301. Derives ADaM-compliant analysis datasets
 *                (ADSL, ADAE), performs primary efficacy analysis (ANCOVA
 *                and logistic regression), and generates safety tables
 *                per ICH E9 guidelines.
 * Input        : SDTM domains (DM, AE, DS, EX, VS, LB)
 * Output       : ADaM datasets (ADSL, ADAE), TFLs (Tables 14.1-14.3)
 * Dependencies : study_macros.sas (shared clinical trial utility macros)
 * Validation   : Double programming per SOP-STAT-003
 * Change Log   :
 *   2025-06-15  v1.0  Initial ADSL / ADAE derivation         (J. Chen)
 *   2025-08-20  v1.1  Added efficacy analysis macros          (J. Chen)
 *   2025-10-10  v1.2  Safety tables with rate differences     (A. Patel)
 *   2025-12-01  v1.3  Population flag refinements per SAP v3  (J. Chen)
 *   2026-01-15  v1.4  Added PROC SQL demographics table       (A. Patel)
 *   2026-02-19  v1.5  Error handling and final QC checks      (J. Chen)
 ******************************************************************************/

/* ========================================================================= */
/* SECTION 1: Environment Setup and Library Definitions                      */
/* ========================================================================= */

options mprint mlogic symbolgen nocenter ls=132 ps=60
        validvarname=v7 nofmterr msglevel=i;

/* --- SDTM source data library (read-only) --- */
libname sdtm '/clinical/XYZ301/data/sdtm'
             access=readonly;

/* --- ADaM analysis dataset library --- */
libname adam '/clinical/XYZ301/data/adam';

/* --- Output library for tables, figures, and listings --- */
libname output '/clinical/XYZ301/output/tables';

/* --- Metadata and format library --- */
libname metadata '/clinical/XYZ301/metadata';

/* Global study parameters */
%let study_id    = XYZ-301;
%let cutoff_date = 15NOV2025;
%let sponsor     = PharmaCorp Inc.;
%let sap_version = 3.0;
%let run_dt      = %sysfunc(today(), date9.);
%let run_tm      = %sysfunc(time(), time8.);
%let analysis_rc = 0;

/* Load shared clinical trial utility macros */
%include '/clinical/XYZ301/macros/study_macros.sas';

/* ========================================================================= */
/* SECTION 2: ADSL — Subject-Level Analysis Dataset                          */
/* ========================================================================= */

/* --------------------------------------------------------------------- */
/* MACRO: derive_adsl                                                     */
/*   Derives the subject-level analysis dataset (ADSL) per ADaM IG.       */
/*   Merges SDTM domains DM, DS, and randomization list.                  */
/*   Calculates age groups, study duration, population flags (ITT, PP).   */
/*   Parameters:                                                          */
/*     study= : Study identifier for title annotations                   */
/* --------------------------------------------------------------------- */
%macro derive_adsl(study=);

    %put NOTE: ========================================================;
    %put NOTE: derive_adsl: Beginning ADSL derivation for study &study.;
    %put NOTE: Cutoff date: &cutoff_date. | SAP version: &sap_version.;
    %put NOTE: ========================================================;

    /* ---- Sort input SDTM domains by USUBJID ---- */
    proc sort data=sdtm.dm out=work.dm_sorted;
        by usubjid;
    run;

    proc sort data=sdtm.ds out=work.ds_sorted;
        by usubjid;
    run;

    proc sort data=metadata.randlist out=work.rand_sorted;
        by usubjid;
    run;

    /* ---- Merge demographics, disposition, and randomization ---- */
    data adam.adsl (label="Subject-Level Analysis Dataset — &study.");
        merge work.dm_sorted  (in=in_dm)
              work.ds_sorted  (in=in_ds
                               keep=usubjid dsdecod dsstdtc dsendtc)
              work.rand_sorted(in=in_rand
                               keep=usubjid trt01p trt01pn randdt stratum);
        by usubjid;

        /* Only keep subjects present in DM domain */
        if in_dm;

        length agegr1 $10 agegr1n 8 racen 8 sexn 8
               ittfl $1 ppfl $1 saffl $1 complfl $1
               studydur 8 trtdur 8;

        /* ---- Age group derivation ---- */
        if      age < 18 then do; agegr1 = '<18';     agegr1n = 1; end;
        else if age < 40 then do; agegr1 = '18-39';   agegr1n = 2; end;
        else if age < 65 then do; agegr1 = '40-64';   agegr1n = 3; end;
        else                  do; agegr1 = '65+';     agegr1n = 4; end;

        /* ---- Sex numeric code ---- */
        select (upcase(sex));
            when ('M') sexn = 1;
            when ('F') sexn = 2;
            otherwise  sexn = 99;
        end;

        /* ---- Race numeric code ---- */
        select (upcase(race));
            when ('WHITE')                                    racen = 1;
            when ('BLACK OR AFRICAN AMERICAN')                racen = 2;
            when ('ASIAN')                                    racen = 3;
            when ('AMERICAN INDIAN OR ALASKA NATIVE')         racen = 4;
            when ('NATIVE HAWAIIAN OR OTHER PACIFIC ISLANDER') racen = 5;
            when ('MULTIPLE')                                 racen = 6;
            otherwise                                         racen = 99;
        end;

        /* ---- Study duration (days from first dose to cutoff) ---- */
        if not missing(rfxstdtc) then do;
            rfxstdt = input(rfxstdtc, yymmdd10.);
            cutoff  = input("&cutoff_date.", date9.);
            studydur = intck('day', rfxstdt, cutoff);
        end;
        else studydur = .;

        /* ---- Treatment duration (first dose to last dose) ---- */
        if not missing(rfxstdtc) and not missing(rfxendtc) then do;
            rfxendt = input(rfxendtc, yymmdd10.);
            trtdur  = intck('day', rfxstdt, rfxendt) + 1;
        end;
        else trtdur = .;

        /* ---- Population flags per SAP v&sap_version ---- */
        /* ITT: all randomized subjects */
        if in_rand then ittfl = 'Y';
        else ittfl = 'N';

        /* Safety: randomized + received at least one dose */
        if in_rand and not missing(rfxstdtc) then saffl = 'Y';
        else saffl = 'N';

        /* Per-protocol: ITT without major protocol deviations */
        if ittfl = 'Y' and upcase(dsdecod) ne 'PROTOCOL VIOLATION'
           and trtdur >= 28 then ppfl = 'Y';
        else ppfl = 'N';

        /* Completion flag */
        if upcase(dsdecod) = 'COMPLETED' then complfl = 'Y';
        else complfl = 'N';

        /* ---- Assign treatment labels ---- */
        if trt01pn = 1 then trt01p = 'XYZ 100mg';
        else if trt01pn = 2 then trt01p = 'XYZ 200mg';
        else if trt01pn = 3 then trt01p = 'Placebo';

        format rfxstdt rfxendt cutoff date9.;

        /* ---- Store first subject ID via CALL SYMPUTX ---- */
        if _n_ = 1 then call symputx('adsl_first_subj', usubjid, 'G');
    run;

    /* ---- Capture ADSL record count ---- */
    proc sql noprint;
        select count(*) into :adsl_nobs trimmed
        from adam.adsl;
    quit;

    %put NOTE: ADSL derivation complete. N=&adsl_nobs subjects.;
    %if &syserr > 0 %then %do;
        %put ERROR: ADSL derivation failed with SYSERR=&syserr.;
        %let analysis_rc = 1;
    %end;

%mend derive_adsl;

/* ========================================================================= */
/* SECTION 3: ADAE — Adverse Event Analysis Dataset                          */
/* ========================================================================= */

/* --------------------------------------------------------------------- */
/* MACRO: derive_adae                                                     */
/*   Derives the adverse event analysis dataset (ADAE) per ADaM IG.       */
/*   Merges SDTM.AE with ADSL for population and treatment context.       */
/*   Derives severity grades, SAE flags, AE duration, and onset day.      */
/*   Parameters:                                                          */
/*     study= : Study identifier for annotations                        */
/* --------------------------------------------------------------------- */
%macro derive_adae(study=);

    %put NOTE: ========================================================;
    %put NOTE: derive_adae: Beginning ADAE derivation for study &study.;
    %put NOTE: ========================================================;

    /* ---- Sort AE domain ---- */
    proc sort data=sdtm.ae out=work.ae_sorted;
        by usubjid;
    run;

    /* ---- Sort ADSL for merge ---- */
    proc sort data=adam.adsl out=work.adsl_for_ae;
        by usubjid;
    run;

    /* ---- Merge AE with ADSL to get treatment and population context ---- */
    data adam.adae (label="Adverse Event Analysis Dataset — &study.");
        merge work.ae_sorted    (in=in_ae)
              work.adsl_for_ae  (in=in_adsl
                                 keep=usubjid trt01p trt01pn saffl ittfl
                                      rfxstdtc agegr1 sex studydur);
        by usubjid;

        /* Only keep AEs for subjects in ADSL with safety flag */
        if in_ae and in_adsl and saffl = 'Y';

        length aesevn 8 aeser_flag $1 aedur 8 aestdy 8
               aebodsys $200 aedecod $200 aereln 8;

        /* ---- Severity grading (numeric) ---- */
        select (upcase(aesev));
            when ('MILD')     aesevn = 1;
            when ('MODERATE') aesevn = 2;
            when ('SEVERE')   aesevn = 3;
            otherwise         aesevn = .;
        end;

        /* ---- Serious adverse event flag ---- */
        if upcase(aeser) = 'Y' then aeser_flag = 'Y';
        else aeser_flag = 'N';

        /* ---- AE duration (days) ---- */
        if not missing(aestdtc) and not missing(aeendtc) then do;
            aestdt = input(aestdtc, yymmdd10.);
            aeendt = input(aeendtc, yymmdd10.);
            aedur  = aeendt - aestdt + 1;
            if aedur < 1 then aedur = 1; /* Minimum 1-day duration */
        end;
        else do;
            aestdt = .;
            aeendt = .;
            aedur  = .;
        end;

        /* ---- Onset study day relative to first dose ---- */
        if not missing(aestdtc) and not missing(rfxstdtc) then do;
            rfxstdt_ae = input(rfxstdtc, yymmdd10.);
            aestdy = aestdt - rfxstdt_ae;
            if aestdy >= 0 then aestdy = aestdy + 1;
        end;
        else aestdy = .;

        /* ---- Relationship to study drug (numeric) ---- */
        select (upcase(aerel));
            when ('NOT RELATED')        aereln = 0;
            when ('UNLIKELY')           aereln = 1;
            when ('POSSIBLE')           aereln = 2;
            when ('PROBABLE')           aereln = 3;
            when ('DEFINITE')           aereln = 4;
            otherwise                   aereln = .;
        end;

        /* ---- Treatment-emergent AE flag ---- */
        if aestdy > 0 or missing(aestdy) then trtemfl = 'Y';
        else trtemfl = 'N';

        format aestdt aeendt date9.;

        drop rfxstdt_ae;
    run;

    /* ---- Capture ADAE record count ---- */
    proc sql noprint;
        select count(*) into :adae_nobs trimmed from adam.adae;
        select count(distinct usubjid) into :adae_nsubj trimmed from adam.adae;
    quit;

    %put NOTE: ADAE derivation complete. &adae_nobs AE records for &adae_nsubj subjects.;
    %if &syserr > 0 %then %do;
        %put ERROR: ADAE derivation failed with SYSERR=&syserr.;
        %let analysis_rc = 1;
    %end;

%mend derive_adae;

/* ========================================================================= */
/* SECTION 4: Efficacy Analysis                                              */
/* ========================================================================= */

/* --------------------------------------------------------------------- */
/* MACRO: efficacy_analysis                                               */
/*   Performs primary efficacy analysis based on the specified endpoint    */
/*   and statistical method. Supports ANCOVA (PROC GLM) for continuous    */
/*   endpoints and logistic regression (PROC LOGISTIC) for binary.        */
/*   Generates descriptive statistics by treatment arm.                    */
/*   Parameters:                                                          */
/*     endpoint= : Variable name of the primary endpoint                 */
/*     method=   : ANCOVA or LOGISTIC                                    */
/*     covars=   : Space-separated list of covariates                    */
/* --------------------------------------------------------------------- */
%macro efficacy_analysis(endpoint=, method=, covars=agegr1n sexn);

    %put NOTE: ========================================================;
    %put NOTE: efficacy_analysis: Endpoint=&endpoint. | Method=&method.;
    %put NOTE: Covariates: &covars.;
    %put NOTE: ========================================================;

    /* ---- Descriptive statistics by treatment arm ---- */
    proc means data=adam.adsl n mean std median min max maxdec=2
               nway noprint;
        where ittfl = 'Y' and not missing(&endpoint.);
        class trt01pn trt01p;
        var &endpoint.;
        output out=work.desc_&endpoint.
               n=n mean=mean std=std median=median min=min max=max;
    run;

    /* Print descriptive statistics for review */
    title "Table 14.2.1: Descriptive Statistics — &endpoint. by Treatment";
    title2 "Study &study_id. | ITT Population | SAP v&sap_version.";
    proc print data=work.desc_&endpoint. noobs label;
        var trt01p n mean std median min max;
        label trt01p = 'Treatment'
              n      = 'N'
              mean   = 'Mean'
              std    = 'Std Dev'
              median = 'Median'
              min    = 'Minimum'
              max    = 'Maximum';
    run;
    title;

    /* ---- Primary analysis: method-dependent ---- */
    %if %upcase(&method.) = ANCOVA %then %do;

        /* ANCOVA via PROC GLM with treatment as factor and covariates */
        %put NOTE: Running ANCOVA for &endpoint. via PROC GLM.;

        proc glm data=adam.adsl plots=none;
            where ittfl = 'Y' and not missing(&endpoint.);
            class trt01pn &covars.;
            model &endpoint. = trt01pn &covars. / ss3 solution;
            lsmeans trt01pn / pdiff cl adjust=tukey;
            ods output LSMeans      = work.lsmeans_&endpoint.
                       Diff         = work.lsdiff_&endpoint.
                       OverallANOVA = work.anova_&endpoint.;
        quit;

        /* ---- Extract p-value for treatment effect ---- */
        data _null_;
            set work.anova_&endpoint.;
            where upcase(source) = 'TRT01PN';
            call symputx('pval_trt', put(probf, pvalue6.4), 'G');
        run;

        %put NOTE: ANCOVA p-value for treatment effect: &pval_trt.;

    %end;
    %else %if %upcase(&method.) = LOGISTIC %then %do;

        /* Logistic regression via PROC LOGISTIC for binary endpoint */
        %put NOTE: Running logistic regression for &endpoint. via PROC LOGISTIC.;

        proc logistic data=adam.adsl descending;
            where ittfl = 'Y' and not missing(&endpoint.);
            class trt01pn(ref='3') &covars. / param=ref;
            model &endpoint. = trt01pn &covars.
                  / lackfit rsquare stb;
            oddsratio trt01pn;
            ods output OddsRatios         = work.or_&endpoint.
                       ParameterEstimates = work.parms_&endpoint.
                       GlobalTests        = work.global_&endpoint.;
        run;

        /* ---- Extract odds ratio for treatment ---- */
        data _null_;
            set work.or_&endpoint.;
            if _n_ = 1 then do;
                call symputx('or_estimate', put(oddsratioest, 8.3), 'G');
                call symputx('or_lower', put(lowercl, 8.3), 'G');
                call symputx('or_upper', put(uppercl, 8.3), 'G');
            end;
        run;

        %put NOTE: Odds Ratio (95%% CI): &or_estimate. (&or_lower., &or_upper.);

    %end;
    %else %do;
        %put ERROR: Unknown analysis method &method.. Valid: ANCOVA, LOGISTIC.;
        %let analysis_rc = 1;
    %end;

    %if &syserr > 0 %then %do;
        %put ERROR: Efficacy analysis for &endpoint. failed (SYSERR=&syserr.).;
        %let analysis_rc = 1;
    %end;

%mend efficacy_analysis;

/* ========================================================================= */
/* SECTION 5: Safety Tables — Adverse Event Incidence                        */
/* ========================================================================= */

/* --------------------------------------------------------------------- */
/* MACRO: safety_tables                                                   */
/*   Generates AE incidence tables by system organ class and preferred    */
/*   term. Iterates over AE categories using %DO loop. Computes rate     */
/*   differences between active treatment and placebo.                    */
/*   Produces Table 14.3 series per SAP.                                  */
/* --------------------------------------------------------------------- */
%macro safety_tables;

    %put NOTE: ========================================================;
    %put NOTE: safety_tables: Generating AE incidence tables.;
    %put NOTE: ========================================================;

    /* ---- Define AE categories to tabulate ---- */
    %let ncat = 4;
    %let cat1 = TEAE;
    %let cat2 = SAE;
    %let cat3 = DRUG_RELATED;
    %let cat4 = LEADING_TO_DISC;
    %let catlab1 = Treatment-Emergent Adverse Events;
    %let catlab2 = Serious Adverse Events;
    %let catlab3 = Drug-Related Adverse Events;
    %let catlab4 = AEs Leading to Discontinuation;

    /* ---- Get denominator counts per treatment arm ---- */
    proc sql noprint;
        select count(distinct case when trt01pn=1 then usubjid end),
               count(distinct case when trt01pn=2 then usubjid end),
               count(distinct case when trt01pn=3 then usubjid end)
        into :n_trt1 trimmed, :n_trt2 trimmed, :n_plac trimmed
        from adam.adsl
        where saffl = 'Y';
    quit;

    %put NOTE: Safety population: TRT1=&n_trt1 | TRT2=&n_trt2 | Placebo=&n_plac;

    /* ---- Loop over AE categories ---- */
    %do i = 1 %to &ncat.;

        %let thiscat  = &&cat&i.;
        %let thislab  = &&catlab&i.;

        %put NOTE: Processing category &i.: &thiscat. — &thislab.;

        /* ---- Apply category-specific filter ---- */
        data work.ae_filtered_&i.;
            set adam.adae;
            %if &thiscat. = TEAE %then %do;
                where trtemfl = 'Y';
            %end;
            %else %if &thiscat. = SAE %then %do;
                where trtemfl = 'Y' and aeser_flag = 'Y';
            %end;
            %else %if &thiscat. = DRUG_RELATED %then %do;
                where trtemfl = 'Y' and aereln >= 2;
            %end;
            %else %if &thiscat. = LEADING_TO_DISC %then %do;
                where trtemfl = 'Y' and upcase(aeacn) = 'DRUG WITHDRAWN';
            %end;
        run;

        /* ---- Frequency table by SOC and preferred term ---- */
        proc freq data=work.ae_filtered_&i. noprint;
            tables aebodsys * aedecod * trt01pn / out=work.ae_freq_&i.
                                                    outpct sparse;
        run;

        /* ---- Compute incidence rates and rate differences ---- */
        proc sort data=work.ae_freq_&i.;
            by aebodsys aedecod trt01pn;
        run;

        data work.ae_rates_&i.;
            set work.ae_freq_&i.;
            by aebodsys aedecod trt01pn;

            length rate 8 denom 8;

            /* Assign denominator based on treatment */
            select (trt01pn);
                when (1) denom = input("&n_trt1.", 8.);
                when (2) denom = input("&n_trt2.", 8.);
                when (3) denom = input("&n_plac.", 8.);
                otherwise denom = .;
            end;

            /* Incidence rate as percentage */
            if denom > 0 then rate = (count / denom) * 100;
            else rate = .;

            format rate 6.1;
        run;

        /* ---- Transpose to one row per SOC/PT with columns per trt ---- */
        proc transpose data=work.ae_rates_&i.
                       out=work.ae_wide_&i.(drop=_name_)
                       prefix=rate_;
            by aebodsys aedecod;
            id trt01pn;
            var rate;
        run;

        /* ---- Calculate rate difference (active vs placebo) ---- */
        data output.table_14_3_&i. (label="Table 14.3.&i.: &thislab.");
            set work.ae_wide_&i.;

            /* Rate difference: active arm 1 vs placebo */
            if not missing(rate_1) and not missing(rate_3) then
                rate_diff_1 = rate_1 - rate_3;
            else rate_diff_1 = .;

            /* Rate difference: active arm 2 vs placebo */
            if not missing(rate_2) and not missing(rate_3) then
                rate_diff_2 = rate_2 - rate_3;
            else rate_diff_2 = .;

            label aebodsys    = 'System Organ Class'
                  aedecod     = 'Preferred Term'
                  rate_1      = "XYZ 100mg (N=&n_trt1.) %"
                  rate_2      = "XYZ 200mg (N=&n_trt2.) %"
                  rate_3      = "Placebo (N=&n_plac.) %"
                  rate_diff_1 = 'Rate Diff (100mg - Placebo)'
                  rate_diff_2 = 'Rate Diff (200mg - Placebo)';

            format rate_diff_1 rate_diff_2 6.1;
        run;

        %put NOTE: Table 14.3.&i.: &thislab. — complete.;

    %end; /* End %DO loop over categories */

    %if &syserr > 0 %then %do;
        %put ERROR: Safety tables generation failed (SYSERR=&syserr.).;
        %let analysis_rc = 1;
    %end;

%mend safety_tables;

/* ========================================================================= */
/* SECTION 6: Main Program Execution                                         */
/* ========================================================================= */

%put NOTE: ============================================================;
%put NOTE: Main program execution begins: &run_dt. &run_tm.;
%put NOTE: Study: &study_id. | SAP: v&sap_version.;
%put NOTE: ============================================================;

/* ---- Step 1: Derive ADSL ---- */
%derive_adsl(study=&study_id.);

/* ---- Step 2: Derive ADAE ---- */
%derive_adae(study=&study_id.);

/* ---- Step 3: Primary efficacy — continuous endpoint (ANCOVA) ---- */
%efficacy_analysis(endpoint=chg_primary, method=ANCOVA,
                   covars=agegr1n sexn baseline);

/* ---- Step 4: Secondary efficacy — binary endpoint (Logistic) ---- */
%efficacy_analysis(endpoint=responder_flag, method=LOGISTIC,
                   covars=agegr1n sexn);

/* ---- Step 5: Safety tables ---- */
%safety_tables;

/* ========================================================================= */
/* SECTION 7: Demographics Table (Table 14.1) via PROC SQL                   */
/* ========================================================================= */

/* ---- Table 14.1: Summary of Demographics and Baseline Characteristics ---- */
proc sql;
    create table output.table_14_1 as
    select trt01p                                            as treatment
          ,count(distinct usubjid)                           as n_subjects
          ,mean(age)                                         as mean_age     format=5.1
          ,std(age)                                          as sd_age       format=5.2
          ,median(age)                                       as median_age   format=5.1
          ,min(age)                                          as min_age
          ,max(age)                                          as max_age
          ,sum(case when sex='M' then 1 else 0 end)         as n_male
          ,calculated n_male / calculated n_subjects * 100   as pct_male     format=5.1
          ,sum(case when sex='F' then 1 else 0 end)         as n_female
          ,calculated n_female / calculated n_subjects * 100 as pct_female   format=5.1
          ,sum(case when racen=1 then 1 else 0 end)         as n_white
          ,sum(case when racen=2 then 1 else 0 end)         as n_black
          ,sum(case when racen=3 then 1 else 0 end)         as n_asian
          ,sum(case when racen>=4 then 1 else 0 end)        as n_other_race
          ,mean(studydur)                                    as mean_studydur format=6.1
          ,mean(trtdur)                                      as mean_trtdur   format=6.1
          ,sum(case when ittfl='Y' then 1 else 0 end)       as n_itt
          ,sum(case when ppfl='Y' then 1 else 0 end)        as n_pp
          ,sum(case when saffl='Y' then 1 else 0 end)       as n_safety
          ,sum(case when complfl='Y' then 1 else 0 end)     as n_completed
    from adam.adsl
    group by trt01p
    order by trt01p;
quit;

/* ---- Print Table 14.1 ---- */
title "Table 14.1: Summary of Demographics and Baseline Characteristics";
title2 "Study &study_id. | ITT Population | SAP v&sap_version.";
proc print data=output.table_14_1 noobs label;
    var treatment n_subjects mean_age sd_age pct_male pct_female
        n_white n_black n_asian n_other_race
        mean_studydur mean_trtdur n_itt n_pp n_safety n_completed;
    label treatment    = 'Treatment Arm'
          n_subjects   = 'N'
          mean_age     = 'Mean Age'
          sd_age       = 'SD Age'
          pct_male     = '% Male'
          pct_female   = '% Female'
          n_white      = 'N White'
          n_black      = 'N Black'
          n_asian      = 'N Asian'
          n_other_race = 'N Other'
          mean_studydur = 'Mean Study Duration'
          mean_trtdur   = 'Mean Trt Duration'
          n_itt        = 'N (ITT)'
          n_pp         = 'N (PP)'
          n_safety     = 'N (Safety)'
          n_completed  = 'N (Completed)';
run;
title;

/* ========================================================================= */
/* SECTION 8: Error Handling and Final Status                                 */
/* ========================================================================= */

%if &analysis_rc. ne 0 or &syserr. ne 0 %then %do;

    %put ERROR: ========================================================;
    %put ERROR: Clinical trial analysis pipeline FAILED.;
    %put ERROR: analysis_rc=&analysis_rc. | syserr=&syserr.;
    %put ERROR: Study=&study_id. | Run date=&run_dt.;
    %put ERROR: ========================================================;

    /* Write error notification file for monitoring system */
    data _null_;
        file '/clinical/XYZ301/logs/analysis_error.flag';
        put "STATUS=FAILED";
        put "STUDY=&study_id.";
        put "RUN_DATE=&run_dt.";
        put "RUN_TIME=&run_tm.";
        put "ANALYSIS_RC=&analysis_rc.";
        put "SYSERR=&syserr.";
        put "PROGRAM=gsh_04_clinical_trial.sas";
    run;

    /* Notify biostatistics team via email */
    filename mailto email
        to='biostat-team@pharmacorp.com'
        subject="ALERT: Study &study_id. analysis pipeline FAILED"
        type='text/plain';

    data _null_;
        file mailto;
        put "Clinical trial analysis pipeline failed.";
        put "Study: &study_id.";
        put "Program: gsh_04_clinical_trial.sas";
        put "Run date/time: &run_dt. &run_tm.";
        put "Return code: &analysis_rc.";
        put "Please review the SAS log immediately.";
    run;

    filename mailto clear;

%end;
%else %do;

    %put NOTE: ========================================================;
    %put NOTE: Clinical trial analysis pipeline completed SUCCESSFULLY.;
    %put NOTE: Study=&study_id. | Run date=&run_dt. &run_tm.;
    %put NOTE: ADSL N=&adsl_nobs | ADAE N=&adae_nobs (&adae_nsubj subj);
    %put NOTE: ========================================================;

    /* Write success flag file */
    data _null_;
        file '/clinical/XYZ301/logs/analysis_complete.flag';
        put "STATUS=SUCCESS";
        put "STUDY=&study_id.";
        put "RUN_DATE=&run_dt.";
        put "RUN_TIME=&run_tm.";
        put "ADSL_N=&adsl_nobs.";
        put "ADAE_N=&adae_nobs.";
        put "PROGRAM=gsh_04_clinical_trial.sas";
    run;

%end;

/* ========================================================================= */
/* SECTION 9: Cleanup and Reset                                              */
/* ========================================================================= */

/* ---- Delete intermediate work datasets ---- */
proc datasets library=work nolist nowarn;
    delete dm_sorted ds_sorted rand_sorted
           adsl_for_ae ae_sorted
           ae_filtered_: ae_freq_: ae_rates_: ae_wide_:
           desc_: lsmeans_: lsdiff_: anova_:
           or_: parms_: global_:;
quit;

/* ---- Reset options to defaults ---- */
options nomprint nomlogic nosymbolgen;

%put NOTE: ============================================================;
%put NOTE: Program gsh_04_clinical_trial.sas complete.;
%put NOTE: End time: %sysfunc(datetime(), datetime20.);
%put NOTE: ============================================================;
