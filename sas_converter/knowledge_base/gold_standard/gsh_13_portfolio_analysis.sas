/******************************************************************************
 * Program Name : gsh_13_portfolio_analysis.sas
 * Author       : Quantitative Analytics Team — Investment Risk Division
 * Created      : 2026-01-10
 * Modified     : 2026-02-19
 * Version      : 2.3
 * Purpose      : Investment portfolio risk and return analysis framework.
 *                Computes portfolio returns at configurable frequency,
 *                risk metrics (VaR, CVaR via historical, parametric, and
 *                Monte Carlo methods), performance attribution using
 *                Brinson-Fachler decomposition, and multi-factor style
 *                analysis. Produces consolidated PDF reports for portfolio
 *                managers and the risk oversight committee.
 * Dependencies : None (self-contained analytics suite)
 * Frequency    : Daily / Monthly / Ad-hoc
 * Portfolio ID : Configurable via macro parameters
 * Analyst      : K. Nakamura
 * Change Log   :
 *   2026-01-10  v1.0  Initial return calculation framework    (K. Nakamura)
 *   2026-01-25  v1.5  Added VaR and Monte Carlo simulation    (R. Gupta)
 *   2026-02-05  v2.0  Brinson-Fachler attribution engine      (K. Nakamura)
 *   2026-02-14  v2.2  Style analysis with factor regression   (S. Park)
 *   2026-02-19  v2.3  ODS reporting, multi-portfolio loop     (K. Nakamura)
 ******************************************************************************/

/* ========================================================================= */
/* SECTION 1: Environment Setup — Libraries, Options, Analysis Parameters    */
/* ========================================================================= */

options mprint mlogic symbolgen nocenter ls=200 ps=65
        validvarname=v7 nofmterr msglevel=i compress=yes;

/* --- Library references for portfolio data sources --- */
libname pos     '/invest/positions'       access=readonly;
libname mkt     '/invest/market_data'     access=readonly;
libname bench   '/invest/benchmarks'      access=readonly;
libname out     '/invest/analytics/output';

/* --- Analysis date and core parameters --- */
%let analysis_date    = 2026-02-19;
%let analysis_dt      = %sysfunc(inputn(&analysis_date, yymmdd10.));
%let risk_free_rate   = 0.0425;
%let confidence_level = 0.95;
%let base_currency    = USD;
%let lookback_days    = 252;
%let annualization    = 252;
%let analyst_name     = K. Nakamura;
%let run_timestamp    = %sysfunc(datetime());
%let run_date         = %sysfunc(today(), yymmdd10.);

/* --- Portfolio list for batch processing --- */
%let portfolio_list   = PORT001 PORT002 PORT003;
%let n_portfolios     = %sysfunc(countw(&portfolio_list));
%let benchmark_id     = BENCH_SP500;

/* --- Processing control flags and accumulators --- */
%let analysis_rc      = 0;
%let positions_loaded = 0;
%let returns_done     = 0;
%let risk_done        = 0;
%let attrib_done      = 0;

/* ========================================================================= */
/* SECTION 2: Macro Definitions                                              */
/* ========================================================================= */

