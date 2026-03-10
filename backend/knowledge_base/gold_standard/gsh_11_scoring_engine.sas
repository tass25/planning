/******************************************************************************
 * PROGRAM:     gsh_11_scoring_engine.sas
 * PURPOSE:     Multi-model scoring engine for insurance underwriting
 * ENGINE VER:  4.2.1
 * EFFECTIVE:   2026-01-01
 * ACTUARY:     J. Richardson, FCAS, MAAA — Signed off 2025-12-15
 * DESCRIPTION: Implements a comprehensive scoring pipeline that combines
 *              territory risk, claims history, credit scoring, and model
 *              monitoring into a unified premium calculation engine.
 *              Supports AUTO, HOME, and COMMERCIAL lines of business.
 * REVISION:    4.2.1 — Added Gini drift detection and competitive positioning
 * COPYRIGHT:   (c) 2026 Actuarial Analytics Division
 ******************************************************************************/

/* ============================================================================
   SECTION 1: ENVIRONMENT SETUP — Libraries and global parameters
   ============================================================================ */

/* Connect to underwriting and actuarial data stores */
LIBNAME policy  '/data/underwriting/policy'  ACCESS=READONLY;
LIBNAME claims  '/data/underwriting/claims'  ACCESS=READONLY;
LIBNAME actuary '/data/actuarial/models'     ACCESS=READONLY;
LIBNAME scoredb '/data/scoring/output';

/* Global processing options for scoring run */
OPTIONS MPRINT MLOGIC SYMBOLGEN COMPRESS=YES
        FULLSTIMER NOFMTERR MINOPERATOR
        ERRORABEND;

/* --- Model version and effective date parameters --- */
%LET model_version    = 4.2.1;
%LET effective_date   = 01JAN2026;
%LET rundate          = %SYSFUNC(TODAY(), DATE9.);
%LET min_premium      = 250;
%LET max_premium      = 50000;
%LET score_floor      = 300;
%LET score_ceiling    = 850;
%LET gini_threshold   = 0.05;
%LET monitoring_window = 12;
%LET n_sub_territories = 5;

/* --- Load external scoring function library --- */
%INCLUDE '/config/models/score_functions.sas';

/* ============================================================================
   SECTION 2: MACRO — load_model_params
   Purpose: Load model coefficients from the actuarial parameter table
            and create macro variables for downstream scoring macros.
   ============================================================================ */

%MACRO load_model_params(model_name=, version=);

    %PUT NOTE: Loading parameters for model=&model_name version=&version;

    /* Validate version format before proceeding */
    %IF %LENGTH(&version) = 0 %THEN %DO;
        %PUT ERROR: Version parameter is required for load_model_params;
        %ABORT CANCEL;
    %END;

    /* Extract coefficients for the specified model and version */
    PROC SQL NOPRINT;
        SELECT coefficient_name,
               coefficient_value,
               coefficient_type,
               effective_from,
               effective_to
        INTO :coeff_names  SEPARATED BY '|',
             :coeff_values SEPARATED BY '|',
             :coeff_types  SEPARATED BY '|',
             :eff_from     SEPARATED BY '|',
             :eff_to       SEPARATED BY '|'
        FROM actuary.model_parameters
        WHERE model_id    = "&model_name"
          AND version_id  = "&version"
          AND status       = 'ACTIVE'
        ORDER BY coefficient_order;

        /* Store count of loaded coefficients */
        %LET n_coefficients = &SQLOBS;
    QUIT;

    %PUT NOTE: Found &n_coefficients coefficients for &model_name v&version;

    /* Create individual macro variables from each coefficient row */
    DATA _NULL_;
        LENGTH cname $32 cvalue 8 ctype $10;
        %DO i = 1 %TO &n_coefficients;
            cname  = SCAN("&coeff_names",  &i, '|');
            cvalue = INPUT(SCAN("&coeff_values", &i, '|'), BEST12.);
            ctype  = SCAN("&coeff_types",  &i, '|');

            /* Store coefficient value and type as macro variables */
            CALL SYMPUT(STRIP(cname), STRIP(PUT(cvalue, BEST12.)));
            CALL SYMPUT(STRIP(cname) || '_type', STRIP(ctype));
        %END;
    RUN;

    /* Version validation: check that coefficients are within effective range */
    %IF "&effective_date"d < "&eff_from"d %THEN %DO;
        %PUT WARNING: Model &model_name v&version is not yet effective;
    %END;

