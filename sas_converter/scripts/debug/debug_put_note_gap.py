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
            end_content = sas_lines[e-1].strip().upper()
            if end_content.startswith('%PUT NOTE:') or end_content.startswith('%PUT WARNING:') or end_content.startswith('%PUT ERROR:'):
                # Find %MACRO line
                macro_line = None
                for li in range(b['line_start']-1, min(e, len(sas_lines))):
                    if sas_lines[li].strip().upper().startswith('%MACRO'):
                        macro_line = li + 1
                        break
                if macro_line:
                    gap = e - macro_line
                    print(f'{fn[-20:]} s={b["line_start"]} e={e} macro_at={macro_line} gap={gap} | {end_content[:45]}')
