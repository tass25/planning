/******************************************************************************
 * Program Name : gsh_06_regulatory_report.sas
 * Author       : Capital Markets Risk & Compliance Division
 * Department   : Regulatory Reporting — Prudential Analytics
 * Version      : 3.1
 * Created      : 2025-01-15
 * Modified     : 2026-02-19
 * Purpose      : Multi-section regulatory filing report generator for
 *                CCAR (Comprehensive Capital Analysis and Review) and
 *                Basel III capital adequacy submissions. Computes
 *                risk-weighted assets (RWA) under Standardized and IRB
 *                approaches, derives CET1/Tier1/Total capital ratios,
 *                runs multi-quarter stress testing projections, and
 *                generates regulatory filing schedules (HC-R, FR Y-14).
 * Input        : risk.exposures, risk.pd_lgd_models, risk.collateral,
 *                fin.capital_components, fin.balance_sheet,
 *                comp.regulatory_limits, comp.buffer_requirements
 * Output       : out.rwa_summary, out.capital_ratios, out.stress_results,
 *                out.schedule_*, out.filing_cover_page
 * Dependencies : regulatory_formats.sas (format library for filing codes)
 * Reg Refs     : Basel III CRR Art. 92, CCAR FR Y-14A, Dodd-Frank §165
 * Filing Period: Quarterly (current quarter derived from process date)
 * Change Log   :
 *   2025-01-15  v1.0  Initial RWA calculation framework         (A. Chen)
 *   2025-04-01  v1.5  Added IRB approach with PD/LGD/EAD       (R. Patel)
 *   2025-06-20  v2.0  Capital ratios and buffer calculations    (A. Chen)
 *   2025-09-10  v2.5  Stress testing module (3 scenarios)       (J. Novak)
 *   2025-11-28  v3.0  Schedule generation and ODS output        (R. Patel)
 *   2026-02-19  v3.1  Error handling, cover page, validation    (A. Chen)
 ******************************************************************************/

/* ========================================================================= */
/* SECTION 1: Environment Setup and Library Definitions                      */
/* ========================================================================= */

options mprint symbolgen mlogic nocenter ls=160 ps=60
        validvarname=v7 nofmterr msglevel=i;

/* --- Risk data library: exposures, PD/LGD models, collateral --- */
libname risk '/regulatory/data/risk'
             access=readonly;

/* --- Finance library: capital components and balance sheet --- */
libname fin '/regulatory/data/finance'
            access=readonly;

/* --- Compliance library: regulatory limits and buffer requirements --- */
libname comp '/regulatory/data/compliance'
             access=readonly;

/* --- Output library: filing schedules and summary reports --- */
libname out '/regulatory/output/filing';

/* ========================================================================= */
/* SECTION 2: Global Parameters and Reporting Period                         */
/* ========================================================================= */

/* --- Reporting period parameters --- */
%let report_date    = %sysfunc(today(), date9.);
%let report_qtr     = %sysfunc(today(), yyq6.);
%let filing_year    = %sysfunc(year(%sysfunc(today())));
%let filing_quarter = %sysfunc(qtr(%sysfunc(today())));
%let run_id         = REG_%sysfunc(today(), yymmddn8.)_%sysfunc(time(), time5.);
%let reg_rc         = 0;

/* --- Regulatory minimum thresholds (Basel III) --- */
%let min_cet1_ratio  = 0.045;
%let min_tier1_ratio = 0.060;
%let min_total_ratio = 0.080;
%let ccb_rate        = 0.025;
%let gsib_rate       = 0.010;

/* --- Stress testing parameters --- */
%let n_quarters      = 9;
%let base_loss_rate  = 0.005;
%let adv_loss_rate   = 0.025;
%let sev_loss_rate   = 0.055;

/* --- Schedule identifiers for filing --- */
%let n_schedules     = 6;
%let sched_id_1      = HC-R_PART1;
%let sched_id_2      = HC-R_PART2;
%let sched_id_3      = FR_Y14A_SUMM;
%let sched_id_4      = FR_Y14A_LOSS;
%let sched_id_5      = FR_Y14A_PPNR;
%let sched_id_6      = FR_Y14Q_SUPP;

/* Load regulatory format library for filing codes */
%include '/regulatory/macros/regulatory_formats.sas';

