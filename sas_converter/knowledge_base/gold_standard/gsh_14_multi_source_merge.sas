/******************************************************************************
 * Program Name : gsh_14_multi_source_merge.sas
 * Author       : Data Integration Team — Master Data Management Division
 * Created      : 2026-01-15
 * Modified     : 2026-02-19
 * Version      : 2.0
 * Purpose      : Multi-source data integration engine for building MDM-style
 *                golden records. Extracts, standardizes, and merges customer
 *                data from CRM, ERP, Web Analytics, and External (D&B) sources
 *                using probabilistic matching and survivorship rules to produce
 *                a single unified master record per entity.
 * Dependencies : matching_utilities.sas (shared fuzzy matching helper functions)
 * Frequency    : Weekly / On-demand
 * Sources      : CRM, ERP, Web Analytics, External (D&B / credit bureau)
 * Analyst      : J. Ramirez
 * Change Log   :
 *   2026-01-15  v1.0  Initial multi-source extraction framework  (J. Ramirez)
 *   2026-01-28  v1.5  Added fuzzy matching with Jaro-Winkler     (A. Chen)
 *   2026-02-10  v1.8  Survivorship rules and golden record build (J. Ramirez)
 *   2026-02-19  v2.0  Quality reporting and cross-reference      (M. Okafor)
 ******************************************************************************/

/* ========================================================================= */
/* SECTION 1: Environment Setup — Libraries, Options, Run Parameters         */
/* ========================================================================= */

options mprint mlogic symbolgen nocenter ls=200 ps=65
        validvarname=v7 nofmterr msglevel=i compress=yes;

/* --- Library references for source systems and master output --- */
libname crm      '/data/sources/crm'            access=readonly;
libname erp      '/data/sources/erp'            access=readonly;
libname web      '/data/sources/web_analytics'  access=readonly;
libname external '/data/sources/external_feeds' access=readonly;
libname golden   '/data/mdm/golden_records';

/* --- Run parameters and control settings --- */
%let run_date       = %sysfunc(today(), yymmdd10.);
%let run_timestamp  = %sysfunc(datetime());
%let analyst_name   = J. Ramirez;
%let run_mode       = PRODUCTION;
%let batch_id       = MDM_%sysfunc(today(), yymmddn8.);

/* --- Match threshold parameters --- */
%let match_threshold_high = 0.85;
%let match_threshold_low  = 0.65;
%let exact_match_weight   = 1.0;
%let fuzzy_match_weight   = 0.8;
%let partial_match_weight = 0.5;
%let max_match_candidates = 100;

/* --- Field-level weights for composite matching --- */
%let wt_name    = 0.30;
%let wt_address = 0.25;
%let wt_phone   = 0.20;
%let wt_email   = 0.15;
%let wt_dob     = 0.10;

/* --- Source priority order for survivorship --- */
%let source_priority = CRM ERP EXTERNAL WEB;
%let n_sources       = 4;

/* --- Control flags --- */
%let integration_rc  = 0;
%let sources_loaded  = 0;
%let matches_done    = 0;
%let golden_built    = 0;
%let xref_created    = 0;
%let report_done     = 0;

/* --- Include shared matching utilities --- */
%include '/data/mdm/shared/matching_utilities.sas';

/* ========================================================================= */
/* SECTION 2: Macro Definitions                                              */
/* ========================================================================= */

/*****************************************************************************
 * MACRO: extract_source
 * Purpose: Extract records from a source system, standardize name and address
 *          fields, normalize phone/email via regex, and dedup within source.
 * Parameters:
 *   source_name  - logical name of source (CRM, ERP, WEB, EXTERNAL)
 *   lib          - libname reference for the source
 *   table        - source table name
 *   key_cols     - primary key columns in that source
 *   standardize  - Y/N flag for additional field cleaning
 * Outputs: work.std_<source_name>
 *****************************************************************************/
