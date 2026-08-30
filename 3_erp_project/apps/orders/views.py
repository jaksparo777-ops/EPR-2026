from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
from .models import SalesOrder, SalesOrderItem, Dispatch, DispatchItem
from django.utils import timezone
from apps.master_data.models import Client, Item
from apps.production.models import StockTransaction, TransactionType

from django.db.models import Sum

def bulk_fetch_order_metrics(orders, company=None):
    """
    Bulk pre-computes dispatched_quantity, ready_stock, and pipeline_quantity for all order items
    in 3 efficient aggregated queries instead of 9,000+ per-item property queries.
    """
    order_ids = [o.id for o in orders]
    if not order_ids:
        return

    # 1. Bulk Dispatched Quantities per (sales_order_id, item_id)
    dispatch_qs = DispatchItem.objects.filter(dispatch__sales_order_id__in=order_ids).values('dispatch__sales_order_id', 'item_id').annotate(total=Sum('quantity'))
    dispatched_map = {(d['dispatch__sales_order_id'], d['item_id']): (d['total'] or 0) for d in dispatch_qs}

    # 2. Bulk Stock Transactions per item_id
    tx_qs = StockTransaction.objects.all()
    if company:
        tx_qs = tx_qs.filter(item__company=company)

    tx_stats = tx_qs.values('item_id', 'transaction_type', 'from_warehouse__code', 'to_warehouse__code').annotate(total=Sum('quantity'))

    casting_in = {}
    machining_out = {}
    machining_in = {}
    polishing_out = {}
    polishing_in = {}
    packaging_in = {}
    dispatch_out = {}
    kitting_produce = {}
    adjustments_ready = {}

    for s in tx_stats:
        iid = s['item_id']
        ttype = s['transaction_type']
        from_wh = s['from_warehouse__code']
        to_wh = s['to_warehouse__code']
        qty = s['total'] or 0

        if ttype == TransactionType.CASTING_ENTRY:
            casting_in[iid] = casting_in.get(iid, 0) + qty
        elif ttype == TransactionType.MACHINING_OUT:
            machining_out[iid] = machining_out.get(iid, 0) + qty
        elif ttype == TransactionType.MACHINING_IN:
            machining_in[iid] = machining_in.get(iid, 0) + qty
        elif ttype == TransactionType.POLISHING_OUT:
            polishing_out[iid] = polishing_out.get(iid, 0) + qty
        elif ttype == TransactionType.POLISHING_IN:
            polishing_in[iid] = polishing_in.get(iid, 0) + qty
        elif ttype == TransactionType.PACKAGING_IN:
            packaging_in[iid] = packaging_in.get(iid, 0) + qty
        elif ttype == TransactionType.DISPATCH_OUT:
            dispatch_out[iid] = dispatch_out.get(iid, 0) + qty
        elif ttype == TransactionType.KITTING_PRODUCE:
            kitting_produce[iid] = kitting_produce.get(iid, 0) + qty
        elif ttype == TransactionType.STOCK_ADJUSTMENT:
            if to_wh == 'READY':
                adjustments_ready[iid] = adjustments_ready.get(iid, 0) + qty
            if from_wh == 'READY':
                adjustments_ready[iid] = adjustments_ready.get(iid, 0) - qty

    for o in orders:
        order_items = list(o.items.all())
        total_needed = 0
        total_ready_for_order = 0
        total_coverage_for_order = 0

        for item in order_items:
            iid = item.item_id
            disp_qty = dispatched_map.get((o.id, iid), 0)
            rem_qty = max(0, item.ordered_quantity - disp_qty)

            pkg_in = packaging_in.get(iid, 0)
            kit_prod = kitting_produce.get(iid, 0)
            disp_o = dispatch_out.get(iid, 0)
            adj_r = adjustments_ready.get(iid, 0)
            item_ready = max(0, (pkg_in + kit_prod - disp_o) + adj_r)

            c_wip = max(0, casting_in.get(iid, 0) - machining_out.get(iid, 0)) if not item.item.is_raw_material else 0
            m_wip = max(0, machining_out.get(iid, 0) - machining_in.get(iid, 0))
            p_wip = max(0, polishing_out.get(iid, 0) - polishing_in.get(iid, 0))
            item_pipeline = c_wip + m_wip + p_wip

            item.cached_dispatched_quantity = disp_qty
            item.cached_remaining_quantity = rem_qty
            item.cached_ready_stock = item_ready
            item.cached_pipeline_quantity = item_pipeline

            total_needed += rem_qty
            total_ready_for_order += min(item_ready, rem_qty)
            total_coverage_for_order += min(item_ready + item_pipeline, rem_qty)

        if total_needed == 0:
            o.cached_readiness_percentage = 100
            o.cached_coverage_percentage = 100
        else:
            o.cached_readiness_percentage = min(100, int((total_ready_for_order / total_needed) * 100))
            o.cached_coverage_percentage = min(100, int((total_coverage_for_order / total_needed) * 100))

