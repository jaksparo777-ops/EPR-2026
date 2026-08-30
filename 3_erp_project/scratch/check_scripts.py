import re, sys

def check_template(filepath):
    print(f'=== CHECKING SCRIPT TAGS IN {filepath} ===')
    with open(filepath) as f:
        content = f.read()
    
    scripts = re.findall(r'<script\b[^>]*>(.*?)</script>', content, re.DOTALL | re.IGNORECASE)
    for idx, s in enumerate(scripts, 1):
        s_clean = s.strip()
        if not s_clean:
            continue
        # Check for unescaped Django template variables inside JS strings or literals
        django_vars = re.findall(r'[\"\'].*?\{\{.*?\}\}.*?[\"\']', s_clean)
        if django_vars:
            print(f'Script #{idx} Has {len(django_vars)} Django vars inside quotes:')
            for v in django_vars[:5]:
                print(f'   {v}')

check_template('/Users/kizzzz/erp_project/3_erp_project/templates/layout/base.html')
check_template('/Users/kizzzz/erp_project/3_erp_project/templates/labor_ledger.html')
