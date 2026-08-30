import re

with open('/Users/kizzzz/erp_project/3_erp_project/templates/labor_ledger.html') as f:
    content = f.read()

scripts = re.findall(r'<script\b[^>]*>(.*?)</script>', content, re.DOTALL | re.IGNORECASE)

print('=== JS LOOPS IN LABOR LEDGER TEMPLATE ===')
for idx, s in enumerate(scripts, 1):
    lines = s.splitlines()
    for line_no, l in enumerate(lines, 1):
        if 'forEach' in l or '.map(' in l or 'for (' in l or 'for(' in l:
            print(f'Script #{idx} Line {line_no}: {l.strip()[:140]}')