/* ------------------------------------------------------------------ */
/* %load_positions — Load portfolio holdings and compute weights      */
/*   Parameters: portfolio_id= (portfolio identifier)                 */
/*               as_of= (valuation date, YYYY-MM-DD)                  */
/*   Outputs: work.positions (with weights and FX-adjusted values)    */
/* ------------------------------------------------------------------ */
%macro load_positions(portfolio_id=, as_of=);
    %local n_positions total_mv as_of_dt;
    %let as_of_dt = %sysfunc(inputn(&as_of, yymmdd10.));

    %put NOTE: ========================================;
    %put NOTE: Loading Positions — Portfolio=&portfolio_id;
    %put NOTE: As-of Date: &as_of;
    %put NOTE: ========================================;

    /* --- Step 1: Extract active positions with current market values --- */
    proc sql noprint;
        create table work.positions_raw as
        select  p.portfolio_id,
                p.security_id,
                p.security_name,
                p.asset_class,
                p.sector,
                p.country,
                p.currency,
                p.quantity,
                p.cost_basis,
                m.close_price,
                p.quantity * m.close_price as market_value,
                p.cost_basis * p.quantity  as total_cost,
                (m.close_price - p.cost_basis) / p.cost_basis
                    as unrealized_return format=percent8.2
        from    pos.holdings p
        inner join mkt.prices m
                on  p.security_id = m.security_id
                and m.price_date  = &as_of_dt
        where   p.portfolio_id = "&portfolio_id"
                and p.status   = 'ACTIVE'
                and p.quantity > 0
        order by p.asset_class, p.sector, p.security_id;

        /* --- Count positions loaded --- */
        select count(*) into :n_positions trimmed
        from   work.positions_raw;
    quit;
    %put NOTE: Loaded &n_positions active positions for &portfolio_id;

    /* --- Step 2: Compute portfolio weights as fraction of total MV --- */
    proc sql noprint;
        select sum(market_value) into :total_mv trimmed
        from   work.positions_raw;
    quit;

    data work.positions;
        set work.positions_raw;

        /* --- Weight = position market value / total portfolio value --- */
        portfolio_weight = market_value / &total_mv;

        /* --- Classify position concentration --- */
        length position_size $10;
        if portfolio_weight >= 0.05 then position_size = 'LARGE';
        else if portfolio_weight >= 0.02 then position_size = 'MEDIUM';
        else position_size = 'SMALL';

        format portfolio_weight percent8.4
               market_value total_cost comma20.2;
    run;

    /* --- Step 3: Multi-currency handling with FX conversion --- */
    %if &base_currency ^= USD_ONLY %then %do;
        data work.positions;
            set work.positions;

            /* --- Load FX rate hash on first observation --- */
            if _n_ = 1 then do;
                declare hash fx(dataset: 'mkt.fx_rates');
                fx.definekey('currency_code', 'rate_date');
                fx.definedata('fx_rate');
                fx.definedone();
            end;

            length fx_rate 8;
            currency_code = currency;
            rate_date = &as_of_dt;

            /* --- Base currency positions need no conversion --- */
            if currency = "&base_currency" then
                fx_rate = 1.0;
            else do;
                rc = fx.find();
                if rc ne 0 then do;
                    put 'WARNING: No FX rate for ' currency= rate_date=;
                    fx_rate = 1.0;
                end;
            end;

            /* --- Convert to base currency --- */
            market_value_base = market_value * fx_rate;
            total_cost_base   = total_cost * fx_rate;

            format market_value_base total_cost_base comma20.2;
            drop rc rate_date currency_code;
        run;
    %end;

    %let positions_loaded = 1;
    %put NOTE: Portfolio &portfolio_id positions loaded successfully;

%mend load_positions;

