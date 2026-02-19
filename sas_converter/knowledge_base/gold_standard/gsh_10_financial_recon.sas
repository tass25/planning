/******************************************************************************
 * Program Name : gsh_10_financial_recon.sas
 * Author       : Financial Controls Team — Corporate Reconciliation Division
 * Created      : 2026-01-20
 * Modified     : 2026-02-19
 * Version      : 2.1
 * Purpose      : Enterprise financial reconciliation engine for matching and
 *                validating balances across General Ledger, subledger modules
 *                (AR, AP, FA), bank statements, and intercompany accounts.
 *                Produces audit-ready reconciliation reports with materiality
 *                assessment and exception tracking.
 * Dependencies : None (self-contained reconciliation suite)
 * Frequency    : Monthly / Period-end close
 * Reconciliation : GL-to-Subledger, Bank, Intercompany
 * Preparer     : D. Martinez
 * Change Log   :
 *   2026-01-20  v1.0  Initial reconciliation framework       (D. Martinez)
 *   2026-02-01  v1.5  Added bank matching with hash objects   (L. Thompson)
 *   2026-02-12  v2.0  Intercompany elimination logic          (D. Martinez)
 *   2026-02-19  v2.1  ODS reporting, materiality assessment   (P. Williams)
 ******************************************************************************/

/* ========================================================================= */
/* SECTION 1: Environment Setup — Libraries, Options, Period Parameters      */
/* ========================================================================= */

options mprint mlogic symbolgen nocenter ls=200 ps=65
        validvarname=v7 nofmterr msglevel=i;

/* --- Library references for reconciliation data sources --- */
libname gl      '/finance/general_ledger'   access=readonly;
libname sub     '/finance/subledger'        access=readonly;
libname bank    '/finance/bank_statements'  access=readonly;
libname recon   '/finance/reconciliation/output';

/* --- Period and reconciliation parameters --- */
%let recon_period    = 2026-01;
%let recon_year      = 2026;
%let recon_month     = 01;
%let prior_period    = 2025-12;
%let period_end_dt   = %sysfunc(mdy(1,31,2026));
%let prior_end_dt    = %sysfunc(mdy(12,31,2025));
%let period_start_dt = %sysfunc(mdy(1,1,2026));
%let preparer        = D. Martinez;
%let reviewer        = P. Williams;
%let recon_type      = FULL;
%let run_timestamp   = %sysfunc(datetime());
%let run_date        = %sysfunc(today(), yymmdd10.);

/* --- Tolerance and materiality thresholds --- */
%let match_tolerance    = 0.01;
%let material_threshold = 5000;
%let ic_tolerance       = 1.00;
%let fx_tolerance       = 0.05;
%let aging_buckets      = 30 60 90 120;
%let base_currency      = USD;

/* --- Processing control flags and accumulators --- */
%let recon_rc          = 0;
%let total_exceptions  = 0;
%let gl_extracted      = 0;
%let sub_extracted     = 0;
%let bank_matched      = 0;
%let ic_reconciled     = 0;

/* ========================================================================= */
/* SECTION 2: Macro Definitions                                              */
/* ========================================================================= */

