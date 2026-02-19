/* gs_39 - Nested conditional and loop blocks */
%MACRO batch_validate(datasets=, strict=YES);
    %LET i = 1;
    %LET dsn = %SCAN(&datasets, &i, %STR( ));
    %LET pass_count = 0;
    %LET fail_count = 0;

    %DO %WHILE(&dsn NE );
        %LET dsid = %SYSFUNC(OPEN(work.&dsn));

        %IF &dsid > 0 %THEN %DO;
            %LET nobs = %SYSFUNC(ATTRN(&dsid, NOBS));
            %LET rc = %SYSFUNC(CLOSE(&dsid));

            %IF &nobs > 0 %THEN %DO;
                %LET pass_count = %EVAL(&pass_count + 1);
                %PUT NOTE: PASS — &dsn has &nobs observations.;
            %END;
            %ELSE %DO;
                %LET fail_count = %EVAL(&fail_count + 1);
                %PUT WARNING: FAIL — &dsn is empty.;
            %END;
        %END;
        %ELSE %DO;
            %LET fail_count = %EVAL(&fail_count + 1);
            %PUT ERROR: FAIL — &dsn does not exist.;
        %END;

        %LET i = %EVAL(&i + 1);
        %LET dsn = %SCAN(&datasets, &i, %STR( ));
    %END;

    %PUT NOTE: Validation complete — &pass_count passed, &fail_count failed.;

    %IF &strict = YES AND &fail_count > 0 %THEN %DO;
        %PUT ERROR: Strict mode — aborting due to &fail_count failures.;
    %END;
%MEND batch_validate;

%batch_validate(datasets=customers orders products inventory, strict=YES);
