rsubmit;
%let annee = 2023;
%let datedeb = 		 '01APR2023'd; 
%let datefin = 		 '30APR2023'd; 
endrsubmit;



rsubmit; proc sql;
create table COMPLACAO as
select distinct a.comax, a.coco, a.codpt2 as code_produit, c.liprlg, b.ddco as date_ouv, b.dfco as date_cloture,
				round(((case when b.dfco > &datefin then &datefin else b.dfco end) - b.ddco)/365.5, 1) as age,

				a.periodtt as periode_traitement, a.ddpfactu as date_deb_fact, a.dfpfactu as date_fin_fact, 
				a.MTHTCMMI as mt_annuel_com,
				a.txcmmiss as tx_com, d.ctfrqa as periodicite,
				a.mtcmmtot as com_placement_bpmed_prev,
				((case when year(a.dfpfactu) > year(&datefin) then 12 else month(a.dfpfactu) end) - month(a.ddpfactu) +1) as nb_mois_cotis_prev,
				a.mtcmmtot / ((case when year(a.dfpfactu) > year(&datefin) then 12 else month(a.dfpfactu) end) - month(a.ddpfactu) +1) as fact_mensuelle_prev,

				a.mtcmmtot / ((case when year(a.dfpfactu) > year(&datefin) then 12 else month(a.dfpfactu) end) - month(a.ddpfactu) +1)
		*((case when a.dfpfactu > &datefin then month(&datefin) else month(a.dfpfactu) end) -
		  (case when month(a.ddpfactu) >= month(&datedeb) and month(a.ddpfactu) <= month(&datefin) then month(a.ddpfactu)
				else 0 end) +1) as com_bpmed_periode
from ent0.v0tj5b a
left join met1.v4tr1w b on a.coetb = b.coetb and a.coco = b.coco and b.cesitc = '1'
left join met1.v4tr10 c on b.copro = c.copro and c.cesitc <= '1'
left join esp0.v5tc1p d on a.coetb = d.coetb and a.coco = d.coco and d.ctetdo = 'A'
where a.coetb = '046'
and a.coreftmt in ('M001', 'M002', 'M003') 
and a.dfvale > &datefin
and a.ddpfactu >= &datedeb
and a.ddpfactu <= &datefin

and a.cesitc <= '1'
order by a.comax, a.coco, c.liprlg;
quit; endrsubmit; 

rsubmit; proc sql;
create table BPIARDPROD as
select distinct &datefin as date_d_arrete format date9., code_produit, liprlg, count(distinct coco) as nb_ct_fact, 
				round(avg(age), 1) as agemoyen,
				sum(com_placement_bpmed_prev) as com_placement_bpmed_prev, sum(com_bpmed_periode) as com_bpmed_periode
from COMPLACAO
group by code_produit, liprlg
order by liprlg;
quit; endrsubmit;



rsubmit; proc sql;
create table AGEMOYAO as
select distinct a.comax, a.coco, b.copro, c.liprlg, b.ddco as date_ouv, b.dfco as date_cloture,
				round(((case when b.dfco > &datefin then &datefin else b.dfco end) - b.ddco)/365.5, 1) as age
from esp0.v5tc1p a
left join met1.v4tr1w b on a.coetb = b.coetb and a.coco = b.coco and b.cesitc = '1'
left join met1.v4tr10 c on b.copro = c.copro and c.cesitc <= '1'
where a.coetb = '046'
and year(b.dfco) = &annee
and b.dfco <= &datefin;
quit; endrsubmit;

rsubmit; proc sql;
create table AGEMOYAO2 as
select distinct &datefin as date_d_arrete format date9., copro, liprlg, count(distinct coco) as nb_clotures, 
				round(avg(age), 1) as agemoyen_ct_clos
from AGEMOYAO
group by copro, liprlg
order by liprlg;
quit; endrsubmit;




 

proc export data=swork.BPIARDPROD	
outfile='//chemin/IARD AO-NO 20230430.xlsx'	
dbms=EXCEL2000
replace;	
sheet='COMPLACAO';
run;	

proc export data=swork.AGEMOYAO2	
outfile='//chemin/IARD AO-NO 20230430.xlsx'	
dbms=EXCEL2000
replace;	
sheet='AGEMOYEN';
run;	