/* ------------------------------------------------------------------ */
/* %extract_gl — Extract General Ledger balances for a given period   */
/*   Parameters: period= (YYYY-MM), account_range= (start-end)       */
/*   Outputs: work.gl_balances (with currency conversion)             */
/* ------------------------------------------------------------------ */
%macro extract_gl(period=, account_range=);
    %local period_start period_end acct_lo acct_hi n_accounts;
    %let period_start = %sysfunc(inputn(01&period, ddYYMM7.));
    %let period_end   = %sysfunc(intnx(month, &period_start, 0, end));
    %let acct_lo = %scan(&account_range, 1, -);
    %let acct_hi = %scan(&account_range, 2, -);

    %put NOTE: ========================================;
    %put NOTE: GL Extraction — Period=&period;
    %put NOTE: Account Range: &acct_lo to &acct_hi;
    %put NOTE: ========================================;

    /* --- GL account-level balance aggregation via PROC SQL --- */
    proc sql noprint;
        create table work.gl_raw as
        select  g.account_id,
                g.account_name,
                g.account_type,
                g.cost_center,
                g.entity_code,
                g.currency_code,
                sum(g.debit_amount)  as total_debits,
                sum(g.credit_amount) as total_credits,
                sum(g.debit_amount) - sum(g.credit_amount) as net_balance
        from    gl.journal_entries g
        where   g.posting_date between &period_start and &period_end
                and input(g.account_id, best12.) between &acct_lo and &acct_hi
                and g.status = 'POSTED'
        group by g.account_id, g.account_name, g.account_type,
                 g.cost_center, g.entity_code, g.currency_code;

        /* --- Count extracted accounts --- */
        select count(*) into :n_accounts trimmed
        from   work.gl_raw;
    quit;
    %put NOTE: Extracted &n_accounts GL accounts for &period;

    /* --- Currency conversion to base currency using exchange rate table --- */
    data work.gl_balances;
        set work.gl_raw;

        /* --- Load exchange rate hash on first iteration --- */
        if _n_ = 1 then do;
            declare hash fx(dataset: 'gl.exchange_rates');
            fx.definekey('currency_code', 'rate_date');
            fx.definedata('exchange_rate');
            fx.definedone();
        end;

        length exchange_rate 8;
        rate_date = &period_end;

        /* --- Lookup exchange rate; default to 1.0 for base currency --- */
        if currency_code = "&base_currency" then
            exchange_rate = 1.0;
        else do;
            rc = fx.find();
            if rc ne 0 then do;
                put 'WARNING: No exchange rate for ' currency_code= rate_date=;
                exchange_rate = .;
            end;
        end;

        /* --- Compute converted balances in base currency --- */
        total_debits_base  = total_debits * exchange_rate;
        total_credits_base = total_credits * exchange_rate;
        net_balance_base   = net_balance * exchange_rate;

        format total_debits_base total_credits_base net_balance_base comma20.2;
        drop rc rate_date;
    run;

    /* --- Conditional logic: consolidated vs entity-level extraction --- */
    %if &recon_type = FULL %then %do;
        /* --- Full consolidation: aggregate across all entities --- */
        proc sql noprint;
            create table work.gl_consolidated as
            select  account_id,
                    account_name,
                    account_type,
                    sum(net_balance_base) as consolidated_balance format=comma20.2
            from    work.gl_balances
            group by account_id, account_name, account_type;
        quit;
        %put NOTE: Consolidated GL balances across all entities;
    %end;
    %else %do;
        /* --- Entity-level: keep balances at entity granularity --- */
        proc sql noprint;
            create table work.gl_consolidated as
            select  account_id,
                    account_name,
                    account_type,
                    entity_code,
                    net_balance_base as consolidated_balance format=comma20.2
            from    work.gl_balances;
        quit;
        %put NOTE: Entity-level GL balances retained;
    %end;

    %let gl_extracted = 1;
    %put NOTE: GL extraction complete — &n_accounts accounts processed;
%mend extract_gl;

