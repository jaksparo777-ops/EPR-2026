from collections import defaultdict
from django.db.models import Sum, Q
from apps.master_data.models import Item
from .models import StockTransaction, TransactionType


def get_all_items_stock(company=None):
    """
    High-performance bulk stock calculation engine.
    Computes stock quantities for ALL items at each stage (casting, machining, polishing, ready)
    in 3 grouped SQL queries instead of hundreds of individual queries.
    
    Returns a dict mapping item_id -> {'casting': int, 'machining': int, 'polishing': int, 'ready': int}
    and item_code -> stock_dict.
    """
    items_qs = Item.objects.all().select_related('client')
    if company:
        if company.id == 1:
            items_qs = items_qs.filter(Q(company=company) | Q(casting_required=True))
        else:
            items_qs = items_qs.filter(company=company)
            
    items = list(items_qs)
    item_map = {item.id: item for item in items}

    # 1. Bulk Specific Item Transaction Totals
    tx_stats = StockTransaction.objects.values(
        'item_id', 'transaction_type', 'from_warehouse__code', 'to_warehouse__code'
    ).annotate(total=Sum('quantity'))

    item_totals = defaultdict(lambda: defaultdict(int))
    item_adjustments = defaultdict(lambda: {'CASTING': 0, 'MACHINING': 0, 'POLISHING': 0, 'READY': 0})

    for s in tx_stats:
        iid = s['item_id']
        tx_type = s['transaction_type']
        from_wh = s['from_warehouse__code']
        to_wh = s['to_warehouse__code']
        qty = s['total'] or 0

        if tx_type == TransactionType.STOCK_ADJUSTMENT:
            if from_wh in item_adjustments[iid]:
                item_adjustments[iid][from_wh] -= qty
            if to_wh in item_adjustments[iid]:
                item_adjustments[iid][to_wh] += qty
        elif tx_type == TransactionType.KITTING_CONSUME:
            key = f"{tx_type}_{from_wh}"
            item_totals[iid][key] += qty
        elif tx_type not in [TransactionType.CASTING_ENTRY, TransactionType.MACHINING_OUT]:
            item_totals[iid][tx_type] += qty

    # 2. Bulk Non-Buffer Packaging In
    non_buffer_pkgs = StockTransaction.objects.filter(
        transaction_type=TransactionType.PACKAGING_IN
    ).exclude(
        notes__contains='[DEDICATED BUFFER]'
    ).values('item_id').annotate(total=Sum('quantity'))
    non_buffer_map = {p['item_id']: (p['total'] or 0) for p in non_buffer_pkgs}

    # 3. Bulk Negative Buffer Consumptions
    buffer_consumptions = StockTransaction.objects.filter(
        transaction_type=TransactionType.PACKAGING_IN,
        notes__contains='[DEDICATED BUFFER]',
        quantity__lt=0
    ).values('item_id').annotate(total=Sum('quantity'))
    buffer_consumption_map = {b['item_id']: -(b['total'] or 0) for b in buffer_consumptions}

    # 4. Cross-company casting and machining aggregations
    # NC casting for OM items:
    om_casting_qs = StockTransaction.objects.filter(
        item__company_id=1,
        transaction_type=TransactionType.CASTING_ENTRY,
        client__name='OM'
    ).values('item__code').annotate(total=Sum('quantity'))
    om_casting_by_code = {c['item__code']: (c['total'] or 0) for c in om_casting_qs}

    # Machining out by item code:
    machining_out_by_code_qs = StockTransaction.objects.filter(
        transaction_type=TransactionType.MACHINING_OUT
    ).values('item__code').annotate(total=Sum('quantity'))
    machining_out_by_code = {m['item__code']: (m['total'] or 0) for m in machining_out_by_code_qs}

    # Standard per-item casting & machining out
    std_casting_qs = StockTransaction.objects.filter(
        transaction_type=TransactionType.CASTING_ENTRY
    ).exclude(client__name='OM').values('item_id').annotate(total=Sum('quantity'))
    std_casting_map = {sc['item_id']: (sc['total'] or 0) for sc in std_casting_qs}

    std_machining_out_qs = StockTransaction.objects.filter(
        transaction_type=TransactionType.MACHINING_OUT
    ).values('item_id').annotate(total=Sum('quantity'))
    std_machining_out_map = {smo['item_id']: (smo['total'] or 0) for smo in std_machining_out_qs}

    results = {}

    for item_id, item in item_map.items():
        is_om = (item.company_id == 2)
        if is_om:
            c_in = om_casting_by_code.get(item.code, 0)
            m_out = machining_out_by_code.get(item.code, 0)
        else:
            c_in = std_casting_map.get(item_id, 0)
            is_om_desig = bool(item.client and item.client.name.strip().upper() == 'OM')
            m_out = 0 if is_om_desig else std_machining_out_map.get(item_id, 0)

        totals = item_totals[item_id]
        adjustments = item_adjustments[item_id]

        m_in = totals.get(TransactionType.MACHINING_IN, 0)
        p_out = totals.get(TransactionType.POLISHING_OUT, 0)
        p_in = totals.get(TransactionType.POLISHING_IN, 0)
        pur_in = totals.get(TransactionType.PURCHASE_ENTRY, 0)

        pkg_in = non_buffer_map.get(item_id, 0) + buffer_consumption_map.get(item_id, 0)
        disp_out = totals.get(TransactionType.DISPATCH_OUT, 0)

        kit_cons_m = totals.get(f"{TransactionType.KITTING_CONSUME}_MACHINING", 0)
        kit_prod = totals.get(TransactionType.KITTING_PRODUCE, 0)

        stock_dict = {
            'casting': ((c_in - m_out) + adjustments['CASTING']) if not item.is_raw_material else 0,
            'machining': (m_in - (p_out + kit_cons_m)) + adjustments['MACHINING'],
            'polishing': (p_in + pur_in - pkg_in) + adjustments['POLISHING'],
            'ready': ((pkg_in + kit_prod) - disp_out) + adjustments['READY']
        }
        results[item_id] = stock_dict
        results[item.code] = stock_dict

    return results

