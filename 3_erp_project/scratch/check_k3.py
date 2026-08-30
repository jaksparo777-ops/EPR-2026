import os, sys, django
sys.path.append('/Users/kizzzz/erp_project/3_erp_project')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from apps.production.models import Item
from apps.master_data.models import LegalEntity

print("=== Items with 'K3' in Company 1 (OM) ===")
c1 = LegalEntity.objects.get(id=1)
items1 = Item.objects.filter(company=c1, code__icontains='K3')
for i in items1:
    print(f"OM (comp 1): id={i.id}, code='{i.code}', name='{i.name}', is_set={i.item_type=='SET'}")

print("\n=== Items with 'K3' in Company 2 (Finishing) ===")
c2 = LegalEntity.objects.get(id=2)
items2 = Item.objects.filter(company=c2, code__icontains='K3')
for i in items2:
    print(f"Finishing (comp 2): id={i.id}, code='{i.code}', name='{i.name}', is_set={i.item_type=='SET'}")
