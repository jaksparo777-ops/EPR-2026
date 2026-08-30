import re, subprocess

with open('/Users/kizzzz/erp_project/3_erp_project/templates/labor_ledger.html') as f:
    content = f.read()

pattern = re.compile(r'<script\b[^>]*>(.*?)</script>', re.DOTALL | re.IGNORECASE)
matches = list(pattern.finditer(content))

s3 = matches[2].group(1) # Script #3

# Clean Django template tags for JS syntax validation
# Replace {% ... %} with /* django block */
s3_clean = re.sub(r'\{%.*?%\}', '/* dj */', s3, flags=re.DOTALL)
# Replace {{ ... }} with "django_var"
s3_clean = re.sub(r'\{\{.*?\}\}', '"django_var"', s3_clean, flags=re.DOTALL)

with open('/Users/kizzzz/erp_project/3_erp_project/scratch/script_3_clean.js', 'w') as f:
    f.write(s3_clean)

print("Wrote cleaned Script #3 to scratch/script_3_clean.js. Validating with python compile / regex...")

# Simple syntax check for unclosed quotes, brackets, template strings
lines = s3_clean.splitlines()
in_tpl = False
tpl_line = 0

for idx, l in enumerate(lines, 1):
    # count backticks
    b_cnt = l.count('`')
    for _ in range(b_cnt):
        if not in_tpl:
            in_tpl = True
            tpl_line = idx
        else:
            in_tpl = False
            tpl_line = 0

if in_tpl:
    print(f"ALERT! Template string starting on line {tpl_line} is NEVER CLOSED!")
else:
    print("All backtick template strings in Script #3 are balanced!")