@login_required
def orders_board(request):
    orders = SalesOrder.objects.prefetch_related('items', 'items__item').select_related('client').all()
    if request.company:
        orders = orders.filter(client__company=request.company)
    
    if request.company:
        clients = Client.objects.filter(company=request.company)
        items = Item.objects.filter(company=request.company)
        if request.company.id == 1:
            items = items.filter(casting_required=True)
        recent_orders = SalesOrder.objects.prefetch_related('items', 'items__item').select_related('client').filter(client__company=request.company).order_by('-id')[:10]
        dispatches = Dispatch.objects.prefetch_related('items', 'items__item').select_related('client', 'sales_order').filter(client__company=request.company).order_by('-id')[:20]
    else:
        clients = Client.objects.all()
        items = Item.objects.all()
        recent_orders = SalesOrder.objects.prefetch_related('items', 'items__item').select_related('client').order_by('-id')[:10]
        dispatches = Dispatch.objects.prefetch_related('items', 'items__item').select_related('client', 'sales_order').order_by('-id')[:20]

    # Bulk pre-fetch metrics for both active orders & recent_orders in 3 queries
    bulk_fetch_order_metrics(list(orders) + list(recent_orders), company=request.company)

    # Sort orders: URGENT first, then OPEN/PARTIAL first, then by promised_date
    orders = sorted(
        orders,
        key=lambda x: (
            0 if x.priority == 'URGENT' else 1,
            0 if x.status in [SalesOrder.OrderStatus.OPEN, SalesOrder.OrderStatus.PARTIAL] else 1,
            x.promised_date
        )
    )
    
    # Calculate telemetry metrics
    import datetime
    today = datetime.date.today()
    active_count = sum(1 for o in orders if o.status in [SalesOrder.OrderStatus.OPEN, SalesOrder.OrderStatus.PARTIAL])
    ready_count = sum(1 for o in orders if o.status == SalesOrder.OrderStatus.OPEN and o.readiness_percentage >= 100)
    wip_count = sum(1 for o in orders if o.status == SalesOrder.OrderStatus.OPEN and o.readiness_percentage < 100 and o.coverage_percentage > 0)
    completed_count = sum(1 for o in orders if o.status == SalesOrder.OrderStatus.COMPLETED)

    for o in orders:
        o.days_left = (o.promised_date - today).days
        o.abs_days_left = abs(o.days_left)

    import json
    client_past_items = {}
    client_item_styles = {}
    
    so_items = SalesOrderItem.objects.select_related('sales_order').order_by('sales_order_id')
    for soi in so_items:
        c_id = soi.sales_order.client_id
        item_id = soi.item_id
        remarks = soi.remarks or ""
        
        if c_id not in client_past_items:
            client_past_items[c_id] = []
        if item_id not in client_past_items[c_id]:
            client_past_items[c_id].append(item_id)
            
        if "(BOX)" in remarks:
            client_item_styles[f"{c_id}_{item_id}"] = 'BOX'
        elif "(REG)" in remarks:
            client_item_styles[f"{c_id}_{item_id}"] = 'REG'

    client_past_items_json = json.dumps(client_past_items)
    client_item_styles_json = json.dumps(client_item_styles)

    return render(request, 'orders_board.html', {
        'orders': orders,
        'clients': clients,
        'items': items,
        'recent_orders': recent_orders,
        'dispatches': dispatches,
        'client_past_items_json': client_past_items_json,
        'client_item_styles_json': client_item_styles_json,
        'kpi': {
            'active': active_count,
            'ready': ready_count,
            'wip': wip_count,
            'completed': completed_count
        }
    })