/* ------------------------------------------------------------------ */
/* %calculate_returns — Compute returns at specified frequency        */
/*   Parameters: frequency= (DAILY, MONTHLY, QUARTERLY)               */
/*   Outputs: work.security_returns, work.portfolio_returns,          */
/*            work.return_stats, work.wealth_index                    */
/* ------------------------------------------------------------------ */
%macro calculate_returns(frequency=);
    %local freq_label period_col n_periods;

    %put NOTE: ========================================;
    %put NOTE: Calculating Returns — Frequency=&frequency;
    %put NOTE: Lookback=&lookback_days trading days;
    %put NOTE: ========================================;

    /* --- Step 1: Set frequency-dependent parameters --- */
    %if &frequency = DAILY %then %do;
        %let freq_label = Daily;
        %let period_col = price_date;
    %end;
    %else %if &frequency = MONTHLY %then %do;
        %let freq_label = Monthly;
        %let period_col = month_end;
    %end;
    %else %if &frequency = QUARTERLY %then %do;
        %let freq_label = Quarterly;
        %let period_col = quarter_end;
    %end;

    /* --- Step 2: Sort price history for LAG-based return calc --- */
    proc sort data=mkt.prices out=work.price_sorted;
        by security_id price_date;
        where price_date >= intnx('day', &analysis_dt, -&lookback_days)
              and price_date <= &analysis_dt;
    run;

    /* --- Step 3: Merge prices with LAG for return calculation --- */
    data work.security_returns;
        set work.price_sorted;
        by security_id price_date;

        /* --- Lagged price from previous observation --- */
        prev_price = lag(close_price);
        prev_id    = lag(security_id);

        /* --- Reset at each new security (first.security_id) --- */
        if first.security_id then do;
            daily_return = .;
            log_return   = .;
        end;
        else if prev_id = security_id and prev_price > 0 then do;
            /* --- Simple and log returns --- */
            daily_return = (close_price - prev_price) / prev_price;
            log_return   = log(close_price / prev_price);
        end;

        /* --- Flag extreme return observations --- */
        length return_flag $15;
        if abs(daily_return) > 0.10 then return_flag = 'EXTREME';
        else if abs(daily_return) > 0.05 then return_flag = 'HIGH';
        else return_flag = 'NORMAL';

        format daily_return log_return percent10.4;
        drop prev_price prev_id;
    run;

    /* --- Step 4: Aggregate to portfolio-level weighted returns --- */
    proc sql noprint;
        create table work.portfolio_returns as
        select  r.price_date,
                sum(r.daily_return * p.portfolio_weight)
                    as portfolio_return,
                sum(r.log_return * p.portfolio_weight)
                    as portfolio_log_return
        from    work.security_returns r
        inner join work.positions p
                on r.security_id = p.security_id
        where   r.daily_return is not null
        group by r.price_date
        order by r.price_date;

        /* --- Count number of return observations --- */
        select count(*) into :n_periods trimmed
        from   work.portfolio_returns;
    quit;
    %put NOTE: Computed &n_periods &freq_label portfolio returns;

    /* --- Step 5: Descriptive statistics — mean, std, min, max --- */
    proc means data=work.portfolio_returns noprint
               n mean std min max median q1 q3;
        var portfolio_return;
        output out=work.return_stats(drop=_type_ _freq_)
               n=n_obs
               mean=mean_return
               std=std_return
               min=min_return
               max=max_return
               median=median_return
               q1=q1_return
               q3=q3_return;
    run;

    /* --- Step 6: Cumulative wealth index using RETAIN --- */
    data work.wealth_index;
        set work.portfolio_returns;

        /* --- Retained accumulators initialized on first obs --- */
        retain cumulative_wealth 1.0
               cumulative_log   0.0
               peak_wealth      1.0
               max_drawdown     0.0;

        /* --- Compound cumulative return period-by-period --- */
        cumulative_wealth = cumulative_wealth * (1 + portfolio_return);
        cumulative_log    = cumulative_log + portfolio_log_return;

        /* --- Track high-water mark and maximum drawdown --- */
        if cumulative_wealth > peak_wealth then
            peak_wealth = cumulative_wealth;
        current_drawdown = (cumulative_wealth - peak_wealth) / peak_wealth;
        if current_drawdown < max_drawdown then
            max_drawdown = current_drawdown;

        /* --- Cumulative return as percentage --- */
        cumulative_return = cumulative_wealth - 1.0;

        format cumulative_wealth peak_wealth 10.6
               cumulative_return current_drawdown max_drawdown percent10.4;
    run;

    %let returns_done = 1;
    %put NOTE: Return calculation complete (&frequency frequency);

%mend calculate_returns;

