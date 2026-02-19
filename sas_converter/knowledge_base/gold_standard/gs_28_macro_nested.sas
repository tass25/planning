/* gs_28 - Nested macro definitions */
%MACRO etl_pipeline(source_lib=, target_lib=, tables=);

    %MACRO process_table(tbl);
        DATA &target_lib..&tbl;
            SET &source_lib..&tbl;
            etl_timestamp = DATETIME();
            etl_source = "&source_lib";
            FORMAT etl_timestamp DATETIME20.;
        RUN;

        PROC SORT DATA=&target_lib..&tbl NODUPKEY;
            BY _ALL_;
        RUN;

        %PUT NOTE: Processed table &tbl from &source_lib to &target_lib;
    %MEND process_table;

    %LET i = 1;
    %LET tbl = %SCAN(&tables, &i, %STR( ));
    %DO %WHILE(&tbl NE );
        %process_table(&tbl);
        %LET i = %EVAL(&i + 1);
        %LET tbl = %SCAN(&tables, &i, %STR( ));
    %END;

%MEND etl_pipeline;

%etl_pipeline(source_lib=raw, target_lib=staging, tables=customers orders products);
