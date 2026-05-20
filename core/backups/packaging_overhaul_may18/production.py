import json
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.db.models import Sum, Q
from django.utils import timezone

from inventory.models import (
    Client,
    Item,
    Worker,
    JobWorker,
    Warehouse,
    StockTransaction,
    TransactionType,
    ItemWorkerAllocation
)
from inventory import services

# =====================================================
# DEFAULT WAREHOUSES
# =====================================================

def create_default_warehouses():
    warehouses = [
        ("CASTING", "Casting Stock"),
        ("MACHINING", "Machining Stock"),
        ("POLISHING", "Polishing Stock"),
        ("READY", "Ready Stock"),
    ]
    for code, name in warehouses:
        Warehouse.objects.get_or_create(
            code=code,
            defaults={"name": name}
        )

# =====================================================
# CASTING ENTRY
# =====================================================

def casting_entry(request):
    create_default_warehouses()

    clients = Client.objects.all()
    items = Item.objects.all()

    if request.method == "POST":
        edit_id = request.POST.get("edit_id")
        heat_no = request.POST.get("heat_no")
        client_id = request.POST.get("client")
        notes = request.POST.get("notes")

        try:
            client = Client.objects.get(id=client_id) if client_id else None
        except Client.DoesNotExist:
            client = None

        if edit_id:
            # Single update
            item_id = request.POST.get("item")
            client_id = request.POST.get("client")
            quantity = int(request.POST.get("quantity") or 0)
            weight = float(request.POST.get("weight") or 0)
            
            try:
                tx = StockTransaction.objects.get(id=edit_id)
                tx.client_id = client_id
                tx.item_id = item_id
                tx.quantity = quantity
                tx.weight = weight
                tx.heat_no = heat_no
                tx.notes = notes
                tx.save()
                messages.success(request, "Entry updated.")
            except StockTransaction.DoesNotExist:
                messages.error(request, "Not found.")
        else:
            # Multiple create
            item_ids = request.POST.getlist("item[]")
            client_ids = request.POST.getlist("client[]")
            quantities = request.POST.getlist("quantity[]")
            weights = request.POST.getlist("weight[]")

            for i in range(len(item_ids)):
                if not item_ids[i]: continue
                
                # Handle client per row
                c_id = client_ids[i] if i < len(client_ids) and client_ids[i] else None
                
                StockTransaction.objects.create(
                    transaction_type=TransactionType.CASTING_ENTRY,
                    client_id=c_id,
                    item_id=item_ids[i],
                    quantity=int(quantities[i] or 0),
                    weight=float(weights[i] or 0),
                    heat_no=heat_no,
                    notes=notes
                )
            messages.success(request, f"Saved {len(item_ids)} entries.")

        return redirect("casting_entry")

    # DELETE logic
    delete_id = request.GET.get("delete_id")
    if delete_id:
        try:
            StockTransaction.objects.get(id=delete_id).delete()
            messages.success(request, "Entry deleted successfully.")
        except StockTransaction.DoesNotExist:
            messages.error(request, "Entry not found.")
        return redirect("casting_entry")

    all_entries = StockTransaction.objects.filter(
        transaction_type__in=[
            "casting_in",
            "casting_entry"
        ]
    ).select_related("item", "client").order_by("-created_at")

    search_query = request.GET.get("search", "")
    date_from = request.GET.get("date_from", "")
    date_to = request.GET.get("date_to", "")
    active_tab = request.GET.get("tab", "entry")

    # Get heats used today for UI highlighting
    today = timezone.now().date()
    used_heats_today = list(StockTransaction.objects.filter(
        transaction_type=TransactionType.CASTING_ENTRY,
        created_at__date=today
    ).values_list('heat_no', flat=True).distinct())

    # Get items from the most recent heat for cloning
    last_entry = StockTransaction.objects.filter(
        transaction_type=TransactionType.CASTING_ENTRY
    ).order_by('-created_at').first()
    
    last_heat_items = []
    if last_entry:
        last_heat_items = list(StockTransaction.objects.filter(
            transaction_type=TransactionType.CASTING_ENTRY,
            heat_no=last_entry.heat_no,
            created_at__date=last_entry.created_at.date()
        ).values('item_id', 'item__code', 'item__name', 'quantity', 'weight', 'client_id'))

    if search_query:
        all_entries = all_entries.filter(
            Q(item__name__icontains=search_query) |
            Q(item__code__icontains=search_query) |
            Q(client__name__icontains=search_query)
        )

    if date_from:
        all_entries = all_entries.filter(created_at__date__gte=date_from)

    if date_to:
        all_entries = all_entries.filter(created_at__date__lte=date_to)

    # Recent entries for today only
    recent_raw = all_entries.filter(created_at__date=timezone.now().date())
    grouped_recent = []
    current_group = None

    for r in recent_raw:
        group_key = (r.created_at.date() if r.created_at else None, r.heat_no)
        
        if not current_group or current_group['key'] != group_key:
            if current_group:
                grouped_recent.append(current_group)
            
            current_group = {
                'key': group_key,
                'date': r.created_at.strftime("%d/%m/%Y") if r.created_at else "-",
                'heat_no': r.heat_no if r.heat_no else "-",
                'total_pcs': 0,
                'total_wt': 0,
                'items': []
            }
        
        item_data = {
            "id": r.id,
            "heat_no": r.heat_no,
            "item_name": f"{r.item.code} - {r.item.name}" if r.item else "-",
            "item_id": r.item.id if r.item else "",
            "client_name": r.client.name if r.client else "-",
            "client_id": r.client.id if r.client else "",
            "quantity": r.quantity or 0,
            "weight": r.weight or 0,
            "notes": r.notes or ""
        }
        
        current_group['items'].append(item_data)
        current_group['total_pcs'] += item_data['quantity']
        current_group['total_wt'] += item_data['weight']

    if current_group:
        grouped_recent.append(current_group)

    # Day-specific stats for the analytics banner
    today_entries = all_entries.filter(created_at__date=timezone.now().date())
    today_total_weight = today_entries.aggregate(total=Sum("weight"))["total"] or 0
    today_heats_count = today_entries.values('heat_no').distinct().count()

    total_entries = all_entries.count()

    total_pcs = all_entries.aggregate(
        total=Sum("quantity")
    )["total"] or 0

    total_weight = all_entries.aggregate(
        total=Sum("weight")
    )["total"] or 0

    summary_data = all_entries.values(
        "item__code", "item__name"
    ).annotate(
        total_pcs=Sum("quantity"),
        total_wt=Sum("weight")
    ).order_by("-total_pcs")

    context = {
        "clients": clients,
        "items": items,

        "recent": grouped_recent,
        "all_entries": all_entries,
        "summary_data": summary_data,

        "total_entries": total_entries,
        "total_pcs": total_pcs,
        "total_weight": round(total_weight, 3),
        "search_query": search_query,
        "date_from": date_from,
        "date_to": date_to,
        "today_weight": today_total_weight,
        "today_heats": today_heats_count,
        "active_tab": active_tab,
        "used_heats_today": used_heats_today,
        "heats_range": range(1, 11),
        "last_heat_items": json.dumps(last_heat_items),
    }

    return render(request, "casting.html", context)

