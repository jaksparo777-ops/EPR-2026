import os, sys, django
sys.path.append('/Users/kizzzz/erp_project/3_erp_project')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from apps.production.models import ItemWorkerAllocation, Item
from apps.authentication.models import JobWorker, WorkerType
from apps.master_data.models import LegalEntity

print("=== Checking Polishing Allocations for K2+D2 in Database ===")
k2d2_set = Item.objects.filter(code='K2+D2').first()
if k2d2_set:
    print(f"SET Item: id={k2d2_set.id}, code={k2d2_set.code}, company={k2d2_set.company_id}")

allocs = ItemWorkerAllocation.objects.filter(item__code__in=['K2+D2', 'K2', 'D2']).select_related('item', 'worker', 'job_worker')
for a in allocs:
    w_info = f"Worker: {a.worker.name} (id={a.worker.id}, process={a.worker.process})" if a.worker else "No Worker"
    jw_info = f"JobWorker: {a.job_worker.name} (id={a.job_worker.id}, process={a.job_worker.process})" if a.job_worker else "No JobWorker"
    print(f"Alloc ID {a.id} | Item {a.item.code} | {w_info} | {jw_info}")
