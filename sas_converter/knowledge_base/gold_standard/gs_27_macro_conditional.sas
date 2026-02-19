/* gs_27 - Macro with conditional logic */
%MACRO validate_dataset(dsn=, required_vars=, min_obs=1);
    %LOCAL dsid nvars rc obs;
    %LET dsid = %SYSFUNC(OPEN(&dsn));

    %IF &dsid = 0 %THEN %DO;
        %PUT ERROR: Dataset &dsn does not exist.;
        %RETURN;
    %END;

    %LET obs = %SYSFUNC(ATTRN(&dsid, NOBS));
    %IF &obs < &min_obs %THEN %DO;
        %PUT WARNING: &dsn has only &obs observations (minimum: &min_obs).;
    %END;
    %ELSE %DO;
        %PUT NOTE: &dsn validated successfully with &obs observations.;
    %END;

    %LET rc = %SYSFUNC(CLOSE(&dsid));
%MEND validate_dataset;

%validate_dataset(dsn=work.customers, required_vars=customer_id name, min_obs=100);
