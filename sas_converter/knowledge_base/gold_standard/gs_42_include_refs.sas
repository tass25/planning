/* gs_42 - %INCLUDE references */
%INCLUDE 'macros/utility_macros.sas';
%INCLUDE 'macros/business_rules.sas';
%INCLUDE "config/environment_setup.sas";

DATA work.processed;
    SET work.raw_input;
    %INCLUDE 'transforms/standard_cleaning.sas';
RUN;

%run_standard_pipeline(input=work.processed);
