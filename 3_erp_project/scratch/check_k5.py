import os, sys, django
sys.path.append('/Users/kizzzz/erp_project/3_erp_project')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from apps.production.models import StockTransaction
from apps.master_data.models import Item

item_k5 = Item.objects.filter(code='K5').first()
print(f"Item K5: id={item_k5.id if item_k5 else None}")

txs = StockTransaction.objects.filter(item__code='K5').order_by('id')
print("=== All StockTransactions for K5 ===")
for tx in txs:
    w_name = tx.worker.name if tx.worker else (tx.job_worker.name if tx.job_worker else 'None')
    print(f"ID: {tx.id} | Date: {tx.created_at.strftime('%Y-%m-%d')} | Type: {tx.transaction_type} | Qty: {tx.quantity} | Worker: {w_name} | Notes: {tx.notes}")