/* ------------------------------------------------------------------ */
/* %extract_subledger — Extract subledger data by module              */
/*   Parameters: module= (AR|AP|FA), period= (YYYY-MM)               */
/*   Outputs: work.sub_<module>_norm (normalized subledger balances)  */
/* ------------------------------------------------------------------ */
%macro extract_subledger(module=, period=);
    %local n_records period_dt;
    %let period_dt = %sysfunc(inputn(01&period, ddYYMM7.));

    %put NOTE: ========================================;
    %put NOTE: Subledger Extraction — Module=&module;
    %put NOTE: Period=&period;
    %put NOTE: ========================================;

    /* --- Accounts Receivable: aging analysis and open invoices --- */
    %if &module = AR %then %do;
        proc sql noprint;
            create table work.sub_ar as
            select  a.customer_id,
                    a.invoice_id,
                    a.invoice_date,
                    a.due_date,
                    a.invoice_amount,
                    a.paid_amount,
                    a.invoice_amount - a.paid_amount as open_balance,
                    a.currency_code,
                    a.entity_code,
                    /* --- Aging bucket classification --- */
                    case
                        when intck('day', a.due_date, &period_end_dt) <= 0
                            then 'CURRENT'
                        when intck('day', a.due_date, &period_end_dt) <= 30
                            then '1-30 DAYS'
                        when intck('day', a.due_date, &period_end_dt) <= 60
                            then '31-60 DAYS'
                        when intck('day', a.due_date, &period_end_dt) <= 90
                            then '61-90 DAYS'
                        else '90+ DAYS'
                    end as aging_bucket,
                    intck('day', a.due_date, &period_end_dt) as days_past_due
            from    sub.ar_invoices a
            where   a.invoice_amount - a.paid_amount > &match_tolerance
                    and a.period = "&period"
            order by a.customer_id, a.invoice_date;

            select count(*) into :n_records trimmed
            from   work.sub_ar;
        quit;

        /* --- AR normalization: map to standard reconciliation format --- */
        data work.sub_ar_norm;
            set work.sub_ar;
            length module $2 sub_account $20 sub_balance 8;
            module      = 'AR';
            sub_account = customer_id;
            sub_balance = open_balance;
            format sub_balance comma20.2;
        run;
        %put NOTE: AR extraction complete — &n_records open invoices;
    %end;

    /* --- Accounts Payable: open items and accrued liabilities --- */
    %else %if &module = AP %then %do;
        proc sql noprint;
            create table work.sub_ap as
            select  v.vendor_id,
                    v.vendor_name,
                    v.invoice_id,
                    v.invoice_date,
                    v.due_date,
                    v.invoice_amount,
                    v.payment_amount,
                    v.invoice_amount - v.payment_amount as open_balance,
                    v.currency_code,
                    v.entity_code,
                    v.po_number,
                    /* --- Payment urgency classification --- */
                    case
                        when v.due_date < &period_end_dt then 'OVERDUE'
                        when v.due_date <= intnx('day', &period_end_dt, 15)
                            then 'DUE_SOON'
                        else 'FUTURE'
                    end as payment_status
            from    sub.ap_invoices v
            where   v.invoice_amount - v.payment_amount > &match_tolerance
                    and v.period = "&period"
            order by v.vendor_id, v.due_date;

            select count(*) into :n_records trimmed
            from   work.sub_ap;
        quit;

        /* --- AP normalization: map to standard reconciliation format --- */
        data work.sub_ap_norm;
            set work.sub_ap;
            length module $2 sub_account $20 sub_balance 8;
            module      = 'AP';
            sub_account = vendor_id;
            sub_balance = -1 * open_balance;  /* AP is credit balance */
            format sub_balance comma20.2;
        run;
        %put NOTE: AP extraction complete — &n_records open items;
    %end;

    /* --- Fixed Assets: asset register with accumulated depreciation --- */
    %else %if &module = FA %then %do;
        data work.sub_fa;
            set sub.fixed_assets;
            where status = 'ACTIVE'
                  and acquisition_date <= &period_end_dt;

            length depreciation_method $20;

            /* --- Calculate useful life in months --- */
            useful_life_months = useful_life_years * 12;
            months_in_service  = intck('month', acquisition_date, &period_end_dt);

            /* --- Straight-line depreciation calculation --- */
            if depreciation_method = 'SL' then do;
                monthly_depr       = (cost - salvage_value) / useful_life_months;
                accum_depreciation = min(monthly_depr * months_in_service,
                                         cost - salvage_value);
            end;
            /* --- Declining balance depreciation --- */
            else if depreciation_method = 'DB' then do;
                depr_rate = 2 / useful_life_years;
                accum_depreciation = cost * (1 - (1 - depr_rate) **
                                     min(months_in_service / 12, useful_life_years));
            end;

            /* --- Net book value computation --- */
            net_book_value = cost - accum_depreciation;
            format cost accum_depreciation net_book_value salvage_value comma20.2;
        run;

        /* --- FA normalization: map to standard reconciliation format --- */
        data work.sub_fa_norm;
            set work.sub_fa;
            length module $2 sub_account $20 sub_balance 8;
            module      = 'FA';
            sub_account = asset_id;
            sub_balance = net_book_value;
            format sub_balance comma20.2;
        run;

        proc sql noprint;
            select count(*) into :n_records trimmed
            from   work.sub_fa;
        quit;
        %put NOTE: FA extraction complete — &n_records active assets;
    %end;

    %let sub_extracted = 1;
%mend extract_subledger;