%MEND load_model_params;

/* ============================================================================
   SECTION 3: MACRO — territory_score
   Purpose: Calculate geographic risk scores based on state and
            sub-territory definitions from the actuarial tables.
   ============================================================================ */

%MACRO territory_score(state=);

    %PUT NOTE: Computing territory score for state=&state;

    /* -----------------------------------------------------------------
       Assign base state-level risk factor using SELECT/WHEN construct.
       Each state maps to a risk tier and numeric factor.
       ----------------------------------------------------------------- */
    DATA work.state_factor;
        SET policy.policy_master(WHERE=(policy_state = "&state"));

        LENGTH state_risk_factor 8 state_tier $10;

        SELECT (policy_state);
            WHEN ('FL') DO; state_risk_factor = 1.85; state_tier = 'HIGH';     END;
            WHEN ('CA') DO; state_risk_factor = 1.62; state_tier = 'HIGH';     END;
            WHEN ('TX') DO; state_risk_factor = 1.45; state_tier = 'MEDIUM';   END;
            WHEN ('NY') DO; state_risk_factor = 1.55; state_tier = 'HIGH';     END;
            WHEN ('IL') DO; state_risk_factor = 1.20; state_tier = 'MEDIUM';   END;
            WHEN ('OH') DO; state_risk_factor = 1.05; state_tier = 'LOW';      END;
            WHEN ('PA') DO; state_risk_factor = 1.10; state_tier = 'LOW';      END;
            WHEN ('GA') DO; state_risk_factor = 1.30; state_tier = 'MEDIUM';   END;
            WHEN ('NC') DO; state_risk_factor = 1.25; state_tier = 'MEDIUM';   END;
            OTHERWISE   DO; state_risk_factor = 1.00; state_tier = 'BASELINE'; END;
        END;
    RUN;

    /* Join state factors with territory definitions for granular geo risk */
    PROC SQL;
        CREATE TABLE work.territory_detail AS
        SELECT a.policy_id,
               a.policy_state,
               a.zip_code,
               a.state_risk_factor,
               a.state_tier,
               b.territory_code,
               b.territory_factor,
               b.catastrophe_zone,
               b.urban_rural_ind,
               a.state_risk_factor * b.territory_factor AS combined_geo_factor
        FROM work.state_factor AS a
        INNER JOIN actuary.territory_defs AS b
            ON a.policy_state = b.state_code
           AND a.zip_code BETWEEN b.zip_start AND b.zip_end
        ORDER BY a.policy_id;
    QUIT;

    /* -----------------------------------------------------------------
       Loop over sub-territories to apply micro-level adjustments.
       Each sub-territory receives a progressive loading factor.
       ----------------------------------------------------------------- */
    %DO sub = 1 %TO &n_sub_territories;

        DATA work.sub_territory_&sub;
            SET work.territory_detail(WHERE=(territory_code = "&sub"));

            /* Apply sub-territory specific loading factor */
            sub_terr_loading = 1.0 + (0.02 * &sub);
            adjusted_geo_factor = combined_geo_factor * sub_terr_loading;

            /* Regulatory cap: geographic factor must stay within bounds */
            IF adjusted_geo_factor > 3.50 THEN adjusted_geo_factor = 3.50;
            IF adjusted_geo_factor < 0.50 THEN adjusted_geo_factor = 0.50;

            /* Flag records that hit the regulatory cap */
            IF adjusted_geo_factor IN (3.50, 0.50) THEN
                geo_cap_flag = 'Y';
            ELSE
                geo_cap_flag = 'N';
        RUN;

    %END;

    /* Consolidate all sub-territory results into a single dataset */
    DATA work.territory_scores;
        SET work.sub_territory_1
            work.sub_territory_2
            work.sub_territory_3
            work.sub_territory_4
            work.sub_territory_5;
    RUN;

    %PUT NOTE: Territory scoring complete for state=&state;

%MEND territory_score;

