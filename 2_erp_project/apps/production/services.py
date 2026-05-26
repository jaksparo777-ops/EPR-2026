from django.db.models import Sum
from apps.products.models import TransactionType
from apps.production.models import StockTransaction

def get_stock_by_item(item):
    """
    Returns a dictionary of stock quantities for a given item at each stage.
    """
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
    
    # Exclude [DEDICATED BUFFER] transactions from packaging calculations
    dedicated_buffer_qty = StockTransaction.objects.filter(
        item=item,
        transaction_type=TransactionType.PACKAGING_IN,
        notes__contains='[DEDICATED BUFFER]'
    ).aggregate(total=Sum('quantity'))['total'] or 0
    
    packaging_in = max(0, totals.get(TransactionType.PACKAGING_IN, 0) - dedicated_buffer_qty)
    dispatch_out = totals.get(TransactionType.DISPATCH_OUT, 0)
    
    # Bifurcated component consumption
    kitting_consume_machining = totals.get(f"{TransactionType.KITTING_CONSUME}_MACHINING", 0)
    kitting_consume_polishing = totals.get(f"{TransactionType.KITTING_CONSUME}_POLISHING", 0)
    kitting_consume_none = totals.get(f"{TransactionType.KITTING_CONSUME}_None", 0) # Fallback
    
    kitting_produce = totals.get(TransactionType.KITTING_PRODUCE, 0)
    
    return {
        'casting': casting_in - machining_out,
        'machining': machining_in - (polishing_out + kitting_consume_machining),
        'polishing': polishing_in - packaging_in,
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
            
    # Exclude [DEDICATED BUFFER] packaging transactions from the global totals
    buffer_totals = StockTransaction.objects.filter(
        transaction_type=TransactionType.PACKAGING_IN,
        notes__contains='[DEDICATED BUFFER]'
    ).aggregate(total_qty=Sum('quantity'), total_weight=Sum('weight'))
    
    dedicated_buffer_qty = buffer_totals['total_qty'] or 0
    dedicated_buffer_weight = buffer_totals['total_weight'] or 0

    casting_qty = qty_totals.get(TransactionType.CASTING_ENTRY, 0) - qty_totals.get(TransactionType.MACHINING_OUT, 0)
    
    machining_qty = qty_totals.get(TransactionType.MACHINING_IN, 0) - (
        qty_totals.get(TransactionType.POLISHING_OUT, 0) + 
        qty_totals.get(f"{TransactionType.KITTING_CONSUME}_MACHINING", 0)
    )
    
    raw_packaging_qty = qty_totals.get(TransactionType.PACKAGING_IN, 0)
    packaging_qty = max(0, raw_packaging_qty - dedicated_buffer_qty)
    
    polishing_qty = qty_totals.get(TransactionType.POLISHING_IN, 0) - packaging_qty
    
    ready_qty = (
        packaging_qty + 
        qty_totals.get(TransactionType.KITTING_PRODUCE, 0)
    ) - qty_totals.get(TransactionType.DISPATCH_OUT, 0)

    casting_weight = weight_totals.get(TransactionType.CASTING_ENTRY, 0) - weight_totals.get(TransactionType.MACHINING_OUT, 0)
    
    machining_weight = weight_totals.get(TransactionType.MACHINING_IN, 0) - (
        weight_totals.get(TransactionType.POLISHING_OUT, 0) + 
        weight_totals.get(f"{TransactionType.KITTING_CONSUME}_MACHINING", 0)
    )
    
    raw_packaging_weight = weight_totals.get(TransactionType.PACKAGING_IN, 0)
    packaging_weight = max(0, raw_packaging_weight - dedicated_buffer_weight)
    
    polishing_weight = weight_totals.get(TransactionType.POLISHING_IN, 0) - packaging_weight
    
    ready_weight = (
        packaging_weight + 
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

def get_stock_for_all_items():
    """
    Calculates stock levels for all items in a single query pass.
    Returns: dict mapping item_id (int) to stock dict {'casting', 'machining', 'polishing', 'ready'}
    """
    from collections import defaultdict
    
    # Query all transaction aggregates grouped by item, type, and warehouse
    stats = StockTransaction.objects.values('item_id', 'transaction_type', 'from_warehouse__code').annotate(total=Sum('quantity'))
    
    # Query all dedicated buffer packaging quantities grouped by item
    buffer_stats = StockTransaction.objects.filter(
        transaction_type=TransactionType.PACKAGING_IN,
        notes__contains='[DEDICATED BUFFER]'
    ).values('item_id').annotate(total=Sum('quantity'))
    
    buffers = {b['item_id']: (b['total'] or 0) for b in buffer_stats}
    
    totals = defaultdict(lambda: defaultdict(int))
    for s in stats:
        item_id = s['item_id']
        tx_type = s['transaction_type']
        wh_code = s['from_warehouse__code']
        qty = s['total'] or 0
        
        if tx_type == TransactionType.KITTING_CONSUME:
            key = f"{tx_type}_{wh_code}"
            totals[item_id][key] += qty
        else:
            totals[item_id][tx_type] += qty
            
    # Now build the output dictionary for each item
    item_stocks = {}
    
    for item_id, item_totals in totals.items():
        casting_in = item_totals.get(TransactionType.CASTING_ENTRY, 0)
        machining_out = item_totals.get(TransactionType.MACHINING_OUT, 0)
        machining_in = item_totals.get(TransactionType.MACHINING_IN, 0)
        polishing_out = item_totals.get(TransactionType.POLISHING_OUT, 0)
        polishing_in = item_totals.get(TransactionType.POLISHING_IN, 0)
        
        dedicated_buffer_qty = buffers.get(item_id, 0)
        packaging_in = max(0, item_totals.get(TransactionType.PACKAGING_IN, 0) - dedicated_buffer_qty)
        dispatch_out = item_totals.get(TransactionType.DISPATCH_OUT, 0)
        
        kitting_consume_machining = item_totals.get(f"{TransactionType.KITTING_CONSUME}_MACHINING", 0)
        kitting_produce = item_totals.get(TransactionType.KITTING_PRODUCE, 0)
        
        item_stocks[item_id] = {
            'casting': casting_in - machining_out,
            'machining': machining_in - (polishing_out + kitting_consume_machining),
            'polishing': polishing_in - packaging_in,
            'ready': (packaging_in + kitting_produce) - dispatch_out
        }
        
    return item_stocks
