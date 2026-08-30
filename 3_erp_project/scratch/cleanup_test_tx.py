import os, sys, django
sys.path.append('/Users/kizzzz/erp_project/3_erp_project')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from apps.production.models import StockTransaction

tx_ids = [1384, 1385]
deleted, _ = StockTransaction.objects.filter(id__in=tx_ids).delete()
print(f"Deleted {deleted} test transactions (IDs {tx_ids}).")
