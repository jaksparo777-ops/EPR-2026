import os, sys, django
sys.path.append('/Users/kizzzz/erp_project/3_erp_project')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from apps.production.models import ItemWorkerAllocation, Item
from apps.authentication.models import JobWorker, WorkerType

allocs = ItemWorkerAllocation.objects.filter(item__code='HK1')
for a in allocs:
    print(f"Alloc ID: {a.id} | Item: {a.item.code} (id={a.item.id}, company={a.item.company_id}) | Worker: {a.worker.name if a.worker else None} | JobWorker: {a.job_worker.name if a.job_worker else None}")

items = Item.objects.filter(machining_required=True)
for i in items:
    if i.code == 'HK1':
        print(f"Active Company Item HK1: id={i.id}, company={i.company_id}")