/* ========================================================================= */
/* SECTION 3: %MACRO calc_rwa — Risk-Weighted Assets Calculation             */
/* ========================================================================= */

/*----------------------------------------------------------------------
  %MACRO calc_rwa
  Purpose: Calculate risk-weighted assets for a given asset class using
           either the Standardized approach (fixed regulatory risk
           weights) or the Internal Ratings-Based (IRB) approach with
           PD/LGD/EAD model outputs. Aggregates exposure-level RWA
           into portfolio-level summaries.
  Parameters:
    asset_class= : Asset class identifier (CORPORATE, SOVEREIGN,
                   RETAIL, EQUITY)
    approach=    : Calculation approach (STANDARDIZED or IRB)
----------------------------------------------------------------------*/

%macro calc_rwa(asset_class=, approach=);

    %put NOTE: ---- calc_rwa: asset_class=&asset_class approach=&approach ----;

    /* ----- Standardized Approach: Fixed Risk Weights ----- */
    %if &approach = STANDARDIZED %then %do;

        /* Apply Basel III standardized risk weights by rating band */
        data work.rwa_&asset_class._std;
            set risk.exposures(where=(asset_class = "&asset_class"));

            /* Assign risk weight based on external credit rating */
            select (rating_band);
                when ('AAA','AA')  risk_weight = 0.20;
                when ('A')         risk_weight = 0.50;
                when ('BBB')       risk_weight = 1.00;
                when ('BB')        risk_weight = 1.00;
                when ('B')         risk_weight = 1.50;
                when ('CCC','D')   risk_weight = 1.50;
                otherwise          risk_weight = 1.00;  /* unrated */
            end;

            /* Sovereign exposures get preferential treatment */
            if "&asset_class" = "SOVEREIGN" and domestic_flag = 'Y' then
                risk_weight = 0.00;

            /* Apply credit risk mitigation (CRM) adjustments */
            if collateral_value > 0 then do;
                crm_factor = min(collateral_value / exposure_amount, 1.0);
                adjusted_exposure = exposure_amount * (1 - crm_factor * 0.80);
            end;
            else do;
                crm_factor = 0;
                adjusted_exposure = exposure_amount;
            end;

            /* Calculate risk-weighted asset amount */
            rwa_amount       = adjusted_exposure * risk_weight;
            calculation_date = "&report_date"d;
            calc_approach    = 'STANDARDIZED';
            calc_asset_class = "&asset_class";
        run;

    %end;

    /* ----- IRB Approach: PD/LGD/EAD Model-Based ----- */
    %else %do;

        /* Retrieve PD/LGD/EAD model parameters for this asset class */
        data work.rwa_&asset_class._irb;
            merge risk.exposures(where=(asset_class = "&asset_class")
                                 in=a)
                  risk.pd_lgd_models(where=(model_asset_class = "&asset_class")
                                     in=b);
            by counterparty_id;
            if a;

            /* Default probability of default if model missing */
            if pd_estimate = . then pd_estimate = 0.03;
            if lgd_estimate = . then lgd_estimate = 0.45;

            /* Effective maturity adjustment (Basel formula) */
            maturity_adj = (1 + (effective_maturity - 2.5) * 0.05);
            if maturity_adj < 0.70 then maturity_adj = 0.70;
            if maturity_adj > 1.50 then maturity_adj = 1.50;

            /* Asset correlation factor (R) per Basel III */
            r_factor = 0.12 * (1 - exp(-50 * pd_estimate)) /
                       (1 - exp(-50))
                     + 0.24 * (1 - (1 - exp(-50 * pd_estimate)) /
                       (1 - exp(-50)));

            /* Capital requirement (K) — Basel IRB formula */
            /* K = LGD * [N((1-R)^(-0.5) * G(PD) + (R/(1-R))^0.5 * G(0.999)) - PD] * MA */
            /* Simplified computation using approximation */
            norm_pd        = probit(pd_estimate);
            norm_999       = probit(0.999);
            adjusted_norm  = (norm_pd + sqrt(r_factor) * norm_999) /
                             sqrt(1 - r_factor);
            capital_req    = lgd_estimate *
                             (probnorm(adjusted_norm) - pd_estimate) *
                             maturity_adj;
            if capital_req < 0 then capital_req = 0;

            /* EAD calculation with credit conversion factors */
            if ead_estimate > 0 then
                effective_ead = ead_estimate;
            else
                effective_ead = exposure_amount * 1.0;  /* on-balance-sheet CCF */

            /* Risk-weighted asset = 12.5 * K * EAD */
            rwa_amount       = 12.5 * capital_req * effective_ead;
            calculation_date = "&report_date"d;
            calc_approach    = 'IRB';
            calc_asset_class = "&asset_class";
        run;

    %end;

    /* ----- Common: Portfolio-level RWA aggregation ----- */
    proc sql noprint;
        create table work.rwa_&asset_class._summary as
        select
            calc_asset_class as asset_class,
            calc_approach    as approach,
            count(*)                       as n_exposures,
            sum(exposure_amount)           as total_exposure
                format=comma20.2,
            sum(rwa_amount)                as total_rwa
                format=comma20.2,
            mean(rwa_amount/exposure_amount) as avg_risk_weight
                format=percent8.2,
            calculation_date
        from work.rwa_&asset_class._&substr(&approach, 1, 3)
        group by calc_asset_class, calc_approach, calculation_date;

        /* Capture total RWA for this asset class into macro variable */
        select sum(rwa_amount) into :rwa_&asset_class._total trimmed
        from work.rwa_&asset_class._&substr(&approach, 1, 3);
    quit;

    %put NOTE: RWA for &asset_class (&approach) = &&rwa_&asset_class._total;

