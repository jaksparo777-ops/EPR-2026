import re

def analyze_html_scripts(path):
    print(f"\n==========================================")
    print(f"ANALYZING: {path}")
    print(f"==========================================")
    with open(path) as f:
        html = f.read()

    # Find script tags
    script_pattern = re.compile(r'<script\b[^>]*>(.*?)</script>', re.DOTALL | re.IGNORECASE)
    matches = list(script_pattern.finditer(html))

    for idx, match in enumerate(matches, 1):
        content = match.group(1).strip()
        if not content:
            continue
        line_offset = html[:match.start()].count('\n') + 1
        
        # Check for obvious hazards
        # 1. document.getElementById('...').something without null check
        # 2. unescaped template tags in JS strings
        # 3. uncaught references
        
        lines = content.splitlines()
        for line_idx, l in enumerate(lines, 1):
            file_line = line_offset + line_idx - 1
            # Check for direct property access on getElementById without null guard
            m_gid = re.search(r"document\.getElementById\(['\"]([^'\"]+)['\"]\)\.([a-zA-Z0-9_\$]+)", l)
            if m_gid:
                el_id, prop = m_gid.groups()
                if prop not in ['style', 'classList', 'value', 'innerText', 'textContent', 'innerHTML', 'click', 'focus', 'addEventListener']:
                    print(f"Line {file_line}: Danger direct access document.getElementById('{el_id}').{prop} -> {l.strip()[:100]}")
            
            # Check for uncaught addEventListener on null
            m_ael = re.search(r"document\.getElementById\(['\"]([^'\"]+)['\"]\)\.addEventListener", l)
            if m_ael:
                el_id = m_ael.group(1)
                print(f"Line {file_line}: Unchecked addEventListener on document.getElementById('{el_id}') -> {l.strip()[:100]}")

analyze_html_scripts('/Users/kizzzz/erp_project/3_erp_project/templates/layout/base.html')
analyze_html_scripts('/Users/kizzzz/erp_project/3_erp_project/templates/labor_ledger.html')