@login_required
def order_details_api(request, order_id):
    order = get_object_or_404(SalesOrder.objects.prefetch_related('items', 'items__item').select_related('client'), id=order_id)
    bulk_fetch_order_metrics([order], company=getattr(request, 'company', None))
    items_data = []
    from apps.production.models import Carton
    for item in order.items.all():
        # Get ready cartons specifically containing this item
        cartons_qs = Carton.objects.filter(status='READY', items__item=item.item)
        
        # Calculate ready stock counts by carton type
        reg_cartons_count = 0
        box_cartons_count = 0
        reg_cartons_pieces = 0
        box_cartons_pieces = 0
        
        for c in cartons_qs:
            # Let's see how much of this item is inside the carton
            ci = c.items.filter(item=item.item).first()
            if ci:
                is_box = "BOX" in (c.carton_label or '').upper() or "LOT" in (c.carton_label or '').upper()
                if is_box:
                    box_cartons_count += 1
                    box_cartons_pieces += ci.quantity
                else:
                    reg_cartons_count += 1
                    reg_cartons_pieces += ci.quantity
                    
        # Total ready pieces from physical Carton models
        total_cartons_pieces = reg_cartons_pieces + box_cartons_pieces
        total_ready_pcs = item.ready_stock
        
        # Loose pieces = total ready stock - carton-allocated pieces
        loose_pieces = max(0, total_ready_pcs - total_cartons_pieces)

        # Calculate loose buffer stock available for this item
        from apps.production import services
        stock_stats = services.get_stock_by_item(item.item)
        if item.item.item_type == 'SET':
            from apps.master_data.models import ItemComposition
            comps = ItemComposition.objects.filter(parent_item=item.item)
            if comps.exists():
                max_sets = 999999
                for comp in comps:
                    comp_stats = services.get_stock_by_item(comp.component_item)
                    c_avail = comp_stats.get('polishing', 0)
                    can_make = c_avail // comp.quantity
                    if can_make < max_sets:
                        max_sets = can_make
                buffer_stock = max_sets
            else:
                buffer_stock = 0
        else:
            buffer_stock = stock_stats.get('polishing', 0)

        items_data.append({
            'id': item.id,
            'item_id': item.item.id,
            'item_code': item.item.code,
            'item_name': item.item.name,
            'ordered_qty': item.ordered_quantity,
            'dispatched_qty': item.dispatched_quantity,
            'remaining_qty': item.remaining_quantity,
            'ready_stock': total_ready_pcs,
            'buffer_stock': buffer_stock,
            'pipeline_qty': item.pipeline_quantity,
            'rate': item.rate_per_piece,
            'remarks': item.remarks or '',
            'stock_details': {
                'reg_cartons_count': reg_cartons_count,
                'reg_cartons_pieces': reg_cartons_pieces,
                'box_cartons_count': box_cartons_count,
                'box_cartons_pieces': box_cartons_pieces,
                'loose_pieces': loose_pieces
            }
        })
    
    return JsonResponse({
        'id': order.id,
        'order_number': order.order_number,
        'client_id': order.client.id,
        'client_name': order.client.name,
        'packing_preference': order.client.packing_preference,
        'external_po_number': order.external_po_number,
        'order_date': order.order_date.strftime('%Y-%m-%d'),
        'promised_date': order.promised_date.strftime('%Y-%m-%d'),
        'priority': order.priority,
        'status': order.get_status_display(),
        'status_code': order.status,
        'notes': order.notes or '',
        'readiness_percentage': order.readiness_percentage,
        'coverage_percentage': order.coverage_percentage,
        'items': items_data
    })