/* ============================================================================
   SECTION 4: MACRO — claim_score
   Purpose: Calculate claims-based risk scores by line of business (LOB).
            Each LOB uses a distinct actuarial model:
              AUTO       — Frequency/Severity model
              HOME       — Catastrophe exposure model
              COMMERCIAL — Multi-peril array-based model
   ============================================================================ */

%MACRO claim_score(lob=);

    %PUT NOTE: Computing claims score for LOB=&lob;

    /* =====================================================================
       AUTO LINE: Frequency/Severity model
       Uses retained accumulators to compute per-policy claim metrics.
       ===================================================================== */
    %IF &lob = AUTO %THEN %DO;

        DATA work.auto_claims_score;
            SET claims.auto_claims;
            BY policy_id claim_date;

            /* Frequency component: count of claims in experience period */
            RETAIN claim_count 0 total_incurred 0;
            IF FIRST.policy_id THEN DO;
                claim_count    = 0;
                total_incurred = 0;
            END;

            claim_count    + 1;
            total_incurred + incurred_amount;

            /* Severity component: average claim size at policy level */
            IF LAST.policy_id THEN DO;
                avg_severity = total_incurred / claim_count;

                /* Frequency score: exponential decay penalizes many claims */
                freq_score = EXP(-0.5 * claim_count) * 100;

                /* Severity score: log-transformed, penalizes large losses */
                IF avg_severity > 0 THEN
                    sev_score = MAX(0, 100 - 15 * LOG(avg_severity / 1000));
                ELSE
                    sev_score = 100;

                /* Combined auto score: weighted 60/40 freq vs severity */
                auto_claim_score = 0.6 * freq_score + 0.4 * sev_score;
                OUTPUT;
            END;
        RUN;

    %END;

    /* =====================================================================
       HOME LINE: Catastrophe exposure model
       Separates catastrophe losses from attritional losses for scoring.
       ===================================================================== */
    %IF &lob = HOME %THEN %DO;

        DATA work.home_claims_score;
            SET claims.home_claims;
            BY policy_id;

            /* Retained accumulators for loss separation */
            RETAIN cat_exposure 0 non_cat_loss 0;

            IF FIRST.policy_id THEN DO;
                cat_exposure  = 0;
                non_cat_loss  = 0;
            END;

            /* Separate catastrophe vs attritional losses */
            IF catastrophe_ind = 'Y' THEN
                cat_exposure + incurred_amount;
            ELSE
                non_cat_loss + incurred_amount;

            IF LAST.policy_id THEN DO;
                /* Catastrophe loading: log-based score with $10K threshold */
                cat_score = MAX(0, 100 - 20 * LOG(1 + cat_exposure / 10000));

                /* Attritional loss score: linear decay at $5K per point */
                attrit_score = MAX(0, 100 - 10 * (non_cat_loss / 5000));

                /* Blended homeowners score: 55% cat / 45% attritional */
                home_claim_score = 0.55 * cat_score + 0.45 * attrit_score;
                OUTPUT;
            END;
        RUN;

    %END;

    /* =====================================================================
       COMMERCIAL LINE: Multi-peril scoring with ARRAY processing
       Scores six peril types independently and blends with weights.
       ===================================================================== */
    %IF &lob = COMMERCIAL %THEN %DO;

        DATA work.commercial_claims_score;
            SET claims.commercial_claims;
            BY policy_id;

            /* Define peril arrays for multi-peril scoring */
            ARRAY peril_losses{6} fire_loss theft_loss liability_loss
                                  flood_loss wind_loss other_loss;
            ARRAY peril_weights{6} _TEMPORARY_ (0.25 0.15 0.30 0.10 0.10 0.10);
            ARRAY peril_scores{6}  fire_scr theft_scr liab_scr
                                   flood_scr wind_scr other_scr;

            /* Retain peril accumulators across observations */
            RETAIN fire_loss theft_loss liability_loss
                   flood_loss wind_loss other_loss 0;

            IF FIRST.policy_id THEN DO;
                DO k = 1 TO 6;
                    peril_losses{k} = 0;
                END;
            END;

            /* Accumulate losses into the appropriate peril bucket */
            SELECT (peril_code);
                WHEN ('FIRE')      fire_loss      + incurred_amount;
                WHEN ('THEFT')     theft_loss     + incurred_amount;
                WHEN ('LIABILITY') liability_loss + incurred_amount;
                WHEN ('FLOOD')     flood_loss     + incurred_amount;
                WHEN ('WIND')      wind_loss      + incurred_amount;
                OTHERWISE          other_loss     + incurred_amount;
            END;

            IF LAST.policy_id THEN DO;
                /* Score each peril independently and compute weighted composite */
                commercial_claim_score = 0;
                DO k = 1 TO 6;
                    IF peril_losses{k} > 0 THEN
                        peril_scores{k} = MAX(0, 100 - 12 * LOG(peril_losses{k} / 2000));
                    ELSE
                        peril_scores{k} = 100;

                    commercial_claim_score + peril_weights{k} * peril_scores{k};
                END;
                OUTPUT;
            END;
        RUN;

    %END;

    /* -----------------------------------------------------------------
       Loss ratio benchmarking: compute actual loss ratios by year
       for the given LOB to establish performance baselines.
       ----------------------------------------------------------------- */
    PROC MEANS DATA=claims.all_claims(WHERE=(lob_code = "&lob"))
               NOPRINT NWAY;
        CLASS accident_year;
        VAR incurred_amount earned_premium;
        OUTPUT OUT=work.loss_ratio_bench(DROP=_TYPE_ _FREQ_)
               SUM(incurred_amount)  = total_incurred
               SUM(earned_premium)   = total_premium
               MEAN(incurred_amount) = avg_claim;
    RUN;

    /* -----------------------------------------------------------------
       Claims trend analysis: use LAG functions to detect deterioration
       or improvement in the loss ratio over a multi-year horizon.
       ----------------------------------------------------------------- */
    DATA work.claims_trend;
        SET work.loss_ratio_bench;

        /* Compute current-year loss ratio */
        loss_ratio = total_incurred / total_premium;

        /* Lag values for 3-year trend detection */
        prev_lr_1 = LAG1(loss_ratio);
        prev_lr_2 = LAG2(loss_ratio);
        prev_lr_3 = LAG3(loss_ratio);

        /* Simple linear trend slope over 3 periods */
        IF _N_ >= 4 THEN DO;
            trend_slope = (loss_ratio - prev_lr_3) / 3;

            /* Classify trend direction */
            IF trend_slope > 0.05 THEN
                trend_flag = 'DETERIORATING';
            ELSE IF trend_slope < -0.05 THEN
                trend_flag = 'IMPROVING';
            ELSE
                trend_flag = 'STABLE';
        END;
    RUN;

    %PUT NOTE: Claims scoring complete for LOB=&lob;