/* ------------------------------------------------------------------ */
/* %bank_reconciliation — Match GL cash entries to bank statements    */
/*   Parameters: account_id= (bank account identifier)               */
/*   Uses hash object for high-performance transaction matching       */
/*   Outputs: work.bank_matched, work.bank_exceptions_gl/bank        */
/* ------------------------------------------------------------------ */
%macro bank_reconciliation(account_id=);
    %local n_gl_txn n_bank_txn n_matched n_unmatched_gl n_unmatched_bank;

    %put NOTE: ========================================;
    %put NOTE: Bank Reconciliation — Account=&account_id;
    %put NOTE: Period=&recon_period;
    %put NOTE: Tolerance=&match_tolerance;
    %put NOTE: ========================================;

    /* --- Sort GL cash transactions for the specified bank account --- */
    proc sort data=gl.cash_transactions
              (where=(bank_account="&account_id"
                      and posting_date between &period_start_dt and &period_end_dt))
              out=work.gl_cash_sorted;
        by transaction_date amount reference_id;
    run;

    /* --- Sort bank statement transactions for matching period --- */
    proc sort data=bank.statements
              (where=(account_id="&account_id"
                      and statement_date between &period_start_dt and &period_end_dt))
              out=work.bank_stmt_sorted;
        by transaction_date amount reference_id;
    run;

    /* --- Hash-based transaction matching: amount + date + reference --- */
    data work.bank_matched
            (keep=match_id gl_txn_id bank_txn_id
                  match_amount match_date match_type)
         work.bank_exceptions_gl
            (keep=gl_txn_id transaction_date amount
                  reference_id exception_reason)
         work.bank_exceptions_bank
            (keep=bank_txn_id transaction_date amount
                  reference_id exception_reason);

        /* --- Load bank statement into hash for fast lookup --- */
        if _n_ = 1 then do;
            declare hash h_bank(dataset: 'work.bank_stmt_sorted',
                                multidata: 'yes');
            h_bank.definekey('reference_id');
            h_bank.definedata('bank_txn_id', 'transaction_date',
                              'amount', 'reference_id', 'description');
            h_bank.definedone();

            /* --- Track which bank items have been matched --- */
            declare hash h_used();
            h_used.definekey('bank_txn_id');
            h_used.definedone();
        end;

        /* --- Tracking accumulators with RETAIN --- */
        retain matched_total 0 unmatched_gl_total 0
               match_seq 0 n_matched_r 0 n_unmatched_r 0;

        length match_id $20 match_type $15 exception_reason $50;
        length bank_txn_id $20 description $100;
        format match_amount comma20.2;

        /* --- Iterate over GL cash transactions --- */
        set work.gl_cash_sorted end=last_gl;

        gl_amount = amount;
        gl_date   = transaction_date;
        gl_ref    = reference_id;

        /* --- Attempt exact match on reference_id --- */
        rc = h_bank.find(key: gl_ref);

        if rc = 0 then do;
            /* --- Verify amount within tolerance --- */
            if abs(gl_amount - amount) <= &match_tolerance then do;
                rc_used = h_used.find(key: bank_txn_id);
                if rc_used ne 0 then do;
                    /* --- Successful match: record and track --- */
                    match_seq + 1;
                    match_id     = cats('M-', put(match_seq, z6.));
                    match_amount = gl_amount;
                    match_date   = gl_date;
                    match_type   = 'EXACT';
                    matched_total + gl_amount;
                    n_matched_r + 1;
                    h_used.add(key: bank_txn_id, data: bank_txn_id);
                    output work.bank_matched;
                end;
                else do;
                    /* --- Bank transaction already consumed by prior match --- */
                    exception_reason = 'GL unmatched: bank txn already used';
                    n_unmatched_r + 1;
                    unmatched_gl_total + abs(gl_amount);
                    output work.bank_exceptions_gl;
                end;
            end;
            else do;
                /* --- Amount difference exceeds tolerance --- */
                exception_reason = 'Amount diff exceeds tolerance';
                n_unmatched_r + 1;
                unmatched_gl_total + abs(gl_amount);
                output work.bank_exceptions_gl;
            end;
        end;
        else do;
            /* --- No matching reference found in bank statement --- */
            exception_reason = 'No bank match for reference';
            n_unmatched_r + 1;
            unmatched_gl_total + abs(gl_amount);
            output work.bank_exceptions_gl;
        end;

        /* --- Final summary statistics at end of file --- */
        if last_gl then do;
            call symputx('n_matched', n_matched_r);
            call symputx('n_unmatched_gl', n_unmatched_r);
            put 'NOTE: Matched total = ' matched_total comma20.2;
            put 'NOTE: Unmatched GL total = ' unmatched_gl_total comma20.2;
        end;

        drop rc rc_used gl_amount gl_date gl_ref;
    run;

    /* --- Identify unmatched bank statement items (not in GL) --- */
    data work.bank_exceptions_bank_temp;
        set work.bank_stmt_sorted;
        length exception_reason $50;

        if _n_ = 1 then do;
            declare hash h_used(dataset: 'work.bank_matched');
            h_used.definekey('bank_txn_id');
            h_used.definedone();
        end;

        rc = h_used.find();
        if rc ne 0 then do;
            exception_reason = 'Bank item not matched to GL';
            output;
        end;
        drop rc;
    run;

    /* --- Append bank-side exceptions to consolidated dataset --- */
    proc append base=work.bank_exceptions_bank
                data=work.bank_exceptions_bank_temp force;
    run;

    proc sql noprint;
        select count(*) into :n_unmatched_bank trimmed
        from   work.bank_exceptions_bank_temp;
    quit;

    /* --- Accumulate exception totals and log results --- */
    %let total_exceptions = %eval(&total_exceptions + &n_unmatched_gl
                                  + &n_unmatched_bank);
    %let bank_matched = 1;
    %put NOTE: Bank &account_id — Matched=&n_matched;
    %put NOTE: Bank &account_id — Unmatched GL=&n_unmatched_gl;
    %put NOTE: Bank &account_id — Unmatched Bank=&n_unmatched_bank;
