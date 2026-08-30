import re, sys

with open('/tmp/debug_ledger.html') as f:
    content = f.read()

overlays = [
    'drawerBackdrop', 'sidebarOverlay', 'notificationBackdrop', 
    'globalSearchOverlay', 'bulkDownloadModal', 'inlineStatementModal', 'editPaymentModal'
]

print('=== OVERLAY ELEMENTS CHECK ===')
for ov in overlays:
    m = re.search(rf'<[a-z0-9]+\b[^>]*\bid=["\']{ov}["\'][^>]*>', content, re.IGNORECASE)
    if m:
        tag_html = m.group(0)
        print(f'Element #{ov}:')
        print(f'  HTML: {tag_html}')
    else:
        print(f'Element #{ov}: NOT FOUND in HTML')
