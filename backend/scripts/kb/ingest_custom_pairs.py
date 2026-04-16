"""Ingest custom SAS→Python pairs from a JSON file into LanceDB.

Usage:
    python scripts/kb/ingest_custom_pairs.py [--json PATH] [--db PATH]

Pairs with empty python_code are skipped.
Embeddings are generated via NomicEmbedder (same model used at retrieval time).
"""

from __future__ import annotations

import argparse
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

# Ensure backend is importable
_pkg = str(Path(__file__).resolve().parent.parent.parent)
if _pkg not in sys.path:
    sys.path.insert(0, _pkg)

from dotenv import load_dotenv
load_dotenv(Path(_pkg).parent / ".env")

import structlog
structlog.configure()

_log = structlog.get_logger("codara.kb.ingest")

# ── Pairs embedded directly (from user-provided JSON) ────────────────────────

_PAIRS = [
    {
        "sas_code": "libname swork slibref=work server=serveur ;",
        "python_code": (
            "import pandas as pd\n"
            "import teradatasql\n"
            "import math\n"
            "from scipy.stats import norm\n"
            "import warnings\n"
            "warnings.filterwarnings('ignore')\n"
            "connect = teradatasql.connect(host='10.201.33.167', user='dbc', password='dbc')\n"
            "chem = r'C:\\Users\\ineguia\\OneDrive - Groupe BPCE\\Projets\\09-Transformation\\XFO_EY_PythonSQL\\pgm_sas_4'"
        ),
        "category": "LIBNAME",
    },
    {
        "sas_code": "proc import datafile='&chem.\\prv3.departements_regions.xlsx' out=swork.dep dbms=xlsx replace; run;",
        "python_code": "dep = pd.read_excel(f'{chem}\\\\prv3.departements_regions.xlsx')",
        "category": "PROC_IMPORT",
    },
    {
        "sas_code": (
            "data tr35(drop=cesitc);\n"
            "set metn.v15tr35(where=(cesitc='1') keep=comax cesitc liclag codcsp cosexe sgrpid copost mctota qtagcl);\n"
            "Code_d_partement = substr(copost,1,2);\n"
            "if (qtagcl>17 and qtagcl<76);\n"
            "run;"
        ),
        "python_code": (
            "tr35 = pd.read_sql(\"\"\"\n"
            "SELECT comax, liclag, codcsp, cosexe, sgrpid, copost, mctota, qtagcl\n"
            "FROM AID.METN__V15TR35__ciblage\n"
            "WHERE (cesitc='1') AND (qtagcl>17) AND (qtagcl<76)\n"
            "\"\"\", connect)\n"
            "tr35['Code_d_partement'] = tr35['COPOST'].str[:2]"
        ),
        "category": "DATA_STEP_FILTER",
    },
    {
        "sas_code": (
            "data tr35_2(drop=qtagcl);\n"
            "set tr35;\n"
            "format MCTOTA_R $15.;\n"
            "if mctota=. then MCTOTA_R='Null';\n"
            "else if mctota=0 then MCTOTA_R='0';\n"
            "else if mctota>0 and mctota<=1000 then MCTOTA_R='[>0;1000]';\n"
            "else if mctota>1000 and mctota<=7000 then MCTOTA_R='[>1000;7000]';\n"
            "else if mctota>7000 and mctota<=30000 then MCTOTA_R='[>7000;30000]';\n"
            "else if mctota>30000 and mctota<=75000 then MCTOTA_R='[>30000;75000]';\n"
            "else if mctota>75000 and mctota<=150000 then MCTOTA_R='[>75000;150000]';\n"
            "else if mctota>150000 then MCTOTA_R='[>150000]';\n"
            "else MCTOTA_R='ERREUR';\n"
            "format intensite $19.;\n"
            "if sgrpid in ('01','04','08','12') then intensite='Inactif';\n"
            "else if sgrpid in ('02','05','09','13') then intensite='actif non equipe';\n"
            "else if sgrpid in ('03','06','10','14') then intensite='actif equipe';\n"
            "else if sgrpid in ('04','07','11','15') then intensite='actif equipe assure';\n"
            "Code_d_partement = substr(copost,1,2);\n"
            "run;"
        ),
        "python_code": (
            "tr35_2 = tr35.copy()\n"
            "tr35_2 = tr35_2.drop(columns=['QTAGCL'])\n"
            "# Numeric range binning — use np.select, not def\n"
            "import numpy as np\n"
            "tr35_2['MCTOTA_R'] = np.select(\n"
            "    [\n"
            "        tr35_2['MCTOTA'].isna(),\n"
            "        tr35_2['MCTOTA'] == 0,\n"
            "        (tr35_2['MCTOTA'] > 0) & (tr35_2['MCTOTA'] <= 1000),\n"
            "        (tr35_2['MCTOTA'] > 1000) & (tr35_2['MCTOTA'] <= 7000),\n"
            "        (tr35_2['MCTOTA'] > 7000) & (tr35_2['MCTOTA'] <= 30000),\n"
            "        (tr35_2['MCTOTA'] > 30000) & (tr35_2['MCTOTA'] <= 75000),\n"
            "        (tr35_2['MCTOTA'] > 75000) & (tr35_2['MCTOTA'] <= 150000),\n"
            "        tr35_2['MCTOTA'] > 150000,\n"
            "    ],\n"
            "    ['Null', '0', '[>0;1000]', '[>1000;7000]', '[>7000;30000]',\n"
            "     '[>30000;75000]', '[>75000;150000]', '[>150000]'],\n"
            "    default='ERREUR'\n"
            ")\n"
            "# Enum mapping — use dict + .map(), not def\n"
            "intensite_map = {\n"
            "    '01': 'Inactif', '04': 'Inactif', '08': 'Inactif', '12': 'Inactif',\n"
            "    '02': 'actif non equipe', '05': 'actif non equipe',\n"
            "    '09': 'actif non equipe', '13': 'actif non equipe',\n"
            "    '03': 'actif equipe', '06': 'actif equipe',\n"
            "    '10': 'actif equipe', '14': 'actif equipe',\n"
            "    '07': 'actif equipe assure', '11': 'actif equipe assure', '15': 'actif equipe assure',\n"
            "}\n"
            "tr35_2['intensite'] = tr35_2['SGRPID'].map(intensite_map).fillna('ERREUR')\n"
            "tr35_2['Code_d_partement'] = tr35_2['COPOST'].str[:2]"
        ),
        "category": "DATA_STEP_CONDITIONAL",
    },
    {
        "sas_code": "proc sort nodupkey;\nby comax;\nrun;",
        "python_code": "tr35_2 = tr35_2.drop_duplicates(subset='COMAX').sort_values(by='COMAX')",
        "category": "PROC_SORT",
    },
    {
        "sas_code": "proc sort nodupkey data=dep;\nby Code_d_partement;\nrun;",
        "python_code": "dep = dep.drop_duplicates(subset='Code_d_partement').sort_values(by='Code_d_partement')",
        "category": "PROC_SORT",
    },
    {
        "sas_code": (
            "data part;\n"
            "merge tr35_2(in=a) dep(in=b);\n"
            "by Code_d_partement;\n"
            "if a;\n"
            "if sgrpid<>'';\n"
            "run;\n"
            "proc sort;\n"
            "by comax;\n"
            "run;"
        ),
        "python_code": (
            "part = pd.merge(tr35_2, dep, on='Code_d_partement', how='left', indicator=True)\n"
            "part = part[part['_merge'] == 'both'].drop(columns=['_merge'])\n"
            "part = part[part['SGRPID'] != '']\n"
            "part = part.sort_values(by='COMAX')"
        ),
        "category": "DATA_STEP_MERGE",
    },
    {
        "sas_code": (
            "data email(drop=coetb cesitc);\n"
            "set met1.v1trdd (where=(coetb='009' and cesitc='1') keep=cesitc comax coetb LIADELPV);\n"
            "run;\n"
            "proc sort;\n"
            "by comax;\n"
            "run;"
        ),
        "python_code": (
            "email = pd.read_sql(\"\"\"\n"
            "SELECT COMAX, LIADELPV\n"
            "FROM AID.met1__v1trdd__ciblage\n"
            "WHERE (COETB='009') AND (CESITC='1')\n"
            "\"\"\", connect)\n"
            "email = email.sort_values(by='COMAX')"
        ),
        "category": "DATA_STEP_FILTER",
    },
    {
        "sas_code": (
            "data part;\n"
            "merge part(in=a) email(in=b);\n"
            "by comax;\n"
            "if a and b;\n"
            "run;"
        ),
        "python_code": "merged_data = pd.merge(part, email, on='COMAX', how='inner')",
        "category": "DATA_STEP_MERGE",
    },
    {
        "sas_code": (
            "data part_ech;\n"
            "set work.part;\n"
            "keep comax codcsp cosexe liclag intensite mctota_r Code_d_partement;\n"
            "run;"
        ),
        "python_code": (
            "part_ech = merged_data[['COMAX','CODCSP','COSEXE','LICLAG','intensite','MCTOTA_R','Code_d_partement']]"
        ),
        "category": "DATA_STEP_KEEP",
    },
    {
        "sas_code": (
            "proc sort data=part_ech;\n"
            "by codcsp liclag intensite mctota_r;\n"
            "run;"
        ),
        "python_code": "part_ech = part_ech.sort_values(by=['CODCSP','LICLAG','intensite','MCTOTA_R'])",
        "category": "PROC_SORT",
    },
    {
        "sas_code": (
            "proc freq data=echantillonage;\n"
            "table codcsp liclag intensite MCTOTA_R;\n"
            "run;"
        ),
        "python_code": (
            "codcsp_freq = echantillonage['CODCSP'].value_counts()\n"
            "liclag_freq = echantillonage['LICLAG'].value_counts()\n"
            "intensite_freq = echantillonage['intensite'].value_counts()\n"
            "MCTOTA_R_freq = echantillonage['MCTOTA_R'].value_counts()"
        ),
        "category": "PROC_FREQ",
    },
    {
        "sas_code": (
            "data echantillonage_part(drop= copost mctota sgrpid codcsp liclag qtagcl cosexe);\n"
            "merge echantillonage_tmp(in=a) tr35(in=b);\n"
            "by comax;\n"
            "if a;\n"
            "format tranche_age $15.;\n"
            "if liclag = 'D.18-19 ans' then tranche_age = '18-19 ans';\n"
            "else if liclag = 'E.20-24 ans' then tranche_age = '20-24 ans';\n"
            "/* ... more elif ... */\n"
            "format csp $49.;\n"
            "if codcsp = '1' then csp = 'Agriculteurs exploitants';\n"
            "else if codcsp = '2' then csp = 'Artisans, commerçants et chefs d entreprise';\n"
            "/* ... more elif ... */\n"
            "format genre $6.;\n"
            "if cosexe = 'F' then genre = 'Femme';\n"
            "else if cosexe = 'M' then genre = 'Homme';\n"
            "else genre = 'ERREUR';\n"
            "run;"
        ),
        "python_code": (
            "echantillonage_part = pd.merge(echantillonage_tmp, tr35, on='COMAX', how='left')\n"
            "echantillonage_part = echantillonage_part.drop(\n"
            "    columns=['COPOST','MCTOTA','SGRPID','CODCSP','LICLAG','QTAGCL','COSEXE'],\n"
            "    errors='ignore'\n"
            ")\n"
            "# Enum mapping — use dict + .map(), never def\n"
            "age_map = {\n"
            "    'D.18-19 ans': '18-19 ans', 'E.20-24 ans': '20-24 ans',\n"
            "    'F.25-29 ans': '25-29 ans', 'G.30-34 ans': '30-34 ans',\n"
            "    'H.35-39 ans': '35-39 ans', 'I.40-44 ans': '40-44 ans',\n"
            "    'J.45-49 ans': '45-49 ans', 'K.50-54 ans': '50-54 ans',\n"
            "    'L.55-59 ans': '55-59 ans', 'M.60-64 ans': '60-64 ans',\n"
            "    'N.65-69 ans': '65-69 ans', 'O.70-74 ans': '70-74 ans',\n"
            "    'P.75-79 ans': '75-79 ans',\n"
            "}\n"
            "echantillonage_part['tranche_age'] = echantillonage_part['LICLAG'].map(age_map).fillna('ERREUR')\n"
            "csp_map = {\n"
            "    '1': 'Agriculteurs exploitants',\n"
            "    '2': 'Artisans, commerçants et chefs d entreprise',\n"
            "    '3': 'Cadres et professions intellectuelles supérieures',\n"
            "    '4': 'Professions intermédiaires',\n"
            "    '5': 'Employés', '6': 'Ouvriers', '7': 'Retraités',\n"
            "    '8': 'Autres personnes sans activité professionnelle',\n"
            "    '9': 'Non renseigné',\n"
            "}\n"
            "echantillonage_part['csp'] = echantillonage_part['CODCSP'].map(csp_map).fillna('ERREUR')\n"
            "echantillonage_part['genre'] = echantillonage_part['COSEXE'].map(\n"
            "    {'F': 'Femme', 'M': 'Homme'}\n"
            ").fillna('ERREUR')\n"
            "echantillonage_part = echantillonage_part.rename(\n"
            "    columns={'Code_d_partement': 'Code_departement'}\n"
            ")"
        ),
        "category": "DATA_STEP_CONDITIONAL",
    },
    {
        "sas_code": (
            "proc export data = swork.echantillonage\n"
            "outfile = \"&chem.\\part.xlsx\"\n"
            "dbms=xlsx replace;\n"
            "run;"
        ),
        "python_code": (
            "outfile = chem + '\\\\part.xlsx'\n"
            "echantillonage.to_excel(outfile, index=False)"
        ),
        "category": "PROC_EXPORT",
    },
    {
        "sas_code": (
            "rsubmit;\n"
            "data date;\n"
            "date_fin_annee='31dec2022'd;\n"
            "date_debut_annee_N1='01jan2021'd;\n"
            "call symput(\"date_fin_annee\", date_fin_annee);\n"
            "call symput(\"date_debut_annee_N1\", date_debut_annee_N1);\n"
            "run;\n"
            "endrsubmit;"
        ),
        "python_code": (
            "import datetime\n"
            "date_fin_annee = datetime.datetime.strptime('31dec2022', '%d%b%Y')\n"
            "date_debut_annee_N1 = datetime.datetime.strptime('01jan2021', '%d%b%Y')"
        ),
        "category": "MACRO_VARIABLE",
    },
    {
        "sas_code": (
            "rsubmit;\n"
            "data date;\n"
            "set date;\n"
            "date_sql_fin_annee = \"'\"||put(date_fin_annee, yymmdd10.)||\"'\";\n"
            "call symput(\"date_sql_fin_annee\", date_sql_fin_annee);\n"
            "date_sql_debut_annee_N1 = \"'\"||put(date_debut_annee_N1, yymmdd10.)||\"'\";\n"
            "call symput(\"date_sql_debut_annee_N1\", date_sql_debut_annee_N1);\n"
            "run;\n"
            "endrsubmit;"
        ),
        "python_code": (
            "date_sql_fin_annee = date_fin_annee.strftime('%Y-%m-%d')\n"
            "date_sql_debut_annee_N1 = date_debut_annee_N1.strftime('%Y-%m-%d')"
        ),
        "category": "MACRO_VARIABLE",
    },
    {
        "sas_code": (
            "proc export data = swork.commissions_commercants\n"
            "outfile = \"C:\\temp\\xfo_testey\\res_alteryx\\commissions_commercants.xlsx\"\n"
            "dbms = EXCEL2010 replace;\n"
            "run;"
        ),
        "python_code": (
            "commissions_commercants.to_excel(\n"
            "    'C:/temp/xfo_testey/res_alteryx/commissions_commercants.xlsx', index=False\n"
            ")"
        ),
        "category": "PROC_EXPORT",
    },
    {
        "sas_code": (
            "proc sql;\n"
            "create table PayPlug_Danelys as\n"
            "select * from connection to teradata\n"
            "(\n"
            "select coco, dacomp, mons, lzoa11, l2odc, laodc,\n"
            "case when coco = 'CPT57999025816' then 'Payplug' else 'Danelys' end as CATEG\n"
            "from t3ecom_ent0.v3tl26\n"
            "where coco in ('CPT57999025816','CPT57999026815')\n"
            "and dacomp between &date_sql_debut_annee_N1 and &date_sql_fin_annee\n"
            "order by dacomp\n"
            ");\n"
            "disconnect from Teradata;\n"
            "quit;"
        ),
        "python_code": (
            "PayPlug_Danelys = pd.read_sql(f'''\n"
            "SELECT\n"
            "    coco, dacomp, mons, lzoa11, l2odc, laodc,\n"
            "    CASE WHEN coco = 'CPT57999025816' THEN 'Payplug' ELSE 'Danelys' END AS CATEG\n"
            "FROM AID.T3ECOM_ENT0__V3TL26__222858\n"
            "WHERE coco IN ('CPT57999025816','CPT57999026815')\n"
            "AND dacomp BETWEEN '{date_sql_debut_annee_N1}' AND '{date_sql_fin_annee}'\n"
            "ORDER BY dacomp;\n"
            "''', connect)"
        ),
        "category": "PROC_SQL",
    },
    {
        "sas_code": (
            "data soc;\n"
            "set soc;\n"
            "keep comax;\n"
            "run;\n"
            "proc sort nodupkey;\n"
            "by comax;\n"
            "run;"
        ),
        "python_code": (
            "soc = soc[['COMAX']]\n"
            "soc = soc.drop_duplicates(subset='COMAX').sort_values(by='COMAX')"
        ),
        "category": "PROC_SORT",
    },
    {
        "sas_code": (
            "data echantillonage_part;\n"
            "merge echantillonage_part(in=a) soc(in=b);\n"
            "by comax;\n"
            "if a;\n"
            "if a and b then top_societaire = 'Oui';\n"
            "else top_societaire = 'Non';\n"
            "format cible $11.;\n"
            "cible = 'Part';\n"
            "run;"
        ),
        "python_code": (
            "echantillonage_part = pd.merge(echantillonage_part, soc, on='COMAX', how='left', indicator=True)\n"
            "echantillonage_part['top_societaire'] = np.where(\n"
            "    echantillonage_part['_merge'] == 'both', 'Oui', 'Non'\n"
            ")\n"
            "echantillonage_part = echantillonage_part.drop(columns=['_merge'])\n"
            "echantillonage_part['cible'] = 'Part'"
        ),
        "category": "DATA_STEP_MERGE",
    },
]


