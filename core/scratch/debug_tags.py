
with open('/Users/kizzzz/erp_project/core/templates/master_data.html', 'r') as f:
    lines = f.readlines()

stack = []
for i, line in enumerate(lines):
    line_no = i + 1
    # Very simple parser
    import re
    ifs = re.findall(r'{% if ', line)
    endifs = re.findall(r'{% endif %}', line)
    
    for _ in ifs:
        stack.append(line_no)
    for _ in endifs:
        if stack:
            stack.pop()
        else:
            print(f"Extra endif at line {line_no}")

if stack:
    print(f"Unclosed if tags starting at lines: {stack}")
else:
    print("All if tags closed.")