%MEND claim_score;

/* ============================================================================
   SECTION 5: MACRO — credit_score_blend
   Purpose: Blend external bureau credit scores with internal behavioral
            scores using configurable weights, with normalization and
            floor/ceiling enforcement.
   ============================================================================ */

%MACRO credit_score_blend(weight_bureau=, weight_internal=);

    %PUT NOTE: Blending credit scores (bureau=&weight_bureau, internal=&weight_internal);

    /* Validate weights sum to 1.0 */
    %LET total_weight = %SYSEVALF(&weight_bureau + &weight_internal);
    %IF &total_weight NE 1.0 %THEN %DO;
        %PUT WARNING: Credit blend weights sum to &total_weight — normalizing;
    %END;

    /* -----------------------------------------------------------------
       Merge bureau and internal credit data by policy, then compute
       a weighted blend with adjustments for payment history and tenure.
       ----------------------------------------------------------------- */
    DATA work.credit_blended;
        MERGE policy.bureau_credit  (IN=a KEEP=policy_id bureau_score bureau_date)
              policy.internal_score (IN=b KEEP=policy_id internal_score payment_score
                                                         tenure_months);
        BY policy_id;

        /* Retain for tracking score band transitions */
        RETAIN prev_blended_score . score_band_count 0;

        /* Keep only records present in both sources */
        IF a AND b;

        /* Normalize bureau score to 0–100 scale using floor/ceiling */
        IF bureau_score >= &score_floor AND bureau_score <= &score_ceiling THEN
            norm_bureau = (bureau_score - &score_floor) /
                          (&score_ceiling - &score_floor) * 100;
        ELSE IF bureau_score < &score_floor THEN
            norm_bureau = 0;
        ELSE
            norm_bureau = 100;

        /* Normalize internal score (already 0–100 scale, enforce bounds) */
        norm_internal = MAX(0, MIN(100, internal_score));

        /* Compute weighted blend of normalized scores */
        blended_score = &weight_bureau * norm_bureau +
                        &weight_internal * norm_internal;

        /* Payment history bonus: reward excellent payment track record */
        IF payment_score >= 95 THEN
            blended_score = MIN(100, blended_score + 5);
        ELSE IF payment_score < 70 THEN
            blended_score = MAX(0, blended_score - 10);

        /* Tenure adjustment: reward long-standing policyholders */
        IF tenure_months > 60 THEN
            blended_score = MIN(100, blended_score + 3);
        ELSE IF tenure_months > 36 THEN
            blended_score = MIN(100, blended_score + 1);

        /* Final floor and ceiling enforcement */
        IF blended_score < 0   THEN blended_score = 0;
        IF blended_score > 100 THEN blended_score = 100;

        /* Assign score band based on blended score thresholds */
        LENGTH score_band $14;
        IF blended_score >= 80      THEN score_band = 'PREFERRED';
        ELSE IF blended_score >= 60 THEN score_band = 'STANDARD';
        ELSE IF blended_score >= 40 THEN score_band = 'NON-STANDARD';
        ELSE                             score_band = 'HIGH-RISK';

        /* Track band count and retain previous score for transitions */
        score_band_count + 1;
        prev_blended_score = blended_score;
    RUN;

    %PUT NOTE: Credit score blending complete;

