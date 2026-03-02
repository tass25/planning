import json, os, re

gold_dir = 'knowledge_base/gold_standard/'
PUT_NOTE = re.compile(r'^\s*%PUT\s+NOTE\s*:', re.IGNORECASE)
PUT_ANY = re.compile(r'^\s*%PUT\b', re.IGNORECASE)

# For whole-body macros (ends at %MEND), check if they have %PUT NOTE: within 20 lines of %MACRO
for fn in sorted(os.listdir(gold_dir)):
    if not fn.endswith('.gold.json'):
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
            if end_content.startswith('%MEND'):
                # Find %MACRO line
                macro_line = None
                for li in range(b['line_start']-1, min(e, len(sas_lines))):
                    if sas_lines[li].strip().upper().startswith('%MACRO'):
                        macro_line = li + 1
                        break
                if macro_line:
                    # Check for %PUT NOTE: within first 20 lines after %MACRO
                    for li in range(macro_line, min(macro_line + 22, e)):
                        if li - 1 < len(sas_lines) and PUT_NOTE.match(sas_lines[li-1]):
                            gap = li - macro_line
                            print(f'WHOLE-BODY %PUT NOTE: {fn[-20:]} s={b["line_start"]} e={e} macro_at={macro_line} gap={gap}')
                            break
