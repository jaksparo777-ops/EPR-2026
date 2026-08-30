with open('/Users/kizzzz/erp_project/3_erp_project/templates/labor_ledger.html') as f:
    lines = f.readlines()

script_3_lines = lines[1112:2688] # 0-indexed

brace_stack = []
paren_stack = []

for idx, line in enumerate(script_3_lines, 1113):
    in_string = False
    str_char = None
    i = 0
    while i < len(line):
        c = line[i]
        # Ignore comments
        if not in_string and c == '/' and i+1 < len(line) and line[i+1] == '/':
            break
        if not in_string and (c == '"' or c == "'"):
            in_string = True
            str_char = c
        elif in_string and c == str_char and (i == 0 or line[i-1] != '\\'):
            in_string = False
            str_char = None
        elif not in_string:
            if c == '{':
                brace_stack.append((idx, c))
            elif c == '}':
                if brace_stack and brace_stack[-1][1] == '{':
                    brace_stack.pop()
                else:
                    print(f"Line {idx}: Unmatched closing brace '}}'")
            elif c == '(':
                paren_stack.append((idx, c))
            elif c == ')':
                if paren_stack and paren_stack[-1][1] == '(':
                    paren_stack.pop()
                else:
                    print(f"Line {idx}: Unmatched closing paren ')'")
        i += 1

print("\n--- UNMATCHED OPEN BRACES AT END OF SCRIPT #3 ---")
for line_no, char in brace_stack:
    print(f"Line {line_no}: Unclosed '{char}' -> {lines[line_no-1].strip()[:100]}")

print("\n--- UNMATCHED OPEN PARENS AT END OF SCRIPT #3 ---")
for line_no, char in paren_stack:
    print(f"Line {line_no}: Unclosed '{char}' -> {lines[line_no-1].strip()[:100]}")
