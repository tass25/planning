%let input_csv = C:/Users/iyedm/OneDrive/Desktop/Code Migration/helper_dataFrames/CARS.csv;
%let output_dir = C:/Users/iyedm/OneDrive/Desktop/Code Migration/output;

proc import datafile="&input_csv"
    out=work.cars_source
    dbms=csv
    replace;
    guessingrows=max;
run;

proc freq data=work.cars_source noprint order=freq;
    tables DriveTrain / out=work.case_022_output;
run;

ods listing gpath="&output_dir";
ods graphics on / reset imagename="case_022_freqplot" imagefmt=png;

proc sgplot data=work.case_022_output;
    vbarparm category=DriveTrain response=COUNT / datalabel;
    xaxis discreteorder=data;
    yaxis label="Frequency";
run;

ods graphics off;

proc export data=work.case_022_output
    outfile="&output_dir./case_022_output.csv"
    dbms=csv
    replace;
run;
