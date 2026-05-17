from django.db.models import Sum
from .models import StockTransaction, TransactionType

def get_stock_by_item(item):
    """
    Returns a dictionary of stock quantities for a given item at each stage.
    """
    # Optimized: Use a single query to get all transaction sums for this item, grouped by type and warehouse
    stats = StockTransaction.objects.filter(item=item).values('transaction_type', 'from_warehouse__code').annotate(total=Sum('quantity'))
    
    totals = {}
    for s in stats:
        tx_type = s['transaction_type']
        wh_code = s['from_warehouse__code']
        qty = s['total'] or 0
        
        if tx_type == TransactionType.KITTING_CONSUME:
            key = f"{tx_type}_{wh_code}"
            totals[key] = totals.get(key, 0) + qty
        else:
            totals[tx_type] = totals.get(tx_type, 0) + qty
            
    casting_in = totals.get(TransactionType.CASTING_ENTRY, 0)
    machining_out = totals.get(TransactionType.MACHINING_OUT, 0)
    machining_in = totals.get(TransactionType.MACHINING_IN, 0)
    polishing_out = totals.get(TransactionType.POLISHING_OUT, 0)
    polishing_in = totals.get(TransactionType.POLISHING_IN, 0)
    packaging_in = totals.get(TransactionType.PACKAGING_IN, 0)
    dispatch_out = totals.get(TransactionType.DISPATCH_OUT, 0)
    
    # Bifurcated component consumption
    kitting_consume_machining = totals.get(f"{TransactionType.KITTING_CONSUME}_MACHINING", 0)
    kitting_consume_polishing = totals.get(f"{TransactionType.KITTING_CONSUME}_POLISHING", 0)
    kitting_consume_none = totals.get(f"{TransactionType.KITTING_CONSUME}_None", 0) # Fallback
    
    kitting_produce = totals.get(TransactionType.KITTING_PRODUCE, 0)
    
    return {
        'casting': casting_in - machining_out,
        'machining': machining_in - (polishing_out + kitting_consume_machining),
        'polishing': polishing_in - (packaging_in + kitting_consume_polishing + kitting_consume_none),
        'ready': (packaging_in + kitting_produce) - dispatch_out
    }

def get_overall_stock():
    """
    Returns total stock across all items for each stage.
    """
    stats = StockTransaction.objects.values('transaction_type', 'from_warehouse__code').annotate(
        total_qty=Sum('quantity'), 
        total_weight=Sum('weight')
    )
    
    qty_totals = {}
    weight_totals = {}
    for s in stats:
        tx_type = s['transaction_type']
        wh_code = s['from_warehouse__code']
        qty = s['total_qty'] or 0
        wt = s['total_weight'] or 0
        
        if tx_type == TransactionType.KITTING_CONSUME:
            key = f"{tx_type}_{wh_code}"
            qty_totals[key] = qty_totals.get(key, 0) + qty
            weight_totals[key] = weight_totals.get(key, 0) + wt
        else:
            qty_totals[tx_type] = qty_totals.get(tx_type, 0) + qty
            weight_totals[tx_type] = weight_totals.get(tx_type, 0) + wt
            
    casting_qty = qty_totals.get(TransactionType.CASTING_ENTRY, 0) - qty_totals.get(TransactionType.MACHINING_OUT, 0)
    
    machining_qty = qty_totals.get(TransactionType.MACHINING_IN, 0) - (
        qty_totals.get(TransactionType.POLISHING_OUT, 0) + 
        qty_totals.get(f"{TransactionType.KITTING_CONSUME}_MACHINING", 0)
    )
    
    polishing_qty = qty_totals.get(TransactionType.POLISHING_IN, 0) - (
        qty_totals.get(TransactionType.PACKAGING_IN, 0) + 
        qty_totals.get(f"{TransactionType.KITTING_CONSUME}_POLISHING", 0) + 
        qty_totals.get(f"{TransactionType.KITTING_CONSUME}_None", 0)
    )
    
    ready_qty = (
        qty_totals.get(TransactionType.PACKAGING_IN, 0) + 
        qty_totals.get(TransactionType.KITTING_PRODUCE, 0)
    ) - qty_totals.get(TransactionType.DISPATCH_OUT, 0)

    casting_weight = weight_totals.get(TransactionType.CASTING_ENTRY, 0) - weight_totals.get(TransactionType.MACHINING_OUT, 0)
    
    machining_weight = weight_totals.get(TransactionType.MACHINING_IN, 0) - (
        weight_totals.get(TransactionType.POLISHING_OUT, 0) + 
        weight_totals.get(f"{TransactionType.KITTING_CONSUME}_MACHINING", 0)
    )
    
    polishing_weight = weight_totals.get(TransactionType.POLISHING_IN, 0) - (
        weight_totals.get(TransactionType.PACKAGING_IN, 0) + 
        weight_totals.get(f"{TransactionType.KITTING_CONSUME}_POLISHING", 0) + 
        weight_totals.get(f"{TransactionType.KITTING_CONSUME}_None", 0)
    )
    
    ready_weight = (
        weight_totals.get(TransactionType.PACKAGING_IN, 0) + 
        weight_totals.get(TransactionType.KITTING_PRODUCE, 0)
    ) - weight_totals.get(TransactionType.DISPATCH_OUT, 0)

    return {
        'casting_qty': casting_qty,
        'casting_weight': round(casting_weight, 3),
        'machining_qty': machining_qty,
        'machining_weight': round(machining_weight, 3),
        'polishing_qty': polishing_qty,
        'polishing_weight': round(polishing_weight, 3),
        'ready_qty': ready_qty,
        'ready_weight': round(ready_weight, 3),
    }
