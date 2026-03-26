rsubmit;
data param;
	maintenant = today();
	moins10 = maintenant-10 ;
	call symput ("moins10",moins10);
run;
%put &moins7 ;
data tj7s_maintenant (drop = coetb cesitc cplco ); 
	set ent0.V6tj7F (where=(coetb = '087' and cesitc = '1' and cplco = '2' and coscox = '11' ) 
						keep = coetb cesitc coco coscox dacjoe cocojo numax cplco coesgs );
run;
proc sort; by coco; run;
data tj7s_moins10  (drop = coetb cesitc ddvale dfvale cplco) ;
	set ent0.V6tj7F (where=(coetb = '087' and cesitc not in ('2','3') and ddvale <= &moins10 
							and dfvale > &moins10 and cplco = '2' and coscox = '11' )  
					keep = coetb cesitc coco ddvale dfvale coscox dacjoe cocojo numax cplco );
run;
proc sort; by coco; run;
data nouvelle_denonciation ;
	merge tj7s_maintenant (in=a) tj7s_moins10 (in=b);
	by coco;
	if a and not b ;
run;
endrsubmit;
PROC EXPORT data = swork.nouvelle_denonciation 
outfile = "C:\temp\xfo_testey\res_sas_3\denonciation_cpt_joint_&sysdate..csv"
dbms = csv replace;
DELIMITER=";";
RUN;
PROC EXPORT data = swork.nouvelle_denonciation 
outfile = "C:\temp\xfo_testey\res_sas_3\denonciation_cpt_joint_&sysdate..csv"
dbms = csv replace;
DELIMITER=";";
RUN;
rsubmit; 
proc sql noprint;
select count(*) into : nb 
from nouvelle_denonciation ;
run;
quit;
endrsubmit;
