/* gs_06 - DATA step with arrays and DO loops */
DATA work.standardized_scores;
    SET work.student_tests;
    ARRAY raw_scores{5} test1-test5;
    ARRAY z_scores{5} z_test1-z_test5;
    ARRAY means{5} _TEMPORARY_ (75 80 70 85 78);
    ARRAY stds{5} _TEMPORARY_ (10 12 8 15 11);

    DO i = 1 TO 5;
        IF NOT MISSING(raw_scores{i}) THEN
            z_scores{i} = (raw_scores{i} - means{i}) / stds{i};
        ELSE
            z_scores{i} = .;
    END;

    avg_z = MEAN(OF z_test1-z_test5);
    DROP i;
RUN;
