rsubmit;
options nodate dflang='French';
 
%let ANNEE=2022; 
%let MOIS=12;

%let date_fin='31dec2022'd; 
%let date_deb='01jan2022'd;

proc sql;

create table PROD_DETAIL3 as
select(case	 
when T1.CTTAUX = 'F' then 'FIXE' 
when T1.CTTAUX = 'V' then 'VARIABLE' 
else 'ERREUR REGROUPEMENT !' 
end	) as TYPE, 
T1.CORIX as CODE_RISQUE , 
T2.LIPROCT as PRODUIT , 
T2.LIRGP1 as CAT_PRET , 
T1.COSPV as AGENCE,
t4.coniv4 as CODE_GROUPE,
T4.LINIV4LG as groupe,
t4.COPT as num_gestionnaire,
t4.liptct as libelle_portefeuille,
T2.LIRGP3 as TYPOLOGIE ,
MONTH(T1.DAPDBL) as MOIS ,
YEAR(T1.DAPDBL) as ANNEE,
T1.NUCOI as NUCOI,
t1.coco,
T1.COMAX as COMAX,
t1.nrpret as num_pret,
T1.DAPDBL as DEBLOCAGE ,
T1.QLDDOS as DUREE, 
T1.QPTRES as POURCENTAGE, 
T1.MEDOS as MONTANT ,
T1.TAINT as TAUX ,
T1.MEDOS * T1.QLDDOS as DUREE_MOY ,
T1.MEDOS * (T1.TAINT/100) as TAUX_MOY,
t1.ctppoo as CODE_POOL,
t1.mtfad as MONTANT_FDD,
t1.mkrdu
from	
 
(MET1.V3TR1W T5 LEFT OUTER JOIN ENG0.CAT_PRD T2 on T5.COPRO = T2.COPRO
LEFT OUTER JOIN METN.V5TR4H T1 on T5.COCO = t1.COCO),
(MET1.V9TR1C T6 LEFT OUTER JOIN ENG0.PTF_COM T4 on T6.COPFCI = T4.COPT)
where	

T1.DAPDBL >=&date_deb and T1.DAPDBL<=&date_fin and
T1.COETB = T5.COETB and	 
T5.COETB = T6.COETB and
T1.COCO = T5.COCO and
T5.COMAX = T6.COMAX and


T1.COMSD not in ('4','5','6','7') and
T1.CESITC = '1' and 	T5.CESITC = '1' and	T6.CESITC = '1'
and T1.CORIX in ('798','799');
quit;
endrsubmit;

rsubmit;
proc sql; 
create table ptz_ecoptz as 
select code_risque, count(coco) as nb ,sum(montant) as montant 
from PROD_DETAIL3
group by code_risque;
quit;
endrsubmit;



proc export data=swork.ptz_ecoptz
outfile='//chemin/data prod prêt ptz et eco ptz 2022.xlsx'
dbms=EXCEL2000
replace;
run;

