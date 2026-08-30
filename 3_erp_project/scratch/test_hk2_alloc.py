import os, sys, django
sys.path.append('/Users/kizzzz/erp_project/3_erp_project')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from apps.production.models import ItemWorkerAllocation, Item
from apps.authentication.models import Worker
from apps.master_data.models import LegalEntity

# Add Ramesh bhai machining allocation to HK2
ramesh = Worker.objects.filter(name__icontains='Ramesh', worker_type='JOB_WORKER').first()
hk2 = Item.objects.filter(code='HK2').first()

print(f"Ramesh bhai Worker ID: {ramesh.id}, jw_code: {ramesh.jw_code}")
print(f"HK2 Item ID: {hk2.id}, code: {hk2.code}")

alloc, created = ItemWorkerAllocation.objects.get_or_create(
    item=hk2,
    worker=ramesh,
    defaults={'rate_per_piece': 0.0}
)
print(f"Allocation created: {created}, Alloc ID: {alloc.id}")
