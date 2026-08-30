import os, sys, django
sys.path.append('/Users/kizzzz/erp_project/3_erp_project')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from apps.production.models import ItemWorkerAllocation, Item
from apps.authentication.models import JobWorker, WorkerType

allocations = ItemWorkerAllocation.objects.all().select_related('worker', 'job_worker', 'item')
items = Item.objects.filter(machining_required=True)
company_items = {it.code: it.id for it in items}

smart_allocations = {}
for a in allocations:
    if a.worker and a.worker.process != 'machining':
        continue
    if a.job_worker and a.job_worker.process != 'machining':
        continue
        
    if a.worker_id:
        is_jw = (a.worker.worker_type == WorkerType.JOB_WORKER)
        if is_jw:
            jw_obj = None
            if a.worker.jw_code:
                jw_obj = JobWorker.objects.filter(jw_code=a.worker.jw_code).first()
            if not jw_obj and a.worker.name:
                jw_obj = JobWorker.objects.filter(name__iexact=a.worker.name).first()
            w_id = f"jw_{jw_obj.id}" if jw_obj else f"w_{a.worker_id}"
            w_name = a.worker.name
        else:
            w_id = f"w_{a.worker_id}"
            w_name = a.worker.name
    else:
        w_id = f"jw_{a.job_worker_id}"
        w_name = a.job_worker.name

    performer = {"id": w_id, "name": w_name}
    
    item_id = str(company_items.get(a.item.code, a.item.id))
    if item_id not in smart_allocations:
        smart_allocations[item_id] = []
    if performer not in smart_allocations[item_id]:
        smart_allocations[item_id].append(performer)

print("=== Smart Allocations Sample for HK1 (id=141) ===")
hk1_item = Item.objects.filter(code='HK1').first()
if hk1_item:
    print(f"HK1 ID: {hk1_item.id}")
    print(smart_allocations.get(str(hk1_item.id)))
