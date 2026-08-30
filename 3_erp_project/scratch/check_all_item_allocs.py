import os, sys, django
sys.path.append('/Users/kizzzz/erp_project/3_erp_project')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from apps.production.models import ItemWorkerAllocation, Item
from apps.master_data.models import LegalEntity

c1 = LegalEntity.objects.get(id=1)
items = Item.objects.filter(company=c1, machining_required=True)

print(f"=== Machining Items in OM (Company 1) Total: {items.count()} ===")
for it in items:
    allocs = ItemWorkerAllocation.objects.filter(item__code=it.code).select_related('worker', 'job_worker')
    alloc_str = ", ".join([f"{a.worker.name if a.worker else a.job_worker.name} (proc={a.worker.process if a.worker else a.job_worker.process})" for a in allocs])
    if not alloc_str:
        alloc_str = "NO ALLOCATION IN DATABASE"
    print(f"Item: {it.code} - {it.name} (id={it.id}) => Allocations: {alloc_str}")
