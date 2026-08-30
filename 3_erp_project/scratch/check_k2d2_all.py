import os, sys, django
sys.path.append('/Users/kizzzz/erp_project/3_erp_project')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from apps.production.models import ItemWorkerAllocation, Item
from apps.master_data.models import LegalEntity, ItemComposition

print("=== All Items with code 'K2+D2' ===")
k_items = Item.objects.filter(code__icontains='K2+D2')
for i in k_items:
    print(f"Item id={i.id}, code='{i.code}', name='{i.name}', company_id={i.company_id}, item_type='{i.item_type}'")

print("\n=== All ItemWorkerAllocations for K2+D2 or K2 or D2 ===")
allocs = ItemWorkerAllocation.objects.filter(item__code__in=['K2+D2', 'K2', 'D2']).select_related('item', 'worker', 'job_worker')
for a in allocs:
    w_info = f"Worker: {a.worker.name} (id={a.worker.id}, proc={a.worker.process})" if a.worker else "No Worker"
    jw_info = f"JobWorker: {a.job_worker.name} (id={a.job_worker.id}, proc={a.job_worker.process})" if a.job_worker else "No JobWorker"
    print(f"Alloc ID {a.id} | Item {a.item.code} (id={a.item.id}, comp={a.item.company_id}) | {w_info} | {jw_info}")
