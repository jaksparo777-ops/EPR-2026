from apps.master_data.models import Item
from apps.production.models import StockTransaction
from django.db.models import Sum

print("Checking non-zero Polishing WIP...")
for code in Item.objects.values_list('code', flat=True).distinct():
    pol_out = StockTransaction.objects.filter(item__code=code, transaction_type='polishing_out').aggregate(total=Sum('quantity'))['total'] or 0
    pol_in = StockTransaction.objects.filter(item__code=code, transaction_type='polishing_in').aggregate(total=Sum('quantity'))['total'] or 0
    pol_rej = StockTransaction.objects.filter(item__code=code, transaction_type='polishing_in').aggregate(total=Sum('rejection_quantity'))['total'] or 0
    wip = pol_out - pol_in - pol_rej
    if wip != 0:
        print(f"SKU: {code} | POL OUT: {pol_out} | POL IN: {pol_in} | POL REJ: {pol_rej} | POL WIP: {wip}")

print("Checking packaging queue...")
for code in Item.objects.values_list('code', flat=True).distinct():
    pol_entries = StockTransaction.objects.filter(item__code=code, transaction_type='polishing_in')
    queue_qty = 0
    for entry in pol_entries:
        packed_qty = StockTransaction.objects.filter(
            transaction_type="packaging_in",
            notes__contains=f"PACKED #{entry.id}"
        ).aggregate(total=Sum('quantity'))['total'] or 0
        rem_qty = entry.quantity - packed_qty - (entry.rejection_quantity or 0)
        queue_qty += max(0, rem_qty)
    if queue_qty != 0:
        print(f"SKU: {code} | Packaging Queue Qty: {queue_qty}")
