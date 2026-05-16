from django.db.models import Sum
from .models import StockTransaction, TransactionType

def get_stock_by_item(item):
    """
    Returns a dictionary of stock quantities for a given item at each stage.
    """
    # Optimized: Use a single query to get all transaction sums for this item
    stats = StockTransaction.objects.filter(item=item).values('transaction_type').annotate(total=Sum('quantity'))
    
    # Convert to a flat dictionary for easy access
    totals = {s['transaction_type']: s['total'] for s in stats}
    
    casting_in = (totals.get(TransactionType.CASTING_ENTRY, 0) or 0)
    machining_out = (totals.get(TransactionType.MACHINING_OUT, 0) or 0)
    machining_in = (totals.get(TransactionType.MACHINING_IN, 0) or 0)
    polishing_out = (totals.get(TransactionType.POLISHING_OUT, 0) or 0)
    polishing_in = (totals.get(TransactionType.POLISHING_IN, 0) or 0)
    packaging_in = (totals.get(TransactionType.PACKAGING_IN, 0) or 0)
    dispatch_out = (totals.get(TransactionType.DISPATCH_OUT, 0) or 0)
    kitting_consume = (totals.get(TransactionType.KITTING_CONSUME, 0) or 0)
    kitting_produce = (totals.get(TransactionType.KITTING_PRODUCE, 0) or 0)
    
    return {
        'casting': casting_in - machining_out,
        'machining': machining_in - polishing_out,
        'polishing': polishing_in - (packaging_in + kitting_consume),
        'ready': (packaging_in + kitting_produce) - dispatch_out
    }

def get_overall_stock():
    """
    Returns total stock across all items for each stage.
    """
    stats = StockTransaction.objects.values('transaction_type').annotate(total_qty=Sum('quantity'), total_weight=Sum('weight'))
    
    qty_totals = {s['transaction_type']: s['total_qty'] for s in stats}
    weight_totals = {s['transaction_type']: s['total_weight'] for s in stats}
    
    def get_sum(mapping, *types):
        return sum(mapping.get(t, 0) or 0 for t in types)

    casting_qty = get_sum(qty_totals, TransactionType.CASTING_ENTRY) - get_sum(qty_totals, TransactionType.MACHINING_OUT)
    machining_qty = get_sum(qty_totals, TransactionType.MACHINING_IN) - get_sum(qty_totals, TransactionType.POLISHING_OUT)
    polishing_qty = get_sum(qty_totals, TransactionType.POLISHING_IN) - get_sum(qty_totals, TransactionType.PACKAGING_IN)
    ready_qty = get_sum(qty_totals, TransactionType.PACKAGING_IN, TransactionType.KITTING_PRODUCE) - get_sum(qty_totals, TransactionType.DISPATCH_OUT)

    casting_weight = get_sum(weight_totals, TransactionType.CASTING_ENTRY) - get_sum(weight_totals, TransactionType.MACHINING_OUT)
    machining_weight = get_sum(weight_totals, TransactionType.MACHINING_IN) - get_sum(weight_totals, TransactionType.POLISHING_OUT)
    polishing_weight = get_sum(weight_totals, TransactionType.POLISHING_IN) - get_sum(weight_totals, TransactionType.PACKAGING_IN, TransactionType.KITTING_CONSUME)
    ready_weight = get_sum(weight_totals, TransactionType.PACKAGING_IN, TransactionType.KITTING_PRODUCE) - get_sum(weight_totals, TransactionType.DISPATCH_OUT)

    return {
        'casting_qty': casting_qty,
        'machining_qty': machining_qty,
        'polishing_qty': polishing_qty,
        'ready_qty': ready_qty,
        'casting_weight': round(casting_weight, 3),
        'machining_weight': round(machining_weight, 3),
        'polishing_weight': round(polishing_weight, 3),
        'ready_weight': round(ready_weight, 3),
    }
