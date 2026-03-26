%macro MultImp(dir=,out=);

 %let rc=%str(%'dir %")&dir.%str(\%" /A-D/B/ON%');
 filename myfiles pipe %unquote(&rc);

 data list;
 length fname $256.;
 infile myfiles truncover;
 input myfiles $100.;

 fname=quote(upcase(cats("&dir",'\',myfiles)));
 out="&out";
 drop myfiles;
 call execute('
   proc import dbms=xls out= _test
             datafile= '||fname||' replace ;
   run;
   proc append data=_test base='||out||' force; run;
   proc delete data=_test; run;
 ');
 run;

 %mend;

 %MultImp(dir=\\dombppc\dfsbpmed\DFJC\Documents\CDG\Etudes_Reporting\Reportings\ENCOURS\0- Balances_Quotidiennes\EURO\202304\,out=cm);       


proc sql;
 create table cible as
 select CGE, Classe, Groupe, PCI, Compte, Libell_, D_bit, Cr_dit, Solde, Fili_re
 from cm
 where Classe in ('1','2','3')
 order by 1,2,3,4;

proc sql;
create table cible_moy as
select distinct CGE, Classe, Groupe, PCI, Compte, Libell_, avg(D_bit) as deb_moy, avg(Cr_dit) as crd_moy, avg(Solde) as solde_moy
from cible
group by CGE, Classe, Groupe, PCI, Compte, Libell_;

quit;


proc export data=work.cible_moy
outfile='//chemin/Cible202304.xlsx'		
dbms=xlsx
replace;
sheet="Moy_BPMED_042023";
run;