@login_required
@transaction.atomic
def dispatch_order(request, order_id):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid request method.'}, status=400)
    
    order = get_object_or_404(SalesOrder, id=order_id)
    
    # Check if this order is already completed
    if order.status == SalesOrder.OrderStatus.COMPLETED:
        return JsonResponse({'success': False, 'error': 'This order is already completed.'}, status=400)
        
    dispatch_type = request.POST.get('dispatch_type', 'partial') # 'full' or 'partial'
    notes = request.POST.get('notes', '')
    
    dispatch_items_data = []
    
    if dispatch_type == 'full':
        # Dispatch the remaining needed quantity for all items, capped by ready stock
        for item in order.items.all():
            qty = min(item.remaining_quantity, item.ready_stock)
            if qty > 0:
                dispatch_items_data.append((item.item, qty))
    else:
        # Partial dispatch with custom quantities from POST
        for item in order.items.all():
            qty_str = request.POST.get(f'qty_{item.id}', '0')
            try:
                qty = int(qty_str)
            except ValueError:
                qty = 0
            if qty > item.remaining_quantity:
                return JsonResponse({'success': False, 'error': f'Cannot dispatch more than remaining needed quantity ({item.remaining_quantity}) for item {item.item.name}.'}, status=400)
            if qty > item.ready_stock:
                return JsonResponse({'success': False, 'error': f'Cannot dispatch more than available ready stock ({item.ready_stock}) for item {item.item.name}.'}, status=400)
            if qty > 0:
                dispatch_items_data.append((item.item, qty))
                
    if not dispatch_items_data:
        return JsonResponse({'success': False, 'error': 'No items to dispatch or insufficient ready stock.'}, status=400)
        
    from apps.production.models import Carton, CartonItem
    
    # Create the Dispatch record
    dispatch = Dispatch.objects.create(
        sales_order=order,
        client=order.client,
        notes=notes
    )
    
    # Process each requested item
    for db_item, qty in dispatch_items_data:
        weight = qty * float(db_item.machining_weight or 0.0)
        
        # Symmetrically create DispatchItem record
        DispatchItem.objects.create(
            dispatch=dispatch,
            item=db_item,
            quantity=qty,
            weight=weight
        )
        
        # Intelligent carton deduction strategy according to Client preferences
        pref = order.client.packing_preference
        remaining_to_deduct = qty
        
        # 1. Box Lot cartons matching item
        box_cartons = list(Carton.objects.filter(status='READY', items__item=db_item).order_by('created_at'))
        # Filter for actual box labels
        box_cartons = [c for c in box_cartons if "BOX" in (c.carton_label or '').upper() or "LOT" in (c.carton_label or '').upper()]
        
        # 2. Regular cartons matching item
        reg_cartons = list(Carton.objects.filter(status='READY', items__item=db_item).order_by('created_at'))
        reg_cartons = [c for c in reg_cartons if c not in box_cartons]
        
        # Prioritize queues based on Client Preference
        primary_queue = []
        secondary_queue = []
        
        if pref == 'BOX_PREF':
            primary_queue = box_cartons
            secondary_queue = reg_cartons
        elif pref == 'REG_PREF':
            primary_queue = reg_cartons
            secondary_queue = box_cartons
        elif pref == 'BOX_STRICT':
            primary_queue = box_cartons
            secondary_queue = []  # No fallback allowed
        elif pref == 'REG_STRICT':
            primary_queue = reg_cartons
            secondary_queue = []  # No fallback allowed
        else:  # ANY / flexible
            # Fallback to whatever carton type we have the most of or first available
            primary_queue = box_cartons + reg_cartons
            secondary_queue = []
            
        # Helper logic to deduct cartons from chosen queue
        def deduct_from_queue(queue):
            nonlocal remaining_to_deduct
            for carton in queue:
                if remaining_to_deduct <= 0:
                    break
                ci = carton.items.filter(item=db_item).first()
                if ci and ci.quantity <= remaining_to_deduct:
                    # Mark entire carton as dispatched cleanly!
                    carton.status = Carton.CartonStatus.DISPATCHED
                    carton.client = order.client
                    carton.dispatched_at = timezone.now()
                    carton.save()
                    remaining_to_deduct -= ci.quantity
                    
        # Apply primary queue then secondary queue
        deduct_from_queue(primary_queue)
        deduct_from_queue(secondary_queue)
        
        # Create a single transaction log representing this item's dispatch
        StockTransaction.objects.create(
            item=db_item,
            transaction_type=TransactionType.DISPATCH_OUT,
            client=order.client,
            quantity=qty,
            weight=weight,
            notes=f"Dispatched {qty} pcs for PO {order.external_po_number} via {dispatch.dispatch_number} (Intelligent Pref Fulfill: {pref})"
        )

        # Inter-company stock transfer trigger: NC -> OM
        if order.client.name.strip().upper() == 'OM':
            from apps.master_data.models import LegalEntity, Warehouse, Item
            om_company = LegalEntity.objects.filter(id=2).first() or LegalEntity.objects.filter(name__icontains='OM').first()
            if om_company:
                om_item = Item.objects.filter(company=om_company, code=db_item.code).first()
                om_warehouse = Warehouse.objects.filter(company=om_company, code='CASTING').first()
                if om_item and om_warehouse:
                    StockTransaction.objects.create(
                        item=om_item,
                        transaction_type=TransactionType.CASTING_ENTRY,
                        to_warehouse=om_warehouse,
                        quantity=qty,
                        weight=weight,
                        notes=f"Auto-received raw casting stock from NC Dispatch {dispatch.dispatch_number} (Item: {db_item.code})"
                    )
        
    # Recalculate status of the SalesOrder
    total_remaining = sum(item.remaining_quantity for item in order.items.all())
    if total_remaining == 0:
        order.status = SalesOrder.OrderStatus.COMPLETED
    else:
        order.status = SalesOrder.OrderStatus.PARTIAL
    order.save()
    
    return JsonResponse({
        'success': True,
        'dispatch_number': dispatch.dispatch_number,
        'message': f'Successfully created dispatch {dispatch.dispatch_number}.'
    })

