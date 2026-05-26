import json
import re
from django.contrib import messages
from django.shortcuts import render, redirect
from django.urls import reverse
from django.db.models import Sum
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from core.security import require_role

from apps.products.models import Client, Item, Warehouse, TransactionType
from apps.production.models import StockTransaction
from apps.logistics.models import Carton, CartonItem
from apps.production import services


@login_required
@require_role(['Logistics Supervisor', 'System Admin'])
def packaging_view(request):
    def get_polishing_entry_remaining_qty(entry):
        packed_qty = StockTransaction.objects.filter(
            transaction_type=TransactionType.PACKAGING_IN,
            notes__contains=f"PACKED #{entry.id}"
        ).aggregate(total=Sum('quantity'))['total'] or 0
        remaining_qty = entry.quantity - packed_qty - (entry.rejection_quantity or 0)
        return max(0, remaining_qty)

    items = Item.objects.all()

    # Optimize N+1 queries by using bulk stock getter
    bulk_stocks = services.get_stock_for_all_items()
    piece_stock = {}
    for item in items:
        item_stock = bulk_stocks.get(item.id, {'polishing': 0})
        piece_stock[item.id] = item_stock.get('polishing', 0)
        item.available_polishing = piece_stock[item.id]
        
    # Batch load all BOM compositions to avoid N+1 queries
    from apps.products.models import ItemComposition
    from collections import defaultdict
    all_comps = defaultdict(list)
    for comp in ItemComposition.objects.all().select_related('component_item'):
        all_comps[comp.parent_item_id].append(comp)

    for item in items:
        if item.item_type == 'SET':
            comps = all_comps.get(item.id, [])
            if comps:
                max_sets = 999999
                for comp in comps:
                    c_avail = piece_stock.get(comp.component_item.id, 0)
                    can_make = c_avail // comp.quantity
                    if can_make < max_sets:
                        max_sets = can_make
                item.available_polishing = max_sets
            else:
                item.available_polishing = 0
        else:
            item.available_polishing = piece_stock[item.id]

    # Separate Single and Set items for select menu filters in JS
    single_items = items.filter(item_type='REGULAR')
    set_items = items.filter(item_type='SET')

    # =====================================
    # PACKAGING QUEUE
    # =====================================
    packaging_queue = []

    polishing_in_entries = StockTransaction.objects.filter(
        transaction_type=TransactionType.POLISHING_IN
    ).order_by("-created_at")

    for entry in polishing_in_entries:
        remaining_qty = get_polishing_entry_remaining_qty(entry)
        if remaining_qty > 0:
            orig_qty = entry.quantity
            orig_wt = entry.weight
            entry.quantity = remaining_qty
            entry.weight = round((remaining_qty / orig_qty) * orig_wt, 3) if orig_qty > 0 else 0.0
            packaging_queue.append(entry)

    # =====================================
    # PACK NOW BUTTON (GET Request Shortcut)
    # =====================================
    pack_id = request.GET.get("pack")

    # =====================================
    # DELETE TRANSACTION / RECEIPT
    # =====================================
    delete_id = request.GET.get("delete_id")
    if delete_id:
        try:
            carton = Carton.objects.get(id=delete_id)
            associated_txs = StockTransaction.objects.filter(notes__contains=f"[Carton #{carton.id}]")
            for tx in associated_txs:
                StockTransaction.objects.filter(notes__contains=f"packaging ID: #{tx.id}").delete()
                tx.delete()
            carton.delete()
            messages.success(request, "Carton packaging log deleted successfully.")
        except Carton.DoesNotExist:
            messages.error(request, "Selected carton log could not be found.")
        return redirect("packaging")

    # =====================================
    # DELETE SPARE TRANSACTION
    # =====================================
    delete_spare_id = request.GET.get("delete_spare_id")
    if delete_spare_id:
        try:
            tx = StockTransaction.objects.get(
                id=delete_spare_id,
                transaction_type=TransactionType.PACKAGING_IN,
                notes__contains="[DEDICATED BUFFER]"
            )
            tx.delete()
            messages.success(request, "Spare stock declaration deleted successfully. Quantity restored to Packaging Queue.")
        except StockTransaction.DoesNotExist:
            messages.error(request, "Selected spare stock transaction could not be found.")
        return redirect("packaging")

    # =====================================
    # PACK NOW BUTTON (GET Request Shortcut)
    # =====================================
    if pack_id:
        try:
            polishing_entry = StockTransaction.objects.get(
                id=pack_id,
                transaction_type=TransactionType.POLISHING_IN
            )

            remaining_qty = get_polishing_entry_remaining_qty(polishing_entry)

            if remaining_qty > 0:
                qty_to_pack = remaining_qty
                weight_to_pack = round((qty_to_pack / polishing_entry.quantity) * polishing_entry.weight, 3) if polishing_entry.quantity > 0 else 0.0

                # Determine packaging type automatically based on quantity for PACK NOW
                item = polishing_entry.item
                packaging_type = "regular"
                if item.lot_with_box and qty_to_pack % item.lot_with_box == 0:
                    packaging_type = "box"
                elif item.lot_size and qty_to_pack % item.lot_size == 0:
                    packaging_type = "regular"
                elif item.lot_with_box and item.lot_size:
                    if qty_to_pack % item.lot_with_box < qty_to_pack % item.lot_size:
                        packaging_type = "box"
                
                suffix = "BOX" if packaging_type == "box" else "REG"
                clean_code = re.sub(r'[^a-zA-Z0-9]', '', item.code).upper()
                label_val = f"{clean_code}-{suffix}"

                # Create Carton first
                carton = Carton.objects.create(
                    carton_type='SET' if item.item_type == 'SET' else 'SINGLE',
                    carton_label=label_val,
                    total_quantity=qty_to_pack,
                    total_weight=weight_to_pack,
                    cleaning=True, labeling=True, packing=True,
                    status='READY'
                )
                
                # Create CartonItem
                CartonItem.objects.create(
                    carton=carton,
                    item=polishing_entry.item,
                    quantity=qty_to_pack,
                    weight=weight_to_pack
                )

                # Symmetrically create the transaction
                new_tx = StockTransaction.objects.create(
                    transaction_type=TransactionType.PACKAGING_IN,
                    item=polishing_entry.item,
                    quantity=qty_to_pack,
                    weight=weight_to_pack,
                    notes=f"PACKED #{polishing_entry.id} [Cleaning, Labeling, Packing] [Carton #{carton.id}]"
                )
                
                messages.success(
                    request,
                    f"Successfully packed {qty_to_pack} pcs into Carton {carton.carton_number}!"
                )
            else:
                messages.info(
                    request,
                    "This polish entry has already been fully packed."
                )
        except StockTransaction.DoesNotExist:
            messages.error(
                request,
                "Selected polishing entry could not be found."
            )
        return redirect("packaging")

    # =====================================
    # TO BUFFER SHORTCUT (GET Request)
    # =====================================
    to_buffer_id = request.GET.get("to_buffer")
    if to_buffer_id:
        try:
            polishing_entry = StockTransaction.objects.get(
                id=to_buffer_id,
                transaction_type=TransactionType.POLISHING_IN
            )
            remaining_qty = get_polishing_entry_remaining_qty(polishing_entry)
            
            qty_to_move_str = request.GET.get("qty")
            qty_to_move = int(qty_to_move_str) if qty_to_move_str else remaining_qty
            qty_to_move = min(qty_to_move, remaining_qty)
            
            if qty_to_move > 0:
                weight_to_move = round((qty_to_move / polishing_entry.quantity) * polishing_entry.weight, 3) if polishing_entry.quantity > 0 else 0.0
                
                StockTransaction.objects.create(
                    transaction_type=TransactionType.PACKAGING_IN,
                    item=polishing_entry.item,
                    quantity=qty_to_move,
                    weight=weight_to_move,
                    notes=f"PACKED #{polishing_entry.id} [DEDICATED BUFFER] Kept loose in warehouse"
                )
                
                messages.success(
                    request,
                    f"Successfully moved {qty_to_move} pcs of {polishing_entry.item.code} directly to Loose Buffer Stock!"
                )
            else:
                messages.info(
                    request,
                    "This polish entry has no remaining pending pieces."
                )
        except StockTransaction.DoesNotExist:
            messages.error(
                request,
                "Selected polishing entry could not be found."
            )
        return redirect("packaging")

    # =====================================
    # POST FORM SUBMISSION HANDLER
    # =====================================
    if request.method == "POST":
        edit_id = request.POST.get("edit_id")
        pack_type = request.POST.get("pack_type", "single")
        cleaning = request.POST.get("cleaning") == "YES"
        labeling = request.POST.get("labeling") == "YES"
        packing = request.POST.get("packing") == "YES"
        rejections = int(request.POST.get("rejections") or 0)
        replace_from_buffer = request.POST.get("replace_from_buffer") == "YES"
        
        component_rejections_raw = request.POST.get("component_rejections")
        component_rejections = {}
        if component_rejections_raw:
            try:
                component_rejections = json.loads(component_rejections_raw)
            except Exception:
                pass
                
        if component_rejections:
            total_comp_rejections = sum(int(q) for q in component_rejections.values() if q)
            if total_comp_rejections > 0:
                rejections = total_comp_rejections
        
        # Build process steps suffix
        steps_list = []
        if cleaning: steps_list.append("Cleaning")
        if labeling: steps_list.append("Labeling")
        if packing: steps_list.append("Packing")
        steps_str = f" [{', '.join(steps_list)}]" if steps_list else ""
        
        if pack_type in ["single", "set"]:
            item_id = request.POST.get("item")
            quantity = int(request.POST.get("quantity") or 0)
            weight = float(request.POST.get("weight") or 0.0)
            packaging_type = request.POST.get("packaging_type", "regular")
            
            if item_id and quantity > 0:
                item = Item.objects.get(id=item_id)
                
                suffix = "BOX" if packaging_type == "box" else "REG"
                clean_code = re.sub(r'[^a-zA-Z0-9]', '', item.code).upper()
                label_val = f"{clean_code}-{suffix}"
                
                # If editing, retrieve the Carton. Symmetrically clear its previous entries first.
                if edit_id:
                    try:
                        carton = Carton.objects.get(id=edit_id)
                        # Delete old StockTransactions associated with this Carton
                        associated_txs = StockTransaction.objects.filter(notes__contains=f"[Carton #{carton.id}]")
                        for tx in associated_txs:
                            StockTransaction.objects.filter(notes__contains=f"packaging ID: #{tx.id}").delete()
                            tx.delete()
                        carton.items.all().delete()
                        
                        # Update Carton details
                        carton.carton_type = 'SET' if pack_type == 'set' else 'SINGLE'
                        carton.carton_label = label_val
                        carton.cleaning = cleaning
                        carton.labeling = labeling
                        carton.packing = packing
                        carton.total_quantity = quantity
                        carton.total_weight = weight
                        carton.save()
                    except Carton.DoesNotExist:
                        messages.error(request, "Selected carton log not found.")
                        return redirect("packaging")
                else:
                    # Create a new Carton
                    carton = Carton.objects.create(
                        carton_type='SET' if pack_type == 'set' else 'SINGLE',
                        carton_label=label_val,
                        cleaning=cleaning,
                        labeling=labeling,
                        packing=packing,
                        total_quantity=quantity,
                        total_weight=weight,
                        status='READY'
                    )
                
                # Create CartonItem
                CartonItem.objects.create(
                    carton=carton,
                    item=item,
                    quantity=quantity,
                    weight=weight
                )
                
                # Perform smart FIFO queue consumption of outstanding polishing entries
                outstanding = []
                polishing_in_entries = StockTransaction.objects.filter(
                    item=item,
                    transaction_type=TransactionType.POLISHING_IN
                ).order_by("created_at")
                
                for entry in polishing_in_entries:
                    entry_remaining = get_polishing_entry_remaining_qty(entry)
                    if entry_remaining > 0:
                        outstanding.append((entry, entry_remaining))
                
                # Apply rejections if not replaced from buffer
                if rejections > 0 and not replace_from_buffer:
                    remaining_rej = rejections
                    for entry, entry_remaining in outstanding:
                        if remaining_rej <= 0:
                            break
                        deduct_qty = min(entry_remaining, remaining_rej)
                        entry.rejection_quantity = (entry.rejection_quantity or 0) + deduct_qty
                        entry.save()
                        remaining_rej -= deduct_qty
 
                # Component-level replacements from buffer for SET items
                if item.item_type == "SET" and replace_from_buffer and component_rejections:
                    for comp_id_str, qty in component_rejections.items():
                        qty = int(qty)
                        if qty > 0:
                            try:
                                comp_item = Item.objects.get(id=comp_id_str)
                                comp_wt = round(qty * (comp_item.machining_weight or 0.0), 3)
                                StockTransaction.objects.create(
                                    transaction_type=TransactionType.PACKAGING_IN,
                                    item=comp_item,
                                    quantity=qty,
                                    weight=comp_wt,
                                    notes=f"[DEDICATED BUFFER CONSUMPTION] Replaced defective {comp_item.code} in Set Carton #{carton.id}"
                                )
                            except Item.DoesNotExist:
                                pass

                remaining_to_pack = quantity
                is_first_tx = True
                for entry, entry_remaining in outstanding:
                    if remaining_to_pack <= 0:
                        break
                    
                    # Fetch fresh entry details (in case rejections reduced it)
                    entry_remaining = get_polishing_entry_remaining_qty(entry)
                    if entry_remaining <= 0:
                        continue
                    
                    pack_qty = min(entry_remaining, remaining_to_pack)
                    pack_wt = round((pack_qty / entry.quantity) * entry.weight, 3) if entry.quantity > 0 else 0.0
                    
                    notes_suffix = ""
                    tx_rejections = 0
                    if is_first_tx and rejections > 0:
                        is_first_tx = False
                        if replace_from_buffer:
                            if item.item_type == "SET":
                                comp_details = ", ".join(f"{qty}x {Item.objects.get(id=cid).code}" for cid, qty in component_rejections.items() if int(qty) > 0)
                                notes_suffix = f" (including component rejections replaced from buffer: {comp_details})"
                            else:
                                tx_rejections = rejections
                                notes_suffix = f" (including {rejections} rejections replaced from loose buffer)"
                        else:
                            notes_suffix = f" ({rejections} rejections deducted from jobworker)"
                    
                    new_tx = StockTransaction.objects.create(
                        transaction_type=TransactionType.PACKAGING_IN,
                        item=item,
                        quantity=pack_qty,
                        weight=pack_wt,
                        rejection_quantity=tx_rejections,
                        notes=f"PACKED #{entry.id}{steps_str} [Carton #{carton.id}]{notes_suffix}"
                    )
                    
                    remaining_to_pack -= pack_qty
                
                # Record any remaining quantity as standard manual packaging
                if remaining_to_pack > 0:
                    rem_wt = max(0.0, weight - (quantity - remaining_to_pack) * (item.machining_weight or 0.0))
                    new_tx = StockTransaction.objects.create(
                        transaction_type=TransactionType.PACKAGING_IN,
                        item=item,
                        quantity=remaining_to_pack,
                        weight=round(rem_wt, 3),
                        notes=f"Manual Packaging{steps_str} [Carton #{carton.id}]"
                    )

                messages.success(request, f"Successfully packed {quantity} pcs of {item.name} into Carton {carton.carton_number}!")
            else:
                messages.error(request, "Please select an item and enter a valid quantity.")
                
        elif pack_type == "mixed":
            carton_label = request.POST.get("carton_label", "Mixed Carton")
            item_ids = request.POST.getlist("item[]")
            quantities = request.POST.getlist("quantity[]")
            weights = request.POST.getlist("weight[]")
            
            # If editing, retrieve the Carton. Symmetrically clear its previous entries first.
            if edit_id:
                try:
                    carton = Carton.objects.get(id=edit_id)
                    # Delete old StockTransactions associated with this Carton
                    associated_txs = StockTransaction.objects.filter(notes__contains=f"[Carton #{carton.id}]")
                    for tx in associated_txs:
                        StockTransaction.objects.filter(notes__contains=f"packaging ID: #{tx.id}").delete()
                        tx.delete()
                    carton.items.all().delete()
                    
                    carton.carton_type = 'MIXED'
                    carton.carton_label = carton_label
                    carton.cleaning = cleaning
                    carton.labeling = labeling
                    carton.packing = packing
                    carton.save()
                except Carton.DoesNotExist:
                    messages.error(request, "Selected carton log not found.")
                    return redirect("packaging")
            else:
                # Create a brand new Mixed Carton
                carton = Carton.objects.create(
                    carton_type='MIXED',
                    carton_label=carton_label,
                    cleaning=cleaning,
                    labeling=labeling,
                    packing=packing,
                    status='READY'
                )
            
            packed_items_count = 0
            total_qty = 0
            total_wt = 0.0
            
            for idx, item_id in enumerate(item_ids):
                if not item_id:
                    continue
                qty = int(quantities[idx] or 0)
                wt = float(weights[idx] or 0.0)
                
                if qty > 0:
                    item = Item.objects.get(id=item_id)
                    total_qty += qty
                    total_wt += wt
                    
                    # Create CartonItem
                    CartonItem.objects.create(
                        carton=carton,
                        item=item,
                        quantity=qty,
                        weight=wt
                    )
                    
                    # FIFO queue consumption
                    outstanding = []
                    consume_queue_ids = request.POST.get("consume_queue_ids", "")
                    selected_tx_ids = [int(x) for x in consume_queue_ids.split(",") if x.strip()]
                    
                    if selected_tx_ids:
                        polishing_in_entries = StockTransaction.objects.filter(
                            id__in=selected_tx_ids,
                            item=item,
                            transaction_type=TransactionType.POLISHING_IN
                        ).order_by("created_at")
                    else:
                        polishing_in_entries = StockTransaction.objects.filter(
                            item=item,
                            transaction_type=TransactionType.POLISHING_IN
                        ).order_by("created_at")
                    
                    for entry in polishing_in_entries:
                        entry_remaining = get_polishing_entry_remaining_qty(entry)
                        if entry_remaining > 0:
                            outstanding.append((entry, entry_remaining))
                    
                    # Apply rejections if this is the first item of the mixed carton
                    item_rejections = rejections if idx == 0 else 0
                    if item_rejections > 0 and not replace_from_buffer:
                        remaining_rej = item_rejections
                        for entry, entry_remaining in outstanding:
                            if remaining_rej <= 0:
                                break
                            deduct_qty = min(entry_remaining, remaining_rej)
                            entry.rejection_quantity = (entry.rejection_quantity or 0) + deduct_qty
                            entry.save()
                            remaining_rej -= deduct_qty

                    remaining_to_pack = qty
                    is_first_tx = True
                    for entry, entry_remaining in outstanding:
                        if remaining_to_pack <= 0:
                            break
                        
                        # Fetch fresh remaining quantity in case rejection changed it
                        entry_remaining = get_polishing_entry_remaining_qty(entry)
                        if entry_remaining <= 0:
                            continue
                        
                        pack_qty = min(entry_remaining, remaining_to_pack)
                        pack_wt = round((pack_qty / entry.quantity) * entry.weight, 3) if entry.quantity > 0 else 0.0
                        
                        notes_suffix = ""
                        tx_rejections = 0
                        if is_first_tx and item_rejections > 0:
                            is_first_tx = False
                            if replace_from_buffer:
                                tx_rejections = item_rejections
                                notes_suffix = f" (including {item_rejections} rejections replaced from loose buffer)"
                            else:
                                notes_suffix = f" ({item_rejections} rejections deducted from jobworker)"
                        
                        new_tx = StockTransaction.objects.create(
                            transaction_type=TransactionType.PACKAGING_IN,
                            item=item,
                            quantity=pack_qty,
                            weight=pack_wt,
                            rejection_quantity=tx_rejections,
                            notes=f"PACKED #{entry.id} [Mixed Carton: {carton_label} - Carton #{carton.id}]{steps_str}{notes_suffix}"
                        )
                        remaining_to_pack -= pack_qty
                    
                    if remaining_to_pack > 0:
                        rem_wt = max(0.0, wt - (qty - remaining_to_pack) * (item.machining_weight or 0.0))
                        new_tx = StockTransaction.objects.create(
                            transaction_type=TransactionType.PACKAGING_IN,
                            item=item,
                            quantity=remaining_to_pack,
                            weight=round(rem_wt, 3),
                            notes=f"Manual Packaging [Mixed Carton: {carton_label} - Carton #{carton.id}]{steps_str}"
                        )

                    packed_items_count += 1
            
            if packed_items_count > 0:
                carton.total_quantity = total_qty
                carton.total_weight = round(total_wt, 3)
                carton.save()
                messages.success(request, f"Successfully saved Mixed Carton '{carton_label}' ({carton.carton_number}) containing {total_qty} pcs across {packed_items_count} items!")
            else:
                carton.delete()
                messages.error(request, "No valid items or quantities were provided for the mixed carton.")
                
        return redirect("packaging")

    active_tab = request.GET.get("tab", "entry")
    
    # Fetch Cartons and Spares
    cartons = Carton.objects.all().order_by("-created_at")
    spares = StockTransaction.objects.filter(
        transaction_type=TransactionType.PACKAGING_IN,
        notes__contains="[DEDICATED BUFFER]"
    ).order_by("-created_at")
    
    ready_stock = []
    for c in cartons:
        ready_stock.append({
            'is_carton': True,
            'id': c.id,
            'created_at': c.created_at,
            'status': c.status,
            'carton_label': c.carton_label,
            'carton_number': c.carton_number,
            'carton_type': c.carton_type,
            'cleaning': c.cleaning,
            'labeling': c.labeling,
            'packing': c.packing,
            'total_quantity': c.total_quantity,
            'total_weight': c.total_weight,
            'items_list': [{
                'item_code': ci.item.code,
                'item_name': ci.item.name,
                'quantity': ci.quantity,
                'weight': ci.weight,
                'item_id': ci.item.id,
                'is_set': ci.item.item_type == 'SET'
            } for ci in c.items.all()]
        })
        
    for s in spares:
        ready_stock.append({
            'is_carton': False,
            'id': s.id,
            'created_at': s.created_at,
            'status': 'SPARE DECLARED',
            'carton_label': 'SPARE / BUFFER',
            'carton_number': f"TX-{s.id}",
            'carton_type': 'SPARE',
            'cleaning': False,
            'labeling': False,
            'packing': False,
            'total_quantity': s.quantity,
            'total_weight': s.weight,
            'items_list': [{
                'item_code': s.item.code,
                'item_name': s.item.name,
                'quantity': s.quantity,
                'weight': s.weight,
                'item_id': s.item.id,
                'is_set': s.item.item_type == 'SET'
            }]
        })
        
    ready_stock.sort(key=lambda x: x['created_at'], reverse=True)

    completed_ids = []

    # Rich Ready Stock Analytics - Grouped logically by physical Cartons
    ready_cartons = Carton.objects.filter(status='READY').prefetch_related('items__item').order_by("-created_at")
    ready_analytics = []
    total_pieces = 0
    total_weight = 0.0
    total_cartons = 0
    
    for carton in ready_cartons:
        nested_items = []
        for ci in carton.items.all():
            nested_items.append({
                'code': ci.item.code,
                'name': ci.item.name,
                'qty': ci.quantity,
                'weight': float(ci.weight)
            })
            
        steps = []
        if carton.cleaning: steps.append("Cleaned")
        if carton.labeling: steps.append("Labeled")
        if carton.packing: steps.append("Packed")
        
        if len(steps) == 3:
            status = "Fully Prepared"
            status_color = "#10b981"
        elif len(steps) > 0:
            status = "In Prep"
            status_color = "#f59e0b"
        else:
            status = "Raw Box"
            status_color = "#8b5cf6"
            
        ready_analytics.append({
            'carton': carton,
            'carton_number': carton.carton_number,
            'carton_type': carton.carton_type,
            'carton_label': carton.carton_label,
            'nested_items': nested_items,
            'qty': carton.total_quantity,
            'weight': round(float(carton.total_weight), 3),
            'status': status,
            'status_color': status_color,
            'created_at': carton.created_at,
            'steps_str': ", ".join(steps) if steps else "None"
        })
        
        total_pieces += carton.total_quantity
        total_weight += float(carton.total_weight)
        total_cartons += 1

    # Calculate top packed items (grouped by item) for sidebar visual analysis
    top_items_qs = CartonItem.objects.filter(
        carton__status='READY'
    ).values(
        'item__code', 'item__name'
    ).annotate(
        total_qty=Sum('quantity'),
        total_weight=Sum('weight')
    ).order_by('-total_qty')
    
    top_packed_items = []
    for row in top_items_qs[:5]:
        top_packed_items.append({
            'code': row['item__code'],
            'name': row['item__name'],
            'qty': row['total_qty'],
            'weight': round(float(row['total_weight'] or 0.0), 3)
        })

    # Group packaging queue by Job Worker / Worker and Category
    grouped_queue = {}
    for entry in packaging_queue:
        w_name = entry.job_worker.name if entry.job_worker else (entry.worker.name if entry.worker else "Internal/House")
        cat_name = entry.item.category.name.upper() if entry.item.category else "OTHER"
        
        if w_name not in grouped_queue:
            grouped_queue[w_name] = {}
        if cat_name not in grouped_queue[w_name]:
            grouped_queue[w_name][cat_name] = []
        
        grouped_queue[w_name][cat_name].append(entry)

    metrics = {
        'total_pieces': total_pieces,
        'total_weight': round(total_weight, 3),
        'total_cartons': total_cartons,
        'ready_items_count': CartonItem.objects.filter(carton__status='READY').values('item').distinct().count(),
        'active_queue_count': len(packaging_queue)
    }

    # Group items by sub_category for loose buffer stock tab (only showing available items > 0)
    buffer_groups = {}
    for item in items:
        if getattr(item, 'available_polishing', 0) > 0:
            subcat = item.sub_category.strip() if item.sub_category else "OTHER"
            if not subcat:
                subcat = "OTHER"
            subcat = subcat.upper()
            if subcat not in buffer_groups:
                buffer_groups[subcat] = []
            buffer_groups[subcat].append(item)

    context = {
        "items": items,
        "single_items": single_items,
        "set_items": set_items,
        "buffer_groups": buffer_groups,
        "packaging_queue": packaging_queue,
        "grouped_queue": grouped_queue,
        "ready_stock": ready_stock,
        "completed_ids": completed_ids,
        "active_tab": active_tab,
        "ready_analytics": ready_analytics,
        "top_packed_items": top_packed_items,
        "metrics": metrics
    }

    return render(request, "packaging.html", context)


