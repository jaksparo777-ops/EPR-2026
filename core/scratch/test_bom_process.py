import os
import sys
import django
from django.test import Client
from django.test.utils import override_settings

sys.path.append('/Users/kizzzz/erp_project/core')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from django.contrib.auth.models import User
from inventory.models import Item, ItemComposition

@override_settings(ALLOWED_HOSTS=['*'])
def run_tests():
    c = Client()
    
    # 1. Clean up old test data if exists
    Item.objects.filter(code='TBP1').delete()
    
    # 2. Login as superuser
    user = User.objects.filter(is_superuser=True).first()
    if not user:
        print("Error: No superuser found.")
        return
    c.force_login(user)
    
    # 3. Choose a component to map in the BOM
    comp = Item.objects.filter(item_type='REGULAR').first()
    if not comp:
        print("Error: No regular items found to use as component.")
        return
        
    print(f"Using component: {comp.name} (id={comp.id}, casting_req={comp.casting_required}, machining_req={comp.machining_required})")
    
    # Force component to have casting/machining required to prove that the parent set DOES NOT inherit them when they are unchecked in form!
    comp.casting_required = True
    comp.machining_required = True
    comp.save()

    # 4. Simulate POST to create a BOM Set with ONLY polishing and packaging selected!
    post_data = {
        'form_type': 'bom',
        'new_set_name': 'TEST BOM PROCESS',
        'new_set_code': 'TBP1',
        'category': 'Mortal & Pestle',
        'sub_category': 'Test',
        'variant': 'TestVar',
        'polishing_required': 'on', # Checked
        'packing_required': 'on',    # Checked
        # casting_required and machining_required are UNCHECKED (not submitted in POST)
        'component_id[]': [comp.id],
        'component_qty[]': ['2']
    }
    
    print("\nSimulating POST request to create BOM Set 'TEST BOM PROCESS'...")
    response = c.post('/master-data/?tab=items&sub=bom', post_data)
    print(f"POST Response status: {response.status_code}")
    
    # 5. Retrieve parent item and verify process flags
    try:
        set_item = Item.objects.get(code='TBP1')
        print(f"\nRetrieved Created BOM Set:")
        print(f" - Name: {set_item.name}")
        print(f" - casting_required: {set_item.casting_required}")
        print(f" - machining_required: {set_item.machining_required}")
        print(f" - polishing_required: {set_item.polishing_required}")
        print(f" - packing_required: {set_item.packing_required}")
        
        # Verify that only the user-selected processes are saved
        assert set_item.casting_required is False, "Casting required should be False!"
        assert set_item.machining_required is False, "Machining required should be False!"
        assert set_item.polishing_required is True, "Polishing required should be True!"
        assert set_item.packing_required is True, "Packing required should be True!"
        
        # Verify compositions are successfully saved
        comps = list(ItemComposition.objects.filter(parent_item=set_item))
        print(f" - Compositions count: {len(comps)}")
        assert len(comps) == 1, f"Expected 1 composition, got {len(comps)}"
        assert comps[0].component_item == comp, "Component item mismatch!"
        assert comps[0].quantity == 2, f"Expected quantity 2, got {comps[0].quantity}"
        
        print("\n✓ Verification PASSED! BOM Set process requirement selections are perfectly honored and default to what is selected in the form!")
        
        # Cleanup
        set_item.delete()
        
    except Item.DoesNotExist:
        print("Error: BOM Set item was not created!")
        assert False

if __name__ == '__main__':
    run_tests()
