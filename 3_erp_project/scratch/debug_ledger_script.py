import re, sys

with open('/tmp/debug_ledger.html') as f:
    content = f.read()

print('=== 1. CHECKING FIXED / ABSOLUTE OVERLAY ELEMENTS ===')
fixed_matches = re.finditer(r'<([a-z0-9]+)\b([^>]*)style=["\']([^"\']*)["\']([^>]*)>', content, re.IGNORECASE)
for m in fixed_matches:
    tag = m.group(1)
    style = m.group(3)
    full_tag = m.group(0)
    if 'position' in style and ('fixed' in style or 'absolute' in style):
        if 'display:none' not in style and 'display: none' not in style:
            print(f'Tag <{tag}> style: {style[:120]}...')
            if 'width:100%' in style or 'width: 100%' in style or 'inset:0' in style or 'inset: 0' in style or '100vw' in style:
                print(f'  --> WARNING: FULL-SCREEN OVERLAY TAG: {full_tag[:200]}')

print('\n=== 2. CHECKING SCRIPT TAGS & FUNCTION DEFINITIONS ===')
scripts = re.findall(r'<script\b[^>]*>(.*?)</script>', content, re.DOTALL | re.IGNORECASE)
combined_js = '\n;\n'.join(s for s in scripts if s.strip())

funcs_to_check = [
    'showSection', 'openAttendanceDrawer', 'openPaymentDrawer', 
    'openWorkerProfile', 'openJobWorkerProfile', 'filterStaffTable', 
    'filterJwTable', 'switchTeam', 'selectSettlementScope'
]

for func in funcs_to_check:
    has_def = f'function {func}' in combined_js or f'window.{func}' in combined_js or f'{func} =' in combined_js
    print(f'Function "{func}": defined={has_def}')