%mend bank_reconciliation;

/* ------------------------------------------------------------------ */
/* %intercompany_recon — Intercompany balance elimination and netting */
/*   Parameters: entity_pairs= (pipe-delimited pairs: E1:E2|E3:E4)   */
/*   Uses %DO loop to iterate over all entity pairs                   */
/*   Outputs: work.ic_all_exceptions (consolidated IC differences)    */
/* ------------------------------------------------------------------ */
%macro intercompany_recon(entity_pairs=);
    %local n_pairs i entity_from entity_to pair_str ic_exception_count;
    %let n_pairs = %sysfunc(countw(&entity_pairs, |));

    %put NOTE: ========================================;
    %put NOTE: Intercompany Reconciliation;
    %put NOTE: Entity pairs to process: &n_pairs;
    %put NOTE: IC Tolerance: &ic_tolerance;
    %put NOTE: ========================================;

    /* --- Initialize consolidated IC exception dataset --- */
    data work.ic_all_exceptions;
        length entity_from $10 entity_to $10 account_id $15
               balance_from 8 balance_to 8 net_difference 8
               exception_flag $1 netting_status $20;
        stop;
    run;

    /* --- Loop over each entity pair for IC matching --- */
    %do i = 1 %to &n_pairs;
        %let pair_str    = %scan(&entity_pairs, &i, |);
        %let entity_from = %scan(&pair_str, 1, :);
        %let entity_to   = %scan(&pair_str, 2, :);

        %put NOTE: Processing IC pair &i of &n_pairs: &entity_from <-> &entity_to;

        /* --- Find unmatched IC balances between entity pair --- */
        proc sql noprint;
            create table work._ic_pair_&i as
            select  coalesce(a.account_id, b.account_id) as account_id,
                    a.entity_code as entity_from length=10,
                    b.entity_code as entity_to length=10,
                    coalesce(a.net_balance_base, 0) as balance_from,
                    coalesce(b.net_balance_base, 0) as balance_to,
                    calculated balance_from + calculated balance_to
                        as net_difference,
                    case
                        when abs(calculated net_difference) > &ic_tolerance
                            then 'Y'
                        else 'N'
                    end as exception_flag length=1
            from    work.gl_balances
                        (where=(entity_code="&entity_from"
                                and account_type='IC')) a
            full join
                    work.gl_balances
                        (where=(entity_code="&entity_to"
                                and account_type='IC')) b
            on      a.account_id = b.account_id;
        quit;

        /* --- Netting with tolerance: classify difference severity --- */
        data work._ic_net_&i;
            set work._ic_pair_&i;
            length netting_status $20;

            if abs(net_difference) <= &ic_tolerance then
                netting_status = 'ELIMINATED';
            else if abs(net_difference) <= &material_threshold then
                netting_status = 'MINOR_DIFF';
            else
                netting_status = 'MATERIAL_DIFF';
        run;

        /* --- Append exceptions to consolidated dataset --- */
        proc append base=work.ic_all_exceptions
                    data=work._ic_net_&i(where=(exception_flag='Y'))
                    force;
        run;
    %end;

    %let ic_reconciled = 1;

    proc sql noprint;
        select count(*) into :ic_exception_count trimmed
        from   work.ic_all_exceptions;
    quit;

    %let total_exceptions = %eval(&total_exceptions + &ic_exception_count);
    %put NOTE: IC reconciliation complete — &ic_exception_count exceptions found;