%macro extract_source(source_name=, lib=, table=, key_cols=, standardize=Y);
    %local n_raw n_deduped rx_phone rx_email;

    %put NOTE: ========================================================;
    %put NOTE: EXTRACT SOURCE: &source_name from &lib..&table;
    %put NOTE: Key columns: &key_cols | Standardize: &standardize;
    %put NOTE: ========================================================;

    /* --- Step 1: Extract and standardize core fields --- */
    data work.raw_&source_name;
        set &lib..&table;

        /* --- Name standardization: uppercase, compress, strip whitespace --- */
        std_first_name = strip(upcase(compress(first_name, , 'ka')));
        std_last_name  = strip(upcase(compress(last_name, , 'ka')));
        std_full_name  = catx(' ', std_first_name, std_last_name);

        /* --- Address standardization --- */
        std_address1 = strip(upcase(address_line1));
        std_address2 = strip(upcase(address_line2));
        std_city     = strip(upcase(city));
        std_state    = strip(upcase(state));
        std_zip      = strip(compress(zip_code, , 'kd'));

        /* --- Phone normalization via PRXMATCH --- */
        rx_phone = prxparse('/(\d{3})[\s\-\.\)]*(\d{3})[\s\-\.]*(\d{4})/');
        if prxmatch(rx_phone, phone) then do;
            std_phone = cats(prxposn(rx_phone, 1, phone),
                             prxposn(rx_phone, 2, phone),
                             prxposn(rx_phone, 3, phone));
        end;
        else std_phone = '';

        /* --- Email normalization via PRXMATCH --- */
        rx_email = prxparse('/([a-zA-Z0-9._%-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})/');
        if prxmatch(rx_email, email) then do;
            std_email = lowcase(strip(prxposn(rx_email, 1, email)));
        end;
        else std_email = '';

        /* --- Source tracking metadata --- */
        source_system  = "&source_name";
        extract_date   = today();
        format extract_date yymmdd10.;

        drop rx_phone rx_email;
    run;

    /* --- Step 2: Additional cleaning if requested --- */
    %if &standardize = Y %then %do;
        data work.raw_&source_name;
            set work.raw_&source_name;

            /* --- Remove common name prefixes/suffixes --- */
            std_first_name = tranwrd(std_first_name, 'JR', '');
            std_first_name = tranwrd(std_first_name, 'SR', '');
            std_last_name  = tranwrd(std_last_name, 'III', '');
            std_last_name  = tranwrd(std_last_name, 'II', '');

            /* --- Address abbreviation standardization --- */
            std_address1 = tranwrd(std_address1, 'STREET', 'ST');
            std_address1 = tranwrd(std_address1, 'AVENUE', 'AVE');
            std_address1 = tranwrd(std_address1, 'BOULEVARD', 'BLVD');
            std_address1 = tranwrd(std_address1, 'DRIVE', 'DR');
            std_address1 = tranwrd(std_address1, 'ROAD', 'RD');
            std_address1 = tranwrd(std_address1, 'SUITE', 'STE');
            std_address1 = tranwrd(std_address1, 'APARTMENT', 'APT');

            /* --- Translate special characters in names --- */
            std_full_name = translate(std_full_name, ' ', '-');
            std_full_name = compress(std_full_name, , 'kas');
        run;
    %end;

    /* --- Step 3: Dedup within source by key columns --- */
    proc sort data=work.raw_&source_name
              out=work.std_&source_name nodupkey;
        by &key_cols;
    run;

    /* --- Log extraction metrics --- */
    proc sql noprint;
        select count(*) into :n_raw trimmed
        from work.raw_&source_name;
        select count(*) into :n_deduped trimmed
        from work.std_&source_name;
    quit;

    %put NOTE: &source_name extraction complete.;
    %put NOTE:   Raw records: &n_raw | After dedup: &n_deduped;
    %let sources_loaded = %eval(&sources_loaded + 1);
%mend extract_source;