# =====================================================
# MACHINING
# =====================================================

def machining_entry(request):
    create_default_warehouses()

    workers = Worker.objects.filter(process="machining", active=True)
    job_workers = JobWorker.objects.filter(process="machining", active=True)
    items = Item.objects.all()

    delete_id = request.GET.get("delete_id")
    if delete_id:
        try:
            tx = StockTransaction.objects.get(id=delete_id)
            tx.delete()
            messages.success(request, "Machining entry deleted successfully.")
        except StockTransaction.DoesNotExist:
            messages.error(request, "Machining transaction not found.")
        return redirect("machining_entry")

    if request.method == "POST":
        direction = request.POST.get("direction")
        worker_id = request.POST.get("worker")
        date_str = request.POST.get("date")

        worker_obj = None
        job_worker_obj = None
        if worker_id:
            if worker_id.startswith('w_'):
                worker_obj = Worker.objects.filter(id=worker_id.replace('w_', '')).first()
            elif worker_id.startswith('jw_'):
                job_worker_obj = JobWorker.objects.filter(id=worker_id.replace('jw_', '')).first()

        created_at_dt = None
        if date_str:
            try:
                created_at_dt = timezone.datetime.strptime(date_str + " 12:00:00", "%Y-%m-%d %H:%M:%S")
                created_at_dt = timezone.make_aware(created_at_dt)
            except Exception:
                pass

        edit_id = request.POST.get("edit_id")
        if edit_id:
            # Symmetrically parse single values or first elements from arrays
            item_id = request.POST.get("item") or (request.POST.getlist("item[]")[0] if request.POST.getlist("item[]") else None)
            quantity_str = request.POST.get("quantity") or (request.POST.getlist("quantity[]")[0] if request.POST.getlist("quantity[]") else "0")
            rejection_quantity_str = request.POST.get("rejection_quantity") or (request.POST.getlist("rejection_quantity[]")[0] if request.POST.getlist("rejection_quantity[]") else "0")
            weight_str = request.POST.get("weight") or (request.POST.getlist("weight[]")[0] if request.POST.getlist("weight[]") else "0.0")

            quantity = int(quantity_str or 0)
            rejection_quantity = int(rejection_quantity_str or 0)
            weight = float(weight_str or 0.0)

            try:
                tx = StockTransaction.objects.get(id=edit_id)
                tx.transaction_type = direction
                tx.item_id = item_id
                tx.worker = worker_obj
                tx.job_worker = job_worker_obj
                tx.quantity = quantity
                tx.rejection_quantity = rejection_quantity
                tx.weight = weight
                if created_at_dt:
                    tx.created_at = created_at_dt
                tx.save()
                messages.success(request, "Updated successfully.")
            except StockTransaction.DoesNotExist:
                messages.error(request, "Transaction not found.")
        else:
            item_ids = request.POST.getlist("item[]")
            quantities = request.POST.getlist("quantity[]")
            rejection_quantities = request.POST.getlist("rejection_quantity[]")
            weights = request.POST.getlist("weight[]")

            count = 0
            for i in range(len(item_ids)):
                it_id = item_ids[i]
                if not it_id:
                    continue

                qty = int(quantities[i] or 0)
                rej_qty = int(rejection_quantities[i] or 0) if i < len(rejection_quantities) else 0
                wt = float(weights[i] or 0)

                tx = StockTransaction.objects.create(
                    transaction_type=direction,
                    item_id=it_id,
                    worker=worker_obj,
                    job_worker=job_worker_obj,
                    quantity=qty,
                    rejection_quantity=rej_qty,
                    weight=wt
                )
                if created_at_dt:
                    tx.created_at = created_at_dt
                    tx.save()
                count += 1

            messages.success(request, f"Saved {count} movement entries.")

        return redirect("machining_entry")

    recent = StockTransaction.objects.filter(
        transaction_type__in=[
            "machining_out",
            "machining_in"
        ]
    ).order_by("-id")[:30]

    machining_stock = []

    for item in items:
        machining_in = StockTransaction.objects.filter(
            item=item,
            transaction_type="machining_in"
        ).aggregate(
            total=Sum("quantity")
        )["total"] or 0

        machining_out = StockTransaction.objects.filter(
            item=item,
            transaction_type="machining_out"
        ).aggregate(
            total=Sum("quantity")
        )["total"] or 0

        polishing_out = StockTransaction.objects.filter(
            item=item,
            transaction_type="polishing_out"
        ).aggregate(
            total=Sum("quantity")
        )["total"] or 0

        available_qty = machining_in - polishing_out

        # 1. Internal Workers WIP for this item
        internal_wip_rows = StockTransaction.objects.filter(
            item=item, 
            transaction_type="machining_out", 
            worker__isnull=False
        ).values('worker', 'worker__name').annotate(issued=Sum('quantity'))

        for row in internal_wip_rows:
            w_id = row['worker']
            w_name = row['worker__name']
            received = StockTransaction.objects.filter(item=item, worker_id=w_id, transaction_type="machining_in").aggregate(total=Sum('quantity'))['total'] or 0
            rejected = StockTransaction.objects.filter(item=item, worker_id=w_id, transaction_type="machining_in").aggregate(total=Sum('rejection_quantity'))['total'] or 0
            
            under_process = row['issued'] - received - rejected
            if under_process > 0:
                machining_stock.append({
                    "item_id": item.id,
                    "item_name": f"{item.code} - {item.name}",
                    "item_category": item.get_category_display(),
                    "worker_id": f"w_{w_id}",
                    "worker_name": f"{w_name} (INT)",
                    "under_process": under_process,
                    "available_qty": available_qty
                })

        # 2. External Job Workers WIP for this item
        external_wip_rows = StockTransaction.objects.filter(
            item=item, 
            transaction_type="machining_out", 
            job_worker__isnull=False
        ).values('job_worker', 'job_worker__name').annotate(issued=Sum('quantity'))

        for row in external_wip_rows:
            jw_id = row['job_worker']
            jw_name = row['job_worker__name']
            received = StockTransaction.objects.filter(item=item, job_worker_id=jw_id, transaction_type="machining_in").aggregate(total=Sum('quantity'))['total'] or 0
            rejected = StockTransaction.objects.filter(item=item, job_worker_id=jw_id, transaction_type="machining_in").aggregate(total=Sum('rejection_quantity'))['total'] or 0
            
            under_process = row['issued'] - received - rejected
            if under_process > 0:
                machining_stock.append({
                    "item_id": item.id,
                    "item_name": f"{item.code} - {item.name}",
                    "item_category": item.get_category_display(),
                    "worker_id": f"jw_{jw_id}",
                    "worker_name": jw_name,
                    "under_process": under_process,
                    "available_qty": available_qty
                })

    worker_wip = []

    # Internal Workers
    for worker in workers:
        issued = StockTransaction.objects.filter(worker=worker, transaction_type="machining_out").aggregate(total=Sum("quantity"))["total"] or 0
        received = StockTransaction.objects.filter(worker=worker, transaction_type="machining_in").aggregate(total=Sum("quantity"))["total"] or 0
        rejected = StockTransaction.objects.filter(worker=worker, transaction_type="machining_in").aggregate(total=Sum("rejection_quantity"))["total"] or 0
        
        pending = issued - received - rejected
        if issued > 0 or received > 0:
            worker_wip.append({
                "name": worker.name,
                "issued": issued,
                "received": received,
                "rejected": rejected,
                "pending": pending
            })

    # External Job Workers
    for jw in job_workers:
        issued = StockTransaction.objects.filter(job_worker=jw, transaction_type="machining_out").aggregate(total=Sum("quantity"))["total"] or 0
        received = StockTransaction.objects.filter(job_worker=jw, transaction_type="machining_in").aggregate(total=Sum("quantity"))["total"] or 0
        rejected = StockTransaction.objects.filter(job_worker=jw, transaction_type="machining_in").aggregate(total=Sum("rejection_quantity"))["total"] or 0
        
        pending = issued - received - rejected
        if issued > 0 or received > 0:
            worker_wip.append({
                "name": f"{jw.name} (EXT)",
                "issued": issued,
                "received": received,
                "rejected": rejected,
                "pending": pending
            })

    # Prepare Worker-wise Ledger
    from collections import defaultdict
    worker_ledger = defaultdict(list)
    for r in recent:
        if r.worker:
            name = f"{r.worker.name} (INT)"
        elif r.job_worker:
            name = f"{r.job_worker.name} (EXT)"
        else:
            name = "UNASSIGNED"
        worker_ledger[name].append(r)

    # Smart Worker Allocation Logic
    from inventory.models import ItemWorkerAllocation
    allocations = ItemWorkerAllocation.objects.all().select_related('worker', 'job_worker')
    smart_allocations = {}
    for a in allocations:
        item_id = str(a.item_id)
        if item_id not in smart_allocations:
            smart_allocations[item_id] = []
        
        w_id = f"w_{a.worker_id}" if a.worker_id else f"jw_{a.job_worker_id}"
        w_name = a.worker.name if a.worker_id else a.job_worker.name
        
        smart_allocations[item_id].append({"id": w_id, "name": w_name})

    # Create sorted copy of machining stock by category for Stock Tab
    machining_stock_by_category = list(machining_stock)
    machining_stock_by_category.sort(key=lambda x: x["item_category"])

    # Sort WIP stock by worker_name to support Django regroup template tag grouping
    machining_stock.sort(key=lambda x: x["worker_name"])

    context = {
        "workers": workers,
        "job_workers": job_workers,
        "items": items,
        "recent": recent,
        "worker_ledger": dict(worker_ledger),
        "machining_stock": machining_stock,
        "machining_stock_by_category": machining_stock_by_category,
        "worker_wip": worker_wip,
        "smart_allocations": json.dumps(smart_allocations),
        "today": timezone.now()
    }

    return render(request, "machining.html", context)