/* ------------------------------------------------------------------ */
/* %risk_metrics — VaR, CVaR, and risk decomposition                  */
/*   Parameters: method= (HISTORICAL, PARAMETRIC, MONTECARLO)         */
/*   Outputs: work.var_results, work.risk_summary                     */
/* ------------------------------------------------------------------ */
%macro risk_metrics(method=);
    %local var_estimate cvar_estimate n_simulations i;

    %put NOTE: ========================================;
    %put NOTE: Risk Metrics — Method=&method;
    %put NOTE: Confidence Level=&confidence_level;
    %put NOTE: ========================================;

    /* --- Method 1: Historical VaR via empirical percentile --- */
    %if &method = HISTORICAL %then %do;

        /* --- Sort returns ascending to find tail percentile --- */
        proc sort data=work.portfolio_returns
                  out=work.returns_sorted;
            by portfolio_return;
        run;

        /* --- Identify the VaR cutoff observation --- */
        data work.var_historical;
            set work.returns_sorted nobs=n_obs;

            /* --- Percentile rank of each observation --- */
            percentile_rank = _n_ / n_obs;

            /* --- VaR = worst return at confidence percentile --- */
            if percentile_rank <= (1 - &confidence_level) then do;
                call symputx('var_estimate', portfolio_return);
                var_level = portfolio_return;
                output;
            end;

            format var_level percent10.4;
        run;
        %put NOTE: Historical VaR(&confidence_level) = &var_estimate;
    %end;

    /* --- Method 2: Parametric VaR using normal distribution --- */
    %if &method = PARAMETRIC %then %do;

        data work.var_parametric;
            set work.return_stats;

            /* --- Normal inverse (PROBIT) for z-score at confidence --- */
            z_score = probit(&confidence_level);

            /* --- VaR = mean - z * sigma (left-tail loss) --- */
            var_parametric = mean_return - z_score * std_return;
            var_annual     = var_parametric * sqrt(&annualization);

            /* --- Parametric CVaR (Expected Shortfall) --- */
            /* --- E[X | X < VaR] = mu - sigma * phi(z) / (1 - alpha) --- */
            pdf_z = pdf('NORMAL', z_score, 0, 1);
            cvar_parametric = mean_return -
                              std_return * pdf_z / (1 - &confidence_level);

            call symputx('var_estimate', put(var_parametric, 10.6));
            call symputx('cvar_estimate', put(cvar_parametric, 10.6));

            format var_parametric var_annual cvar_parametric percent10.4;
        run;
        %put NOTE: Parametric VaR = &var_estimate, CVaR = &cvar_estimate;
    %end;

    /* --- Method 3: Monte Carlo VaR via simulated return paths --- */
    %if &method = MONTECARLO %then %do;
        %let n_simulations = 1000;

        /* --- Generate 1000 simulated returns from fitted distribution --- */
        data work.mc_simulations;
            set work.return_stats;

            call streaminit(42);

            /* --- Simulate n_simulations draws from N(mu, sigma) --- */
            %do i = 1 %to 1000;
                sim_id     = &i;
                sim_return = mean_return + std_return * rand('NORMAL');
                output;
            %end;

            format sim_return percent10.6;
            keep sim_id sim_return mean_return std_return;
        run;

        /* --- Sort simulated returns to find tail --- */
        proc sort data=work.mc_simulations
                  out=work.mc_sorted;
            by sim_return;
        run;

        /* --- Identify VaR from simulation percentile --- */
        data work.var_montecarlo;
            set work.mc_sorted nobs=n_sims;

            percentile_rank = _n_ / n_sims;
            if percentile_rank <= (1 - &confidence_level) then do;
                call symputx('var_estimate', sim_return);
            end;
        run;
        %put NOTE: Monte Carlo VaR(&confidence_level) = &var_estimate;

        /* --- CVaR: mean of tail observations below VaR --- */
        proc means data=work.mc_sorted noprint;
            where sim_return <= input(symget('var_estimate'), best12.);
            var sim_return;
            output out=work.mc_cvar(drop=_type_ _freq_)
                   mean=cvar_mc;
        run;
    %end;

    /* --- Consolidate VaR results into standard output table --- */
    data work.var_results;
        length method $12 portfolio_id $10;
        method        = "&method";
        portfolio_id  = symget('current_portfolio');
        confidence    = &confidence_level;
        var_estimate  = input(symget('var_estimate'), best12.);
        analysis_date = &analysis_dt;
        format var_estimate percent10.4 analysis_date yymmdd10.;
    run;

    %let risk_done = 1;
    %put NOTE: Risk metrics complete — Method=&method;

%mend risk_metrics;