def get_stock_by_item(item):
    """
    Returns a dictionary of stock quantities for a given item at each stage.
    """
    # Determine the company of the item
    is_om = (item.company_id == 2)
    
    # 1. Fetch transaction stats for this specific item ID (for standard stages like machining_in onwards)
    stats_specific = StockTransaction.objects.filter(item=item).values('transaction_type', 'from_warehouse__code', 'to_warehouse__code').annotate(total=Sum('quantity'))
    
    # 2. Fetch cross-company casting/issue stats by item code
    casting_in = 0
    machining_out = 0
    
    if is_om:
        # For OM (Company 2): 
        # casting_in comes from NC's casting entries (Company 1) where client is 'OM'
        casting_in = StockTransaction.objects.filter(
            item__code=item.code,
            item__company_id=1,
            transaction_type=TransactionType.CASTING_ENTRY,
            client__name='OM'
        ).aggregate(total=Sum('quantity'))['total'] or 0
        
        # machining_out comes from NC's machining issues (Company 1) or OM's own machining issues where item code matches
        machining_out = StockTransaction.objects.filter(
            item__code=item.code,
            transaction_type=TransactionType.MACHINING_OUT
        ).aggregate(total=Sum('quantity'))['total'] or 0
    else:
        # For NC (Company 1):
        # casting_in comes from NC's casting entries, excluding client 'OM'
        casting_in = StockTransaction.objects.filter(
            item=item,
            transaction_type=TransactionType.CASTING_ENTRY
        ).exclude(
            client__name='OM'
        ).aggregate(total=Sum('quantity'))['total'] or 0
        
        # machining_out comes from NC's machining issues, excluding those for OM-designated items
        is_om_designated = (item.client and item.client.name.strip().upper() == 'OM')
        if is_om_designated:
            machining_out = 0
        else:
            machining_out = StockTransaction.objects.filter(
                item=item,
                transaction_type=TransactionType.MACHINING_OUT
            ).aggregate(total=Sum('quantity'))['total'] or 0
            
    totals = {}
    adjustments = {
        'CASTING': 0,
        'MACHINING': 0,
        'POLISHING': 0,
        'READY': 0
    }
    
    for s in stats_specific:
        tx_type = s['transaction_type']
        from_wh = s['from_warehouse__code']
        to_wh = s['to_warehouse__code']
        qty = s['total'] or 0
        
        if tx_type == TransactionType.STOCK_ADJUSTMENT:
            if from_wh in adjustments:
                adjustments[from_wh] -= qty
            if to_wh in adjustments:
                adjustments[to_wh] += qty
        elif tx_type == TransactionType.KITTING_CONSUME:
            key = f"{tx_type}_{from_wh}"
            totals[key] = totals.get(key, 0) + qty
        elif tx_type not in [TransactionType.CASTING_ENTRY, TransactionType.MACHINING_OUT]:
            # We already handle casting_entry and machining_out separately above
            totals[tx_type] = totals.get(tx_type, 0) + qty
            
    machining_in = totals.get(TransactionType.MACHINING_IN, 0)
    polishing_out = totals.get(TransactionType.POLISHING_OUT, 0)
    polishing_in = totals.get(TransactionType.POLISHING_IN, 0)
    purchase_in = totals.get(TransactionType.PURCHASE_ENTRY, 0)
    
    # Sum of all non-buffer packaging transactions
    non_buffer_packages = StockTransaction.objects.filter(
        item=item,
        transaction_type=TransactionType.PACKAGING_IN
    ).exclude(
        notes__contains='[DEDICATED BUFFER]'
    ).aggregate(total=Sum('quantity'))['total'] or 0
    
    # Sum of all buffer consumptions (absolute value of negative buffer transactions)
    buffer_consumptions_qty = -(StockTransaction.objects.filter(
        item=item,
        transaction_type=TransactionType.PACKAGING_IN,
        notes__contains='[DEDICATED BUFFER]',
        quantity__lt=0
    ).aggregate(total=Sum('quantity'))['total'] or 0)
    
    packaging_in = non_buffer_packages + buffer_consumptions_qty
    dispatch_out = totals.get(TransactionType.DISPATCH_OUT, 0)
    
    # Bifurcated component consumption
    kitting_consume_machining = totals.get(f"{TransactionType.KITTING_CONSUME}_MACHINING", 0)
    kitting_consume_polishing = totals.get(f"{TransactionType.KITTING_CONSUME}_POLISHING", 0)
    kitting_consume_none = totals.get(f"{TransactionType.KITTING_CONSUME}_None", 0) # Fallback
    
    kitting_produce = totals.get(TransactionType.KITTING_PRODUCE, 0)
    
    return {
        'casting': ((casting_in - machining_out) + adjustments['CASTING']) if not item.is_raw_material else 0,
        'machining': (machining_in - (polishing_out + kitting_consume_machining)) + adjustments['MACHINING'],
        'polishing': (polishing_in + purchase_in - packaging_in) + adjustments['POLISHING'],
        'ready': ((packaging_in + kitting_produce) - dispatch_out) + adjustments['READY']
    }

