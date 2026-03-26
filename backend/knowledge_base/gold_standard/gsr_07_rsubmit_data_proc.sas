rsubmit; 
%let datedeb = 	'01APR2023'd; 
%let datefin = 	'30APR2023'd;

endrsubmit;



rsubmit; proc sql;
create table COMSPLAC as
select a.coco, b.copro, c.liprlg, a.*
from ent0.v1tj6x a
left join metn.v4tr1w b on a.coco = b.coco and b.cesitc <= '1' and b.coetb = '046' and b.dafms eq '30NOV2022'd
left join met1.v1tr10 c on b.copro = c.copro and c.cesitc eq '1'
where a.coetb = '046'
and a.damdas between &datedeb and &datefin
and a.cesitc <= '1'
order by a.coco, a.damdas, a.ddvale desc;
quit; endrsubmit;

rsubmit;
data COMSPLAC2;
set COMSPLAC;
by coco;
if first.coco;
run; endrsubmit;

rsubmit; proc sql;
create table COMSPLAC3 as
select distinct &datedeb as date format date9., ctstas, copro, liprlg, sum(qtpra4) as prime_mois, sum(qtcom2) as com_bp
from COMSPLAC2
group by ctstas, copro, liprlg
order by ctstas, copro, liprlg;
quit; endrsubmit;



proc export 
data = swork.COMSPLAC3
outfile = '//chemin/COMS PLAC 2023-04.xlsx'
DBMS = EXCEL2000
REPLACE;
sheet='COMSPRIMES';
run;