/* ------------------------------------------------------------------ */
/* %attribution_analysis — Brinson-Fachler performance attribution    */
/*   Parameters: benchmark_id= (benchmark identifier)                 */
/*   Outputs: work.attribution, work.attrib_summary,                  */
/*            work.style_factors                                       */
/* ------------------------------------------------------------------ */
%macro attribution_analysis(benchmark_id=);
    %local n_sectors total_bench_return;

    %put NOTE: ========================================;
    %put NOTE: Attribution Analysis — Benchmark=&benchmark_id;
    %put NOTE: Method: Brinson-Fachler Decomposition;
    %put NOTE: ========================================;

    /* --- Step 1: Compute total benchmark return for reference --- */
    proc sql noprint;
        select sum(bench_weight * bench_return)
               format=percent10.6
        into   :total_bench_return trimmed
        from   bench.sector_weights
        where  benchmark_id = "&benchmark_id";
    quit;

    /* --- Step 2: Join portfolio vs benchmark weights and returns --- */
    proc sql noprint;
        create table work.attrib_raw as
        select  p.sector,
                p.security_id,
                p.portfolio_weight  as port_weight,
                r.daily_return      as port_return,
                b.bench_weight,
                b.bench_return,
                p.portfolio_weight - b.bench_weight as active_weight,
                r.daily_return - b.bench_return     as active_return
        from    work.positions p
        inner join work.security_returns r
                on  p.security_id = r.security_id
        inner join bench.sector_weights b
                on  p.sector       = b.sector
                and b.benchmark_id = "&benchmark_id"
        where   r.price_date = &analysis_dt
                and r.daily_return is not null
        order by p.sector;

        select count(distinct sector) into :n_sectors trimmed
        from   work.attrib_raw;
    quit;
    %put NOTE: Attribution across &n_sectors sectors;

    /* --- Step 3: Brinson-Fachler decomposition at security level --- */
    data work.attribution;
        set work.attrib_raw;

        /* --- Allocation: over/underweight in out/underperforming sectors --- */
        allocation_effect = (port_weight - bench_weight) *
                           (bench_return - &total_bench_return);

        /* --- Selection: stock-picking alpha within each sector --- */
        selection_effect = bench_weight * (port_return - bench_return);

        /* --- Interaction: combined allocation x selection residual --- */
        interaction_effect = (port_weight - bench_weight) *
                            (port_return - bench_return);

        /* --- Total active return = allocation + selection + interaction --- */
        total_effect = allocation_effect + selection_effect
                     + interaction_effect;

        format allocation_effect selection_effect interaction_effect
               total_effect percent10.4;
    run;

    /* --- Step 4: Attribution summary aggregated by sector --- */
    proc means data=work.attribution noprint nway;
        class sector;
        var allocation_effect selection_effect
            interaction_effect total_effect;
        output out=work.attrib_summary(drop=_type_ _freq_)
               sum(allocation_effect)  = alloc_sum
               sum(selection_effect)   = select_sum
               sum(interaction_effect) = interact_sum
               sum(total_effect)       = total_sum;
    run;

    /* --- Step 5: Style analysis with multi-factor exposures --- */
    data work.style_factors;
        set work.positions;

        /* --- Define factor arrays for value, growth, size --- */
        array factors{3} factor_value factor_growth factor_size;
        array betas{3}   beta_value   beta_growth   beta_size;
        array labels{3} $10 _temporary_ ('VALUE' 'GROWTH' 'SIZE');

        /* --- Value factor: financials, energy, utilities sectors --- */
        if sector in ('FINANCIALS', 'ENERGY', 'UTILITIES') then
            factor_value = 1.0;
        else
            factor_value = 0.0;

        /* --- Growth factor: technology, healthcare, consumer disc --- */
        if sector in ('TECHNOLOGY', 'HEALTHCARE', 'CONSUMER_DISC') then
            factor_growth = 1.0;
        else
            factor_growth = 0.0;

        /* --- Size factor: based on position market value --- */
        if market_value > 1000000 then factor_size = 1.0;
        else if market_value > 500000 then factor_size = 0.5;
        else factor_size = 0.0;

        /* --- Portfolio-weighted factor betas --- */
        do j = 1 to 3;
            betas{j} = factors{j} * portfolio_weight;
        end;

        format factor_value factor_growth factor_size
               beta_value beta_growth beta_size 8.4;
        drop j;
    run;

    %let attrib_done = 1;
    %put NOTE: Attribution analysis complete for &benchmark_id;

%mend attribution_analysis;

