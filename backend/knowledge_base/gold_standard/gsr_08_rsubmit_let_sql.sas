




rsubmit;
%let DATE_fin ='31dec2020'd; 





proc sql;
create table encours2020 as
select
T1.CORIX as CODE_RISQUE , 
T2.LIPROCT as PRODUIT , 
T2.LIRGP1 as CAT_PRET ,
T1.DA1ECD, 
t1.coco,
T1.COMAX as COMAX,
t1.nrpret as num_pret,
T1.MEDOS as MONTANT ,
t1.ctppoo as CODE_POOL,
t1.MKRDU 
from MET1.V7TS84 T1 LEFT OUTER JOIN eng0.CAT_PRD T2 ON T1.COPRO = T2.COPRO 

where
t2.LIRGP1 in ('PRETS IMMOBILIERS')and
T1.DAFMS= &DATE_fin and t1.mkrdu>0 and t1.comsd not in ('3') and 
T1.COSITD in ('2') and t1.ctppoo in ('1'); 
quit;
endrsubmit;
