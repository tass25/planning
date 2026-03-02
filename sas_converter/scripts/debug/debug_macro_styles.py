"""
Analyze MACRO_DEFINITION gold annotations across ALL gold files.
For each file: show macros, their actual %mend lines, gold span, and style (header-only vs whole-body).
"""
import json
from pathlib import Path

gold_dir = Path('knowledge_base/gold_standard')

print(f"{'File':<35} {'GoldSpan':>15} {'%macro':>8} {'%mend':>8} {'ActualLen':>10} {'Style'}")
print("-" * 90)

stats = {"header-only": 0, "whole-body": 0}

for gf in sorted(gold_dir.glob("*.gold.json")):
    d = json.loads(gf.read_text())
    sas_path = gold_dir / (Path(gf.stem.replace('.gold', '')).stem + '.sas')
    if not sas_path.exists():
        # Try alternate name
        stem = gf.stem.replace('.gold', '')
        sas_path = gold_dir / f"{stem}.sas"
    if not sas_path.exists():
        print(f"  [MISSING SAS] {gf.name}")
        continue

    lines = sas_path.read_text(encoding='latin-1').splitlines()
    # Map %mend lines
    mend_lines = {}
    macro_lines = {}
    for i, l in enumerate(lines, 1):
        lc = l.strip().lower()
        if lc.startswith('%mend'):
            mend_lines[i] = l.strip()
        if lc.startswith('%macro ') or lc == '%macro':
            macro_lines[i] = l.strip()

    macro_blocks = [b for b in d['blocks'] if b['partition_type'] == 'MACRO_DEFINITION']
    for mb in macro_blocks:
        gs = mb['line_start']
        ge = mb['line_end']
        gold_len = ge - gs + 1

        # Find nearest %macro in range [gs, ge]
        ml = min((l for l in macro_lines if gs <= l <= ge), default=None, key=lambda x: x)
        # Find nearest %mend after %macro
        if ml is not None:
            nearest_mend = min((l for l in mend_lines if l >= ml), default=None)
        else:
            nearest_mend = None

        actual_len = (nearest_mend - (ml or gs) + 1) if nearest_mend else "?"
        # Is gold end at %mend?
        if nearest_mend and abs(ge - nearest_mend) <= 2:
            style = "whole-body"
            stats["whole-body"] += 1
        else:
            style = "header-only"
            stats["header-only"] += 1

        print(f"  {gf.stem.replace('.gold',''):<33} L{gs}-{ge} ({gold_len:>3}L)  "
              f"@{ml or '?':>5}  @{nearest_mend or '?':>5}  "
              f"actual={actual_len!s:>6}  {style}")

print()
print(f"Summary: {stats['whole-body']} whole-body macros, {stats['header-only']} header-only macros")
