/* gs_37 - %DO loop iterating over list */
%MACRO process_regions;
    %LET regions = NORTH SOUTH EAST WEST;
    %LET n = 4;

    %DO i = 1 %TO &n;
        %LET region = %SCAN(&regions, &i);

        DATA work.sales_&region;
            SET work.all_sales;
            WHERE UPCASE(region) = "&region";
        RUN;

        PROC MEANS DATA=work.sales_&region NOPRINT;
            VAR revenue units;
            OUTPUT OUT=work.stats_&region MEAN= SUM= / AUTONAME;
        RUN;

        %PUT NOTE: Processed region &region;
    %END;
%MEND process_regions;

%process_regions;