/*****************************************************************************
 * MACRO: fuzzy_match
 * Purpose: Perform probabilistic matching between two standardized source
 *          datasets. Computes approximate Jaro-Winkler similarity on name
 *          fields, exact matching on key fields, and composite scoring
 *          across multiple fields using weighted arrays.
 * Parameters:
 *   ds1        - first source dataset (work.std_*)
 *   ds2        - second source dataset (work.std_*)
 *   match_cols - columns to use for matching
 *   threshold  - minimum composite score for automatic match
 * Outputs: work.matches_<ds1>_<ds2>, work.review_<ds1>_<ds2>
 *****************************************************************************/
%macro fuzzy_match(ds1=, ds2=, match_cols=, threshold=&match_threshold_high);
    %local n_exact n_fuzzy n_review n_total pair_label;
    %let pair_label = %scan(&ds1, 2, .)_%scan(&ds2, 2, .);

    %put NOTE: ========================================================;
    %put NOTE: FUZZY MATCH: &ds1 vs &ds2;
    %put NOTE: Match columns: &match_cols | Threshold: &threshold;
    %put NOTE: ========================================================;

    /* --- Step 1: Exact key matching via PROC SQL --- */
    proc sql noprint;
        create table work.exact_&pair_label as
        select
            a.source_system as source_1,
            a.customer_id   as id_1,
            a.std_full_name as name_1,
            b.source_system as source_2,
            b.customer_id   as id_2,
            b.std_full_name as name_2,
            1.0             as match_score,
            'EXACT'         as match_type length=10,
            0               as score_name,
            0               as score_addr,
            0               as score_phone,
            0               as score_email,
            0               as score_zip,
            1.0             as total_score
        from &ds1 a
        inner join &ds2 b
            on  a.std_phone = b.std_phone
            and a.std_phone ne ''
            and a.std_last_name = b.std_last_name
        order by a.customer_id, b.customer_id;

        select count(*) into :n_exact trimmed
        from work.exact_&pair_label;
    quit;

    %put NOTE: Exact matches found: &n_exact;

    /* --- Step 2: Jaro-Winkler similarity approximation DATA step --- */
    data work.fuzzy_candidates_&pair_label;
        set &ds1(keep=customer_id std_full_name std_first_name std_last_name
                      std_address1 std_city std_state std_zip
                      std_phone std_email source_system
                 rename=(customer_id=id_1 std_full_name=name_1
                         std_first_name=fname_1 std_last_name=lname_1
                         std_address1=addr_1 std_city=city_1
                         std_state=state_1 std_zip=zip_1
                         std_phone=phone_1 std_email=email_1
                         source_system=source_1));

        /* --- Load second dataset into hash for comparison --- */
        if _n_ = 1 then do;
            declare hash h2(dataset: "&ds2");
            h2.definekey('_seq2');
            h2.definedata('customer_id', 'std_full_name', 'std_first_name',
                          'std_last_name', 'std_address1', 'std_city',
                          'std_state', 'std_zip', 'std_phone', 'std_email',
                          'source_system');
            h2.definedone();
            declare hiter hi2('h2');
        end;

        /* --- Declare variables from second dataset --- */
        length customer_id $20 std_full_name $80 std_first_name $40
               std_last_name $40 std_address1 $100 std_city $50
               std_state $2 std_zip $10 std_phone $10 std_email $80
               source_system $20;

        /* --- Scoring arrays and variables --- */
        length id_2 $20 name_2 $80 source_2 $20 match_type $10;
        array scores{5} score_name score_addr score_phone score_email score_zip;
        array weights{5} _temporary_ (&wt_name &wt_address &wt_phone
                                       &wt_email &wt_dob);

        retain match_pair_seq 0;

        /* --- Iterate over second dataset for each record in first --- */
        rc = hi2.first();
        do while (rc = 0);
            id_2     = customer_id;
            name_2   = std_full_name;
            source_2 = source_system;

            /* --- Name similarity: character-level overlap approximation --- */
            len1 = length(strip(name_1));
            len2 = length(strip(name_2));
            if len1 > 0 and len2 > 0 then do;
                common = 0;
                do k = 1 to min(len1, len2);
                    if substr(name_1, k, 1) = substr(name_2, k, 1) then
                        common + 1;
                end;
                score_name = common / max(len1, len2);
            end;
            else score_name = 0;

            /* --- Address similarity: exact or substring match --- */
            if addr_1 ne '' and std_address1 ne '' then do;
                if addr_1 = std_address1 then score_addr = 1.0;
                else if index(addr_1, strip(std_address1)) > 0
                     or index(std_address1, strip(addr_1)) > 0
                     then score_addr = 0.7;
                else score_addr = 0;
            end;
            else score_addr = 0;

            /* --- Phone exact match --- */
            if phone_1 ne '' and std_phone ne '' then
                score_phone = (phone_1 = std_phone);
            else score_phone = 0;

            /* --- Email exact match --- */
            if email_1 ne '' and std_email ne '' then
                score_email = (lowcase(email_1) = lowcase(std_email));
            else score_email = 0;

            /* --- ZIP code: exact or prefix match --- */
            if zip_1 ne '' and std_zip ne '' then do;
                if zip_1 = std_zip then score_zip = 1.0;
                else if substr(zip_1, 1, 3) = substr(std_zip, 1, 3)
                     then score_zip = 0.5;
                else score_zip = 0;
            end;
            else score_zip = 0;

            /* --- Composite weighted score from all fields --- */
            total_score = 0;
            do f = 1 to 5;
                total_score + (scores{f} * weights{f});
            end;

            /* --- Apply threshold filter and classify --- */
            %if &threshold >= &match_threshold_low %then %do;
                if total_score >= &match_threshold_low then do;
                    match_pair_seq + 1;
                    if total_score >= &threshold then
                        match_type = 'FUZZY';
                    else
                        match_type = 'REVIEW';
                    output;
                end;
            %end;

            rc = hi2.next();
        end;

        keep id_1 name_1 source_1 id_2 name_2 source_2
             score_name score_addr score_phone score_email score_zip
             total_score match_type match_pair_seq;
    run;

    /* --- Step 3: Combine exact and fuzzy matches into final outputs --- */
    data work.matches_&pair_label(where=(match_type in ('EXACT' 'FUZZY')))
         work.review_&pair_label(where=(match_type = 'REVIEW'));
        set work.exact_&pair_label
            work.fuzzy_candidates_&pair_label;
    run;

    /* --- Log match summary --- */
    proc sql noprint;
        select count(*) into :n_fuzzy trimmed
        from work.matches_&pair_label
        where match_type = 'FUZZY';
        select count(*) into :n_review trimmed
        from work.review_&pair_label;
    quit;

    %let n_total = %eval(&n_exact + &n_fuzzy);
    %put NOTE: Match summary for &pair_label:;
    %put NOTE:   Exact: &n_exact | Fuzzy: &n_fuzzy | Total: &n_total | Review: &n_review;
    %let matches_done = %eval(&matches_done + 1);
