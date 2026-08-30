import re, sys

with open('/tmp/debug_ledger.html') as f:
    content = f.read()

scripts = re.findall(r'<script\b[^>]*>(.*?)</script>', content, re.DOTALL | re.IGNORECASE)

print(f'Total script blocks in rendered HTML: {len(scripts)}')

# Check order of function definitions and top-level statements
for i, s in enumerate(scripts, 1):
    s_clean = s.strip()
    if not s_clean:
        continue
    funcs = re.findall(r'function\s+([a-zA-Z0-9_$]+)\s*\(', s_clean)
    top_level_calls = re.findall(r'^[ \t]*([a-zA-Z0-9_$]+)\s*\(', s_clean, re.MULTILINE)
    print(f'\n--- Script #{i} (len={len(s_clean)}) ---')
    print(f'  Functions defined ({len(funcs)}): {funcs[:15]}')
    print(f'  Top-level calls ({len(top_level_calls)}): {top_level_calls[:15]}')