def get_overall_stock(company=None):
    """
    Returns total stock across all items for each stage. Optionally scoped by company.
    """
    tx_qs = StockTransaction.objects.all()
    buffer_qs = StockTransaction.objects.filter(
        transaction_type=TransactionType.PACKAGING_IN,
        notes__contains='[DEDICATED BUFFER]'
    )
    
    if company:
        from apps.master_data.models import Item
        if company.id == 2: # OM
            om_item_codes = Item.objects.filter(company_id=2).values_list('code', flat=True)
            tx_qs = tx_qs.filter(
                Q(item__company=company) |
                Q(item__company_id=1, transaction_type=TransactionType.CASTING_ENTRY, client__name='OM') |
                Q(item__company_id=1, transaction_type=TransactionType.MACHINING_OUT, item__code__in=om_item_codes)
            )
            buffer_qs = buffer_qs.filter(item__company=company)
        elif company.id == 1: # NC
            tx_qs = tx_qs.filter(item__company=company).exclude(
                Q(transaction_type=TransactionType.CASTING_ENTRY, client__name='OM') |
                Q(transaction_type=TransactionType.MACHINING_OUT, item__client__name='OM')
            )
            buffer_qs = buffer_qs.filter(item__company=company)
        else:
            tx_qs = tx_qs.filter(item__company=company)
            buffer_qs = buffer_qs.filter(item__company=company)

    stats = tx_qs.values('transaction_type', 'from_warehouse__code', 'to_warehouse__code').annotate(
        total_qty=Sum('quantity'), 
        total_weight=Sum('weight')
    )
    
    qty_totals = {}
    weight_totals = {}
    
    adjustments_qty = {
        'CASTING': 0,
        'MACHINING': 0,
        'POLISHING': 0,
        'READY': 0
    }
    adjustments_wt = {
        'CASTING': 0.0,
        'MACHINING': 0.0,
        'POLISHING': 0.0,
        'READY': 0.0
    }
    
    for s in stats:
        tx_type = s['transaction_type']
        from_wh = s['from_warehouse__code']
        to_wh = s['to_warehouse__code']
        qty = s['total_qty'] or 0
        wt = s['total_weight'] or 0
        
        if tx_type == TransactionType.STOCK_ADJUSTMENT:
            if from_wh in adjustments_qty:
                adjustments_qty[from_wh] -= qty
                adjustments_wt[from_wh] -= wt
            if to_wh in adjustments_qty:
                adjustments_qty[to_wh] += qty
                adjustments_wt[to_wh] += wt
        elif tx_type == TransactionType.KITTING_CONSUME:
            key = f"{tx_type}_{from_wh}"
            qty_totals[key] = qty_totals.get(key, 0) + qty
            weight_totals[key] = weight_totals.get(key, 0) + wt
        else:
            qty_totals[tx_type] = qty_totals.get(tx_type, 0) + qty
            weight_totals[tx_type] = weight_totals.get(tx_type, 0) + wt
            
    # Exclude [DEDICATED BUFFER] packaging transactions from the global totals
    # Non-buffer packages
    non_buffer_qs = tx_qs.filter(
        transaction_type=TransactionType.PACKAGING_IN
    ).exclude(
        notes__contains='[DEDICATED BUFFER]'
    ).aggregate(total_qty=Sum('quantity'), total_weight=Sum('weight'))
    
    non_buffer_qty = non_buffer_qs['total_qty'] or 0
    non_buffer_weight = non_buffer_qs['total_weight'] or 0
    
    # Negative buffer consumption transactions (absolute value)
    buffer_consumptions_qs = tx_qs.filter(
        transaction_type=TransactionType.PACKAGING_IN,
        notes__contains='[DEDICATED BUFFER]',
        quantity__lt=0
    ).aggregate(total_qty=Sum('quantity'), total_weight=Sum('weight'))
    
    buffer_consumptions_qty = -(buffer_consumptions_qs['total_qty'] or 0)
    buffer_consumptions_weight = -(buffer_consumptions_qs['total_weight'] or 0.0)
    
    packaging_qty = non_buffer_qty + buffer_consumptions_qty
    packaging_weight = non_buffer_weight + buffer_consumptions_weight

    # Calculate casting quantity and weight only for items that are not raw materials
    casting_txs = tx_qs.exclude(item__is_raw_material=True)
    casting_stats = casting_txs.values('transaction_type').annotate(
        total_qty=Sum('quantity'),
        total_weight=Sum('weight')
    )
    casting_qty_totals = {}
    casting_wt_totals = {}
    for cs in casting_stats:
        casting_qty_totals[cs['transaction_type']] = cs['total_qty'] or 0
        casting_wt_totals[cs['transaction_type']] = cs['total_weight'] or 0.0

    casting_qty = (casting_qty_totals.get(TransactionType.CASTING_ENTRY, 0) - casting_qty_totals.get(TransactionType.MACHINING_OUT, 0)) + adjustments_qty['CASTING']
    
    machining_qty = (qty_totals.get(TransactionType.MACHINING_IN, 0) - (
        qty_totals.get(TransactionType.POLISHING_OUT, 0) + 
        qty_totals.get(f"{TransactionType.KITTING_CONSUME}_MACHINING", 0)
    )) + adjustments_qty['MACHINING']
    
    polishing_qty = (
        qty_totals.get(TransactionType.POLISHING_IN, 0) + 
        qty_totals.get(TransactionType.PURCHASE_ENTRY, 0) - 
        packaging_qty
    ) + adjustments_qty['POLISHING']
    
    ready_qty = (
        (packaging_qty + qty_totals.get(TransactionType.KITTING_PRODUCE, 0)) - qty_totals.get(TransactionType.DISPATCH_OUT, 0)
    ) + adjustments_qty['READY']

    casting_weight = (casting_wt_totals.get(TransactionType.CASTING_ENTRY, 0) - casting_wt_totals.get(TransactionType.MACHINING_OUT, 0)) + adjustments_wt['CASTING']
    
    machining_weight = (weight_totals.get(TransactionType.MACHINING_IN, 0) - (
        weight_totals.get(TransactionType.POLISHING_OUT, 0) + 
        weight_totals.get(f"{TransactionType.KITTING_CONSUME}_MACHINING", 0)
    )) + adjustments_wt['MACHINING']
    
    polishing_weight = (
        weight_totals.get(TransactionType.POLISHING_IN, 0) + 
        weight_totals.get(TransactionType.PURCHASE_ENTRY, 0) - 
        packaging_weight
    ) + adjustments_wt['POLISHING']
    
    ready_weight = (
        (packaging_weight + weight_totals.get(TransactionType.KITTING_PRODUCE, 0)) - weight_totals.get(TransactionType.DISPATCH_OUT, 0)
    ) + adjustments_wt['READY']

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

