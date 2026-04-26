%let input_csv = C:/Users/iyedm/OneDrive/Desktop/Code Migration/helper_dataFrames/CARS.csv;
%let output_dir = C:/Users/iyedm/OneDrive/Desktop/Code Migration/output;

%macro import_source;
    proc import datafile="&input_csv"
        out=work.cars_source
        dbms=csv
        replace;
        guessingrows=max;
    run;
%mend;

%macro prepare_numeric(out_ds=);
    data work.&out_ds;
        set work.cars_source;
        msrp_num = input(compress(MSRP, '$,'), comma12.);
        invoice_num = input(compress(Invoice, '$,'), comma12.);
        markup_amt = msrp_num - invoice_num;
        markup_pct = round((markup_amt / invoice_num) * 100, 0.01);
        efficiency_gap = MPG_Highway - MPG_City;
    run;
%mend;

%macro build_origin_summary(in_ds=, out_ds=);
    proc sql;
        create table work.&out_ds as
        select
            Origin,
            count(*) as car_count,
            round(avg(markup_pct), 0.01) as avg_markup_pct,
            round(avg(Horsepower), 0.01) as avg_horsepower,
            round(avg(MPG_Highway), 0.01) as avg_mpg_highway
        from work.&in_ds
        group by Origin
        order by Origin;
    quit;
%mend;

%macro build_drivetrain_freq(in_ds=, out_ds=);
    proc freq data=work.&in_ds noprint order=freq;
        tables DriveTrain / out=work.&out_ds;
    run;
%mend;

%macro build_top_markup(in_ds=, out_ds=, n=10);
    proc sort data=work.&in_ds out=work.&out_ds._sorted;
        by descending markup_pct;
    run;

    data work.&out_ds;
        set work.&out_ds._sorted;
        if _N_ <= &n;
        keep Make Model Type Origin markup_amt markup_pct Horsepower MPG_Highway;
    run;
%mend;

%macro plot_origin_summary(in_ds=);
    ods listing gpath="&output_dir";
    ods graphics on / reset imagename="case_040_origin_bar" imagefmt=png;

    proc sgplot data=work.&in_ds;
        vbar Origin / response=avg_markup_pct datalabel;
        yaxis label="Average Markup Percent";
    run;

    ods graphics off;
%mend;

%macro plot_efficiency(in_ds=);
    ods listing gpath="&output_dir";
    ods graphics on / reset imagename="case_040_efficiency_scatter" imagefmt=png;

    proc sgplot data=work.&in_ds;
        scatter x=Horsepower y=MPG_Highway / group=Origin transparency=0.25;
        reg x=Horsepower y=MPG_Highway / nomarkers;
    run;

    ods graphics off;
%mend;

%macro export_outputs;
    proc export data=work.case_040_detail_output
        outfile="&output_dir./case_040_detail_output.csv"
        dbms=csv
        replace;
    run;

    proc export data=work.case_040_origin_summary
        outfile="&output_dir./case_040_origin_summary.csv"
        dbms=csv
        replace;
    run;

    proc export data=work.case_040_drivetrain_freq
        outfile="&output_dir./case_040_drivetrain_freq.csv"
        dbms=csv
        replace;
    run;

    proc export data=work.case_040_top_markup
        outfile="&output_dir./case_040_top_markup.csv"
        dbms=csv
        replace;
    run;
%mend;

%macro run_dashboard(top_n=12);
    %import_source;
    %prepare_numeric(out_ds=case_040_detail_output);
    %build_origin_summary(in_ds=case_040_detail_output, out_ds=case_040_origin_summary);
    %build_drivetrain_freq(in_ds=case_040_detail_output, out_ds=case_040_drivetrain_freq);
    %build_top_markup(in_ds=case_040_detail_output, out_ds=case_040_top_markup, n=&top_n);
    %plot_origin_summary(in_ds=case_040_origin_summary);
    %plot_efficiency(in_ds=case_040_detail_output);
    %export_outputs;
%mend;

%run_dashboard(top_n=12);
