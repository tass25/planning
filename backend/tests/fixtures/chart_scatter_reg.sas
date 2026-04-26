%let input_csv = C:/Users/iyedm/OneDrive/Desktop/Code Migration/helper_dataFrames/CARS.csv;
%let output_dir = C:/Users/iyedm/OneDrive/Desktop/Code Migration/output;

proc import datafile="&input_csv"
    out=work.cars_source
    dbms=csv
    replace;
    guessingrows=max;
run;

data work.case_030_output;
    set work.cars_source;
    where Type in ("Sedan", "SUV", "Sports");
    efficiency_gap = MPG_Highway - MPG_City;
    keep Make Model Type Origin Horsepower MPG_Highway efficiency_gap;
run;

ods listing gpath="&output_dir";
ods graphics on / reset imagename="case_030_scatter_reg" imagefmt=png;

proc sgplot data=work.case_030_output;
    scatter x=Horsepower y=MPG_Highway / group=Origin transparency=0.25;
    reg x=Horsepower y=MPG_Highway / nomarkers;
    yaxis label="Highway MPG";
    xaxis label="Horsepower";
run;

ods graphics off;

proc export data=work.case_030_output
    outfile="&output_dir./case_030_output.csv"
    dbms=csv
    replace;
run;