@login_required
@require_role(['Logistics Supervisor', 'System Admin'])
def dispatch_view(request):
    clients = Client.objects.all()
    items = Item.objects.all()

    if request.method == "POST":
        client_id = request.POST.get("client")
        dispatch_type = request.POST.get("dispatch_type", "cartons")

        if not client_id:
            messages.error(request, "Client is required.")
            return redirect("dispatch")

        try:
            client = Client.objects.get(id=client_id)
        except Client.DoesNotExist:
            messages.error(request, "Selected client was not found.")
            return redirect("dispatch")

        if dispatch_type == "cartons":
            carton_ids = request.POST.getlist("cartons_selected")
            if not carton_ids:
                messages.error(request, "Please select at least one ready carton to dispatch.")
                return redirect("dispatch")

            dispatched_count = 0
            total_pieces = 0
            total_weight = 0.0

            for c_id in carton_ids:
                try:
                    carton = Carton.objects.get(id=c_id, status='READY')
                    carton.status = 'DISPATCHED'
                    carton.client = client
                    carton.dispatched_at = timezone.now()
                    carton.save()

                    # Symmetrically create dispatch transaction for each item in the carton
                    for ci in carton.items.all():
                        StockTransaction.objects.create(
                            transaction_type=TransactionType.DISPATCH_OUT,
                            client=client,
                            item=ci.item,
                            quantity=ci.quantity,
                            weight=ci.weight,
                            notes=f"Dispatched via Carton {carton.carton_number} to {client.name}"
                        )
                        total_pieces += ci.quantity
                        total_weight += ci.weight
                    dispatched_count += 1
                except Carton.DoesNotExist:
                    continue

            if dispatched_count > 0:
                messages.success(
                    request,
                    f"Successfully dispatched {dispatched_count} cartons ({total_pieces} pcs, {round(total_weight, 3)} kg) to {client.name}."
                )
            else:
                messages.error(request, "Failed to dispatch selected cartons.")
            return redirect("dispatch")

        else:
            # Legacy Manual Piece Dispatch Flow
            item_id = request.POST.get("item")
            cartons_cnt = int(request.POST.get("cartons") or 0)
            loose_pieces = int(request.POST.get("loose_pieces") or 0)
            weight = float(request.POST.get("weight") or 0)

            if not item_id:
                messages.error(request, "Item is required for manual dispatch.")
                return redirect("dispatch")

            try:
                item = Item.objects.get(id=item_id)
            except Item.DoesNotExist:
                messages.error(request, "Selected item was not found.")
                return redirect("dispatch")

            lot_size = item.lot_with_box or 0
            pieces = (cartons_cnt * lot_size) + loose_pieces

            if pieces <= 0:
                messages.error(request, "Valid quantity (Cartons or Loose Pieces) is required.")
                return redirect("dispatch")

            # Create standard dispatch transaction
            StockTransaction.objects.create(
                transaction_type=TransactionType.DISPATCH_OUT,
                client=client,
                item=item,
                quantity=pieces,
                weight=weight,
                notes=f"Manual Dispatch {pieces} pcs to {client.name}"
            )

            messages.success(request, f"Successfully dispatched {pieces} pcs of {item.name} to {client.name} (Manual Override).")
            return redirect("dispatch")

    # GET Handler: Get Ready Stock summary
    stock_rows = []
    for item in items:
        item_stock = services.get_stock_by_item(item)
        ready_qty = item_stock['ready']
        if ready_qty > 0:
            cartons_cnt, loose_pieces = item.calculate_cartons_and_loose(ready_qty)
            stock_rows.append({
                "item": item,
                "cartons": cartons_cnt,
                "loose_pieces": loose_pieces,
                "total_pieces": ready_qty,
                "weight": round(ready_qty * float(item.machining_weight or 0), 3)
            })

    # Available ready cartons for the dispatch checkbox list
    available_cartons = Carton.objects.filter(status='READY').order_by('-created_at')

    recent_dispatches = StockTransaction.objects.filter(
        transaction_type=TransactionType.DISPATCH_OUT
    ).order_by("-created_at")[:20]

    context = {
        "clients": clients,
        "items": items,
        "stock_rows": stock_rows,
        "available_cartons": available_cartons,
        "recent_dispatches": recent_dispatches,
    }
    return render(request, "dispatch.html", context)