%mend fuzzy_match;


/*****************************************************************************
 * MACRO: build_golden_record
 * Purpose: Create the master golden record by applying survivorship rules
 *          to matched record clusters. Survivorship determines which source
 *          value wins for each field based on recency, completeness, and
 *          source priority.
 * Parameters:
 *   matched_ds        - consolidated match dataset
 *   survivorship_rules - rule type (MOST_RECENT / MOST_COMPLETE / SOURCE_PRIORITY)
 * Outputs: work.golden_master, golden.golden_records
 *****************************************************************************/
%macro build_golden_record(matched_ds=, survivorship_rules=SOURCE_PRIORITY);
    %local n_clusters n_golden i field_group;

    %put NOTE: ========================================================;
    %put NOTE: BUILD GOLDEN RECORD from &matched_ds;
    %put NOTE: Survivorship rules: &survivorship_rules;
    %put NOTE: Source priority: &source_priority;
    %put NOTE: ========================================================;

    /* --- Step 1: Assign cluster IDs to matched record groups --- */
    proc sql noprint;
        create table work.match_clusters as
        select
            monotonic() as cluster_id,
            id_1, source_1, name_1,
            id_2, source_2, name_2,
            total_score as match_score,
            match_type
        from &matched_ds
        order by id_1, match_score desc;

        select count(distinct cluster_id) into :n_clusters trimmed
        from work.match_clusters;
    quit;

    %put NOTE: Identified &n_clusters match clusters.;

    /* --- Step 2: Apply survivorship rules via DATA step --- */
    data work.golden_candidates;
        set work.match_clusters;
        by cluster_id;

        length golden_id $20 winning_source $20
               golden_name $80 golden_address $100
               golden_city $50 golden_state $2 golden_zip $10
               golden_phone $10 golden_email $80
               golden_dob 8 survivorship_method $20;

        retain golden_id golden_name golden_address golden_city
               golden_state golden_zip golden_phone golden_email
               golden_dob winning_source completeness_score;

        format golden_dob yymmdd10.;

        if first.cluster_id then do;
            golden_id = cats('GLD_', put(cluster_id, z8.));
            /* --- Initialize from first record in cluster --- */
            golden_name    = name_1;
            winning_source = source_1;
            golden_phone   = '';
            golden_email   = '';
            golden_address = '';
            golden_city    = '';
            golden_state   = '';
            golden_zip     = '';
            completeness_score = 0;
        end;

        /* --- Most recent wins for address fields --- */
        %if &survivorship_rules = MOST_RECENT %then %do;
            survivorship_method = 'MOST_RECENT';
            /* Address: take the most recently updated source record */
            if source_2 in ('CRM' 'ERP') and golden_address = '' then do;
                winning_source = source_2;
            end;
        %end;

        /* --- Most complete wins for demographics --- */
        %if &survivorship_rules = MOST_COMPLETE %then %do;
            survivorship_method = 'MOST_COMPLETE';
            /* Pick the record with the most non-missing fields */
            completeness_score = (golden_name ne '') + (golden_phone ne '') +
                                 (golden_email ne '') + (golden_address ne '');
        %end;

        /* --- Source priority based survivorship --- */
        %if &survivorship_rules = SOURCE_PRIORITY %then %do;
            survivorship_method = 'SOURCE_PRIORITY';
            /* --- Loop over field groups to apply priority --- */
            %do i = 1 %to &n_sources;
                %let field_group = %scan(&source_priority, &i);

                /* --- CRM wins for contact preferences --- */
                %if &field_group = CRM %then %do;
                    if source_1 = 'CRM' or source_2 = 'CRM' then do;
                        if source_1 = 'CRM' then winning_source = source_1;
                        else winning_source = source_2;
                    end;
                %end;

                /* --- ERP wins for billing address --- */
                %if &field_group = ERP %then %do;
                    if source_1 = 'ERP' or source_2 = 'ERP' then do;
                        /* ERP address takes priority for billing */
                        if golden_address = '' then
                            winning_source = 'ERP';
                    end;
                %end;

                /* --- EXTERNAL wins for credit and demographic data --- */
                %if &field_group = EXTERNAL %then %do;
                    if source_1 = 'EXTERNAL' or source_2 = 'EXTERNAL' then do;
                        /* External data enrichment for demographics */
                        if golden_dob = . then
                            winning_source = 'EXTERNAL';
                    end;
                %end;

                /* --- WEB is lowest priority, gap-fill only --- */
                %if &field_group = WEB %then %do;
                    if source_1 = 'WEB' or source_2 = 'WEB' then do;
                        /* Web data used only for email gap-fill */
                        if golden_email = '' then
                            winning_source = 'WEB';
                    end;
                %end;
            %end;
        %end;

        if last.cluster_id then output;
    run;

    /* --- Step 3: Final deduplication to create golden master --- */
    proc sql noprint;
        create table work.golden_master as
        select distinct
            golden_id,
            golden_name,
            golden_address,
            golden_city,
            golden_state,
            golden_zip,
            golden_phone,
            golden_email,
            winning_source,
            survivorship_method,
            "&run_date"d           as created_date format=yymmdd10.,
            "&batch_id"            as batch_id     length=30,
            "&analyst_name"        as created_by   length=30
        from work.golden_candidates
        where golden_id ne ''
        order by golden_id;

        select count(*) into :n_golden trimmed
        from work.golden_master;
    quit;

    /* --- Step 4: Write to permanent golden library --- */
    data golden.golden_records;
        set work.golden_master;
    run;

    %put NOTE: Golden record build complete.;
    %put NOTE:   Clusters: &n_clusters | Golden records: &n_golden;
    %let golden_built = 1;
