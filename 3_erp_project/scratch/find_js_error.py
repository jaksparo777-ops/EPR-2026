import re

with open('/Users/kizzzz/erp_project/3_erp_project/templates/polishing.html', 'r') as f:
    html = f.read()

# Extract script blocks
scripts = re.findall(r'<script\b[^>]*>(.*?)</script>', html, re.DOTALL)
print(f"Found {len(scripts)} script tags.")

for idx, s in enumerate(scripts):
    if 'addItemRow' in s:
        print(f"Script #{idx} contains addItemRow. Length: {len(s)}")
        # Save script block to temporary js file to check node syntax
        with open(f'/Users/kizzzz/erp_project/3_erp_project/scratch/script_{idx}.js', 'w') as out:
            out.write(s)
