/* gs_33 - Complex macro with error handling */
%MACRO safe_import(file=, out=, type=CSV);
    %IF NOT %SYSFUNC(FILEEXIST(&file)) %THEN %DO;
        %PUT ERROR: File &file not found. Aborting import.;
        %RETURN;
    %END;

    %IF %UPCASE(&type) = CSV %THEN %DO;
        PROC IMPORT DATAFILE="&file"
            OUT=&out DBMS=CSV REPLACE;
            GUESSINGROWS=MAX;
        RUN;
    %END;
    %ELSE %IF %UPCASE(&type) = EXCEL %THEN %DO;
        PROC IMPORT DATAFILE="&file"
            OUT=&out DBMS=XLSX REPLACE;
            SHEET="Sheet1";
        RUN;
    %END;
    %ELSE %DO;
        %PUT ERROR: Unsupported file type: &type;
        %RETURN;
    %END;

    %LET dsid = %SYSFUNC(OPEN(&out));
    %IF &dsid > 0 %THEN %DO;
        %LET nobs = %SYSFUNC(ATTRN(&dsid, NOBS));
        %LET rc = %SYSFUNC(CLOSE(&dsid));
        %PUT NOTE: Successfully imported &nobs rows into &out;
    %END;
%MEND safe_import;

%safe_import(file=/data/input/sales.csv, out=work.sales_import, type=CSV);