# =====================================================
# POLISHING
# =====================================================

def polishing_entry(request):
    workers = Worker.objects.filter(process="polishing", active=True)
    job_workers = JobWorker.objects.filter(process="polishing", active=True)
    items = Item.objects.all()

    piece_stock = {}
    set_capacity = {}

    for item in items:
        stock = services.get_stock_by_item(item)
        current_machining_stock = stock.get('machining', 0)
        
        # Store individual piece stock
        piece_stock[item.id] = current_machining_stock
        item.current_stock = current_machining_stock

    # Second pass: Calculate Set Capacity based on piece stock
    for item in items:
        if item.components.exists():
            from inventory.models import ItemComposition
            comps = ItemComposition.objects.filter(parent_item=item)
            if comps.exists():
                max_sets = 999999
                for comp in comps:
                    c_avail = piece_stock.get(comp.component_item.id, 0)
                    can_make = c_avail // comp.quantity
                    if can_make < max_sets:
                        max_sets = can_make
                set_capacity[item.id] = max_sets
                item.set_capacity = max_sets
            else:
                set_capacity[item.id] = 0
                item.set_capacity = 0
        else:
            set_capacity[item.id] = 0
            item.set_capacity = 0

    # available_data for backward compatibility if needed, but we'll use specific dicts
    available_data = {**piece_stock, **set_capacity}

    # ======================================
    # DELETE TRANSACTION
    # ======================================
    delete_id = request.GET.get("delete_id")
    if delete_id:
        try:
            tx = StockTransaction.objects.get(id=delete_id)
            # Delete child auto-consumed transactions for sets
            StockTransaction.objects.filter(notes__startswith=f"Auto-consumed for Set Transaction #{tx.id}").delete()
            
            # Find and delete component extras and their associated polishing_in transactions
            comp_extras = StockTransaction.objects.filter(notes=f"Component Extra for Set Transaction #{tx.id}")
            for comp_tx in comp_extras:
                StockTransaction.objects.filter(notes=f"IN for OUT #{comp_tx.id}").delete()
            comp_extras.delete()
            
            StockTransaction.objects.filter(notes=f"IN for OUT #{tx.id}").delete()
            # Delete the transaction itself
            tx.delete()
            messages.success(request, "Polishing entry and all associated auto-consumed/receipt transactions deleted successfully.")
        except StockTransaction.DoesNotExist:
            messages.error(request, "Selected transaction not found.")
        return redirect("polishing_entry")

    # ======================================
    # MARK IN BUTTON
    # ======================================

    mark_in_id = request.GET.get("mark_in")

    if mark_in_id:
        try:
            out_entry = StockTransaction.objects.get(
                id=mark_in_id,
                transaction_type="polishing_out"
            )

            already_done = StockTransaction.objects.filter(
                notes=f"IN for OUT #{out_entry.id}"
            ).exists()

            if not already_done:
                StockTransaction.objects.create(
                    transaction_type="polishing_in",
                    item=out_entry.item,
                    worker=out_entry.worker,
                    job_worker=out_entry.job_worker,
                    quantity=out_entry.quantity,
                    weight=out_entry.weight,
                    notes=f"IN for OUT #{out_entry.id}"
                )
                messages.success(
                    request,
                    "Polishing entry marked IN successfully."
                )
            else:
                messages.info(
                    request,
                    "This polishing out entry is already marked IN."
                )
        except StockTransaction.DoesNotExist:
            messages.error(
                request,
                "Selected polishing entry could not be found."
            )
        return redirect("polishing_entry")

    if request.method == "POST":
        worker_id = request.POST.get("worker")

        if not worker_id:
            messages.error(
                request,
                "Please select a worker before saving polishing entries."
            )
            return redirect("polishing_entry")

        worker_obj = None
        job_worker_obj = None

        if worker_id:
            if worker_id.startswith('w_'):
                worker_obj = Worker.objects.filter(id=worker_id.replace('w_', '')).first()
            elif worker_id.startswith('jw_'):
                job_worker_obj = JobWorker.objects.filter(id=worker_id.replace('jw_', '')).first()

        if not worker_obj and not job_worker_obj:
            messages.error(
                request,
                "Selected worker was not found."
            )
            return redirect("polishing_entry")

        direction = request.POST.get("direction", "polishing_out")
        
        transaction_data_str = request.POST.get("transaction_data")
        
        if transaction_data_str:
            try:
                transaction_data = json.loads(transaction_data_str)
            except json.JSONDecodeError:
                messages.error(request, "Invalid transaction data payload.")
                return redirect("polishing_entry")

            for row in transaction_data:
                item_id = row.get("item_id")
                if not item_id:
                    continue

                try:
                    item = Item.objects.get(id=item_id)
                except Item.DoesNotExist:
                    continue

                lots = int(row.get("lots") or 0)
                manual = int(row.get("manual") or 0)
                weight = float(row.get("weight") or 0)
                packaging = row.get("packaging", "regular")

                # Get correct lot size based on packaging (with fallback to lot_size if lot_with_box is 0 or None)
                if packaging == "box":
                    lot_size = item.lot_with_box if (item.lot_with_box and item.lot_with_box > 0) else item.lot_size
                else:
                    lot_size = item.lot_size
                lot_size = lot_size or 0
                total_quantity = (lots * lot_size) + manual

                if total_quantity <= 0:
                    continue

                edit_id = request.POST.get("edit_id")
                if edit_id:
                    try:
                        tx = StockTransaction.objects.get(id=edit_id)
                        tx.transaction_type = direction
                        tx.item = item
                        tx.worker = worker_obj
                        tx.job_worker = job_worker_obj
                        tx.quantity = total_quantity
                        tx.weight = weight
                        tx.save()

                        # Delete old component consumptions
                        StockTransaction.objects.filter(notes__startswith=f"Auto-consumed for Set Transaction #{tx.id}").delete()

                        # Delete old component extras and their associated polishing_in transactions
                        comp_extras = StockTransaction.objects.filter(notes=f"Component Extra for Set Transaction #{tx.id}")
                        for comp_tx in comp_extras:
                            StockTransaction.objects.filter(notes=f"IN for OUT #{comp_tx.id}").delete()
                        comp_extras.delete()

                        # Re-create child auto-consumption and component extras if applicable
                        if direction == "polishing_out" and item.components.exists():
                            from inventory.models import Warehouse
                            from_wh = Warehouse.objects.filter(code='MACHINING').first()
                            components = row.get("components", [])
                            for comp_row in components:
                                comp_id = comp_row.get("component_id")
                                qty_per_set = int(comp_row.get("qty_per_set") or 0)
                                extra_qty = int(comp_row.get("extra_qty") or 0)
                                
                                base_qty = qty_per_set * total_quantity
                                try:
                                    comp_item = Item.objects.get(id=comp_id)
                                except Item.DoesNotExist:
                                    continue
                                
                                if base_qty > 0:
                                    StockTransaction.objects.create(
                                        transaction_type="kitting_consume",
                                        item=comp_item,
                                        quantity=base_qty,
                                        from_warehouse=from_wh,
                                        notes=f"Auto-consumed for Set Transaction #{tx.id}"
                                    )
                                
                                if extra_qty > 0:
                                    StockTransaction.objects.create(
                                        transaction_type="polishing_out",
                                        item=comp_item,
                                        worker=worker_obj,
                                        job_worker=job_worker_obj,
                                        quantity=extra_qty,
                                        weight=extra_qty * (comp_item.machining_weight or 0.0),
                                        notes=f"Component Extra for Set Transaction #{tx.id}"
                                    )
                        messages.success(request, "Polishing entry updated successfully.")
                    except StockTransaction.DoesNotExist:
                        messages.error(request, "Selected polishing entry not found.")
                else:
                    # Creating a new transaction
                    parent_tx = StockTransaction.objects.create(
                        transaction_type=direction,
                        item=item,
                        worker=worker_obj,
                        job_worker=job_worker_obj,
                        quantity=total_quantity,
                        weight=weight
                    )

                    if direction == "polishing_out" and item.components.exists():
                        from inventory.models import Warehouse
                        from_wh = Warehouse.objects.filter(code='MACHINING').first()
                        
                        components = row.get("components", [])
                        for comp_row in components:
                            comp_id = comp_row.get("component_id")
                            qty_per_set = int(comp_row.get("qty_per_set") or 0)
                            extra_qty = int(comp_row.get("extra_qty") or 0)
                            
                            base_qty = qty_per_set * total_quantity
                            try:
                                comp_item = Item.objects.get(id=comp_id)
                            except Item.DoesNotExist:
                                continue
                                
                            if base_qty > 0:
                                StockTransaction.objects.create(
                                    transaction_type="kitting_consume",
                                    item=comp_item,
                                    quantity=base_qty,
                                    from_warehouse=from_wh,
                                    notes=f"Auto-consumed for Set Transaction #{parent_tx.id}"
                                )
                                
                            if extra_qty > 0:
                                StockTransaction.objects.create(
                                    transaction_type="polishing_out",
                                    item=comp_item,
                                    worker=worker_obj,
                                    job_worker=job_worker_obj,
                                    quantity=extra_qty,
                                    weight=extra_qty * (comp_item.machining_weight or 0.0),
                                    notes=f"Component Extra for Set Transaction #{parent_tx.id}"
                                )
                    messages.success(request, f"Polishing { 'Issue' if direction == 'polishing_out' else 'Receipt' } saved successfully.")

            return redirect("polishing_entry")
        else:
            # Fallback to standard form fields (legacy support)
            rows = request.POST.getlist("item[]")
            for index, item_id in enumerate(rows):
                if not item_id:
                    continue

                try:
                    item = Item.objects.get(id=item_id)
                except Item.DoesNotExist:
                    continue

                lots = int(request.POST.getlist("lots[]")[index] or 0)
                manual = int(request.POST.getlist("manual[]")[index] or 0)
                weight = float(request.POST.getlist("weight[]")[index] or 0)

                lot_size = item.lot_size or 0
                total_quantity = (lots * lot_size) + manual

                if total_quantity <= 0:
                    continue

                # If it's a SET item, consume components (only for OUT transactions)
                if direction == "polishing_out" and item.components.exists():
                    from inventory.models import ItemComposition, Warehouse
                    comps = ItemComposition.objects.filter(parent_item=item)
                    from_wh = Warehouse.objects.filter(code='MACHINING').first()
                    for comp in comps:
                        comp_total_qty = comp.quantity * total_quantity
                        StockTransaction.objects.create(
                            transaction_type="kitting_consume",
                            item=comp.component_item,
                            quantity=comp_total_qty,
                            from_warehouse=from_wh,
                            notes=f"Auto-consumed for Set: {item.name} (Polishing Out)"
                        )

                StockTransaction.objects.create(
                    transaction_type=direction,
                    item=item,
                    worker=worker_obj,
                    job_worker=job_worker_obj,
                    quantity=total_quantity,
                    weight=weight
                )

            messages.success(
                request,
                f"Polishing { 'Issue' if direction == 'polishing_out' else 'Receipt' } saved successfully."
            )
            return redirect("polishing_entry")

    recent = StockTransaction.objects.filter(
        transaction_type__in=[
            "polishing_out",
            "polishing_in"
        ]
    ).order_by("-created_at")[:20]

    completed_ids = []

    for row in recent:
        if row.transaction_type == "polishing_out":
            done = StockTransaction.objects.filter(
                notes=f"IN for OUT #{row.id}"
            ).exists()
            if done:
                completed_ids.append(row.id)

    # Calculate Polishing WIP Stock
    polishing_stock = []
    for item in items:
        # 1. Internal Workers WIP for this item
        internal_wip_rows = StockTransaction.objects.filter(
            item=item, 
            transaction_type="polishing_out", 
            worker__isnull=False
        ).values('worker', 'worker__name').annotate(issued=Sum('quantity'))

        for row in internal_wip_rows:
            w_id = row['worker']
            w_name = row['worker__name']
            received = StockTransaction.objects.filter(item=item, worker_id=w_id, transaction_type="polishing_in").aggregate(total=Sum('quantity'))['total'] or 0
            
            under_process = row['issued'] - received
            if under_process > 0:
                polishing_stock.append({
                    "item_id": item.id,
                    "item_name": f"{item.code} - {item.name}",
                    "worker_id": f"w_{w_id}",
                    "worker_name": f"{w_name} (INT)",
                    "under_process": under_process,
                })

        # 2. External Job Workers WIP for this item
        external_wip_rows = StockTransaction.objects.filter(
            item=item, 
            transaction_type="polishing_out", 
            job_worker__isnull=False
        ).values('job_worker', 'job_worker__name').annotate(issued=Sum('quantity'))

        for row in external_wip_rows:
            jw_id = row['job_worker']
            jw_name = row['job_worker__name']
            received = StockTransaction.objects.filter(item=item, job_worker_id=jw_id, transaction_type="polishing_in").aggregate(total=Sum('quantity'))['total'] or 0
            
            under_process = row['issued'] - received
            if under_process > 0:
                polishing_stock.append({
                    "item_id": item.id,
                    "item_name": f"{item.code} - {item.name}",
                    "worker_id": f"jw_{jw_id}",
                    "worker_name": jw_name,
                    "under_process": under_process,
                })

    from inventory.models import ItemWorkerAllocation
    allocations = ItemWorkerAllocation.objects.all().select_related('item', 'worker', 'job_worker')

    context = {
        "workers": workers,
        "job_workers": job_workers,
        "items": items,
        "recent": recent,
        "available_data": available_data,
        "completed_ids": completed_ids,
        "allocations": allocations,
        "polishing_stock": polishing_stock,
    }

    return render(request, "polishing.html", context)