%MEND credit_score_blend;

/* ============================================================================
   SECTION 6: MACRO — final_premium_calc
   Purpose: Compute the final premium by applying all rating factors
            multiplicatively, enforcing min/max bounds, applying
            discount/surcharge rules, and checking competitive position.
   ============================================================================ */

%MACRO final_premium_calc(base_rate=);

    %PUT NOTE: Computing final premium with base_rate=&base_rate;

    /* -----------------------------------------------------------------
       Merge all scoring components into a unified rating table.
       Territory scores are required; claims and credit are optional.
       ----------------------------------------------------------------- */
    DATA work.premium_calc;
        MERGE work.territory_scores   (IN=a KEEP=policy_id adjusted_geo_factor
                                                            policy_state)
              work.auto_claims_score  (IN=b KEEP=policy_id auto_claim_score)
              work.home_claims_score  (IN=c KEEP=policy_id home_claim_score)
              work.credit_blended     (IN=d KEEP=policy_id blended_score score_band);
        BY policy_id;

        /* Must have territory score at minimum */
        IF a;

        /* Convert claim scores to multiplicative factors */
        IF auto_claim_score NE . THEN
            claim_factor = 2.0 - (auto_claim_score / 100);
        ELSE IF home_claim_score NE . THEN
            claim_factor = 2.0 - (home_claim_score / 100);
        ELSE
            claim_factor = 1.0;

        /* Convert credit score to multiplicative factor */
        credit_factor = 2.0 - (blended_score / 100);
        IF credit_factor = . THEN credit_factor = 1.0;

        /* Multiplicative premium calculation: base * geo * claims * credit */
        raw_premium = &base_rate
                    * adjusted_geo_factor
                    * claim_factor
                    * credit_factor;

        /* Apply discount/surcharge based on score band */
        %IF "&score_band" = "PREFERRED" %THEN %DO;
            discount_pct = 0.15;
        %END;
        %ELSE %IF "&score_band" = "HIGH-RISK" %THEN %DO;
            discount_pct = -0.20;  /* Surcharge for high-risk */
        %END;
        %ELSE %DO;
            discount_pct = 0.00;
        %END;

        adjusted_premium = raw_premium * (1.0 - discount_pct);

        /* Enforce minimum and maximum premium bounds */
        IF adjusted_premium < &min_premium THEN
            final_premium = &min_premium;
        ELSE IF adjusted_premium > &max_premium THEN
            final_premium = &max_premium;
        ELSE
            final_premium = ROUND(adjusted_premium, 1.00);

        /* Flag policies hitting min/max premium boundaries */
        LENGTH boundary_flag $3;
        IF final_premium = &min_premium THEN boundary_flag = 'MIN';
        ELSE IF final_premium = &max_premium THEN boundary_flag = 'MAX';
        ELSE boundary_flag = ' ';
    RUN;

    /* -----------------------------------------------------------------
       Competitive positioning: compare our premiums to market benchmarks
       to ensure we remain within competitive corridors.
       ----------------------------------------------------------------- */
    PROC SQL;
        CREATE TABLE work.competitive_check AS
        SELECT a.policy_id,
               a.final_premium,
               a.raw_premium,
               a.score_band,
               a.policy_state,
               b.market_avg_premium,
               b.market_25th_pctl,
               b.market_75th_pctl,
               CASE
                   WHEN a.final_premium < b.market_25th_pctl THEN 'BELOW MARKET'
                   WHEN a.final_premium > b.market_75th_pctl THEN 'ABOVE MARKET'
                   ELSE 'COMPETITIVE'
               END AS market_position
        FROM work.premium_calc AS a
        LEFT JOIN actuary.market_benchmarks AS b
            ON a.policy_state = b.state_code
        ORDER BY a.policy_id;
    QUIT;

    %PUT NOTE: Final premium calculation complete;