def _classify(sas_code: str) -> str:
    """Infer a partition_type label from SAS code."""
    s = sas_code.lower()
    if "proc sql" in s:
        return "PROC_SQL"
    if "proc sort" in s:
        return "PROC_SORT"
    if "proc freq" in s:
        return "PROC_FREQ"
    if "proc means" in s:
        return "PROC_MEANS"
    if "proc export" in s:
        return "PROC_EXPORT"
    if "proc import" in s:
        return "PROC_IMPORT"
    if "proc transpose" in s:
        return "PROC_TRANSPOSE"
    if "data " in s and ("set " in s or "merge " in s):
        return "DATA_STEP"
    if "%macro" in s or "%let" in s:
        return "MACRO"
    if "libname" in s:
        return "LIBNAME"
    return "GENERAL"


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest custom SAS→Python pairs into LanceDB")
    parser.add_argument("--db", default="data/lancedb", help="LanceDB path")
    args = parser.parse_args()

    db_path = str(Path(_pkg) / args.db)

    # Load NomicEmbedder
    _log.info("loading_embedder")
    try:
        from partition.raptor.embedder import NomicEmbedder
        embedder = NomicEmbedder()
    except Exception as exc:
        _log.error("embedder_load_failed", error=str(exc))
        sys.exit(1)

    from partition.kb.kb_writer import KBWriter
    writer = KBWriter(db_path=db_path)
    before = writer.count()
    _log.info("kb_before", count=before)

    now = datetime.now(timezone.utc).isoformat()
    records = []

    valid_pairs = [(p["sas_code"], p["python_code"], p.get("category", "GENERAL"))
                   for p in _PAIRS if p.get("python_code", "").strip()]

    _log.info("pairs_to_ingest", count=len(valid_pairs))

    # Embed all SAS snippets in batch for efficiency
    sas_texts = [sas for sas, _, _ in valid_pairs]
    try:
        embeddings = embedder.embed_batch(sas_texts)
    except Exception as exc:
        _log.error("embedding_failed", error=str(exc))
        sys.exit(1)

    for (sas, py, category), emb in zip(valid_pairs, embeddings):
        records.append({
            "example_id":          f"custom-{uuid.uuid4().hex[:12]}",
            "sas_code":            sas,
            "python_code":         py,
            "embedding":           emb if isinstance(emb, list) else list(emb),
            "partition_type":      _classify(sas),
            "complexity_tier":     "LOW",
            "target_runtime":      "python",
            "verified":            True,
            "source":              "custom_pairs_v1",
            "failure_mode":        "",
            "verification_method": "human",
            "verification_score":  1.0,
            "category":            category,
            "version":             1,
            "superseded_by":       "",
            "created_at":          now,
            "issues_text":         "",
        })

    inserted = writer.insert_pairs(records)
    after = writer.count()
    _log.info("ingestion_complete", inserted=inserted, total_before=before, total_after=after)
    print(f"\nIngested {inserted} pairs. KB size: {before} -> {after}")


if __name__ == "__main__":
    main()