%mend build_golden_record;


/*****************************************************************************
 * MACRO: cross_reference_table
 * Purpose: Build a cross-reference (XREF) table mapping each source system
 *          ID back to its assigned golden record ID. Enables bidirectional
 *          lookup between source and master.
 * Outputs: golden.xref_source_golden
 *****************************************************************************/
%macro cross_reference_table;
    %local n_xref;

    %put NOTE: ========================================================;
    %put NOTE: CROSS-REFERENCE TABLE — Source to Golden ID Mapping;
    %put NOTE: ========================================================;

    /* --- Step 1: Build XREF from match clusters and golden candidates --- */
    proc sql noprint;
        create table work.xref_raw as
        select distinct
            a.golden_id,
            b.id_1 as source_id,
            b.source_1 as source_system
        from work.golden_candidates a
        inner join work.match_clusters b
            on a.cluster_id = b.cluster_id
        union
        select distinct
            a.golden_id,
            b.id_2 as source_id,
            b.source_2 as source_system
        from work.golden_candidates a
        inner join work.match_clusters b
            on a.cluster_id = b.cluster_id
        order by golden_id, source_system, source_id;
    quit;

    /* --- Step 2: Assign global sequence IDs and write permanent --- */
    data golden.xref_source_golden;
        set work.xref_raw;
        by golden_id source_system;

        retain global_xref_seq 0;
        global_xref_seq + 1;

        length xref_id $20;
        xref_id = cats('XREF_', put(global_xref_seq, z8.));

        xref_date = today();
        format xref_date yymmdd10.;

        label golden_id     = 'Golden Record ID'
              source_id     = 'Source System ID'
              source_system = 'Source System Name'
              xref_id       = 'Cross-Reference ID'
              xref_date     = 'XREF Creation Date';
    run;

    proc sql noprint;
        select count(*) into :n_xref trimmed
        from golden.xref_source_golden;
    quit;

    %put NOTE: Cross-reference table created with &n_xref entries.;
    %let xref_created = 1;
