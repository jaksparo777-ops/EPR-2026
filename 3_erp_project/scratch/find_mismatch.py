with open('/Users/kizzzz/erp_project/3_erp_project/scratch/script_4.js', 'r') as f:
    code = f.read()

lines = code.split('\n')
depth = 0
for i, l in enumerate(lines):
    # Ignore string literals simple heuristic or track carefully
    prev = depth
    for c in l:
        if c == '{': depth += 1
        elif c == '}': depth -= 1
    # print significant depth changes or end depth
    if i > 800 and i < 900:
        print(f"L{i+1}: depth={depth} | {l}")

print(f"End depth: {depth}")
