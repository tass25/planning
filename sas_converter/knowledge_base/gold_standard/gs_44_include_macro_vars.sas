/* gs_44 - %INCLUDE with macro variable paths */
%LET project_root = /sas/projects/analytics;
%LET macro_lib = &project_root/macros;

%INCLUDE "&macro_lib/logging.sas";
%INCLUDE "&macro_lib/data_quality.sas";
%INCLUDE &project_root/config/runtime_params.sas;

%init_logging(log_path=&project_root/logs);

DATA work.analysis_data;
    SET rawlib.source_table;
    WHERE process_date = TODAY();
RUN;

%data_quality_check(dsn=work.analysis_data, checks=missing duplicates range);