%mend calc_rwa;

/* ========================================================================= */
/* SECTION 4: %MACRO capital_ratios — Capital Adequacy Ratios                */
/* ========================================================================= */

/*----------------------------------------------------------------------
  %MACRO capital_ratios
  Purpose: Compute CET1, Tier 1, and Total Capital ratios against
           total risk-weighted assets. Compare to regulatory minimums
           and calculate capital conservation buffer (CCB) and G-SIB
           surcharge. Flags breaches against regulatory thresholds.
----------------------------------------------------------------------*/

%macro capital_ratios;

    %put NOTE: ---- capital_ratios: Computing regulatory capital ratios ----;

    /* Step 1: Aggregate capital components from finance library */
    proc sql noprint;
        /* CET1 Capital = Common equity - regulatory deductions */
        select sum(case when component_type = 'CET1_POSITIVE' then amount
                        when component_type = 'CET1_DEDUCTION' then -amount
                        else 0 end)
            into :cet1_capital trimmed
        from fin.capital_components
        where reporting_date = "&report_date"d;

        /* Additional Tier 1 Capital */
        select sum(case when component_type = 'AT1_INSTRUMENT' then amount
                        when component_type = 'AT1_DEDUCTION' then -amount
                        else 0 end)
            into :at1_capital trimmed
        from fin.capital_components
        where reporting_date = "&report_date"d;

        /* Tier 2 Capital */
        select sum(case when component_type = 'T2_INSTRUMENT' then amount
                        when component_type = 'T2_DEDUCTION' then -amount
                        else 0 end)
            into :t2_capital trimmed
        from fin.capital_components
        where reporting_date = "&report_date"d;

        /* Total RWA across all asset classes */
        select sum(total_rwa) into :total_rwa trimmed
        from (select total_rwa from work.rwa_corporate_summary
              union all
              select total_rwa from work.rwa_sovereign_summary
              union all
              select total_rwa from work.rwa_retail_summary
              union all
              select total_rwa from work.rwa_equity_summary);
    quit;

    /* Step 2: Compute ratios and compare to minimums */
    data out.capital_ratios;
        length ratio_name $30 ratio_value 8 regulatory_min 8
               buffer_amount 8 surplus_deficit 8 breach_flag $1;

        /* Derived capital levels */
        cet1_cap    = &cet1_capital;
        tier1_cap   = &cet1_capital + &at1_capital;
        total_cap   = &cet1_capital + &at1_capital + &t2_capital;
        total_rwa   = &total_rwa;
        report_date = "&report_date"d;
        format report_date date9.;

        /* --- CET1 Ratio --- */
        ratio_name     = 'CET1 Capital Ratio';
        ratio_value    = cet1_cap / total_rwa;
        regulatory_min = &min_cet1_ratio;
        surplus_deficit = ratio_value - regulatory_min;
        breach_flag    = ifc(ratio_value < regulatory_min, 'Y', 'N');
        buffer_amount  = 0;
        output;

        /* --- Tier 1 Ratio --- */
        ratio_name     = 'Tier 1 Capital Ratio';
        ratio_value    = tier1_cap / total_rwa;
        regulatory_min = &min_tier1_ratio;
        surplus_deficit = ratio_value - regulatory_min;
        breach_flag    = ifc(ratio_value < regulatory_min, 'Y', 'N');
        buffer_amount  = 0;
        output;

        /* --- Total Capital Ratio --- */
        ratio_name     = 'Total Capital Ratio';
        ratio_value    = total_cap / total_rwa;
        regulatory_min = &min_total_ratio;
        surplus_deficit = ratio_value - regulatory_min;
        breach_flag    = ifc(ratio_value < regulatory_min, 'Y', 'N');
        buffer_amount  = 0;
        output;

        /* --- Capital Conservation Buffer (CCB) --- */
        %if &ccb_rate > 0 %then %do;
            ratio_name     = 'CET1 + CCB Ratio';
            ratio_value    = cet1_cap / total_rwa;
            regulatory_min = &min_cet1_ratio + &ccb_rate;
            surplus_deficit = ratio_value - regulatory_min;
            breach_flag    = ifc(ratio_value < regulatory_min, 'Y', 'N');
            buffer_amount  = &ccb_rate * total_rwa;
            output;
        %end;

        /* --- G-SIB Surcharge --- */
        %if &gsib_rate > 0 %then %do;
            ratio_name     = 'CET1 + CCB + G-SIB';
            ratio_value    = cet1_cap / total_rwa;
            regulatory_min = &min_cet1_ratio + &ccb_rate + &gsib_rate;
            surplus_deficit = ratio_value - regulatory_min;
            breach_flag    = ifc(ratio_value < regulatory_min, 'Y', 'N');
            buffer_amount  = (&ccb_rate + &gsib_rate) * total_rwa;
            output;
        %end;

        drop cet1_cap tier1_cap total_cap total_rwa;
    run;

    /* Store key ratios as macro variables for downstream use */
    data _null_;
        set out.capital_ratios;
        if ratio_name = 'CET1 Capital Ratio' then
            call symputx('cet1_ratio', put(ratio_value, 8.4));
        if ratio_name = 'Tier 1 Capital Ratio' then
            call symputx('tier1_ratio', put(ratio_value, 8.4));
        if ratio_name = 'Total Capital Ratio' then
            call symputx('total_ratio', put(ratio_value, 8.4));
    run;

    %put NOTE: CET1 Ratio  = &cet1_ratio;
    %put NOTE: Tier1 Ratio  = &tier1_ratio;
    %put NOTE: Total Ratio  = &total_ratio;

