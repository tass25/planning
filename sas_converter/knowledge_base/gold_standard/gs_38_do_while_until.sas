/* gs_38 - %DO %WHILE and %DO %UNTIL loops */
%MACRO iterative_model(target_r2=0.80, max_iter=10);
    %LET current_r2 = 0;
    %LET iteration = 0;
    %LET converged = 0;

    %DO %WHILE(&current_r2 < &target_r2 AND &iteration < &max_iter);
        %LET iteration = %EVAL(&iteration + 1);

        PROC REG DATA=work.model_data OUTEST=work.est NOPRINT;
            MODEL y = x1-x&iteration / RSQUARE;
        QUIT;

        DATA _NULL_;
            SET work.est;
            CALL SYMPUTX('current_r2', _RSQ_);
        RUN;

        %PUT NOTE: Iteration &iteration — R-squared = &current_r2;
    %END;

    %IF &current_r2 >= &target_r2 %THEN
        %PUT NOTE: Converged at iteration &iteration with R2=&current_r2;
    %ELSE
        %PUT WARNING: Did not converge after &max_iter iterations;
%MEND iterative_model;

%iterative_model(target_r2=0.85, max_iter=5);
