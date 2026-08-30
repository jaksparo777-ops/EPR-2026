import re, sys

with open('/tmp/debug_ledger.html') as f:
    content = f.read()

scripts = re.findall(r'<script\b[^>]*>(.*?)</script>', content, re.DOTALL | re.IGNORECASE)

s6 = scripts[5] # Script #6

# Let's strip function bodies to see what top-level code runs when Script #6 loads
lines = s6.splitlines()
in_func = 0
top_level_lines = []

for i, l in enumerate(lines, 1):
    l_strip = l.strip()
    if not l_strip or l_strip.startswith('//'):
        continue
    
    # count braces outside strings
    in_str = None
    for ch in l:
        if in_str:
            if ch == in_str: in_str = None
        else:
            if ch in ('"', "'", '`'): in_str = ch
            elif ch == '{': in_func += 1
            elif ch == '}': in_func -= 1
            
    if in_func == 0 or 'document.addEventListener' in l or 'window.addEventListener' in l:
        top_level_lines.append((i, l))

print(f'Top-level lines in Script #6 ({len(top_level_lines)} lines):')
for line_no, l_text in top_level_lines[:40]:
    print(f'Line {line_no}: {l_text}')
