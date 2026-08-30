import os, sys, django
sys.path.append('/Users/kizzzz/erp_project/3_erp_project')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from apps.production.models import ItemWorkerAllocation, Item
from apps.authentication.models import Worker, JobWorker

print("=== All ItemWorkerAllocations ===")
allocs = ItemWorkerAllocation.objects.all().select_related('item', 'worker', 'job_worker')
for a in allocs:
    item_str = f"{a.item.code} - {a.item.name} (id={a.item.id})"
    w_str = f"Worker: {a.worker.name} (id={a.worker.id}, type={a.worker.worker_type})" if a.worker else "No Worker"
    jw_str = f"JobWorker: {a.job_worker.name} (id={a.job_worker.id})" if a.job_worker else "No JobWorker"
    print(f"Alloc ID: {a.id} | Item: {item_str} | {w_str} | {jw_str}")
