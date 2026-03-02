"""
Analyze what heuristic can distinguish whole-body vs header-only macros.
Check: what is the first non-comment/non-%local/%put line INSIDE the macro body?
If it's PROC/DATA/SQL -> it might determine the style.
"""
import json, re
from pathlib import Path

gold_dir = Path('knowledge_base/gold_standard')

PROC_RE = re.compile(r'^\s*proc\s+', re.I)
DATA_RE = re.compile(r'^\s*data\s+', re.I)
SQL_RE  = re.compile(r'^\s*proc\s+sql', re.I)
LOCAL_RE = re.compile(r'^\s*%local\b', re.I)
PUT_RE   = re.compile(r'^\s*%put\b', re.I)
LET_RE   = re.compile(r'^\s*%let\b', re.I)
GLOBAL_RE = re.compile(r'^\s*%global\b', re.I)
COMMENT_RE = re.compile(r'^\s*(/\*|$|\*;|//)')
MACRO_RE = re.compile(r'^\s*%macro\s+', re.I)
IF_RE   = re.compile(r'^\s*%if\b', re.I)
DO_RE   = re.compile(r'^\s*%do\b', re.I)

print(f"File                              GoldSpan     Style        FirstInnerLine")
print("-" * 100)

for gf in sorted(gold_dir.glob("*.gold.json")):
    d = json.loads(gf.read_text())
    sas_path = gold_dir / (gf.stem.replace('.gold', '') + '.sas')
    if not sas_path.exists():
        continue
    lines = sas_path.read_text(encoding='latin-1').splitlines()

    mend_lines = {}
    for i, l in enumerate(lines, 1):
        lc = l.strip().lower()
        if lc.startswith('%mend'):
            mend_lines[i] = l.strip()

    macro_blocks = [b for b in d['blocks'] if b['partition_type'] == 'MACRO_DEFINITION']
    for mb in macro_blocks:
        gs = mb['line_start']
        ge = mb['line_end']

        # Find %macro line
        macro_line = None
        for i in range(gs, min(ge+1, gs+15)):
            if MACRO_RE.match(lines[i-1]):
                macro_line = i
                break

        if macro_line is None:
            continue

        # Find nearest %mend after %macro
        nearest_mend = min((l for l in mend_lines if l >= macro_line), default=None)

        # Determine style
        is_whole_body = nearest_mend and abs(ge - nearest_mend) <= 2
        style = "whole-body" if is_whole_body else "header-only"

        # Find first non-trivial line after %macro declaration line
        first_inner = None
        first_inner_type = None
        first_inner_linenum = None
        for i in range(macro_line + 1, min(macro_line + 20, len(lines) + 1)):
            lc = lines[i-1].strip()
            if not lc or lc.startswith('/*') or lc.startswith('*;') or lc.endswith('*/'):
                continue
            if LOCAL_RE.match(lc) or PUT_RE.match(lc) or LET_RE.match(lc) or GLOBAL_RE.match(lc):
                first_inner = lc[:60]
                first_inner_type = 'decl'
                first_inner_linenum = i
                # Don't stop — keep looking past decls
                continue
            # Non-trivial first line
            if PROC_RE.match(lc):
                first_inner = lc[:60]
                first_inner_type = 'PROC'
                first_inner_linenum = i
            elif DATA_RE.match(lc):
                first_inner = lc[:60]
                first_inner_type = 'DATA'
                first_inner_linenum = i
            elif IF_RE.match(lc):
                first_inner = lc[:60]
                first_inner_type = 'IF'
                first_inner_linenum = i
            elif DO_RE.match(lc):
                first_inner = lc[:60]
                first_inner_type = 'DO'
                first_inner_linenum = i
            else:
                first_inner = lc[:60]
                first_inner_type = 'OTHER'
                first_inner_linenum = i
            break

        fname = gf.stem.replace('.gold', '')[:30]
        print(f"  {fname:<32} L{gs}-{ge:<5} {style:<12}  "
              f"first_non_decl=L{first_inner_linenum}:{first_inner_type} | {first_inner or '?'}")
