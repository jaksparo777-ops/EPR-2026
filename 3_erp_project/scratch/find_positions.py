import re, sys

with open('/tmp/debug_ledger.html') as f:
    content = f.read()

print('=== ALL STYLED ELEMENTS WITH POSITION OR Z-INDEX ===')
# Find all style attributes
styles = re.findall(r'<([a-z0-9]+)\b[^>]*?(id=["\'][^"\']*["\'])?[^>]*?(class=["\'][^"\']*["\'])?[^>]*?style=["\']([^"\']*)["\'][^>]*>', content, re.IGNORECASE)
for tag, el_id, el_class, style in styles:
    if 'position' in style or 'z-index' in style or 'pointer-events' in style:
        print(f'<{tag} {el_id} {el_class}> style="{style}"')

# Also search inside <style> blocks for fixed/absolute or high z-index rules
print('\n=== ALL CSS RULES WITH POSITION OR Z-INDEX ===')
style_blocks = re.findall(r'<style\b[^>]*>(.*?)</style>', content, re.DOTALL | re.IGNORECASE)
for sb in style_blocks:
    rules = sb.split('}')
    for r in rules:
        if 'position' in r or 'z-index' in r or 'pointer-events' in r:
            cleaned_r = ' '.join(r.split())
            if len(cleaned_r) < 200:
                print(' ', cleaned_r)