%mend intercompany_recon;

/* ------------------------------------------------------------------ */
/* %generate_recon_report — Produce audit-ready reconciliation report */
/*   No parameters — uses all work datasets from prior macro steps    */
/*   Outputs: recon.recon_detail, ODS PDF report                      */
/* ------------------------------------------------------------------ */
%macro generate_recon_report;
    %local total_gl_balance total_sub_balance recon_diff
           n_material_items report_status;

    %put NOTE: ========================================;
    %put NOTE: Generating Reconciliation Report;
    %put NOTE: Period=&recon_period  Preparer=&preparer;
    %put NOTE: ========================================;

    /* --- Consolidate all reconciliation results into summary --- */
    proc sql noprint;
        create table work.recon_summary as
        select  'GL_TOTAL' as recon_category,
                sum(consolidated_balance) as balance format=comma20.2,
                count(*) as item_count
        from    work.gl_consolidated

        union all
        select  'SUB_AR' as recon_category,
                sum(sub_balance) as balance,
                count(*) as item_count
        from    work.sub_ar_norm

        union all
        select  'SUB_AP' as recon_category,
                sum(sub_balance) as balance,
                count(*) as item_count
        from    work.sub_ap_norm

        union all
        select  'SUB_FA' as recon_category,
                sum(sub_balance) as balance,
                count(*) as item_count
        from    work.sub_fa_norm

        union all
        select  'BANK_MATCHED' as recon_category,
                sum(match_amount) as balance,
                count(*) as item_count
        from    work.bank_matched

        union all
        select  'IC_EXCEPTIONS' as recon_category,
                sum(net_difference) as balance,
                count(*) as item_count
        from    work.ic_all_exceptions;
    quit;

    /* --- Materiality assessment: flag items exceeding threshold --- */
    data recon.recon_detail;
        set work.recon_summary;
        length materiality_flag $10 assessment_note $100;

        if abs(balance) > &material_threshold then do;
            materiality_flag = 'MATERIAL';
            assessment_note  = catx(' ', 'Balance of',
                               put(balance, comma20.2),
                               'exceeds threshold of',
                               put(&material_threshold, comma12.));
        end;
        else do;
            materiality_flag = 'IMMATERIAL';
            assessment_note  = 'Within acceptable threshold';
        end;

        /* --- Reconciliation metadata stamps --- */
        recon_period  = "&recon_period";
        preparer      = "&preparer";
        reviewer      = "&reviewer";
        assessed_date = datetime();
        format assessed_date datetime20.;
    run;

    /* --- Count material items requiring manual review --- */
    proc sql noprint;
        select count(*) into :n_material_items trimmed
        from   recon.recon_detail
        where  materiality_flag = 'MATERIAL';
    quit;

    %if &n_material_items > 0 %then
        %let report_status = REQUIRES_REVIEW;
    %else
        %let report_status = CLEAN;

    /* --- ODS PDF output for audit-ready documentation --- */
    ods pdf file="/finance/reconciliation/output/recon_&recon_period..pdf"
        style=journal;

    title1 "Financial Reconciliation Report";
    title2 "Period: &recon_period  |  Preparer: &preparer  |  Status: &report_status";
    footnote1 "Generated: &run_date  |  Tolerance: &match_tolerance  |  Materiality: &material_threshold";

    /* --- PROC REPORT with COMPUTE blocks for formatted output --- */
    proc report data=recon.recon_detail nowd
                style(header)=[backgroundcolor=lightblue font_weight=bold];
        columns recon_category item_count balance materiality_flag
                assessment_note;

        define recon_category   / group   'Category'    width=20;
        define item_count       / sum     'Items'       width=10
                                                        format=comma12.;
        define balance          / sum     'Balance'     width=20
                                                        format=comma20.2;
        define materiality_flag / display 'Materiality' width=12;
        define assessment_note  / display 'Assessment'  width=40;

        /* --- Compute block: highlight material items in red --- */
        compute balance;
            if abs(balance.sum) > &material_threshold then
                call define(_col_, 'style',
                    'style=[foreground=red font_weight=bold]');
        endcomp;

        /* --- Compute block: grand total and status summary --- */
        compute after;
            line ' ';
            line "Report Status: &report_status";
            line "Total Exceptions: &total_exceptions";
            line "Material Items: &n_material_items";
        endcomp;

        rbreak after / summarize style=[font_weight=bold
                                        backgroundcolor=lightyellow];
    run;

    title;
    footnote;
    ods pdf close;

    %put NOTE: Reconciliation report generated — Status=&report_status;
    %put NOTE: Material items requiring review: &n_material_items;