/* ------------------------------------------------------------------ */
/* %generate_report — Compile consolidated portfolio report           */
/*   Parameters: none (uses work datasets from prior macro steps)     */
/*   Outputs: out.portfolio_report, ODS PDF report file               */
/* ------------------------------------------------------------------ */
%macro generate_report;
    %local total_return sharpe_ratio alpha beta ann_return ann_vol;

    %put NOTE: ========================================;
    %put NOTE: Generating Portfolio Report;
    %put NOTE: Portfolio: %sysfunc(symget(current_portfolio));
    %put NOTE: ========================================;

    /* --- Step 1: Executive summary — total return, Sharpe, alpha/beta --- */
    proc sql noprint;
        /* --- Total cumulative return from wealth index --- */
        select  max(cumulative_return) format=percent10.4
        into    :total_return trimmed
        from    work.wealth_index;

        /* --- Annualized Sharpe ratio: (E[Rp]-Rf) / sigma --- */
        select  (mean_return * &annualization - &risk_free_rate) /
                (std_return * sqrt(&annualization))
                format=8.4
        into    :sharpe_ratio trimmed
        from    work.return_stats;

        /* --- Annualized return and volatility --- */
        select  mean_return * &annualization format=percent10.4,
                std_return * sqrt(&annualization) format=percent10.4
        into    :ann_return trimmed,
                :ann_vol trimmed
        from    work.return_stats;
    quit;
    %put NOTE: Total Return=&total_return, Sharpe=&sharpe_ratio;

    /* --- Step 2: Sector allocation comparison via PROC TABULATE --- */
    proc tabulate data=work.attribution out=work.sector_tab;
        class sector;
        var port_weight bench_weight active_weight total_effect;
        table sector='Sector' ALL='TOTAL',
              port_weight='Portfolio Wt'*sum=''*f=percent8.2
              bench_weight='Benchmark Wt'*sum=''*f=percent8.2
              active_weight='Active Wt'*sum=''*f=percent8.2
              total_effect='Total Effect'*sum=''*f=percent10.4;
    run;

    /* --- Step 3: Identify top and bottom return contributors --- */
    proc sort data=work.security_returns out=work.contrib_sorted;
        by descending daily_return;
        where price_date = &analysis_dt;
    run;

    data work.top_bottom;
        set work.contrib_sorted nobs=n_total;

        /* --- Top 10 contributors (highest returns) --- */
        if _n_ <= 10 then do;
            rank_type    = 'TOP';
            contrib_rank = _n_;
            output;
        end;

        /* --- Bottom 10 contributors (lowest returns) --- */
        if _n_ > n_total - 10 then do;
            rank_type    = 'BOTTOM';
            contrib_rank = n_total - _n_ + 1;
            output;
        end;

        keep security_id daily_return rank_type contrib_rank;
    run;

    /* --- Step 4: ODS PDF report output --- */
    ods pdf file="/invest/analytics/output/portfolio_&current_portfolio..pdf"
            style=journal;

    title1 "Investment Portfolio Analysis Report";
    title2 "Portfolio: &current_portfolio | Date: &analysis_date"
           " | Analyst: &analyst_name";
    footnote1 "Sharpe Ratio: &sharpe_ratio | Ann. Return: &ann_return"
              " | Ann. Vol: &ann_vol";
    footnote2 "Generated: &run_date | Confidence: &confidence_level";

    /* --- Attribution summary table --- */
    proc report data=work.attrib_summary nowd;
        columns sector alloc_sum select_sum interact_sum total_sum;
        define sector       / group   'Sector';
        define alloc_sum    / sum     'Allocation'  format=percent10.4;
        define select_sum   / sum     'Selection'   format=percent10.4;
        define interact_sum / sum     'Interaction'  format=percent10.4;
        define total_sum    / sum     'Total Effect' format=percent10.4;
        rbreak after / summarize
               style=[font_weight=bold backgroundcolor=lightyellow];
    run;

    /* --- Top/bottom contributor listing --- */
    proc print data=work.top_bottom noobs label;
        var rank_type contrib_rank security_id daily_return;
        label rank_type    = 'Category'
              contrib_rank = 'Rank'
              security_id  = 'Security'
              daily_return = 'Return';
    run;

    title;
    footnote;
    ods pdf close;

    /* --- Step 5: Persist report metadata to output library --- */
    data out.portfolio_report;
        length portfolio_id $10 analyst $30 report_status $15;
        portfolio_id  = symget('current_portfolio');
        analysis_date = &analysis_dt;
        total_return  = input(symget('total_return'), percent10.);
        sharpe_ratio  = input(symget('sharpe_ratio'), best8.);
        ann_return    = input(symget('ann_return'), percent10.);
        ann_vol       = input(symget('ann_vol'), percent10.);
        analyst       = "&analyst_name";
        report_date   = datetime();
        report_status = 'COMPLETE';
        format analysis_date yymmdd10. report_date datetime20.
               total_return ann_return ann_vol percent10.4
               sharpe_ratio 8.4;
    run;

    %put NOTE: Report generated for %sysfunc(symget(current_portfolio));

%mend generate_report;

/* ========================================================================= */
/* SECTION 3: Main Program Execution                                         */
/* ========================================================================= */

