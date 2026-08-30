import os, sys, django
sys.path.append('/Users/kizzzz/erp_project/3_erp_project')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from apps.production.models import ItemWorkerAllocation, Item
from apps.authentication.models import JobWorker

print("=== All Allocations for Tarkeshwar bhai ===")
tarkeshwar_jw = JobWorker.objects.filter(name__icontains='Tarkeshwar').first()
if tarkeshwar_jw:
    print(f"JobWorker ID: {tarkeshwar_jw.id} (key: jw_{tarkeshwar_jw.id})")
    allocs = ItemWorkerAllocation.objects.filter(job_worker=tarkeshwar_jw).select_related('item')
    for a in allocs:
        print(f"Alloc ID={a.id} | Item ID={a.item.id}, code='{a.item.code}', name='{a.item.name}', comp={a.item.company_id}, is_set={a.item.item_type=='SET'}")

    print("\n=== Allocations matching w_26 or jw_30 ===")
    allocs2 = ItemWorkerAllocation.objects.filter(worker_id=26).select_related('item')
    for a in allocs2:
        print(f"Worker Alloc ID={a.id} | Item ID={a.item.id}, code='{a.item.code}', name='{a.item.name}', comp={a.item.company_id}")