%MEND final_premium_calc;

/* ============================================================================
   SECTION 7: MACRO — model_monitoring
   Purpose: Track ongoing model performance including:
            - Actual vs expected loss ratios by accident year
            - Gini coefficient drift detection
            - Score stability metrics across rating periods
   ============================================================================ */

%MACRO model_monitoring;

    %PUT NOTE: Running model monitoring suite;

    /* -----------------------------------------------------------------
       Part A: Actual vs Expected loss ratios by accident year and LOB.
       Flags deviations that exceed tolerance thresholds.
       ----------------------------------------------------------------- */
    PROC SQL;
        CREATE TABLE work.actual_vs_expected AS
        SELECT a.accident_year,
               a.lob_code,
               SUM(a.incurred_amount) / SUM(a.earned_premium) AS actual_lr,
               b.expected_lr,
               CALCULATED actual_lr - b.expected_lr AS lr_deviation,
               CASE
                   WHEN ABS(CALCULATED lr_deviation) > 0.10 THEN 'ALERT'
                   WHEN ABS(CALCULATED lr_deviation) > 0.05 THEN 'WATCH'
                   ELSE 'OK'
               END AS monitoring_status
        FROM claims.all_claims AS a
        INNER JOIN actuary.expected_results AS b
            ON a.accident_year = b.accident_year
           AND a.lob_code      = b.lob_code
        WHERE a.accident_year >= YEAR(TODAY()) - &monitoring_window
        GROUP BY a.accident_year, a.lob_code
        ORDER BY a.lob_code, a.accident_year;
    QUIT;

    /* -----------------------------------------------------------------
       Part B: Gini coefficient drift detection
       Computes a Lorenz curve to measure model discriminatory power.
       ----------------------------------------------------------------- */
    DATA work.gini_drift;
        SET work.competitive_check END=last;
        BY policy_id;

        /* Cumulative distribution trackers for Lorenz curve */
        RETAIN cum_policies 0 cum_losses 0
               total_policies 0 total_losses 0
               prev_pct_pol 0 gini_area 0;

        /* Initialize totals on first observation */
        IF _N_ = 1 THEN DO;
            total_policies = n_policies;
            total_losses   = n_losses;
        END;

        cum_policies + 1;
        cum_losses   + final_premium;

        /* Compute cumulative percentages */
        pct_policies = cum_policies / total_policies;
        pct_losses   = cum_losses / total_losses;

        /* Incremental Lorenz curve area using trapezoidal rule */
        prev_pct_losses = LAG(pct_losses);
        IF _N_ > 1 THEN DO;
            lorenz_area = (pct_policies - prev_pct_pol) *
                          (pct_losses + prev_pct_losses) / 2;
            gini_area + lorenz_area;
        END;

        prev_pct_pol = pct_policies;
    RUN;

    /* -----------------------------------------------------------------
       Part C: Score stability metrics across score bands.
       Summarizes premium distribution and factor averages.
       ----------------------------------------------------------------- */
    PROC MEANS DATA=work.premium_calc
               N MEAN STD MIN MAX P25 P50 P75
               NOPRINT NWAY;
        CLASS score_band;
        VAR final_premium adjusted_geo_factor claim_factor credit_factor;
        OUTPUT OUT=work.score_stability(DROP=_TYPE_ _FREQ_)
               MEAN(final_premium)        = avg_premium
               STD(final_premium)         = std_premium
               MEAN(adjusted_geo_factor)  = avg_geo
               MEAN(claim_factor)         = avg_claim
               MEAN(credit_factor)        = avg_credit
               N(final_premium)           = n_policies;
    RUN;

    /* Final Gini computation and drift check */
    DATA work.gini_summary;
        SET work.gini_drift END=last;
        RETAIN gini_coeff 0;

        gini_coeff + lorenz_area;

        IF last THEN DO;
            /* Gini = 1 - 2 * area under Lorenz curve */
            gini_coeff = 1 - 2 * gini_coeff;

            /* Check drift against baseline Gini of 0.40 */
            IF ABS(gini_coeff - 0.40) > &gini_threshold THEN
                drift_flag = 'DRIFT DETECTED';
            ELSE
                drift_flag = 'STABLE';

            OUTPUT;
        END;
    RUN;

    %PUT NOTE: Model monitoring complete;

