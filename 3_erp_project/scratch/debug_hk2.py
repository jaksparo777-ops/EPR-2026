import os, sys, django
sys.path.append('/Users/kizzzz/erp_project/3_erp_project')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from apps.production.models import ItemWorkerAllocation, Item
from apps.authentication.models import Worker, JobWorker, WorkerType
from apps.master_data.models import LegalEntity

print("=== Checking HK2 - HKhal 2 in Database ===")
hk2_items = Item.objects.filter(code='HK2')
for i in hk2_items:
    print(f"Item: id={i.id}, code={i.code}, name={i.name}, company={i.company_id}")

print("\n=== All ItemWorkerAllocations for HK2 ===")
allocs = ItemWorkerAllocation.objects.filter(item__code='HK2').select_related('item', 'worker', 'job_worker')
for a in allocs:
    w_info = f"Worker: {a.worker.name} (id={a.worker.id}, type={a.worker.worker_type}, jw_code={a.worker.jw_code})" if a.worker else "No Worker"
    jw_info = f"JobWorker: {a.job_worker.name} (id={a.job_worker.id}, jw_code={a.job_worker.jw_code})" if a.job_worker else "No JobWorker"
    print(f"Alloc ID {a.id} | Item code={a.item.code} (id={a.item.id}, company={a.item.company_id}) | {w_info} | {jw_info}")

# Now let's run the exact smart_allocations logic from production.py for active company OM (id=1)
active_company = LegalEntity.objects.get(id=1)
items = Item.objects.filter(company=active_company, machining_required=True)
company_items = {it.code: it.id for it in items}

all_allocations = ItemWorkerAllocation.objects.all().select_related('worker', 'job_worker', 'item')
smart_allocations = {}
for a in all_allocations:
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

print("\n=== smart_allocations output for company 1 HK2 (id=62 or similar) ===")
hk2_c1 = Item.objects.filter(company_id=1, code='HK2').first()
if hk2_c1:
    print(f"HK2 Company 1 ID: {hk2_c1.id}")
    print(f"smart_allocations['{hk2_c1.id}']: {smart_allocations.get(str(hk2_c1.id))}")