# =====================================================
# PACKAGING
# =====================================================

def packaging_view(request):
    from inventory.models import Item, StockTransaction, TransactionType, Warehouse
    from django.db.models import Sum
    from inventory import services
    import uuid

    items = Item.objects.all()

    # Calculate live Polishing WIP Stock/Capacity for each item
    piece_stock = {}
    for item in items:
        # Fetch current polishing stock using service
        stock_stats = services.get_stock_by_item(item)
        piece_stock[item.id] = stock_stats.get('polishing', 0)
        item.available_polishing = piece_stock[item.id]
        
    for item in items:
        if item.item_type == 'SET':
            from inventory.models import ItemComposition
            comps = ItemComposition.objects.filter(parent_item=item)
            if comps.exists():
                max_sets = 999999
                for comp in comps:
                    c_avail = piece_stock.get(comp.component_item.id, 0)
                    can_make = c_avail // comp.quantity
                    if can_make < max_sets:
                        max_sets = can_make
                item.available_polishing = max_sets
            else:
                item.available_polishing = 0

    # Separate Single and Set items for select menu filters in JS
    single_items = items.filter(item_type='REGULAR')
    set_items = items.filter(item_type='SET')

    # =====================================
    # PACKAGING QUEUE
    # =====================================
    packaging_queue = []

    polishing_in_entries = StockTransaction.objects.filter(
        transaction_type="polishing_in"
    ).order_by("-created_at")

    for entry in polishing_in_entries:
        already_packed = StockTransaction.objects.filter(
            notes__startswith=f"PACKED #{entry.id}"
        ).exists()
        if not already_packed:
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
            tx = StockTransaction.objects.get(id=delete_id)
            import re
            
            # Check if this is a mixed carton transaction
            mixed_ref_match = re.search(r"Ref:\s*(MIXED-[0-9A-Z]+)", tx.notes or "")
            if mixed_ref_match:
                ref_code = mixed_ref_match.group(1)
                # Find all associated transactions
                associated = StockTransaction.objects.filter(notes__contains=ref_code)
                count = 0
                for assoc in associated:
                    StockTransaction.objects.filter(notes__contains=f"Auto-consumed for packaging ID: #{assoc.id}").delete()
                    assoc.delete()
                    count += 1
                messages.success(request, f"Successfully deleted Mixed Carton containing {count} entries.")
            else:
                # Delete any associated kitting consume
                StockTransaction.objects.filter(notes__contains=f"Auto-consumed for packaging ID: #{tx.id}").delete()
                tx.delete()
                messages.success(request, "Packaging entry deleted successfully.")
        except StockTransaction.DoesNotExist:
            messages.error(request, "Selected entry could not be found.")
        return redirect("packaging")

    if pack_id:
        try:
            polishing_entry = StockTransaction.objects.get(
                id=pack_id,
                transaction_type="polishing_in"
            )

            already_done = StockTransaction.objects.filter(
                notes__startswith=f"PACKED #{polishing_entry.id}"
            ).exists()

            if not already_done:
                # Symmetrically create the transaction
                new_tx = StockTransaction.objects.create(
                    transaction_type="packaging_in",
                    item=polishing_entry.item,
                    quantity=polishing_entry.quantity,
                    weight=polishing_entry.weight,
                    notes=f"PACKED #{polishing_entry.id}"
                )
                
                # Symmetrically consume component parts if SET
                if polishing_entry.item.item_type == 'SET':
                    from inventory.models import ItemComposition
                    comps = ItemComposition.objects.filter(parent_item=polishing_entry.item)
                    polishing_wh = Warehouse.objects.filter(code='POLISHING').first()
                    for comp in comps:
                        needed = comp.quantity * polishing_entry.quantity
                        StockTransaction.objects.create(
                            item=comp.component_item,
                            transaction_type=TransactionType.KITTING_CONSUME,
                            quantity=needed,
                            from_warehouse=polishing_wh,
                            notes=f"Auto-consumed for packaging ID: #{new_tx.id}"
                        )
                messages.success(
                    request,
                    "Packaging entry saved successfully."
                )
            else:
                messages.info(
                    request,
                    "This polish entry has already been packed."
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
        
        # Build process steps suffix
        steps_list = []
        if cleaning: steps_list.append("Cleaning")
        if labeling: steps_list.append("Labeling")
        if packing: steps_list.append("Packing")
        steps_str = f" [{', '.join(steps_list)}]" if steps_list else ""
        
        if edit_id:
            try:
                tx = StockTransaction.objects.get(id=edit_id)
                import re
                
                # Check if it was a mixed carton transaction
                mixed_ref_match = re.search(r"Ref:\s*(MIXED-[0-9A-Z]+)", tx.notes or "")
                if mixed_ref_match:
                    ref_code = mixed_ref_match.group(1)
                    # For Mixed Carton edit:
                    # Symmetrically delete old mixed entries & their consumptions
                    associated = StockTransaction.objects.filter(notes__contains=ref_code)
                    for assoc in associated:
                        StockTransaction.objects.filter(notes__contains=f"Auto-consumed for packaging ID: #{assoc.id}").delete()
                        assoc.delete()
                        
                    # Now record updated mixed carton rows
                    carton_label = request.POST.get("carton_label", "Mixed Carton")
                    item_ids = request.POST.getlist("item[]")
                    quantities = request.POST.getlist("quantity[]")
                    weights = request.POST.getlist("weight[]")
                    
                    packed_items_count = 0
                    total_qty = 0
                    
                    for idx, item_id in enumerate(item_ids):
                        if not item_id:
                            continue
                        qty = int(quantities[idx] or 0)
                        wt = float(weights[idx] or 0.0)
                        
                        if qty > 0:
                            item = Item.objects.get(id=item_id)
                            total_qty += qty
                            
                            # Create new parent transaction
                            new_tx = StockTransaction.objects.create(
                                transaction_type="packaging_in",
                                item=item,
                                quantity=qty,
                                weight=wt,
                                notes=f"Manual Packaging [Mixed Carton: {carton_label} - Ref: {ref_code}]{steps_str}"
                            )
                            
                            # If Set, consume components
                            if item.item_type == 'SET':
                                from inventory.models import ItemComposition
                                comps = ItemComposition.objects.filter(parent_item=item)
                                polishing_wh = Warehouse.objects.filter(code='POLISHING').first()
                                for comp in comps:
                                    needed = comp.quantity * qty
                                    StockTransaction.objects.create(
                                        item=comp.component_item,
                                        transaction_type=TransactionType.KITTING_CONSUME,
                                        quantity=needed,
                                        from_warehouse=polishing_wh,
                                        notes=f"Auto-consumed for packaging ID: #{new_tx.id}"
                                    )
                            packed_items_count += 1
                    messages.success(request, f"Updated Mixed Carton '{carton_label}' successfully.")
                    
                else:
                    # Symmetrically edit standard Single/Set transaction
                    item_id = request.POST.get("item")
                    quantity = int(request.POST.get("quantity") or 0)
                    weight = float(request.POST.get("weight") or 0.0)
                    
                    if item_id and quantity > 0:
                        item = Item.objects.get(id=item_id)
                        
                        # Delete old component consumption
                        StockTransaction.objects.filter(notes__contains=f"Auto-consumed for packaging ID: #{tx.id}").delete()
                        
                        # Update main transaction properties
                        tx.item = item
                        tx.quantity = quantity
                        tx.weight = weight
                        
                        # Set notes back, preserving any PACKED queue tags if possible, or keeping it manual edit
                        if tx.notes and tx.notes.startswith("PACKED"):
                            # Extract original PACKED tag
                            orig_packed = tx.notes.split(" [")[0] if " [" in tx.notes else tx.notes.split(" (")[0]
                            tx.notes = f"{orig_packed}{steps_str}"
                        else:
                            tx.notes = f"Manual Packaging{steps_str}"
                        tx.save()
                        
                        # Create new component consumptions if Set
                        if item.item_type == 'SET':
                            from inventory.models import ItemComposition
                            comps = ItemComposition.objects.filter(parent_item=item)
                            polishing_wh = Warehouse.objects.filter(code='POLISHING').first()
                            for comp in comps:
                                needed = comp.quantity * quantity
                                StockTransaction.objects.create(
                                    item=comp.component_item,
                                    transaction_type=TransactionType.KITTING_CONSUME,
                                    quantity=needed,
                                    from_warehouse=polishing_wh,
                                    notes=f"Auto-consumed for packaging ID: #{tx.id}"
                                )
                        messages.success(request, f"Updated packaging transaction for {item.name} successfully.")
                    else:
                        messages.error(request, "Invalid item or quantity for update.")
            except StockTransaction.DoesNotExist:
                messages.error(request, "Selected transaction not found.")
            return redirect("packaging")

        # Fallback to standard creation flow
        if pack_type in ["single", "set"]:
            item_id = request.POST.get("item")
            quantity = int(request.POST.get("quantity") or 0)
            weight = float(request.POST.get("weight") or 0.0)
            
            if item_id and quantity > 0:
                item = Item.objects.get(id=item_id)
                
                # Perform smart FIFO queue consumption of outstanding polishing entries
                outstanding = []
                polishing_in_entries = StockTransaction.objects.filter(
                    item=item,
                    transaction_type="polishing_in"
                ).order_by("created_at")
                
                for entry in polishing_in_entries:
                    already_done = StockTransaction.objects.filter(
                        notes__startswith=f"PACKED #{entry.id}"
                    ).exists()
                    if not already_done:
                        outstanding.append(entry)
                
                remaining_to_pack = quantity
                for entry in outstanding:
                    if remaining_to_pack <= 0:
                        break
                    
                    pack_qty = min(entry.quantity, remaining_to_pack)
                    pack_wt = round((pack_qty / entry.quantity) * entry.weight, 3) if entry.quantity > 0 else 0.0
                    
                    new_tx = StockTransaction.objects.create(
                        transaction_type="packaging_in",
                        item=item,
                        quantity=pack_qty,
                        weight=pack_wt,
                        notes=f"PACKED #{entry.id}{steps_str}"
                    )
                    
                    # If this is a SET item, consume components
                    if pack_type == "set" and item.item_type == 'SET':
                        from inventory.models import ItemComposition
                        comps = ItemComposition.objects.filter(parent_item=item)
                        polishing_wh = Warehouse.objects.filter(code='POLISHING').first()
                        for comp in comps:
                            needed = comp.quantity * pack_qty
                            StockTransaction.objects.create(
                                item=comp.component_item,
                                transaction_type=TransactionType.KITTING_CONSUME,
                                quantity=needed,
                                from_warehouse=polishing_wh,
                                notes=f"Auto-consumed for packaging ID: #{new_tx.id}"
                            )
                    
                    remaining_to_pack -= pack_qty
                
                # Record any remaining quantity as standard manual packaging
                if remaining_to_pack > 0:
                    rem_wt = max(0.0, weight - (quantity - remaining_to_pack) * (item.machining_weight or 0.0))
                    new_tx = StockTransaction.objects.create(
                        transaction_type="packaging_in",
                        item=item,
                        quantity=remaining_to_pack,
                        weight=round(rem_wt, 3),
                        notes=f"Manual Packaging{steps_str}"
                    )
                    
                    if pack_type == "set" and item.item_type == 'SET':
                        from inventory.models import ItemComposition
                        comps = ItemComposition.objects.filter(parent_item=item)
                        polishing_wh = Warehouse.objects.filter(code='POLISHING').first()
                        for comp in comps:
                            needed = comp.quantity * remaining_to_pack
                            StockTransaction.objects.create(
                                item=comp.component_item,
                                transaction_type=TransactionType.KITTING_CONSUME,
                                quantity=needed,
                                from_warehouse=polishing_wh,
                                notes=f"Auto-consumed for packaging ID: #{new_tx.id}"
                            )
                    
                messages.success(request, f"Successfully packed {quantity} pcs of {item.name} into ready stock!")
            else:
                messages.error(request, "Please select an item and enter a valid quantity.")
                
        elif pack_type == "mixed":
            carton_label = request.POST.get("carton_label", "Mixed Carton")
            item_ids = request.POST.getlist("item[]")
            quantities = request.POST.getlist("quantity[]")
            weights = request.POST.getlist("weight[]")
            
            packed_items_count = 0
            total_qty = 0
            mixed_ref = f"MIXED-{uuid.uuid4().hex[:6].upper()}"
            
            for idx, item_id in enumerate(item_ids):
                if not item_id:
                    continue
                qty = int(quantities[idx] or 0)
                wt = float(weights[idx] or 0.0)
                
                if qty > 0:
                    item = Item.objects.get(id=item_id)
                    total_qty += qty
                    
                    # FIFO queue consumption
                    outstanding = []
                    polishing_in_entries = StockTransaction.objects.filter(
                        item=item,
                        transaction_type="polishing_in"
                    ).order_by("created_at")
                    
                    for entry in polishing_in_entries:
                        already_done = StockTransaction.objects.filter(
                            notes__startswith=f"PACKED #{entry.id}"
                        ).exists()
                        if not already_done:
                            outstanding.append(entry)
                    
                    remaining_to_pack = qty
                    for entry in outstanding:
                        if remaining_to_pack <= 0:
                            break
                        
                        pack_qty = min(entry.quantity, remaining_to_pack)
                        pack_wt = round((pack_qty / entry.quantity) * entry.weight, 3) if entry.quantity > 0 else 0.0
                        
                        new_tx = StockTransaction.objects.create(
                            transaction_type="packaging_in",
                            item=item,
                            quantity=pack_qty,
                            weight=pack_wt,
                            notes=f"PACKED #{entry.id} [Mixed Carton: {carton_label} - Ref: {mixed_ref}]{steps_str}"
                        )
                        
                        if item.item_type == 'SET':
                            from inventory.models import ItemComposition
                            comps = ItemComposition.objects.filter(parent_item=item)
                            polishing_wh = Warehouse.objects.filter(code='POLISHING').first()
                            for comp in comps:
                                needed = comp.quantity * pack_qty
                                StockTransaction.objects.create(
                                    item=comp.component_item,
                                    transaction_type=TransactionType.KITTING_CONSUME,
                                    quantity=needed,
                                    from_warehouse=polishing_wh,
                                    notes=f"Auto-consumed for packaging ID: #{new_tx.id}"
                                )
                        remaining_to_pack -= pack_qty
                    
                    if remaining_to_pack > 0:
                        rem_wt = max(0.0, wt - (qty - remaining_to_pack) * (item.machining_weight or 0.0))
                        new_tx = StockTransaction.objects.create(
                            transaction_type="packaging_in",
                            item=item,
                            quantity=remaining_to_pack,
                            weight=round(rem_wt, 3),
                            notes=f"Manual Packaging [Mixed Carton: {carton_label} - Ref: {mixed_ref}]{steps_str}"
                        )
                        
                        if item.item_type == 'SET':
                            from inventory.models import ItemComposition
                            comps = ItemComposition.objects.filter(parent_item=item)
                            polishing_wh = Warehouse.objects.filter(code='POLISHING').first()
                            for comp in comps:
                                needed = comp.quantity * remaining_to_pack
                                StockTransaction.objects.create(
                                    item=comp.component_item,
                                    transaction_type=TransactionType.KITTING_CONSUME,
                                    quantity=needed,
                                    from_warehouse=polishing_wh,
                                    notes=f"Auto-consumed for packaging ID: #{new_tx.id}"
                                )
                    packed_items_count += 1
                    
            if packed_items_count > 0:
                messages.success(request, f"Successfully created Mixed Carton '{carton_label}' (Ref: {mixed_ref}) containing {total_qty} pcs across {packed_items_count} items!")
            else:
                messages.error(request, "No valid items or quantities were provided for the mixed carton.")
                
        return redirect("packaging")

    # =====================================
    # READY STOCK
    # =====================================
    active_tab = request.GET.get("tab", "entry")

    ready_stock = StockTransaction.objects.filter(
        transaction_type="packaging_in"
    ).order_by("-created_at")

    completed_ids = []

    for row in packaging_queue:
        done = StockTransaction.objects.filter(
            notes__startswith=f"PACKED #{row.id}"
        ).exists()
        if done:
            completed_ids.append(row.id)

    # Rich Ready Stock Analytics
    ready_analytics = []
    total_pieces = 0
    total_weight = 0.0
    total_cartons = 0
    
    from inventory.models import TransactionType
    
    for item in items:
        item_stock = services.get_stock_by_item(item)
        ready_qty = item_stock.get('ready', 0)
        
        if ready_qty > 0:
            cartons, loose = item.calculate_cartons_and_loose(ready_qty)
                
            # Precise weight calculations
            txs = StockTransaction.objects.filter(item=item)
            pack_wt = txs.filter(transaction_type=TransactionType.PACKAGING_IN).aggregate(total=Sum('weight'))['total'] or 0
            kit_wt = txs.filter(transaction_type=TransactionType.KITTING_PRODUCE).aggregate(total=Sum('weight'))['total'] or 0
            disp_wt = txs.filter(transaction_type=TransactionType.DISPATCH_OUT).aggregate(total=Sum('weight'))['total'] or 0
            ready_wt = max(0.0, (pack_wt + kit_wt) - disp_wt)
            
            # Status allocation
            if ready_qty > 500:
                status = "High Stock"
                status_color = "#10b981"
            elif ready_qty > 100:
                status = "Healthy"
                status_color = "#3b82f6"
            else:
                status = "Low Stock"
                status_color = "#f59e0b"
                
            # Last packed or dispatch action
            last_tx = StockTransaction.objects.filter(
                item=item,
                transaction_type__in=[TransactionType.PACKAGING_IN, TransactionType.DISPATCH_OUT]
            ).order_by('-created_at').first()
            last_activity = last_tx.created_at if last_tx else None
            
            ready_analytics.append({
                'item': item,
                'qty': ready_qty,
                'weight': round(ready_wt, 3),
                'cartons': cartons,
                'loose': loose,
                'status': status,
                'status_color': status_color,
                'last_activity': last_activity
            })
            
            total_pieces += ready_qty
            total_weight += ready_wt
            total_cartons += cartons

    # Sort items by quantity descending for top item analysis
    ready_analytics = sorted(ready_analytics, key=lambda x: x['qty'], reverse=True)

    # Group packaging queue by Job Worker / Worker and Category
    grouped_queue = {}
    for entry in packaging_queue:
        w_name = entry.job_worker.name if entry.job_worker else (entry.worker.name if entry.worker else "Internal/House")
        cat_name = entry.item.category.upper() if entry.item.category else "OTHER"
        
        if w_name not in grouped_queue:
            grouped_queue[w_name] = {}
        if cat_name not in grouped_queue[w_name]:
            grouped_queue[w_name][cat_name] = []
        
        grouped_queue[w_name][cat_name].append(entry)

    metrics = {
        'total_pieces': total_pieces,
        'total_weight': round(total_weight, 3),
        'total_cartons': total_cartons,
        'ready_items_count': len(ready_analytics),
        'active_queue_count': len(packaging_queue)
    }

    context = {
        "items": items,
        "single_items": single_items,
        "set_items": set_items,
        "packaging_queue": packaging_queue,
        "grouped_queue": grouped_queue,
        "ready_stock": ready_stock,
        "completed_ids": completed_ids,
        "active_tab": active_tab,
        "ready_analytics": ready_analytics,
        "metrics": metrics
    }

    return render(request, "packaging.html", context)


# =====================================================
# OLD URL SUPPORT
# =====================================================

def issue_machining(request):
    return redirect("machining_entry")

