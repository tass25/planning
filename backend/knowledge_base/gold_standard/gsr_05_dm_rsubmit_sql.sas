
DM "LOG" CLEAR;
RUN;

rsubmit;
LIBNAME RFIN TERADATA  SCHEMA=TGECOM_RFIN  user=&tera_user pwd=&tera_pwd TDPID=&tera_srv defer=YES;
endrsubmit;

rsubmit; 
%let Darr='30/04/2023';  
%let MOIS=03;            
%let ANNEE=2023;  
run;
endrsubmit;

rsubmit;
proc sql;
create table COMM_PRECRIP as
select distinct b.COMAX, c.coco, 'APPAFF' as CDCOM, c.COPRO, &Darr as DMDER2,
case when (-a.mtcocs)<0 then 0 else (a.mtcocs) end as MTPERC,
case when (a.mtcocs)>=0 then (a.mtcocs) else 0 end as MTRETR,
0 as REESM, 0 as REESMP, (-a.mtcocs) as PDCHMN,c.COSPV

from ent0.v0tjk6 as a
left outer join rfin.v18ty4c as b on a.codosb=b.codosh and a.copret=b.nrpret 
left outer join met1.v5tr4h as c on b.coco=c.coco and c.cesitc='1'
where a.coetb='046'
and b.coetb='046'
and c.coetb='046'
and a.cesitc='1'
and a.copret ne ''
and a.copro ne ''
and a.mtcocs ne 0
and month(c.dapdbl)=&MOIS  
and year(c.dapdbl)=&ANNEE  
order by b.comax;
quit;
endrsubmit;

rsubmit;
proc sql;
create table COMM_PRECRIP_FINAL as
select distinct COMAX, COCO, CDCOM, COPRO, DMDER2, sum(MTPERC)as MTPERC,sum(MTRETR)as MTRETR,REESM,REESMP,sum(PDCHMN)as PDCHMN,cospv
from COMM_PRECRIP
group by comax,copro;
quit;
endrsubmit;

rsubmit; 
data FINALE; 
set COMM_PRECRIP_FINAL; 
if last.comax then output; 
by COMAX coco; 
run;
endrsubmit;

PROC EXPORT DATA = SWORK.FINALE
OUTFILE = '//chemin/EXPORT COMMISSIONS APPAFF 04 2023.xlsx'
DBMS = xlsx
REPLACE;
SHEET="COMM_APPAFF";
RUN;