@login_required
@transaction.atomic
def create_order_view(request):
    if request.method == 'POST':
        client_id = request.POST.get('client')
        external_po_number = request.POST.get('external_po_number')
        promised_date = request.POST.get('promised_date')
        priority = request.POST.get('priority', 'NORMAL')
        notes = request.POST.get('notes', '')
        po_id = request.POST.get('po_id')

        if not client_id:
            messages.error(request, "Client is required.")
            return redirect('/orders/?tab=create')

        if not promised_date or not promised_date.strip():
            import datetime
            promised_date = (datetime.date.today() + datetime.timedelta(days=10)).strftime('%Y-%m-%d')


        client = get_object_or_404(Client, id=client_id)

        if po_id:
            order = get_object_or_404(SalesOrder, id=po_id)
        else:
            order = None

        # Parse dynamic item rows
        item_ids = request.POST.getlist('item_id[]')
        quantities = request.POST.getlist('quantity[]')
        remarks_list = request.POST.getlist('remarks[]')

        # Perform quantities verification against dispatched counts first
        if order:
            dispatched_map = {item.item.id: item.dispatched_quantity for item in order.items.all()}
            for i in range(len(item_ids)):
                if not item_ids[i]:
                    continue
                try:
                    item_id = int(item_ids[i])
                    quantity = int(quantities[i])
                except (ValueError, IndexError):
                    continue
                
                dispatched_qty = dispatched_map.get(item_id, 0)
                if quantity < dispatched_qty:
                    item_obj = get_object_or_404(Item, id=item_id)
                    messages.error(request, f"Cannot reduce ordered quantity below dispatched quantity ({dispatched_qty} pcs) for item {item_obj.code}.")
                    return redirect('/orders/?tab=create')

        # Create or update SalesOrder
        if order:
            order.client = client
            order.external_po_number = external_po_number
            order.promised_date = promised_date
            order.priority = priority
            order.notes = notes
            order.save()
            
            # Delete old items
            order.items.all().delete()
        else:
            order = SalesOrder.objects.create(
                client=client,
                external_po_number=external_po_number,
                promised_date=promised_date,
                priority=priority,
                notes=notes
            )

        created_items = 0
        for i in range(len(item_ids)):
            if not item_ids[i]:
                continue
            try:
                item_id = int(item_ids[i])
                quantity = int(quantities[i])
                remarks = remarks_list[i] if i < len(remarks_list) else ''
            except (ValueError, IndexError):
                continue

            if quantity > 0:
                item = get_object_or_404(Item, id=item_id)
                SalesOrderItem.objects.create(
                    sales_order=order,
                    item=item,
                    ordered_quantity=quantity,
                    rate_per_piece=0.0,
                    remarks=remarks
                )
                created_items += 1

        if created_items == 0:
            if not po_id:
                order.delete()
            messages.error(request, "You must add at least one item with quantity greater than 0.")
            return redirect('/orders/?tab=create')

        if po_id:
            messages.success(request, f"Successfully updated Customer PO {order.order_number} for {client.name}.")
        else:
            messages.success(request, f"Successfully created Customer PO {order.order_number} for {client.name}.")
        return redirect('orders_board')

    # GET Request
    return redirect('/orders/?tab=create')


@login_required
def delete_order(request, order_id):
    if not request.user.is_staff:
        messages.error(request, "Permission denied.")
        return redirect('orders_board')
        
    order = get_object_or_404(SalesOrder, id=order_id)
    if order.dispatches.exists():
        messages.error(request, "Cannot delete PO with active dispatch history.")
        return redirect('orders_board')
        
    order_num = order.order_number
    # Cascade delete items
    order.items.all().delete()
    order.delete()
    messages.success(request, f"Customer PO {order_num} deleted successfully.")
    return redirect('orders_board')