%put NOTE: ================================================================;
%put NOTE: PORTFOLIO ANALYSIS ENGINE v2.3;
%put NOTE: Analysis Date: &analysis_date;
%put NOTE: Portfolios: &portfolio_list;
%put NOTE: Benchmark: &benchmark_id;
%put NOTE: Analyst: &analyst_name;
%put NOTE: Run Date: &run_date;
%put NOTE: ================================================================;

/* ------------------------------------------------------------------ */
/* %run_all_portfolios — Iterate over portfolio list                  */
/*   Executes load → returns → risk → attribution → report pipeline  */
/*   for each portfolio, with error handling and VaR consolidation    */
/* ------------------------------------------------------------------ */
%macro run_all_portfolios;
    %local i current_portfolio;

    %do i = 1 %to &n_portfolios;
        %let current_portfolio = %scan(&portfolio_list, &i);

        %put NOTE: ------------------------------------------------;
        %put NOTE: Processing Portfolio &i of &n_portfolios: &current_portfolio;
        %put NOTE: ------------------------------------------------;

        /* --- Step 1: Load portfolio positions --- */
        %load_positions(portfolio_id=&current_portfolio,
                        as_of=&analysis_date);

        /* --- Step 2: Calculate returns at daily frequency --- */
        %calculate_returns(frequency=DAILY);

        /* --- Step 3: Compute risk metrics — all three methods --- */
        %risk_metrics(method=HISTORICAL);
        %risk_metrics(method=PARAMETRIC);
        %risk_metrics(method=MONTECARLO);

        /* --- Step 4: Run performance attribution --- */
        %attribution_analysis(benchmark_id=&benchmark_id);

        /* --- Step 5: Generate portfolio report --- */
        %generate_report;

        /* --- Append VaR results to consolidated output --- */
        proc append base=out.var_consolidated
                    data=work.var_results force;
        run;

        /* --- Error check after each portfolio iteration --- */
        %if &syserr > 0 %then %do;
            %let analysis_rc = 1;
            %put ERROR: Processing failed for portfolio &current_portfolio;
            %put ERROR: SYSERR=&syserr — continuing to next portfolio;
        %end;
    %end;

%mend run_all_portfolios;

/* --- Execute the multi-portfolio analysis pipeline --- */
%run_all_portfolios;

/* ========================================================================= */
/* SECTION 4: Diagnostic Output and Cleanup                                  */
/* ========================================================================= */

/* --- Diagnostic: Consolidated VaR summary across all portfolios --- */
title1 "Consolidated VaR Summary — All Portfolios";
title2 "Analysis Date: &analysis_date | Confidence: &confidence_level";

proc print data=out.var_consolidated noobs label;
    var portfolio_id method confidence var_estimate analysis_date;
    label portfolio_id  = 'Portfolio'
          method        = 'VaR Method'
          confidence    = 'Confidence'
          var_estimate  = 'VaR Estimate'
          analysis_date = 'Analysis Date';
run;

title;

/* --- Diagnostic: Portfolio return statistics --- */
title1 "Portfolio Return Statistics — Last Processed";
title2 "Frequency: Daily | Lookback: &lookback_days trading days";

proc print data=work.return_stats noobs;
    var n_obs mean_return std_return min_return max_return
        median_return q1_return q3_return;
    format mean_return std_return min_return max_return
           median_return q1_return q3_return percent10.4;
run;

title;

/* --- Diagnostic: Wealth index endpoints --- */
title1 "Wealth Index — Cumulative Performance";

proc print data=work.wealth_index(obs=5) noobs;
    var price_date portfolio_return cumulative_wealth
        peak_wealth current_drawdown;
run;

title;

/* --- Cleanup temporary work datasets --- */
proc datasets lib=work nolist nowarn;
    delete positions_raw price_sorted returns_sorted
           mc_simulations mc_sorted mc_cvar
           contrib_sorted sector_tab attrib_raw
           var_historical var_parametric var_montecarlo;
quit;

/* --- Reset options to defaults --- */
options nomprint nomlogic nosymbolgen;

%put NOTE: ================================================================;
%put NOTE: PORTFOLIO ANALYSIS COMPLETE;
%put NOTE: Portfolios Processed: &n_portfolios;
%put NOTE: Analysis Date: &analysis_date;
%put NOTE: Return Code: &analysis_rc;
%put NOTE: ================================================================;
