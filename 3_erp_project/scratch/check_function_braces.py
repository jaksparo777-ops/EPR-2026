with open('/Users/kizzzz/erp_project/3_erp_project/templates/labor_ledger.html') as f:
    lines = f.readlines()

sub_lines = lines[1860:2198] # lines 1861 to 2198

depth = 0
for idx, l in enumerate(sub_lines, 1861):
    open_cnt = l.count('{')
    close_cnt = l.count('}')
    # Remove django template braces {{ and }} from count
    dj_open = l.count('{{')
    dj_close = l.count('}}')
    
    js_open = open_cnt - (dj_open * 2)
    js_close = close_cnt - (dj_close * 2)
    
    depth += (js_open - js_close)
    if js_open != js_close:
        print(f"Line {idx} (depth={depth}): open={js_open}, close={js_close} | {l.strip()[:90]}")
