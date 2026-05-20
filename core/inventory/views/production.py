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
    ItemWorkerAllocation,
    Carton,
    CartonItem
)
from inventory import services

# =====================================================
# DEFAULT WAREHOUSES
# =====================================================

def create_default_warehouses():
    warehouses = [
        ("CASTING", "Casting Stock"),
        ("MACHINING", "Machining Stock"),
        ("POLISHING", "Polished Stock"),
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

    # ======================================
    # GROUP MARK IN BUTTON (WIP Table 1-Click Receive)
    # ======================================
    mark_in_group = request.GET.get("mark_in_group")
    if mark_in_group == "true":
        worker_str = request.GET.get("worker_id")
        item_id = request.GET.get("item_id")
        rejections = int(request.GET.get("rejections") or 0)
        
        worker_obj = None
        job_worker_obj = None
        if worker_str:
            if worker_str.startswith("w_"):
                worker_obj = Worker.objects.filter(id=worker_str.replace("w_", "")).first()
            elif worker_str.startswith("jw_"):
                job_worker_obj = JobWorker.objects.filter(id=worker_str.replace("jw_", "")).first()
                
        if item_id:
            try:
                item_obj = Item.objects.get(id=item_id)
                out_txs = StockTransaction.objects.filter(
                    item=item_obj,
                    transaction_type="polishing_out"
                ).order_by("id")
                
                in_txs = StockTransaction.objects.filter(
                    item=item_obj,
                    transaction_type="polishing_in"
                )
                
                if worker_obj:
                    out_txs = out_txs.filter(worker=worker_obj)
                    in_txs = in_txs.filter(worker=worker_obj)
                elif job_worker_obj:
                    out_txs = out_txs.filter(job_worker=job_worker_obj)
                    in_txs = in_txs.filter(job_worker=job_worker_obj)
                else:
                    out_txs = out_txs.none()
                    in_txs = in_txs.none()
                    
                total_received = in_txs.aggregate(total=Sum('quantity'))['total'] or 0
                
                credit = total_received
                outstanding_txs = []
                for tx in out_txs:
                    if credit >= tx.quantity:
                        credit -= tx.quantity
                    elif credit > 0:
                        rem_qty = tx.quantity - credit
                        rem_wt = round((rem_qty / tx.quantity) * tx.weight, 3) if tx.quantity > 0 else 0.0
                        outstanding_txs.append((tx, rem_qty, rem_wt))
                        credit = 0
                    else:
                        outstanding_txs.append((tx, tx.quantity, tx.weight))
                        
                count = 0
                remaining_rejections = rejections
                for tx, q, w in outstanding_txs:
                    if q > 0:
                        tx_rejections = min(q, remaining_rejections)
                        StockTransaction.objects.create(
                            transaction_type="polishing_in",
                            item=tx.item,
                            worker=tx.worker,
                            job_worker=tx.job_worker,
                            quantity=q,
                            weight=w,
                            rejection_quantity=tx_rejections,
                            notes=f"IN for OUT #{tx.id}"
                        )
                        remaining_rejections -= tx_rejections
                        count += 1
                        
                if count > 0:
                    rejection_suffix = f" (with {rejections} rejections recorded)" if rejections > 0 else ""
                    messages.success(request, f"Successfully marked IN {count} entries, perfectly preserving original issue lot sizes and weights{rejection_suffix}!")
                else:
                    messages.info(request, "No outstanding polishing issues to mark IN.")
            except Item.DoesNotExist:
                messages.error(request, "Selected item not found.")
                
        return redirect("polishing_entry")

    mark_in_id = request.GET.get("mark_in")
    rejections = int(request.GET.get("rejections") or 0)

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
                    rejection_quantity=rejections,
                    notes=f"IN for OUT #{out_entry.id}"
                )
                rejection_suffix = f" with {rejections} rejections" if rejections > 0 else ""
                messages.success(
                    request,
                    f"Polishing entry marked IN successfully{rejection_suffix}."
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
                    # Creating new transaction(s) split by lot sizes
                    sub_transactions = []
                    if lots > 0 and lot_size > 0:
                        for _ in range(lots):
                            sub_transactions.append((lot_size, round((lot_size / total_quantity) * weight, 3) if total_quantity > 0 else 0.0))
                    if manual > 0:
                        sub_transactions.append((manual, round((manual / total_quantity) * weight, 3) if total_quantity > 0 else 0.0))
                    
                    if not sub_transactions:
                        sub_transactions = [(total_quantity, weight)]
                        
                    for sub_idx, (q, w) in enumerate(sub_transactions):
                        parent_tx = StockTransaction.objects.create(
                            transaction_type=direction,
                            item=item,
                            worker=worker_obj,
                            job_worker=job_worker_obj,
                            quantity=q,
                            weight=w
                        )

                        if direction == "polishing_out" and item.components.exists():
                            from inventory.models import Warehouse
                            from_wh = Warehouse.objects.filter(code='MACHINING').first()
                            
                            components = row.get("components", [])
                            for comp_row in components:
                                comp_id = comp_row.get("component_id")
                                qty_per_set = int(comp_row.get("qty_per_set") or 0)
                                extra_qty = int(comp_row.get("extra_qty") or 0)
                                
                                base_qty = qty_per_set * q
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
                                    
                                # Only attach component extra pieces once on the first sub-transaction
                                if extra_qty > 0 and sub_idx == 0:
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

                sub_transactions = []
                if lots > 0 and lot_size > 0:
                    for _ in range(lots):
                        sub_transactions.append((lot_size, round((lot_size / total_quantity) * weight, 3) if total_quantity > 0 else 0.0))
                if manual > 0:
                    sub_transactions.append((manual, round((manual / total_quantity) * weight, 3) if total_quantity > 0 else 0.0))
                
                if not sub_transactions:
                    sub_transactions = [(total_quantity, weight)]
                    
                for i, (q, w) in enumerate(sub_transactions):
                    parent_tx = StockTransaction.objects.create(
                        transaction_type=direction,
                        item=item,
                        worker=worker_obj,
                        job_worker=job_worker_obj,
                        quantity=q,
                        weight=w
                    )

                    # If it's a SET item, consume components (only for OUT transactions)
                    if direction == "polishing_out" and item.components.exists():
                        from inventory.models import ItemComposition, Warehouse
                        comps = ItemComposition.objects.filter(parent_item=item)
                        from_wh = Warehouse.objects.filter(code='MACHINING').first()
                        for comp in comps:
                            comp_total_qty = comp.quantity * q
                            StockTransaction.objects.create(
                                transaction_type="kitting_consume",
                                item=comp.component_item,
                                quantity=comp_total_qty,
                                from_warehouse=from_wh,
                                notes=f"Auto-consumed for Set: {item.name} (Polishing Out) [Set Transaction #{parent_tx.id}]"
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

    # Calculate Polishing WIP Stock - Grouped by Worker
    polishing_stock = {}
    for item in items:
        # 1. Internal Workers WIP for this item
        internal_wip_rows = StockTransaction.objects.filter(
            item=item, 
            transaction_type="polishing_out", 
            worker__isnull=False
        ).values('worker', 'worker__name').annotate(issued=Sum('quantity'))

        for row in internal_wip_rows:
            w_id = row['worker']
            w_name = f"{row['worker__name']} (INT)"
            received = StockTransaction.objects.filter(item=item, worker_id=w_id, transaction_type="polishing_in").aggregate(total=Sum('quantity'))['total'] or 0
            
            under_process = row['issued'] - received
            if under_process > 0:
                if w_name not in polishing_stock:
                    polishing_stock[w_name] = []
                    
                polishing_stock[w_name].append({
                    "item_id": item.id,
                    "item_code": item.code,
                    "item_name": item.name,
                    "worker_id": f"w_{w_id}",
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
                if jw_name not in polishing_stock:
                    polishing_stock[jw_name] = []
                    
                polishing_stock[jw_name].append({
                    "item_id": item.id,
                    "item_code": item.code,
                    "item_name": item.name,
                    "worker_id": f"jw_{jw_id}",
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

    def get_polishing_entry_remaining_qty(entry):
        packed_qty = StockTransaction.objects.filter(
            transaction_type="packaging_in",
            notes__contains=f"PACKED #{entry.id}"
        ).aggregate(total=Sum('quantity'))['total'] or 0
        remaining_qty = entry.quantity - packed_qty - (entry.rejection_quantity or 0)
        return max(0, remaining_qty)

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
                transaction_type="packaging_in",
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
                transaction_type="polishing_in"
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
                
                import re
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
                    transaction_type="packaging_in",
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
                transaction_type="polishing_in"
            )
            remaining_qty = get_polishing_entry_remaining_qty(polishing_entry)
            
            qty_to_move_str = request.GET.get("qty")
            qty_to_move = int(qty_to_move_str) if qty_to_move_str else remaining_qty
            qty_to_move = min(qty_to_move, remaining_qty)
            
            if qty_to_move > 0:
                weight_to_move = round((qty_to_move / polishing_entry.quantity) * polishing_entry.weight, 3) if polishing_entry.quantity > 0 else 0.0
                
                StockTransaction.objects.create(
                    transaction_type="packaging_in",
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
        
        import json
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
                
                import re
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
                    transaction_type="polishing_in"
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
                        if qty > 0:
                            try:
                                comp_item = Item.objects.get(id=comp_id_str)
                                comp_wt = round(qty * (comp_item.machining_weight or 0.0), 3)
                                StockTransaction.objects.create(
                                    transaction_type="packaging_in",
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
                                comp_details = ", ".join(f"{qty}x {Item.objects.get(id=cid).code}" for cid, qty in component_rejections.items() if qty > 0)
                                notes_suffix = f" (including component rejections replaced from buffer: {comp_details})"
                            else:
                                tx_rejections = rejections
                                notes_suffix = f" (including {rejections} rejections replaced from loose buffer)"
                        else:
                            notes_suffix = f" ({rejections} rejections deducted from jobworker)"
                    
                    new_tx = StockTransaction.objects.create(
                        transaction_type="packaging_in",
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
                        transaction_type="packaging_in",
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
                            transaction_type="polishing_in"
                        ).order_by("created_at")
                    else:
                        polishing_in_entries = StockTransaction.objects.filter(
                            item=item,
                            transaction_type="polishing_in"
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
                            transaction_type="packaging_in",
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
                            transaction_type="packaging_in",
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
        transaction_type="packaging_in",
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
    from django.db.models import Sum
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


# =====================================================
# OLD URL SUPPORT
# =====================================================

def issue_machining(request):
    return redirect("machining_entry")

