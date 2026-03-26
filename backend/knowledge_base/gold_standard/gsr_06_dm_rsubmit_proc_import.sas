DM "LOG" CLEAR;
RUN;

rsubmit;
%let DAFMS = '31MAR2023'd;   

endrsubmit;




proc import out=swork.TY89_TERADATA
DATAFILE='//chemin/TERADATA TY89 HSBC 04 2023.xlsx'
DBMS=XLSX
replace;
RUN;

rsubmit;
proc sql;
create table REPART_COMM_HSBC as
select comax2, cdcomm, copro2, '30/04/2023' as dmder2, mtperc, mtretr, reesm, reesmp, pdchnm, cospv
from TY89_TERADATA;
quit;
endrsubmit;

rsubmit;
proc sql;
create table TR1W as
select comax, coco, copro
from metn.v4tr1w
where coetb='046'
and comax in (select distinct comax2 from REPART_COMM_HSBC)
and copro in ('00848','01938','02349','02352','02355','02356','02358','02619','02620','02621',
'02622','02624','02626','02627','02628','02629','02630','02631','02632','02633','02634','02635',
'02636','02637','02638','02639','02640','02641','02642','02643','02644','02645','02646','02647',
'02649','02650','02651','02653','02656','02657','02658','02659','02660','02661','02662','02663',
'02664','02665','02666','02667','02668','02669','02670','02671','02672','02673','02674','02675',
'02676','02678','02679','02683','02684','02685','02903')
and dafms=&DAFMS
order by comax;
quit;
endrsubmit;

rsubmit; 
data TR1W_SINGLE_COCO; 
set TR1W; 
if first.comax then output; 
by COMAX; 
run;
endrsubmit;

rsubmit;
proc sql;
create table TY89_FORMAT_IHM as
select distinct a.comax2, b.coco, a.cdcomm, b.copro, a.dmder2, a.mtperc, a.mtretr, a.reesm, a.reesmp, a.pdchnm, a.cospv
from REPART_COMM_HSBC as a
left outer join TR1W_SINGLE_COCO as b on a.comax2=b.comax
where a.comax2 is not null
order by a.comax2;
quit;
endrsubmit;

PROC EXPORT DATA = SWORK.TY89_FORMAT_IHM
OUTFILE = '//chemin/EXPORT COMMISSIONS ASSVIE HSBC 04 2023.xlsx'
DBMS = XLSX
REPLACE;

RUN;
