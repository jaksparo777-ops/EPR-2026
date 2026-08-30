import os, sys, django
sys.path.append('/Users/kizzzz/erp_project/3_erp_project')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from apps.production.models import StockTransaction
from apps.authentication.models import Worker, JobWorker

txs = StockTransaction.objects.filter(item__code='K5').order_by('-id')[:10]
print("=== Latest 10 StockTransactions for K5 ===")
for tx in txs:
    w_name = tx.worker.name if tx.worker else 'None'
    jw_name = tx.job_worker.name if tx.job_worker else 'None'
    w_id = tx.worker_id
    jw_id = tx.job_worker_id
    print(f"ID: {tx.id} | Date: {tx.created_at.strftime('%Y-%m-%d')} | Type: {tx.transaction_type} | Qty: {tx.quantity} | WorkerFK: {w_id} ({w_name}) | JobWorkerFK: {jw_id} ({jw_name}) | Notes: {tx.notes}")
