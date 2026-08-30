import re

with open('/Users/kizzzz/erp_project/3_erp_project/templates/labor_ledger.html') as f:
    content = f.read()

pattern = re.compile(r'<script\b[^>]*>(.*?)</script>', re.DOTALL | re.IGNORECASE)
matches = list(pattern.finditer(content))

for idx, m in enumerate(matches, 1):
    s = m.group(1)
    s_clean = re.sub(r'\{%.*?%\}', '/* dj */', s, flags=re.DOTALL)
    s_clean = re.sub(r'\{\{.*?\}\}', '"django_var"', s_clean, flags=re.DOTALL)
    
    filename = f'/Users/kizzzz/erp_project/3_erp_project/scratch/script_{idx}.js'
    with open(filename, 'w') as out:
        out.write(s_clean)

print("Saved all 5 cleaned scripts to scratch/script_1.js ... script_5.js")
