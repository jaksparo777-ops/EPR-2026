import os
import django
import json

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
django.setup()

from inventory.models import Item, StockTransaction, JobWorker
from django.test import RequestFactory
from django.contrib.messages.storage.fallback import FallbackStorage
from inventory.views.production import polishing_entry

def test_set_manual_transaction():
    # 1. Get a SET item (e.g. KHAL 1 + DASTA 1)
    set_item = Item.objects.filter(item_type='SET').first()
    if not set_item:
        print("No SET item found in database to test.")
        return

    # 2. Get a Polishing Job Worker
    jw = JobWorker.objects.filter(process='polishing').first()
    if not jw:
        print("No Polishing Job Worker found in database to test.")
        return

    print(f"Testing with Set Item: {set_item.name} (ID: {set_item.id})")
    print(f"Testing with Job Worker: {jw.name} (ID: {jw.id})")

    # 3. Simulate a POST request with lots=0, manual=25 (Pure Manual Entry)
    factory = RequestFactory()
    
    components_payload = []
    for comp in set_item.components.all():
        components_payload.append({
            "component_id": str(comp.component_item.id),
            "qty_per_set": comp.quantity,
            "extra_qty": 0,
            "total_qty": comp.quantity * 25
        })

    row_data = {
        "item_id": str(set_item.id),
        "packaging": "regular",
        "lots": 0,
        "manual": 25,
        "weight": 12.5,
        "components": components_payload
    }

    post_data = {
        "direction": "polishing_out",
        "worker": f"jw_{jw.id}",
        "transaction_data": json.dumps([row_data])
    }

    request = factory.post("/polishing/", post_data)
    
    # Enable session and messages support
    from django.contrib.sessions.middleware import SessionMiddleware
    middleware = SessionMiddleware(lambda r: None)
    middleware.process_request(request)
    request.session.save()
    
    messages = FallbackStorage(request)
    setattr(request, '_messages', messages)

    # 4. Execute the view
    response = polishing_entry(request)
    print(f"Response status code: {response.status_code}")

    # 5. Verify transaction creation
    tx = StockTransaction.objects.filter(item=set_item, quantity=25, job_worker=jw).order_by('-id')
    latest_tx = tx.first()
    
    if latest_tx:
        print(f"✅ Success! Created parent StockTransaction ID: {latest_tx.id} with quantity: {latest_tx.quantity}")
        
        # Verify component consumption
        consumptions = StockTransaction.objects.filter(
            transaction_type='kitting_consume',
            notes__contains=f"Auto-consumed for Set Transaction #{latest_tx.id}"
        )
        print(f"Found {consumptions.count()} child consumption transactions:")
        for c in consumptions:
            print(f" - Component: {c.item.name}, Qty consumed: {c.quantity}")
            expected_qty = set_item.components.get(component_item=c.item).quantity * 25
            if c.quantity == expected_qty:
                print(f"   ✅ Correctly consumed {expected_qty} pcs!")
            else:
                print(f"   ❌ Incorrect consumption quantity: expected {expected_qty}, got {c.quantity}")
    else:
        print("❌ Failed! No StockTransaction created with quantity 25.")

if __name__ == "__main__":
    test_set_manual_transaction()
