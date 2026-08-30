import re

for s_num in range(1, 6):
    filename = f'/Users/kizzzz/erp_project/3_erp_project/scratch/script_{s_num}.js'
    with open(filename) as f:
        code = f.read()

    # Check for unclosed quotes
    lines = code.splitlines()
    in_single = False
    in_double = False
    in_tpl = False
    
    for l_idx, line in enumerate(lines, 1):
        i = 0
        while i < len(line):
            c = line[i]
            if c == '\\':
                i += 2
                continue
            if c == '/' and i + 1 < len(line) and line[i+1] == '/' and not in_single and not in_double and not in_tpl:
                break
            if c == "'" and not in_double and not in_tpl:
                in_single = not in_single
            elif c == '"' and not in_single and not in_tpl:
                in_double = not in_double
            elif c == '`' and not in_single and not in_double:
                in_tpl = not in_tpl
            i += 1
        
        if in_single:
            print(f"Script #{s_num} Line {l_idx}: Unclosed single quote -> {line[:80]}")
            in_single = False
        if in_double:
            print(f"Script #{s_num} Line {l_idx}: Unclosed double quote -> {line[:80]}")
            in_double = False

print("Quote check complete.")
