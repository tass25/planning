/* gs_32 - Macro with SYMPUT and data-driven logic */
DATA _NULL_;
    SET work.config_params;
    CALL SYMPUTX(param_name, param_value);
RUN;

%PUT NOTE: Processing with threshold=&threshold and method=&method;

DATA work.processed;
    SET work.raw_data;
    IF score >= &threshold THEN status = 'PASS';
    ELSE status = 'FAIL';
RUN;

%summary_report(dsn=work.processed, by_var=status);
