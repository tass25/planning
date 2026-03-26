dm 'out' clear; dm 'log' clear;
 


FILENAME initFile "&MV_D.\Automatisation_SAS\Sources";
%INCLUDE initFile (FonctionsUtiles.sas);
run;

filename LIB_SP "&MV_DSP.\Automatisation_SAS\Sources\sous_programmes\";
run;

 
%include LIB_SP(SP_NOMPROG.sas);
run;

 
%let MV_DEM1=D16657_;                   
%include LIB_SP(SP_MV_BPMED.SAS);	   
%put _user_;
run;
%include LIB_SP(SP_GEST_ERREUR_ABEND.sas);
run;

 
%include LIB_SP(SP_AGENCE_STRUCTURE.sas);
run;

 
%include LIB_SP(SP_DATEFM.SAS);
run; 


%let MV_REPERTC=&MV_D.\Automatisation_SAS\Sources\&MV_NOMREP.\ ;
%let MV_REPERT1=SAV_Rapports\  ;
%let MV_FIC1= &MV_BANQUEX._Compte_Groupement_reliquat_divers;   
%put _user_;
run;



  
%put _user_;
run;

 
 
 %include LIB_SP(SP_AUTOM_VAR_REPFP.sas);
run;






RSUBMIT ; proc sql;
create table compte_groupement  as 
select 
		
		"&mv_banquex." as LIBEL_BQ 'Libellé Banque'

		
		, ag.LINIV4CT "Groupe"
		, ag.liniv1CT 
		, str.cotic_Resp_struct
		, str.nom_Resp_struct
		, str.prenom_Resp_struct
		, str.LIPTCT "Gestionnaire"
		, str.LIADEM "Mail Gestionnaire"


		, a.numax "Matricule"
		, a.nucoi "Compte"
		, a.ctcge "CGE"
		, b.liraso "Intitulé compte"
		, a.daouv "Date ouverture"
		, b.ctcatj "Catégorie juridique"
		, a.coscr "Passage auto reliquat divers"

from esp0.v9td40 a
	inner join esp0.v5tn03 b on a.numax = b.comax and b.ctcatj = '2900'
	inner join esp0.v6tn01 c on a.numax = c.comax and c.corelb = '1'
	left join &MV_FBQ.agence ag on c.coetb=ag.coetb_struct and c.COSPV = ag.coniv1
	left join &MV_FBQ.structure str on c.coetb=str.coetb_struct and c.COPFCI = str.COPT and str.cesitc='1'

where a.cplco = '2' and a.coscr = '0'
order by ag.coniv4, ag.coniv1, a.coscr, a.numax;
quit; ENDRSUBMIT;


proc export DATA	=	SWORK.compte_groupement  LABEL
	  OUTFILE	= "&MV_REPERTC.&MV_REPERT1.&MV_FIC1.-&MV_DTJOUR..xlsx"  
DBMS	=	excel2010
REPLACE; sheet='RELIQUAT';
run;


 





