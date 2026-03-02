import json, os

gold_dir = 'knowledge_base/gold_standard/'
for fn in sorted(os.listdir(gold_dir)):
    if not fn.endswith('.gold.json') or not fn.startswith('gsh'):
        continue
    with open(gold_dir + fn) as f:
        gold = json.load(f)
    blocks = gold['blocks']    
    sas_fn = fn.replace('.gold.json', '.sas')
    if not os.path.exists(gold_dir + sas_fn):
        continue
    with open(gold_dir + sas_fn) as sf:
        sas_lines = sf.readlines()
    
    for b in blocks:
        if b['partition_type'] != 'MACRO_DEFINITION':
            continue
        e = b['line_end']
        if e <= len(sas_lines):
            end_content = sas_lines[e-1].strip()
            if not end_content.upper().startswith('%MEND'):
                next_content = sas_lines[e].strip() if e < len(sas_lines) else ''
                print(f'{fn[-20:]!s} s={b["line_start"]} e={e} | {end_content[:45]!s}')