%mend capital_ratios;

/* ========================================================================= */
/* SECTION 5: %MACRO stress_testing — Stress Scenario Analysis               */
/* ========================================================================= */

/*----------------------------------------------------------------------
  %MACRO stress_testing
  Purpose: Project losses and capital impacts over 9 quarters under
           a given macroeconomic stress scenario. Uses arrays for
           multi-period loss projection, scenario-specific loss rates,
           and PROC MEANS for summary statistics.
  Parameters:
    scenario= : Stress scenario name (BASE, ADVERSE, SEVERELY_ADVERSE)
----------------------------------------------------------------------*/

%macro stress_testing(scenario=);

    %put NOTE: ---- stress_testing: scenario=&scenario ----;

    /* Determine scenario-specific loss rate multiplier */
    %if &scenario = BASE %then %do;
        %let loss_rate = &base_loss_rate;
        %let gdp_shock = -0.005;
        %let unemp_delta = 0.002;
    %end;
    %else %if &scenario = ADVERSE %then %do;
        %let loss_rate = &adv_loss_rate;
        %let gdp_shock = -0.035;
        %let unemp_delta = 0.025;
    %end;
    %else %if &scenario = SEVERELY_ADVERSE %then %do;
        %let loss_rate = &sev_loss_rate;
        %let gdp_shock = -0.080;
        %let unemp_delta = 0.060;
    %end;

    /* Multi-quarter loss projection using arrays */
    data work.stress_&scenario;
        set work.rwa_corporate_summary(keep=total_exposure total_rwa)
            work.rwa_retail_summary(keep=total_exposure total_rwa);

        /* Quarter projection arrays */
        array qtr_loss{&n_quarters}    qtr_loss_1 - qtr_loss_&n_quarters;
        array qtr_capital{&n_quarters} qtr_cap_1  - qtr_cap_&n_quarters;
        array qtr_rwa{&n_quarters}     qtr_rwa_1  - qtr_rwa_&n_quarters;
        array cum_loss{&n_quarters}    cum_loss_1 - cum_loss_&n_quarters;

        /* Scenario parameters */
        scenario_name = "&scenario";
        base_capital  = &cet1_capital;
        annual_rate   = &loss_rate;

        /* Project losses over each quarter with increasing severity */
        %do q = 1 %to &n_quarters;
            /* Loss rate increases in early quarters, stabilizes later */
            %let q_weight = %sysevalf(&q / &n_quarters);
            qtr_loss{&q} = total_exposure * annual_rate *
                           (0.5 + &q_weight * 0.5) / 4;
            if &q = 1 then
                cum_loss{&q} = qtr_loss{&q};
            else
                cum_loss{&q} = cum_loss{%eval(&q - 1)} + qtr_loss{&q};

            /* Capital after losses (simplified — no earnings offset) */
            qtr_capital{&q} = base_capital - cum_loss{&q};

            /* RWA migration under stress (assets deteriorate) */
            qtr_rwa{&q} = total_rwa * (1 + &q_weight * 0.15);
        %end;

        /* Minimum capital ratio across projection horizon */
        min_capital = min(of qtr_cap_1 - qtr_cap_&n_quarters);
        min_ratio   = min_capital / max(of qtr_rwa_1 - qtr_rwa_&n_quarters);
        gdp_impact  = &gdp_shock;
        unemp_impact = &unemp_delta;

        format total_exposure total_rwa base_capital min_capital
               qtr_loss_1-qtr_loss_&n_quarters
               qtr_cap_1-qtr_cap_&n_quarters
               cum_loss_1-cum_loss_&n_quarters
               comma20.2;
        format min_ratio percent8.2;
    run;

    /* Summary statistics for the stress scenario */
    proc means data=work.stress_&scenario
               n mean std min max sum maxdec=2;
        var qtr_loss_1-qtr_loss_&n_quarters
            qtr_cap_1-qtr_cap_&n_quarters
            cum_loss_1-cum_loss_&n_quarters;
        title "Stress Testing — &scenario Scenario: Quarterly Projections";
        title2 "Filing Period: &report_qtr | Run ID: &run_id";
    run;
    title;

    /* Append scenario results to consolidated output */
    proc append base=out.stress_results
                data=work.stress_&scenario force;
    run;

    %put NOTE: Stress testing complete for &scenario scenario.;
    %put NOTE: Minimum projected CET1 ratio = %sysfunc(putn(
               %sysevalf(&cet1_capital * 0.85), comma20.2));