%mend cross_reference_table;


/*****************************************************************************
 * MACRO: quality_report
 * Purpose: Measure and report on integration quality: match rates per source
 *          pair, match type distributions, average match scores, unmatched
 *          record analysis, and overall summary statistics.
 * Outputs: work.quality_summary, ODS report
 *****************************************************************************/
%macro quality_report;
    %local n_unmatched total_records overall_match_rate;

    %put NOTE: ========================================================;
    %put NOTE: QUALITY REPORT — Integration Metrics;
    %put NOTE: Run date: &run_date | Batch: &batch_id;
    %put NOTE: ========================================================;

    /* --- Step 1: Match rates per source pair via PROC SQL --- */
    proc sql noprint;
        create table work.match_rates as
        select
            source_1,
            source_2,
            count(*)    as total_pairs,
            sum(case when match_type = 'EXACT'  then 1 else 0 end) as exact_matches,
            sum(case when match_type = 'FUZZY'  then 1 else 0 end) as fuzzy_matches,
            sum(case when match_type = 'REVIEW' then 1 else 0 end) as review_needed,
            avg(total_score)   as avg_match_score format=8.4,
            min(total_score)   as min_score       format=8.4,
            max(total_score)   as max_score       format=8.4
        from work.all_matches
        group by source_1, source_2
        order by source_1, source_2;
    quit;

    /* --- Step 2: Match type distribution via PROC FREQ --- */
    proc freq data=work.all_matches noprint;
        tables match_type / out=work.match_type_dist;
        tables source_1 * match_type / out=work.source_match_dist;
    run;

    /* --- Step 3: Average match scores summary via PROC MEANS --- */
    proc means data=work.all_matches noprint
               n mean std min q1 median q3 max;
        var total_score score_name score_addr score_phone
            score_email score_zip;
        class match_type;
        output out=work.score_stats
            mean= n= std= min= max= / autoname;
    run;

    /* --- Step 4: Unmatched record analysis DATA step --- */
    data work.unmatched_records;
        set work.std_CRM(in=a)
            work.std_ERP(in=b)
            work.std_WEB(in=c)
            work.std_EXTERNAL(in=d);

        if a then source_system = 'CRM';
        else if b then source_system = 'ERP';
        else if c then source_system = 'WEB';
        else if d then source_system = 'EXTERNAL';

        /* --- Check if this record was matched anywhere --- */
        if _n_ = 1 then do;
            declare hash h_matched(dataset: 'work.all_match_ids');
            h_matched.definekey('matched_id');
            h_matched.definedone();
        end;

        length matched_id $20;
        matched_id = customer_id;
        rc = h_matched.find();
        if rc ne 0 then output;

        drop rc matched_id;
    run;

    proc sql noprint;
        select count(*) into :n_unmatched trimmed
        from work.unmatched_records;

        select count(*) into :total_records trimmed
        from (select id_1 as rid from work.all_matches
              union
              select id_2 as rid from work.all_matches);
    quit;

    %let overall_match_rate = %sysevalf(
        &total_records / (&total_records + &n_unmatched) * 100);

    /* --- Step 5: Summary report via PROC REPORT --- */
    title1 "Multi-Source Data Integration — Quality Report";
    title2 "Run Date: &run_date | Batch: &batch_id | Analyst: &analyst_name";

    proc report data=work.match_rates nowd
                style(header)=[backgroundcolor=steelblue foreground=white
                               font_weight=bold];
        columns source_1 source_2 total_pairs exact_matches fuzzy_matches
                review_needed avg_match_score;

        define source_1       / group   'Source 1';
        define source_2       / group   'Source 2';
        define total_pairs    / sum     'Total Pairs'  format=comma12.;
        define exact_matches  / sum     'Exact'        format=comma12.;
        define fuzzy_matches  / sum     'Fuzzy'        format=comma12.;
        define review_needed  / sum     'Review'       format=comma12.;
        define avg_match_score / mean   'Avg Score'    format=8.4;

        rbreak after / summarize
            style=[font_weight=bold backgroundcolor=lightyellow];

        compute after;
            line '';
            line "Overall Match Rate: &overall_match_rate.%";
            line "Unmatched Records: &n_unmatched";
            line "Golden Records Created: (see golden.golden_records)";
        endcomp;
    run;
    title;

    %put NOTE: Quality report generated.;
    %put NOTE:   Overall match rate: &overall_match_rate.%;
    %put NOTE:   Unmatched records: &n_unmatched;
    %let report_done = 1;
