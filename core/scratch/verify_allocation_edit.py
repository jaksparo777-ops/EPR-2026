import os
import sys
import django
from django.test import Client
from django.test.utils import override_settings

sys.path.append('/Users/kizzzz/erp_project/core')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from django.contrib.auth.models import User
from inventory.models import Item, ItemWorkerAllocation, ItemComposition, Worker, JobWorker, Category, Material, Client as ERPClient

@override_settings(ALLOWED_HOSTS=['*'])
def run_tests():
    c = Client()
    
    # Login the test client using force_login with the superuser
    user = User.objects.filter(is_superuser=True).first()
    if not user:
        print("Error: No superuser found in database.")
        return
        
    c.force_login(user)
    print(f"Force logged in as: {user.username}")

    # 1. Fetch DASTA 1 and verify current state
    dasta = Item.objects.get(id=12)
    print(f"Initial DASTA 1 details: type={dasta.item_type}, name={dasta.name}, category={dasta.category}, material={dasta.material}")
    initial_allocs = list(ItemWorkerAllocation.objects.filter(item=dasta))
    print("Initial Allocations:")
    for a in initial_allocs:
        name = a.worker.name if a.worker else a.job_worker.name
        print(f" - {name}: ₹{a.rate_per_piece}")

    # 2. Find valid workers for testing
    workers = list(Worker.objects.all()[:3])
    if len(workers) < 2:
        print("Error: Need at least 2 workers to run test.")
        return
        
    w1_val = f"w_{workers[0].id}"
    w2_val = f"w_{workers[1].id}"
    
    # Add a new process step (e.g. the third worker or a job worker)
    job_workers = list(JobWorker.objects.all())
    jw_val = f"jw_{job_workers[0].id}" if job_workers else w1_val
    jw_name = job_workers[0].name if job_workers else workers[0].name

    # 3. Simulate POST request to edit DASTA 1 details and add worker allocation
    # Since DASTA 1 is REGULAR type now, we can edit its worker allocations directly!
    post_data = {
        'form_type': 'item',
        'code': dasta.code,
        'name': dasta.name,
        'item_type': 'REGULAR', # simulate standard drawer field
        'category': dasta.category or Category.objects.first().name,
        'material': dasta.material or Material.objects.first().name,
        'client': dasta.client.id if dasta.client else ERPClient.objects.first().id,
        'casting_weight': dasta.casting_weight,
        'machining_weight': dasta.machining_weight,
        'lot_size': dasta.lot_size,
        'lot_with_box': dasta.lot_with_box,
        'worker_id[]': [w1_val, w2_val, jw_val],
        'worker_rate[]': ['6.50', '5.00', '8.50']
    }
    
    print("\nSimulating POST request to update DASTA 1...")
    response = c.post('/master-data/?edit=12&tab=items', post_data)
    print(f"POST Response status: {response.status_code}")
    if response.status_code == 302:
        print(f"Redirected to: {response.url}")
    
    # Verify allocations got updated in database
    dasta.refresh_from_db()
    updated_allocs = list(ItemWorkerAllocation.objects.filter(item=dasta))
    print("\nUpdated Allocations for DASTA 1 in DB:")
    for a in updated_allocs:
        name = a.worker.name if a.worker else a.job_worker.name
        print(f" - {name}: ₹{a.rate_per_piece}")
        
    assert len(updated_allocs) == 3, f"Expected 3 allocations, got {len(updated_allocs)}"
    print("✓ Verification PASSED for REGULAR item editing!")

    # 4. Now test editing a SET item (SANCHA 7 - ID 41)
    sancha = Item.objects.get(id=41)
    print(f"\nInitial SANCHA 7 (SET) details: type={sancha.item_type}, name={sancha.name}")
    initial_s_comps = list(ItemComposition.objects.filter(parent_item=sancha))
    print("Initial Compositions for SANCHA 7:")
    for comp in initial_s_comps:
        print(f" - {comp.component_item.name}: qty={comp.quantity}")
    
    initial_s_allocs = list(ItemWorkerAllocation.objects.filter(item=sancha))
    print("Initial Labor Allocations for SANCHA 7:")
    for a in initial_s_allocs:
        name = a.worker.name if a.worker else a.job_worker.name
        print(f" - {name}: ₹{a.rate_per_piece}")

    # Simulate POST request to edit SANCHA 7 (SET) via the standard item drawer form.
    # The form should NOT send component_id[] or worker_id[] fields, but MUST send item_type='SET'.
    set_post_data = {
        'form_type': 'item',
        'code': sancha.code,
        'name': 'SANCHA 7 UPDATED',
        'item_type': 'SET', # send correct item_type
        'category': 'Mortal & Pestle', # must be valid Category name
        'material': 'Stainless Steel', # must be valid Material name
        'client': sancha.client.id if sancha.client else ERPClient.objects.first().id,
        'casting_weight': sancha.casting_weight,
        'machining_weight': sancha.machining_weight,
        'lot_size': sancha.lot_size,
        'lot_with_box': sancha.lot_with_box,
    }
    
    print("\nSimulating POST request to update SANCHA 7 (SET) standard details...")
    response = c.post('/master-data/?edit=41&tab=items', set_post_data)
    print(f"POST Response status: {response.status_code}")
    
    # Verify SANCHA 7 (SET) kept its compositions and allocations completely untouched!
    sancha.refresh_from_db()
    print(f"Updated SANCHA 7 details: name={sancha.name}")
    
    updated_s_comps = list(ItemComposition.objects.filter(parent_item=sancha))
    print("Compositions for SANCHA 7 after edit:")
    for comp in updated_s_comps:
        print(f" - {comp.component_item.name}: qty={comp.quantity}")
        
    updated_s_allocs = list(ItemWorkerAllocation.objects.filter(item=sancha))
    print("Labor Allocations for SANCHA 7 after edit:")
    for a in updated_s_allocs:
        name = a.worker.name if a.worker else a.job_worker.name
        print(f" - {name}: ₹{a.rate_per_piece}")
        
    assert len(updated_s_comps) == len(initial_s_comps), "Compositions were deleted!"
    assert len(updated_s_allocs) == len(initial_s_allocs), "Labor allocations were deleted/modified!"
    print("✓ Verification PASSED for SET item editing (Compositions and Allocations completely protected)!")

if __name__ == '__main__':
    run_tests()
