import os, re

template_dir = '/Users/kizzzz/erp_project/3_erp_project/templates'

print("=== SEARCHING ALL TEMPLATES FOR UNCHECKED getElementById CALLS ===")

for root, dirs, files in os.walk(template_dir):
    for f in files:
        if f.endswith('.html'):
            filepath = os.path.join(root, f)
            with open(filepath) as file_obj:
                content = file_obj.read()
            
            # Find script blocks
            script_pattern = re.compile(r'<script\b[^>]*>(.*?)</script>', re.DOTALL | re.IGNORECASE)
            for m in script_pattern.finditer(content):
                script_text = m.group(1)
                lines = script_text.splitlines()
                for idx, line in enumerate(lines, 1):
                    # Look for getElementById('...').addEventListener or .style or .value or .classList
                    danger_matches = re.finditer(r"document\.getElementById\(['\"]([^'\"]+)['\"]\)\.(addEventListener|classList|style|value|focus|click|setAttribute)", line)
                    for dm in danger_matches:
                        el_id, method = dm.groups()
                        # Check if line or preceding line has null check
                        if "if (" not in line and "if(" not in line and "&&" not in line and "?." not in line:
                            rel_path = os.path.relpath(filepath, template_dir)
                            print(f"File: {rel_path} | ID: '{el_id}' -> .{method} | Line: {line.strip()[:100]}")