%mend generate_recon_report;

/* ========================================================================= */
/* SECTION 3: Main Program Execution                                         */
/* ========================================================================= */

%put NOTE: ============================================================;
%put NOTE: FINANCIAL RECONCILIATION ENGINE v2.1;
%put NOTE: Period: &recon_period  |  Type: &recon_type;
%put NOTE: Preparer: &preparer   |  Run Date: &run_date;
%put NOTE: ============================================================;

/* --- Step 1: Extract GL balances — current and prior period --- */
%extract_gl(period=&recon_period, account_range=1000-9999);
%extract_gl(period=&prior_period, account_range=1000-9999);

/* --- Step 2: Extract subledger data — AR, AP, FA modules --- */
%extract_subledger(module=AR, period=&recon_period);
%extract_subledger(module=AP, period=&recon_period);
%extract_subledger(module=FA, period=&recon_period);

/* --- Step 3: Bank reconciliation for 3 operating accounts --- */
%bank_reconciliation(account_id=ACCT-001);
%bank_reconciliation(account_id=ACCT-002);
%bank_reconciliation(account_id=ACCT-003);

/* --- Step 4: Intercompany reconciliation — 4 entity pairs --- */
%intercompany_recon(entity_pairs=US01:UK01|US01:DE01|UK01:FR01|DE01:FR01);

/* --- Step 5: Generate audit-ready reconciliation report --- */
%generate_recon_report;

/* --- Step 6: Reconciling items summary printout --- */
title1 "Reconciling Items Summary";
title2 "Period: &recon_period  |  Generated: &run_date";

proc print data=recon.recon_detail noobs label;
    var recon_category item_count balance materiality_flag;
    label recon_category   = 'Reconciliation Area'
          item_count       = 'Number of Items'
          balance          = 'Net Balance'
          materiality_flag = 'Materiality Status';
    sum balance;
run;
title;

/* --- Step 7: Bank reconciliation exception detail --- */
title1 "Bank Reconciliation Exceptions — GL Side";
proc print data=work.bank_exceptions_gl noobs;
    var gl_txn_id transaction_date amount reference_id exception_reason;
run;

title1 "Bank Reconciliation Exceptions — Bank Side";
proc print data=work.bank_exceptions_bank noobs;
    var bank_txn_id transaction_date amount reference_id exception_reason;
run;
title;

/* --- Step 8: Intercompany reconciliation exception detail --- */
title1 "Intercompany Reconciliation Exceptions";
proc print data=work.ic_all_exceptions noobs;
    var entity_from entity_to account_id balance_from balance_to
        net_difference netting_status;
    where exception_flag = 'Y';
    sum net_difference;
run;
title;

/* --- Cleanup temporary work datasets --- */
proc datasets lib=work nolist nowarn;
    delete gl_raw gl_cash_sorted bank_stmt_sorted
           bank_exceptions_bank_temp
           _ic_pair_: _ic_net_:;
quit;

/* --- Reset options to defaults --- */
options nomprint nomlogic nosymbolgen;

%put NOTE: ============================================================;
%put NOTE: RECONCILIATION COMPLETE;
%put NOTE: Period: &recon_period;
%put NOTE: Total Exceptions: &total_exceptions;
%put NOTE: Return Code: &recon_rc;
%put NOTE: ============================================================;