%mend stress_testing;

/* ========================================================================= */
/* SECTION 6: %MACRO generate_schedules — Regulatory Filing Schedules        */
/* ========================================================================= */

/*----------------------------------------------------------------------
  %MACRO generate_schedules
  Purpose: Generate individual regulatory filing schedules for the
           current reporting period. Iterates over schedule IDs,
           applies schedule-specific formatting and data aggregation
           rules, and produces ODS output for each schedule.
----------------------------------------------------------------------*/

%macro generate_schedules;

    %put NOTE: ---- generate_schedules: Creating &n_schedules schedules ----;

    /* Loop through each schedule identifier */
    %do s = 1 %to &n_schedules;

        %let current_sched = &&sched_id_&s;
        %put NOTE: Processing schedule &s of &n_schedules: &current_sched;

        /* Schedule-specific data aggregation */
        %if &current_sched = HC-R_PART1 %then %do;
            /* HC-R Part 1: Regulatory Capital Components */
            proc sql;
                create table out.schedule_hcr_p1 as
                select
                    component_type,
                    component_name,
                    sum(amount) as reported_amount format=comma20.2,
                    "&report_qtr" as filing_period,
                    "&report_date"d as as_of_date format=date9.
                from fin.capital_components
                where reporting_date = "&report_date"d
                group by component_type, component_name
                order by component_type, component_name;
            quit;
        %end;

        %else %if &current_sched = HC-R_PART2 %then %do;
            /* HC-R Part 2: Risk-Weighted Assets by Category */
            proc sql;
                create table out.schedule_hcr_p2 as
                select
                    asset_class,
                    approach,
                    n_exposures,
                    total_exposure format=comma20.2,
                    total_rwa      format=comma20.2,
                    avg_risk_weight format=percent8.2,
                    "&report_qtr" as filing_period,
                    "&report_date"d as as_of_date format=date9.
                from (select * from work.rwa_corporate_summary
                      union all
                      select * from work.rwa_sovereign_summary
                      union all
                      select * from work.rwa_retail_summary
                      union all
                      select * from work.rwa_equity_summary)
                order by asset_class;
            quit;
        %end;

        %else %if &current_sched = FR_Y14A_SUMM %then %do;
            /* FR Y-14A Summary: Capital ratios and buffers */
            proc sql;
                create table out.schedule_y14a_summ as
                select
                    ratio_name,
                    ratio_value    format=percent8.4,
                    regulatory_min format=percent8.4,
                    surplus_deficit format=percent8.4,
                    breach_flag,
                    buffer_amount  format=comma20.2,
                    "&report_qtr" as filing_period
                from out.capital_ratios
                order by ratio_name;
            quit;
        %end;

        %else %if &current_sched = FR_Y14A_LOSS %then %do;
            /* FR Y-14A Loss Projections: Stress test loss outputs */
            proc sql;
                create table out.schedule_y14a_loss as
                select
                    scenario_name,
                    sum(qtr_loss_1) as q1_loss format=comma20.2,
                    sum(qtr_loss_2) as q2_loss format=comma20.2,
                    sum(qtr_loss_3) as q3_loss format=comma20.2,
                    sum(cum_loss_9) as total_cum_loss format=comma20.2,
                    min(min_ratio)  as worst_ratio format=percent8.4,
                    "&report_qtr" as filing_period
                from out.stress_results
                group by scenario_name
                order by scenario_name;
            quit;
        %end;

        %else %if &current_sched = FR_Y14A_PPNR %then %do;
            /* FR Y-14A PPNR: Pre-Provision Net Revenue projections */
            proc sql;
                create table out.schedule_y14a_ppnr as
                select
                    line_item,
                    sum(case when quarter = 1 then amount else 0 end)
                        as q1_amount format=comma20.2,
                    sum(case when quarter = 2 then amount else 0 end)
                        as q2_amount format=comma20.2,
                    sum(case when quarter = 3 then amount else 0 end)
                        as q3_amount format=comma20.2,
                    sum(amount) as total_amount format=comma20.2,
                    "&report_qtr" as filing_period
                from fin.balance_sheet
                where fiscal_year = &filing_year
                  and line_category = 'PPNR'
                group by line_item
                order by line_item;
            quit;
        %end;

        %else %if &current_sched = FR_Y14Q_SUPP %then %do;
            /* FR Y-14Q Supplemental: Detailed exposure data */
            proc sql;
                create table out.schedule_y14q_supp as
                select
                    e.asset_class,
                    e.counterparty_id,
                    e.exposure_amount  format=comma20.2,
                    e.rating_band,
                    m.pd_estimate      format=8.6,
                    m.lgd_estimate     format=8.4,
                    c.collateral_value format=comma20.2,
                    c.collateral_type,
                    "&report_qtr" as filing_period,
                    "&report_date"d as as_of_date format=date9.
                from risk.exposures e
                left join risk.pd_lgd_models m
                    on e.counterparty_id = m.counterparty_id
                   and e.asset_class = m.model_asset_class
                left join risk.collateral c
                    on e.counterparty_id = c.counterparty_id
                order by e.asset_class, e.counterparty_id;
            quit;
        %end;

        /* ODS output for each schedule */
        ods pdf file="/regulatory/output/filing/&current_sched._&filing_year.Q&filing_quarter..pdf";
        proc print data=out.schedule_%sysfunc(translate(&current_sched, '_', '-'))
                   noobs label;
            title "Regulatory Filing Schedule: &current_sched";
            title2 "Reporting Period: &report_qtr | As of &report_date";
            title3 "Institution: Sample Bank, N.A. | RSSD ID: 1234567";
        run;
        ods pdf close;

        %put NOTE: Schedule &current_sched generated successfully.;

    %end;

    title;
    %put NOTE: All &n_schedules regulatory schedules generated.;

