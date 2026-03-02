import json
from pathlib import Path

d = json.loads(Path('knowledge_base/gold_standard/gsh_09_analytics_pipeline.gold.json').read_text())
macros = [b for b in d['blocks'] if b['partition_type'] == 'MACRO_DEFINITION']
print('gsh_09 MACRO_DEFINITION blocks:')
for m in macros:
    start = m['line_start']
    end = m['line_end']
    print(f"  L{start}-{end} ({end-start+1} lines)")

# Find %mend lines
lines = Path('knowledge_base/gold_standard/gsh_09_analytics_pipeline.sas').read_text(encoding='latin-1').splitlines()
print()
print('All %mend lines:')
for i, l in enumerate(lines, 1):
    if '%mend' in l.lower():
        print(f"  L{i}: {l}")

print()
print('All %macro lines:')
for i, l in enumerate(lines, 1):
    if '%macro ' in l.lower():
        print(f"  L{i}: {l}")