%mend quality_report;


/* ========================================================================= */
/* SECTION 3: Main Program Execution                                         */
/* ========================================================================= */

%put NOTE: ========================================================;
%put NOTE: MULTI-SOURCE DATA INTEGRATION ENGINE v2.0;
%put NOTE: Run date: &run_date | Mode: &run_mode;
%put NOTE: Analyst: &analyst_name | Batch: &batch_id;
%put NOTE: ========================================================;

/* --- Step 1: Extract and standardize all source systems --- */
%extract_source(source_name=CRM,
                lib=crm,
                table=customers,
                key_cols=customer_id,
                standardize=Y);

%extract_source(source_name=ERP,
                lib=erp,
                table=business_partners,
                key_cols=partner_id,
                standardize=Y);

%extract_source(source_name=WEB,
                lib=web,
                table=registered_users,
                key_cols=user_id,
                standardize=Y);

%extract_source(source_name=EXTERNAL,
                lib=external,
                table=dnb_records,
                key_cols=duns_number,
                standardize=N);

/* --- Step 2: Fuzzy match all source pairs (C(4,2) = 6 combinations) --- */
%fuzzy_match(ds1=work.std_CRM, ds2=work.std_ERP,
             match_cols=std_full_name std_phone std_email,
             threshold=&match_threshold_high);