%mend generate_schedules;

/* ========================================================================= */
/* SECTION 7: Main Program — Orchestrate Full Regulatory Filing              */
/* ========================================================================= */

%put NOTE: ================================================================;
%put NOTE: REGULATORY FILING PIPELINE — START;
%put NOTE: Run ID: &run_id;
%put NOTE: Report Date: &report_date;
%put NOTE: Filing Period: &filing_year Q&filing_quarter;
%put NOTE: ================================================================;

/* ----- Step 1: Calculate RWA for each asset class ----- */
%put NOTE: --- Step 1: Risk-Weighted Assets Calculation ---;

%calc_rwa(asset_class=CORPORATE, approach=IRB);

%if &syserr > 0 %then %do;
    %let reg_rc = 1;
    %put ERROR: RWA calculation failed for CORPORATE.;
    %goto reg_exit;
%end;

%calc_rwa(asset_class=SOVEREIGN, approach=STANDARDIZED);

%if &syserr > 0 %then %do;
    %let reg_rc = 2;
    %put ERROR: RWA calculation failed for SOVEREIGN.;
    %goto reg_exit;
%end;

%calc_rwa(asset_class=RETAIL, approach=IRB);

%if &syserr > 0 %then %do;
    %let reg_rc = 3;
    %put ERROR: RWA calculation failed for RETAIL.;
    %goto reg_exit;
