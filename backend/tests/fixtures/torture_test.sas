/* torture_test.sas — hits every hard SAS pattern the pipeline must handle.
   Used by translate_test.py to validate end-to-end translation quality.
*/

/* ── 1. RETAIN + BY-group FIRST./LAST. ──────────────────────────── */
data customer_summary;
    set transactions;
    by customer_id;
    retain running_total 0 tx_count 0;
    if first.customer_id then do;
        running_total = 0;
        tx_count = 0;
    end;
    running_total + amount;
    tx_count + 1;
    if last.customer_id then output;
run;

/* ── 2. Missing value logic (SAS . < any number) ─────────────────── */
data cleaned;
    set raw_data;
    if age = . then age = 0;
    if score < . then flag = 'MISSING';
    else if score > 100 then flag = 'INVALID';
    else flag = 'OK';
run;

/* ── 3. PROC SQL with correlated subquery ────────────────────────── */
proc sql;
    create table high_value as
    select t.customer_id,
           t.amount,
           avg_t.avg_amount
    from transactions t
    inner join (
        select customer_id,
               mean(amount) as avg_amount
        from transactions
        group by customer_id
    ) avg_t on t.customer_id = avg_t.customer_id
    where t.amount > avg_t.avg_amount * 1.5;
quit;

/* ── 4. Macro with parameters + %DO loop ────────────────────────── */
%macro rolling_mean(dsn=, var=, window=3, out=);
    data &out;
        set &dsn;
        array vals{&window} _temporary_;
        retain idx 0;
        idx = mod(idx, &window) + 1;
        vals{idx} = &var;
        if _n_ >= &window then
            &var._ma = mean(of vals{*});
        else
            &var._ma = .;
    run;
%mend;

%rolling_mean(dsn=prices, var=close, window=5, out=prices_ma);

/* ── 5. PROC MEANS with CLASS and OUTPUT ────────────────────────── */
proc means data=sales noprint;
    class region product_line;
    var revenue units_sold;
    output out=summary(drop=_type_ _freq_)
        mean=avg_revenue avg_units
        sum=total_revenue total_units
        n=obs_count;
run;

/* ── 6. PROC SORT NODUPKEY ──────────────────────────────────────── */
proc sort data=customers nodupkey;
    by customer_id;
run;

/* ── 7. Hash object for lookup ──────────────────────────────────── */
data enriched;
    if _n_ = 1 then do;
        declare hash h(dataset: 'lookup_table');
        h.defineKey('product_id');
        h.defineData('product_name', 'category');
        h.defineDone();
    end;
    set transactions;
    rc = h.find();
    if rc ^= 0 then product_name = 'UNKNOWN';
run;

/* ── 8. Multi-level nested macro ────────────────────────────────── */
%macro apply_to_all(action=, datasets=);
    %let n = %sysfunc(countw(&datasets));
    %do i = 1 %to &n;
        %let ds = %scan(&datasets, &i);
        %&action(dsn=&ds);
    %end;
%mend;

%macro summarise(dsn=);
    proc means data=&dsn; run;
%mend;

%apply_to_all(action=summarise, datasets=sales returns inventory);

/* ── 9. PROC TRANSPOSE ──────────────────────────────────────────── */
proc transpose data=monthly_sales out=wide_sales prefix=month_;
    by product_id;
    id month;
    var revenue;
run;

/* ── 10. Complex WHERE + FORMAT + LABEL ──────────────────────────── */
data report;
    set survey;
    where age >= 18 and age <= 65
          and status in ('ACTIVE', 'PENDING')
          and score ^= .;
    format score 8.2
           survey_date date9.;
    label score = 'Survey Score (0-100)'
          survey_date = 'Date of Survey';
    score_pct = score / 100;
run;
