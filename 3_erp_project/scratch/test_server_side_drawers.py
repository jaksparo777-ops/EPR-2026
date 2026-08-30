import django, os, sys
sys.path.insert(0, '/Users/kizzzz/erp_project/3_erp_project')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from apps.production.views.hr_ledger import labor_ledger
from django.test import RequestFactory
from django.contrib.auth import get_user_model

User = get_user_model()
factory = RequestFactory()
user = User.objects.filter(is_superuser=True).first() or User.objects.first()

def test_url(url, expected_active_tab, expected_drawer=None):
    request = factory.get(url)
    request.user = user
    request.session = {}
    request.company = None
    response = labor_ledger(request)
    html = response.content.decode('utf-8')
    
    sec_active_str = f'id="section-{expected_active_tab}" class="ledger-section active'
    
    print(f"Testing URL: {url}")
    print(f"  Status: {response.status_code}")
    print(f"  Active Tab '{expected_active_tab}' in HTML: {sec_active_str in html}")
    if expected_drawer:
        print(f"  Auto-open '{expected_drawer}' in JS: {expected_drawer in html}")

test_url('/ledger/?tab=staff&month=2026-08', 'staff')
test_url('/ledger/?tab=jw&month=2026-08', 'jw')
test_url('/ledger/?tab=sheet&month=2026-08', 'sheet')
test_url('/ledger/?tab=staff&drawer=attendance&month=2026-08', 'staff', 'openAttendanceDrawer()')
test_url('/ledger/?tab=staff&drawer=payment&month=2026-08', 'staff', 'openPaymentDrawer()')
test_url('/ledger/?tab=jw&drawer=jw_profile&jw_id=9&month=2026-08', 'jw', "openJobWorkerProfile('9')")
test_url('/ledger/?tab=staff&drawer=worker_profile&worker_id=14&month=2026-08', 'staff', "openWorkerProfile('14')")
