with open('/Users/kizzzz/erp_project/3_erp_project/scratch/script_4.js', 'r') as f:
    code = f.read()

lines = code.split('\n')
print(f"Total lines in script_4.js: {len(lines)}")

# Check brace matching
open_braces = 0
for i, line in enumerate(lines):
    for char in line:
        if char == '{':
            open_braces += 1
        elif char == '}':
            open_braces -= 1
    if open_braces < 0:
        print(f"Brace mismatch at line {i+1}: {line}")
        break

print(f"Final open braces count: {open_braces}")