%fuzzy_match(ds1=work.std_CRM, ds2=work.std_WEB,
             match_cols=std_full_name std_email,
             threshold=&match_threshold_high);

%fuzzy_match(ds1=work.std_CRM, ds2=work.std_EXTERNAL,
             match_cols=std_full_name std_address1 std_zip,
             threshold=&match_threshold_high);

%fuzzy_match(ds1=work.std_ERP, ds2=work.std_WEB,
             match_cols=std_full_name std_email std_phone,
             threshold=&match_threshold_high);

%fuzzy_match(ds1=work.std_ERP, ds2=work.std_EXTERNAL,
             match_cols=std_full_name std_address1,
             threshold=&match_threshold_high);

%fuzzy_match(ds1=work.std_WEB, ds2=work.std_EXTERNAL,
             match_cols=std_full_name std_email,
             threshold=&match_threshold_high);

/* --- Step 3: Consolidate all match results --- */
data work.all_matches;
    set work.matches_std_CRM_std_ERP
        work.matches_std_CRM_std_WEB
        work.matches_std_CRM_std_EXTERNAL
        work.matches_std_ERP_std_WEB
        work.matches_std_ERP_std_EXTERNAL
        work.matches_std_WEB_std_EXTERNAL;
run;

/* --- Create lookup of all matched IDs for unmatched analysis --- */
proc sql noprint;
    create table work.all_match_ids as
    select distinct id_1 as matched_id from work.all_matches
    union
    select distinct id_2 as matched_id from work.all_matches;
quit;

/* --- Step 4: Build golden records with survivorship --- */
%build_golden_record(matched_ds=work.all_matches,
                     survivorship_rules=SOURCE_PRIORITY);

/* --- Step 5: Create cross-reference table --- */
%cross_reference_table;

/* --- Step 6: Generate quality report --- */
%quality_report;

/* --- Step 7: Error handling and final status --- */
%if &integration_rc ne 0 %then %do;
    %put ERROR: ========================================================;
    %put ERROR: Integration completed with errors (RC=&integration_rc).;
    %put ERROR: Review log for details.;
    %put ERROR: ========================================================;
%end;
%else %do;
    %put NOTE: ========================================================;
    %put NOTE: Integration completed successfully (RC=0).;
    %put NOTE: ========================================================;
%end;

/* --- Cleanup temporary work datasets --- */
proc datasets lib=work nolist nowarn;
    delete raw_: fuzzy_candidates_: exact_: match_clusters
           xref_raw all_match_ids all_matches
           unmatched_records match_rates score_stats
           match_type_dist source_match_dist;
quit;

/* --- Reset options to defaults --- */
options nomprint nomlogic nosymbolgen;

/* --- Final completion banner --- */
%put NOTE: ========================================================;
%put NOTE: MULTI-SOURCE INTEGRATION COMPLETE;
%put NOTE: Sources loaded: &sources_loaded | Matches done: &matches_done;
%put NOTE: Golden built: &golden_built | XREF created: &xref_created;
%put NOTE: Report done: &report_done | Return code: &integration_rc;
%put NOTE: ========================================================;
