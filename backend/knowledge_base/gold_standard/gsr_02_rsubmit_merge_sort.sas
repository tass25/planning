
rsubmit;

data date ;
            date = today();
			/*date='12jan2017'd;*/
			jour=weekday(date);
			if jour=2 /*lundi*/ then filtre=3;
			else filtre=1;
            format date ddmmyy8. avant ddmmyy8.;
			avant = date - filtre ;
			call symput ("avant", avant);
run;

data clients_VDFA_avant (drop = coetb cesitc dfvale ddvale );
	set ent0.v4tj3p (where=(coetb='087' and cesitc in ('1','0') and cosges='00082' and ddvale < &avant and dfvale >= &avant ) 
						keep= coetb cesitc cosges comax ddvale dfvale);
run;
proc sort; by comax; run;

data clients_VDFA_auj (drop = coetb cesitc)  ;
	set ent0.v4tj3p (where=(coetb='087' and cesitc ='1' and cosges='00082'  ) 
						keep= coetb cesitc cosges comax ddvale);
run;
proc sort; by comax; run;


data clients_VDFA ;
	merge clients_VDFA_avant (in=a) clients_VDFA_auj (in=b) ;
	by comax ;
	if b and not a ;
run;
proc sort; by comax; run;

data info1 (keep=comax cosges ddvale liraso);
	merge clients_VDFA(in=x) ent0.v4tj3z (where=(coetb='087' and cesitc='1') keep=coetb cesitc comax liraso);
	by comax; 
	if x=1;
run;
proc sort nodupkey; by comax liraso cosges ddvale; run;

data info2 (keep=comax liraso ctsurv lisur ddvale);
	attrib 
	comax 	label='Matricule'
	liraso	label='entreprise'
	ctsurv  label='Code surveillance'
	lisur 	label='Libellé surveillance'
	ddvale 	label='Date informatique bascule VDFA';
		merge info1(in=x) ent0.v0tj5q (where=(coetb='087' and cesitc='1' and ddsurv<today() and dfsurv>today() ) keep=coetb cesitc comax ctsurv lisur ddsurv dfsurv);
		by comax; 
	if x=1;
run;
proc sort nodupkey; by comax liraso ctsurv lisur ddvale; run;


endrsubmit;

/* export du fichier */

proc export data=swork.info2
	outfile ="C:\temp\xfo_testey\res_sas_3\Nvx_Clients_sur_ura00082_&sysdate..xlsx" 
	dbms=xlsx label
	replace;
	sheet="nv_cli";
run;


