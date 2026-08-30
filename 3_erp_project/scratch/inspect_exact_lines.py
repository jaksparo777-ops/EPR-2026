import django, os, sys
sys.path.insert(0, '/Users/kizzzz/erp_project/3_erp_project')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from apps.production.views.hr_ledger import labor_ledger
from django.test import RequestFactory
from django.contrib.auth import get_user_model

User = get_user_model()
factory = RequestFactory()
request = factory.get('/ledger/?month=2026-08')
request.user = User.objects.filter(is_superuser=True).first() or User.objects.first()
request.session = {}
request.company = None

response = labor_ledger(request)
html = response.content.decode('utf-8')
lines = html.splitlines()

print("--- LINES 3560 TO 3575 ---")
for i in range(3559, min(3575, len(lines))):
    print(f"{i+1:4d}: {lines[i]}")

print("\n--- LINES 5000 TO 5015 ---")
for i in range(4999, min(5015, len(lines))):
    print(f"{i+1:4d}: {lines[i]}")
