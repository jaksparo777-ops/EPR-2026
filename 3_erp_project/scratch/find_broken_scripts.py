import re

with open('/Users/kizzzz/erp_project/3_erp_project/templates/labor_ledger.html') as f:
    content = f.read()

# Find all script tags with their line numbers
pattern = re.compile(r'<script\b[^>]*>(.*?)</script>', re.DOTALL | re.IGNORECASE)

matches = list(pattern.finditer(content))
print(f"Total <script> blocks found in labor_ledger.html: {len(matches)}")

for idx, m in enumerate(matches, 1):
    script_text = m.group(1)
    start_line = content[:m.start()].count('\n') + 1
    end_line = content[:m.end()].count('\n') + 1
    
    # Check for unclosed braces or parentheses in script_text
    open_braces = script_text.count('{') - script_text.count('}')
    open_parens = script_text.count('(') - script_text.count(')')
    open_brackets = script_text.count('[') - script_text.count(']')
    
    print(f"Script #{idx} (Lines {start_line}-{end_line}): Braces delta={open_braces}, Parens delta={open_parens}, Brackets delta={open_brackets}")
    if open_braces != 0 or open_parens != 0 or open_brackets != 0:
        print(f"  --> ALERT! Unbalanced brackets in Script #{idx}!")