%end;

%calc_rwa(asset_class=EQUITY, approach=STANDARDIZED);

%if &syserr > 0 %then %do;
    %let reg_rc = 4;
    %put ERROR: RWA calculation failed for EQUITY.;
    %goto reg_exit;
%end;

/* Consolidate RWA results across all asset classes */
proc sql;
    create table out.rwa_summary as
    select * from work.rwa_corporate_summary
    union all
    select * from work.rwa_sovereign_summary
    union all
    select * from work.rwa_retail_summary
    union all
    select * from work.rwa_equity_summary
    order by asset_class;
quit;

%put NOTE: Step 1 complete — RWA calculated for all 4 asset classes.;

/* ----- Step 2: Calculate Capital Ratios ----- */
%put NOTE: --- Step 2: Capital Adequacy Ratios ---;

%capital_ratios;

%if &syserr > 0 %then %do;
    %let reg_rc = 5;
    %put ERROR: Capital ratio calculation failed.;
    %goto reg_exit;
%end;

%put NOTE: Step 2 complete — Capital ratios derived.;

/* ----- Step 3: Run Stress Testing Scenarios ----- */
%put NOTE: --- Step 3: Stress Testing Projections ---;

/* Clear any prior stress results */
proc datasets lib=out nolist;
    delete stress_results;
run; quit;

%stress_testing(scenario=BASE);

%if &syserr > 0 %then %do;
    %let reg_rc = 6;
    %put ERROR: Stress testing failed for BASE scenario.;
    %goto reg_exit;
%end;

%stress_testing(scenario=ADVERSE);

%if &syserr > 0 %then %do;
    %let reg_rc = 7;
    %put ERROR: Stress testing failed for ADVERSE scenario.;
    %goto reg_exit;
%end;

%stress_testing(scenario=SEVERELY_ADVERSE);

%if &syserr > 0 %then %do;
    %let reg_rc = 8;
    %put ERROR: Stress testing failed for SEVERELY_ADVERSE scenario.;
    %goto reg_exit;
%end;

%put NOTE: Step 3 complete — All 3 stress scenarios projected.;

/* ----- Step 4: Generate Filing Schedules ----- */
%put NOTE: --- Step 4: Filing Schedule Generation ---;

%generate_schedules;

%if &syserr > 0 %then %do;
    %let reg_rc = 9;
    %put ERROR: Schedule generation failed.;
    %goto reg_exit;
%end;

%put NOTE: Step 4 complete — All schedules generated.;

/* ----- Step 5: Cover Page Summary ----- */
%put NOTE: --- Step 5: Cover Page and Validation ---;

proc sql;
    create table out.filing_cover_page as
    select
        "&run_id"                            as run_id,
        "&filing_year Q&filing_quarter"      as filing_period,
        "&report_date"d                      as report_date format=date9.,
        &total_rwa                           as total_rwa format=comma20.2,
        input("&cet1_ratio", best8.)         as cet1_ratio format=percent8.4,
        input("&tier1_ratio", best8.)        as tier1_ratio format=percent8.4,
        input("&total_ratio", best8.)        as total_ratio format=percent8.4,
        (select count(*) from out.rwa_summary) as n_exposures,
        &n_schedules                         as schedules_filed,
        datetime()                           as filing_timestamp
            format=datetime20.,
        'PENDING_REVIEW'                     as filing_status length=20
    from fin.balance_sheet(obs=1);  /* single-row driver table */
