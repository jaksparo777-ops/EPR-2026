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

print(f'Total rendered lines: {len(lines)}')

def print_around(target_line, radius=10):
    start = max(0, target_line - radius)
    end = min(len(lines), target_line + radius)
    print(f'\n--- LINES {start+1} TO {end} ---')
    for i in range(start, end):
        print(f'{i+1:4d}: {lines[i]}')

print_around(1359, 5)
print_around(3569, 10)
if len(lines) >= 4900:
    print_around(4995, 15)
