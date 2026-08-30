import os, sys, django
sys.path.append('/Users/kizzzz/erp_project/3_erp_project')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from apps.production.models import ItemWorkerAllocation, Item
from apps.authentication.models import JobWorker, WorkerType
from apps.master_data.models import LegalEntity, ItemComposition

active_company = LegalEntity.objects.get(id=1)
items = Item.objects.filter(company=active_company).filter(polishing_required=True) | Item.objects.filter(company=active_company, item_type='SET')
company_items = {it.code: it.id for it in items}

allocations = ItemWorkerAllocation.objects.all().select_related('item', 'worker', 'job_worker')
smart_allocations = {}

for a in allocations:
    if a.worker and a.worker.process != 'polishing':
        continue
    if a.job_worker and a.job_worker.process != 'polishing':
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
    
    resolved_id = company_items.get(a.item.code, a.item.id)
    item_id_str = str(resolved_id)
    if item_id_str not in smart_allocations:
        smart_allocations[item_id_str] = []
    if performer not in smart_allocations[item_id_str]:
        smart_allocations[item_id_str].append(performer)

    # Inherit parent set allocations for sub-components AND vice versa
    equivalent_item_id = company_items.get(a.item.code)
    if equivalent_item_id:
        for comp in ItemComposition.objects.filter(parent_item_id=equivalent_item_id):
            comp_id = str(comp.component_item_id)
            if comp_id not in smart_allocations:
                smart_allocations[comp_id] = []
            if performer not in smart_allocations[comp_id]:
                smart_allocations[comp_id].append(performer)

print("=== Checking K2+D2 in Company 1 ===")
k2d2 = Item.objects.filter(company=active_company, code='K2+D2').first()
if k2d2:
    print(f"K2+D2 ID in Company 1: {k2d2.id}")
    print(f"smart_allocations['{k2d2.id}']: {smart_allocations.get(str(k2d2.id))}")

print("\n=== Checking Components of K2+D2 ===")
comps = ItemComposition.objects.filter(parent_item=k2d2)
for c in comps:
    print(f"Comp: {c.component_item.code} (id={c.component_item.id}) => smart_allocations: {smart_allocations.get(str(c.component_item.id))}")