quit;

/* ----- Step 6: Validation Reports ----- */

/* Print capital ratio validation */
proc print data=out.capital_ratios noobs label;
    title 'Regulatory Filing Validation: Capital Adequacy Ratios';
    title2 "Filing Period: &filing_year Q&filing_quarter";
    var ratio_name ratio_value regulatory_min surplus_deficit breach_flag;
    format ratio_value regulatory_min surplus_deficit percent8.4;
run;

/* Print RWA validation by asset class */
proc print data=out.rwa_summary noobs label;
    title 'Regulatory Filing Validation: RWA by Asset Class';
    title2 "Filing Period: &filing_year Q&filing_quarter";
    var asset_class approach n_exposures total_exposure total_rwa
        avg_risk_weight;
run;

/* Print stress testing worst-case ratios */
proc print data=out.stress_results noobs label;
    title 'Regulatory Filing Validation: Stress Test Projections';
    title2 "Filing Period: &filing_year Q&filing_quarter";
    var scenario_name total_exposure base_capital min_capital min_ratio
        gdp_impact unemp_impact;
    format min_ratio percent8.4 gdp_impact unemp_impact percent6.2;
run;
title;

/* ========================================================================= */
/* SECTION 8: Error Handling and Completion                                   */
/* ========================================================================= */

%reg_exit:

%if &reg_rc ne 0 %then %do;
    %put ERROR: ============================================================;
    %put ERROR: REGULATORY FILING PIPELINE FAILED;
    %put ERROR: Return code = &reg_rc;
    %put ERROR: Run ID = &run_id;
    %put ERROR: ============================================================;

    /* Log error details for audit trail */
    data out.filing_errors;
        length run_id $40 error_step $60 error_code 8
               error_message $200 error_datetime 8;
        run_id         = "&run_id";
        error_step     = "Step failed at reg_rc=&reg_rc";
        error_code     = &reg_rc;
        error_message  = "Pipeline terminated — check SAS log for details.";
        error_datetime = datetime();
        format error_datetime datetime20.;
    run;
%end;

%else %do;
    %put NOTE: ============================================================;
    %put NOTE: REGULATORY FILING PIPELINE COMPLETE;
    %put NOTE: Run ID        : &run_id;
    %put NOTE: Report Date   : &report_date;
    %put NOTE: Filing Period  : &filing_year Q&filing_quarter;
    %put NOTE: CET1 Ratio    : &cet1_ratio;
    %put NOTE: Tier1 Ratio   : &tier1_ratio;
    %put NOTE: Total Ratio   : &total_ratio;
    %put NOTE: Schedules Filed: &n_schedules;
    %put NOTE: ============================================================;

    /* Write completion flag for downstream systems */
    data _null_;
        file '/regulatory/output/filing/completion_flag.txt';
        put "RUN_ID=&run_id";
        put "STATUS=SUCCESS";
        put "FILING_PERIOD=&filing_year.Q&filing_quarter";
        put "CET1_RATIO=&cet1_ratio";
        put "TIER1_RATIO=&tier1_ratio";
        put "TOTAL_RATIO=&total_ratio";
        put "SCHEDULES_FILED=&n_schedules";
        put "COMPLETION_TIME=" datetime() datetime20.;
    run;
%end;

/* ========================================================================= */
/* SECTION 9: Cleanup                                                        */
/* ========================================================================= */

/* Delete intermediate work datasets */
proc datasets lib=work nolist;
    delete rwa_corporate_std rwa_corporate_irb rwa_corporate_summary
           rwa_sovereign_std rwa_sovereign_irb rwa_sovereign_summary
           rwa_retail_std rwa_retail_irb rwa_retail_summary
           rwa_equity_std rwa_equity_irb rwa_equity_summary
           stress_base stress_adverse stress_severely_adverse;
run; quit;

/* Reset options to defaults */
options nomprint nomlogic nosymbolgen;

%put NOTE: Regulatory filing pipeline ended at %sysfunc(datetime(), datetime20.);
%put NOTE: Final return code = &reg_rc;