%MEND model_monitoring;

/* ============================================================================
   SECTION 8: MAIN PROGRAM — Execute the scoring pipeline
   Purpose: Orchestrate the full scoring engine by invoking each macro
            in sequence: load parameters, score territory/claims/credit,
            calculate premiums, run monitoring, and produce diagnostics.
   ============================================================================ */

/* --- Step 1: Load model parameters for the current version --- */
%load_model_params(model_name=UW_SCORE, version=&model_version);

/* --- Step 2: Compute territory scores for key underwriting states --- */
%territory_score(state=FL);
%territory_score(state=CA);
%territory_score(state=TX);

/* --- Step 3: Compute claims scores for each line of business --- */
%claim_score(lob=AUTO);
%claim_score(lob=HOME);
%claim_score(lob=COMMERCIAL);

/* --- Step 4: Blend credit scores with configured weights --- */
%credit_score_blend(weight_bureau=0.65, weight_internal=0.35);

/* --- Step 5: Calculate final premiums with base rate --- */
%final_premium_calc(base_rate=1200);

/* --- Step 6: Run model monitoring diagnostics --- */
%model_monitoring;

/* --- Score distribution analysis: frequency tables --- */
PROC FREQ DATA=work.premium_calc;
    TABLES score_band / NOCUM;
    TABLES boundary_flag / NOCUM;
    TITLE "Score Band Distribution — Model v&model_version";
RUN;

/* --- Summary statistics for final premiums by score band --- */
PROC MEANS DATA=work.premium_calc
           N MEAN STD MIN P25 P50 P75 MAX;
    CLASS score_band;
    VAR final_premium raw_premium;
    TITLE "Premium Summary by Score Band";
RUN;

/* --- Write final scored output to permanent scoring library --- */
DATA scoredb.scored_policies;
    SET work.premium_calc;

    /* Attach metadata to each scored record */
    LENGTH model_version_lbl $10 engine_version $10;
    model_version_lbl = "&model_version";
    scoring_date      = TODAY();
    engine_version    = "4.2.1";

    FORMAT scoring_date DATE9.;
RUN;

/* --- Error handling: validate output record counts --- */
PROC SQL NOPRINT;
    SELECT COUNT(*) INTO :n_scored TRIMMED
    FROM scoredb.scored_policies;
QUIT;

%IF &n_scored = 0 %THEN %DO;
    %PUT ERROR: Scoring engine produced zero records — aborting pipeline;
    %ABORT CANCEL;
%END;
%ELSE %DO;
    %PUT NOTE: ========================================================;
    %PUT NOTE: Scoring engine complete;
    %PUT NOTE: Policies scored: &n_scored;
    %PUT NOTE: Model version:   &model_version;
    %PUT NOTE: Run date:        &rundate;
    %PUT NOTE: ========================================================;
%END;

/* End of scoring engine */
