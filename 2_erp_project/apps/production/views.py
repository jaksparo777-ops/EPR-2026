import json
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.db.models import Sum, Q
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from core.security import require_role

from apps.products.models import Client, Item, Warehouse, TransactionType, ItemComposition
from apps.workforce.models import Worker, JobWorker
from apps.ledger_pay.models import ItemWorkerAllocation
from apps.production.models import StockTransaction
from apps.production.services import get_stock_by_item, get_overall_stock
from apps.products.views import merge_bom_component_details, sync_bom_worker_allocations

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

@login_required
@require_role(['Production Operator', 'System Admin'])
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

@login_required
@require_role(['Production Operator', 'System Admin'])
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

    # Bulk fetch overall stock levels to avoid N+1 queries
    from apps.production.services import get_stock_for_all_items
    bulk_stocks = get_stock_for_all_items()

    # Bulk calculate internal worker WIP for all items and workers
    internal_stats = StockTransaction.objects.filter(
        transaction_type__in=["machining_out", "machining_in"],
        worker__isnull=False
    ).values('item_id', 'worker_id', 'worker__name', 'transaction_type').annotate(
        qty_sum=Sum('quantity'),
        rej_sum=Sum('rejection_quantity')
    )
    
    from collections import defaultdict
    internal_wip_data = defaultdict(lambda: {'issued': 0, 'received': 0, 'rejected': 0, 'worker_name': ''})
    for s in internal_stats:
        key = (s['item_id'], s['worker_id'])
        internal_wip_data[key]['worker_name'] = s['worker__name']
        if s['transaction_type'] == 'machining_out':
            internal_wip_data[key]['issued'] += s['qty_sum'] or 0
        elif s['transaction_type'] == 'machining_in':
            internal_wip_data[key]['received'] += s['qty_sum'] or 0
            internal_wip_data[key]['rejected'] += s['rej_sum'] or 0

    # Bulk calculate external job worker WIP for all items and workers
    external_stats = StockTransaction.objects.filter(
        transaction_type__in=["machining_out", "machining_in"],
        job_worker__isnull=False
    ).values('item_id', 'job_worker_id', 'job_worker__name', 'transaction_type').annotate(
        qty_sum=Sum('quantity'),
        rej_sum=Sum('rejection_quantity')
    )
    
    external_wip_data = defaultdict(lambda: {'issued': 0, 'received': 0, 'rejected': 0, 'worker_name': ''})
    for s in external_stats:
        key = (s['item_id'], s['job_worker_id'])
        external_wip_data[key]['worker_name'] = s['job_worker__name']
        if s['transaction_type'] == 'machining_out':
            external_wip_data[key]['issued'] += s['qty_sum'] or 0
        elif s['transaction_type'] == 'machining_in':
            external_wip_data[key]['received'] += s['qty_sum'] or 0
            external_wip_data[key]['rejected'] += s['rej_sum'] or 0

    machining_stock = []

    for item in items:
        item_stock = bulk_stocks.get(item.id, {'machining': 0})
        available_qty = item_stock.get('machining', 0)

        # 1. Internal Workers WIP for this item
        for (item_id, w_id), data in internal_wip_data.items():
            if item_id == item.id:
                under_process = data['issued'] - data['received'] - data['rejected']
                if under_process > 0:
                    machining_stock.append({
                        "item_id": item.id,
                        "item_name": f"{item.code} - {item.name}",
                        "item_category": item.get_category_display(),
                        "worker_id": f"w_{w_id}",
                        "worker_name": f"{data['worker_name']} (INT)",
                        "under_process": under_process,
                        "available_qty": available_qty
                    })

        # 2. External Job Workers WIP for this item
        for (item_id, jw_id), data in external_wip_data.items():
            if item_id == item.id:
                under_process = data['issued'] - data['received'] - data['rejected']
                if under_process > 0:
                    machining_stock.append({
                        "item_id": item.id,
                        "item_name": f"{item.code} - {item.name}",
                        "item_category": item.get_category_display(),
                        "worker_id": f"jw_{jw_id}",
                        "worker_name": data['worker_name'],
                        "under_process": under_process,
                        "available_qty": available_qty
                    })

    # Bulk calculate internal worker overall metrics
    internal_overall = StockTransaction.objects.filter(
        transaction_type__in=["machining_out", "machining_in"],
        worker__isnull=False
    ).values('worker_id', 'worker__name', 'transaction_type').annotate(
        qty_sum=Sum('quantity'),
        rej_sum=Sum('rejection_quantity')
    )
    
    internal_wip_totals = defaultdict(lambda: {'issued': 0, 'received': 0, 'rejected': 0, 'worker_name': ''})
    for s in internal_overall:
        w_id = s['worker_id']
        internal_wip_totals[w_id]['worker_name'] = s['worker__name']
        if s['transaction_type'] == 'machining_out':
            internal_wip_totals[w_id]['issued'] += s['qty_sum'] or 0
        elif s['transaction_type'] == 'machining_in':
            internal_wip_totals[w_id]['received'] += s['qty_sum'] or 0
            internal_wip_totals[w_id]['rejected'] += s['rej_sum'] or 0

    # Bulk calculate external job worker overall metrics
    external_overall = StockTransaction.objects.filter(
        transaction_type__in=["machining_out", "machining_in"],
        job_worker__isnull=False
    ).values('job_worker_id', 'job_worker__name', 'transaction_type').annotate(
        qty_sum=Sum('quantity'),
        rej_sum=Sum('rejection_quantity')
    )
    
    external_wip_totals = defaultdict(lambda: {'issued': 0, 'received': 0, 'rejected': 0, 'worker_name': ''})
    for s in external_overall:
        jw_id = s['job_worker_id']
        external_wip_totals[jw_id]['worker_name'] = s['job_worker__name']
        if s['transaction_type'] == 'machining_out':
            external_wip_totals[jw_id]['issued'] += s['qty_sum'] or 0
        elif s['transaction_type'] == 'machining_in':
            external_wip_totals[jw_id]['received'] += s['qty_sum'] or 0
            external_wip_totals[jw_id]['rejected'] += s['rej_sum'] or 0

    worker_wip = []

    # Internal Workers
    for worker in workers:
        totals_data = internal_wip_totals.get(worker.id, {'issued': 0, 'received': 0, 'rejected': 0})
        issued = totals_data['issued']
        received = totals_data['received']
        rejected = totals_data['rejected']
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
        totals_data = external_wip_totals.get(jw.id, {'issued': 0, 'received': 0, 'rejected': 0})
        issued = totals_data['issued']
        received = totals_data['received']
        rejected = totals_data['rejected']
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

@login_required
@require_role(['Production Operator', 'System Admin'])
def polishing_entry(request):
    workers = Worker.objects.filter(process="polishing", active=True)
    job_workers = JobWorker.objects.filter(process="polishing", active=True)
    items = Item.objects.all()

    # Optimize N+1 queries by using bulk stock getter
    from apps.production.services import get_stock_for_all_items
    bulk_stocks = get_stock_for_all_items()

    piece_stock = {}
    set_capacity = {}

    for item in items:
        item_stock = bulk_stocks.get(item.id, {'machining': 0})
        current_machining_stock = item_stock.get('machining', 0)
        
        piece_stock[item.id] = current_machining_stock
        item.current_stock = current_machining_stock

    # Batch load all BOM item compositions to avoid N+1 queries
    from collections import defaultdict
    all_comps = defaultdict(list)
    for comp in ItemComposition.objects.all().select_related('component_item'):
        all_comps[comp.parent_item_id].append(comp)

    for item in items:
        comps = all_comps.get(item.id, [])
        if comps:
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

    available_data = {**piece_stock, **set_capacity}

    # DELETE TRANSACTION
    delete_id = request.GET.get("delete_id")
    if delete_id:
        try:
            tx = StockTransaction.objects.get(id=delete_id)
            StockTransaction.objects.filter(notes__startswith=f"Auto-consumed for Set Transaction #{tx.id}").delete()
            
            comp_extras = StockTransaction.objects.filter(notes=f"Component Extra for Set Transaction #{tx.id}")
            for comp_tx in comp_extras:
                StockTransaction.objects.filter(notes=f"IN for OUT #{comp_tx.id}").delete()
            comp_extras.delete()
            
            StockTransaction.objects.filter(notes=f"IN for OUT #{tx.id}").delete()
            tx.delete()
            messages.success(request, "Polishing entry and all associated auto-consumed/receipt transactions deleted successfully.")
        except StockTransaction.DoesNotExist:
            messages.error(request, "Selected transaction not found.")
        return redirect("polishing_entry")

    # GROUP MARK IN BUTTON (WIP Table 1-Click Receive)
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

                        # Delete old component extras
                        comp_extras = StockTransaction.objects.filter(notes=f"Component Extra for Set Transaction #{tx.id}")
                        for comp_tx in comp_extras:
                            StockTransaction.objects.filter(notes=f"IN for OUT #{comp_tx.id}").delete()
                        comp_extras.delete()

                        # Re-create child auto-consumption and component extras
                        if direction == "polishing_out" and item.components.exists():
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

                    if direction == "polishing_out" and item.components.exists():
                        from_wh = Warehouse.objects.filter(code='MACHINING').first()
                        for comp in item.components.all():
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
# KITTING / ASSEMBLY
# =====================================================

@login_required
@require_role(['Production Operator', 'System Admin'])
def assembly_view(request):
    if request.method == 'POST':
        form_type = request.POST.get('form_type')
        
        if form_type == 'bom':
            parent_id = request.POST.get('parent_item_id')
            new_set_name = request.POST.get('new_set_name')
            
            try:
                if new_set_name:
                    code = request.POST.get('new_set_code', '').strip()
                    if Item.objects.filter(code=code).exists():
                        messages.error(request, f"Error saving BOM: An item with code '{code}' already exists in the Item Master. Please choose a unique code.")
                        return redirect(f"{reverse('master_data')}?tab=items&sub=bom")
                    
                    parent_item = Item.objects.create(
                        name=new_set_name,
                        code=code,
                        category=request.POST.get('category', 'OTHER'),
                        sub_category=request.POST.get('sub_category', ''),
                        variant=request.POST.get('variant', ''),
                        item_type='SET',
                        casting_required=request.POST.get('casting_required') == 'on',
                        machining_required=request.POST.get('machining_required') == 'on',
                        polishing_required=request.POST.get('polishing_required') == 'on',
                        packing_required=request.POST.get('packing_required') == 'on'
                    )
                else:
                    parent_item = Item.objects.get(id=parent_id)
                    parent_item.category = request.POST.get('category', parent_item.category)
                    parent_item.sub_category = request.POST.get('sub_category', parent_item.sub_category)
                    parent_item.variant = request.POST.get('variant', parent_item.variant)
                    
                    if any(x in request.POST for x in ['casting_required', 'machining_required', 'polishing_required', 'packing_required']):
                        parent_item.casting_required = request.POST.get('casting_required') == 'on'
                        parent_item.machining_required = request.POST.get('machining_required') == 'on'
                        parent_item.polishing_required = request.POST.get('polishing_required') == 'on'
                        parent_item.packing_required = request.POST.get('packing_required') == 'on'

                ItemComposition.objects.filter(parent_item=parent_item).delete()
                parent_item.item_type = 'SET'
                parent_item.save()

                comp_ids = request.POST.getlist('component_id[]')
                comp_qtys = request.POST.getlist('component_qty[]')
                
                total_weight = 0
                for cid, qty in zip(comp_ids, comp_qtys):
                    if cid and qty:
                        comp_obj = Item.objects.get(id=cid)
                        qty_int = int(qty)
                        total_weight += (comp_obj.machining_weight * qty_int)
                        
                        ItemComposition.objects.create(
                            parent_item=parent_item,
                            component_item=comp_obj,
                            quantity=qty_int
                        )
                
                merge_bom_component_details(parent_item)
                sync_bom_worker_allocations(parent_item)
                
                messages.success(request, f"BOM for {parent_item.name} saved successfully.")
                return redirect(f"{reverse('master_data')}?tab=items&sub=bom")
            except Exception as e:
                messages.error(request, f"Error saving BOM: {str(e)}")
                return redirect(f"{reverse('master_data')}?tab=items&sub=bom")
                
        else:
            item_id = request.POST.get('item_id')
            quantity = int(request.POST.get('quantity') or 0)
            
            if not item_id or quantity <= 0:
                messages.error(request, "Please select an item and enter a valid quantity.")
                return redirect(f"{reverse('master_data')}?tab=items&sub=bom&kitting_action=true")

            try:
                item = Item.objects.get(id=item_id)
                compositions = item.components.all()
                
                can_assemble = True
                missing = []
                for comp in compositions:
                    stock = get_stock_by_item(comp.component_item)
                    needed = comp.quantity * quantity
                    if stock['polishing'] < needed:
                        can_assemble = False
                        missing.append(f"{comp.component_item.name} (Need {needed}, Have {stock['polishing']})")
                
                if not can_assemble:
                    messages.error(request, f"Insufficient component stock: {', '.join(missing)}")
                else:
                    from_wh = Warehouse.objects.filter(code='POLISHING').first()
                    for comp in compositions:
                        StockTransaction.objects.create(
                            item=comp.component_item,
                            transaction_type=TransactionType.KITTING_CONSUME,
                            quantity=comp.quantity * quantity,
                            from_warehouse=from_wh
                        )
                    StockTransaction.objects.create(
                        item=item,
                        transaction_type=TransactionType.KITTING_PRODUCE,
                        quantity=quantity
                    )
                    messages.success(request, f"Successfully assembled {quantity} units of {item.name}.")
                return redirect(f"{reverse('master_data')}?tab=items&sub=bom&kitting_action=true")
            except Exception as e:
                messages.error(request, f"Error: {str(e)}")
                return redirect(f"{reverse('master_data')}?tab=items&sub=bom&kitting_action=true")
            
    return redirect(f"{reverse('master_data')}?tab=items&sub=bom")

# =====================================================
# STOCK PAGES (logistics / view transitions)
# =====================================================

@login_required
@require_role(['Production Operator', 'System Admin'])
def casting_stock(request):
    from collections import defaultdict

    casting_txs = StockTransaction.objects.filter(
        transaction_type__in=["casting_in", "casting_entry"]
    ).select_related("client", "item")

    machining_out_txs = StockTransaction.objects.filter(
        transaction_type="machining_out"
    ).select_related("client", "item")

    grouped = defaultdict(lambda: {
        "cast_qty": 0,
        "cast_weight": 0.0,
        "issued_qty": 0,
        "issued_weight": 0.0,
    })

    for tx in casting_txs:
        client_name = tx.client.name if tx.client else "NO CLIENT"
        item_code = tx.item.code if tx.item else "-"
        item_name = tx.item.name if tx.item else "-"
        key = (client_name, item_code, item_name)
        
        grouped[key]["cast_qty"] += tx.quantity or 0
        grouped[key]["cast_weight"] += float(tx.weight or 0)

    for tx in machining_out_txs:
        client_name = tx.client.name if tx.client else "NO CLIENT"
        item_code = tx.item.code if tx.item else "-"
        item_name = tx.item.name if tx.item else "-"
        key = (client_name, item_code, item_name)

        grouped[key]["issued_qty"] += tx.quantity or 0
        grouped[key]["issued_weight"] += float(tx.weight or 0)

    rows = []
    total_cast_pcs = 0
    total_cast_wt = 0.0
    total_issued_pcs = 0
    total_issued_wt = 0.0
    total_stock_pcs = 0
    total_stock_wt = 0.0

    for key, value in grouped.items():
        cast_qty = value["cast_qty"]
        cast_wt = round(value["cast_weight"], 3)
        issued_qty = value["issued_qty"]
        issued_wt = round(value["issued_weight"], 3)
        
        stock_qty = max(0, cast_qty - issued_qty)
        stock_wt = max(0.0, round(value["cast_weight"] - value["issued_weight"], 3))

        rows.append({
            "client": key[0],
            "code": key[1],
            "item": key[2],
            "cast_pcs": cast_qty,
            "cast_weight": cast_wt,
            "issued_pcs": issued_qty,
            "issued_weight": issued_wt,
            "pcs": stock_qty,
            "weight": stock_wt,
        })

        total_cast_pcs += cast_qty
        total_cast_wt += value["cast_weight"]
        total_issued_pcs += issued_qty
        total_issued_wt += value["issued_weight"]
        total_stock_pcs += stock_qty
        total_stock_wt += (value["cast_weight"] - value["issued_weight"])

    client_stock = defaultdict(int)
    item_stock = defaultdict(lambda: {"cast": 0, "issued": 0, "net": 0})

    for row in rows:
        client_stock[row["client"]] += row["pcs"]
        item_stock[row["item"]]["cast"] += row["cast_pcs"]
        item_stock[row["item"]]["issued"] += row["issued_pcs"]
        item_stock[row["item"]]["net"] += row["pcs"]

    graph_client_labels = list(client_stock.keys())
    graph_client_values = list(client_stock.values())

    graph_item_labels = list(item_stock.keys())
    graph_item_cast = [d["cast"] for d in item_stock.values()]
    graph_item_issued = [d["issued"] for d in item_stock.values()]
    graph_item_net = [d["net"] for d in item_stock.values()]

    first_day_of_month = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_prod_qty = StockTransaction.objects.filter(
        transaction_type__in=["casting_in", "casting_entry"],
        created_at__gte=first_day_of_month
    ).aggregate(total=Sum('quantity'))['total'] or 0

    context = {
        "rows": rows,
        "total_cast_pcs": total_cast_pcs,
        "total_cast_wt": round(total_cast_wt, 3),
        "total_issued_pcs": total_issued_pcs,
        "total_issued_wt": round(total_issued_wt, 3),
        "total_stock_pcs": max(0, total_stock_pcs),
        "total_stock_wt": max(0.0, round(total_stock_wt, 3)),
        "month_prod_qty": month_prod_qty,
        "graph_client_labels": graph_client_labels,
        "graph_client_values": graph_client_values,
        "graph_item_labels": graph_item_labels,
        "graph_item_cast": graph_item_cast,
        "graph_item_issued": graph_item_issued,
        "graph_item_net": graph_item_net,
    }

    return render(request, "casting_stock.html", context)

@login_required
@require_role(['Production Operator', 'System Admin'])
def machining_stock(request):
    from collections import defaultdict

    txs = StockTransaction.objects.filter(
        transaction_type__in=["machining_out", "machining_in"]
    ).select_related("worker", "job_worker", "item")

    grouped = defaultdict(lambda: {
        "issued_qty": 0,
        "issued_weight": 0.0,
        "received_qty": 0,
        "received_weight": 0.0,
    })

    for tx in txs:
        if tx.job_worker:
            worker_name = tx.job_worker.name
        elif tx.worker:
            worker_name = tx.worker.name
        else:
            worker_name = "NO WORKER"

        item_code = tx.item.code if tx.item else "-"
        item_name = tx.item.name if tx.item else "-"
        key = (worker_name, item_code, item_name)

        if tx.transaction_type == "machining_out":
            grouped[key]["issued_qty"] += tx.quantity or 0
            grouped[key]["issued_weight"] += float(tx.weight or 0)
        elif tx.transaction_type == "machining_in":
            grouped[key]["received_qty"] += tx.quantity or 0
            grouped[key]["received_weight"] += float(tx.weight or 0)

    rows = []
    total_issued_pcs = 0
    total_issued_wt = 0.0
    total_received_pcs = 0
    total_received_wt = 0.0
    total_wip_pcs = 0
    total_wip_wt = 0.0

    for key, val in grouped.items():
        issued_qty = val["issued_qty"]
        issued_wt = round(val["issued_weight"], 3)
        received_qty = val["received_qty"]
        received_wt = round(val["received_weight"], 3)
        wip_qty = max(0, issued_qty - received_qty)
        wip_wt = max(0.0, round(val["issued_weight"] - val["received_weight"], 3))

        rows.append({
            "worker": key[0],
            "code": key[1],
            "item": key[2],
            "issued_pcs": issued_qty,
            "issued_weight": issued_wt,
            "received_pcs": received_qty,
            "received_weight": received_wt,
            "pcs": wip_qty,
            "weight": wip_wt,
        })

        total_issued_pcs += issued_qty
        total_issued_wt += val["issued_weight"]
        total_received_pcs += received_qty
        total_received_wt += val["received_weight"]
        total_wip_pcs += wip_qty
        total_wip_wt += (val["issued_weight"] - val["received_weight"])

    worker_stock = defaultdict(int)
    item_stock = defaultdict(lambda: {"issued": 0, "received": 0, "net": 0})

    for row in rows:
        worker_stock[row["worker"]] += row["pcs"]
        item_stock[row["item"]]["issued"] += row["issued_pcs"]
        item_stock[row["item"]]["received"] += row["received_pcs"]
        item_stock[row["item"]]["net"] += row["pcs"]

    graph_worker_labels = list(worker_stock.keys())
    graph_worker_values = list(worker_stock.values())

    graph_item_labels = list(item_stock.keys())
    graph_item_issued = [d["issued"] for d in item_stock.values()]
    graph_item_received = [d["received"] for d in item_stock.values()]
    graph_item_net = [d["net"] for d in item_stock.values()]

    first_day_of_month = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_prod_qty = StockTransaction.objects.filter(
        transaction_type="machining_in",
        created_at__gte=first_day_of_month
    ).aggregate(total=Sum('quantity'))['total'] or 0

    context = {
        "rows": rows,
        "total_issued_pcs": total_issued_pcs,
        "total_issued_wt": round(total_issued_wt, 3),
        "total_received_pcs": total_received_pcs,
        "total_received_wt": round(total_received_wt, 3),
        "total_wip_pcs": max(0, total_wip_pcs),
        "total_wip_wt": max(0.0, round(total_wip_wt, 3)),
        "month_prod_qty": month_prod_qty,
        "graph_worker_labels": graph_worker_labels,
        "graph_worker_values": graph_worker_values,
        "graph_item_labels": graph_item_labels,
        "graph_item_issued": graph_item_issued,
        "graph_item_received": graph_item_received,
        "graph_item_net": graph_item_net,
    }

    return render(request, "machining_stock.html", context)

@login_required
@require_role(['Production Operator', 'System Admin'])
def polishing_stock(request):
    from collections import defaultdict

    txs = StockTransaction.objects.filter(
        transaction_type__in=["polishing_out", "polishing_in"]
    ).select_related("worker", "job_worker", "item")

    grouped = defaultdict(lambda: {
        "issued_qty": 0,
        "issued_weight": 0.0,
        "received_qty": 0,
        "received_weight": 0.0,
    })

    for tx in txs:
        if tx.job_worker:
            worker_name = tx.job_worker.name
        elif tx.worker:
            worker_name = tx.worker.name
        else:
            worker_name = "NO WORKER"

        item_code = tx.item.code if tx.item else "-"
        item_name = tx.item.name if tx.item else "-"
        key = (worker_name, item_code, item_name)

        if tx.transaction_type == "polishing_out":
            grouped[key]["issued_qty"] += tx.quantity or 0
            grouped[key]["issued_weight"] += float(tx.weight or 0)
        elif tx.transaction_type == "polishing_in":
            grouped[key]["received_qty"] += tx.quantity or 0
            grouped[key]["received_weight"] += float(tx.weight or 0)

    rows = []
    total_issued_pcs = 0
    total_issued_wt = 0.0
    total_received_pcs = 0
    total_received_wt = 0.0
    total_wip_pcs = 0
    total_wip_wt = 0.0

    for key, val in grouped.items():
        issued_qty = val["issued_qty"]
        issued_wt = round(val["issued_weight"], 3)
        received_qty = val["received_qty"]
        received_wt = round(val["received_weight"], 3)
        wip_qty = max(0, issued_qty - received_qty)
        wip_wt = max(0.0, round(val["issued_weight"] - val["received_weight"], 3))

        rows.append({
            "worker": key[0],
            "code": key[1],
            "item": key[2],
            "issued_pcs": issued_qty,
            "issued_weight": issued_wt,
            "received_pcs": received_qty,
            "received_weight": received_wt,
            "pcs": wip_qty,
            "weight": wip_wt,
        })

        total_issued_pcs += issued_qty
        total_issued_wt += val["issued_weight"]
        total_received_pcs += received_qty
        total_received_wt += val["received_weight"]
        total_wip_pcs += wip_qty
        total_wip_wt += (val["issued_weight"] - val["received_weight"])

    worker_stock = defaultdict(int)
    item_stock = defaultdict(lambda: {"issued": 0, "received": 0, "net": 0})

    for row in rows:
        worker_stock[row["worker"]] += row["pcs"]
        item_stock[row["item"]]["issued"] += row["issued_pcs"]
        item_stock[row["item"]]["received"] += row["received_pcs"]
        item_stock[row["item"]]["net"] += row["pcs"]

    graph_worker_labels = list(worker_stock.keys())
    graph_worker_values = list(worker_stock.values())

    graph_item_labels = list(item_stock.keys())
    graph_item_issued = [d["issued"] for d in item_stock.values()]
    graph_item_received = [d["received"] for d in item_stock.values()]
    graph_item_net = [d["net"] for d in item_stock.values()]

    first_day_of_month = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_prod_qty = StockTransaction.objects.filter(
        transaction_type="polishing_in",
        created_at__gte=first_day_of_month
    ).aggregate(total=Sum('quantity'))['total'] or 0

    context = {
        "rows": rows,
        "total_issued_pcs": total_issued_pcs,
        "total_issued_wt": round(total_issued_wt, 3),
        "total_received_pcs": total_received_pcs,
        "total_received_wt": round(total_received_wt, 3),
        "total_wip_pcs": max(0, total_wip_pcs),
        "total_wip_wt": max(0.0, round(total_wip_wt, 3)),
        "month_prod_qty": month_prod_qty,
        "graph_worker_labels": graph_worker_labels,
        "graph_worker_values": graph_worker_values,
        "graph_item_labels": graph_item_labels,
        "graph_item_issued": graph_item_issued,
        "graph_item_received": graph_item_received,
        "graph_item_net": graph_item_net,
    }

    return render(request, "polishing_stock.html", context)

@login_required
@require_role(['Production Operator', 'System Admin'])
def ready_stock(request):
    from collections import defaultdict
    from apps.logistics.models import Carton

    txs = StockTransaction.objects.filter(
        transaction_type__in=["packaging_in", "kitting_produce", "dispatch_out"]
    ).select_related("item")

    grouped = defaultdict(lambda: {
        "received_qty": 0,
        "received_weight": 0.0,
        "dispatched_qty": 0,
        "dispatched_weight": 0.0,
    })

    for tx in txs:
        item_code = tx.item.code if tx.item else "-"
        item_name = tx.item.name if tx.item else "-"
        key = (item_code, item_name)

        if tx.transaction_type in ["packaging_in", "kitting_produce"]:
            grouped[key]["received_qty"] += tx.quantity or 0
            grouped[key]["received_weight"] += float(tx.weight or 0)
        elif tx.transaction_type == "dispatch_out":
            grouped[key]["dispatched_qty"] += tx.quantity or 0
            grouped[key]["dispatched_weight"] += float(tx.weight or 0)

    rows = []
    total_received_pcs = 0
    total_received_wt = 0.0
    total_dispatched_pcs = 0
    total_dispatched_wt = 0.0
    total_net_pcs = 0
    total_net_wt = 0.0

    for key, val in grouped.items():
        received_qty = val["received_qty"]
        received_wt = round(val["received_weight"], 3)
        dispatched_qty = val["dispatched_qty"]
        dispatched_wt = round(val["dispatched_weight"], 3)
        net_qty = max(0, received_qty - dispatched_qty)
        net_wt = max(0.0, round(val["received_weight"] - val["dispatched_weight"], 3))

        rows.append({
            "code": key[0],
            "item": key[1],
            "received_pcs": received_qty,
            "received_weight": received_wt,
            "dispatched_pcs": dispatched_qty,
            "dispatched_weight": dispatched_wt,
            "pcs": net_qty,
            "weight": net_wt,
        })

        total_received_pcs += received_qty
        total_received_wt += val["received_weight"]
        total_dispatched_pcs += dispatched_qty
        total_dispatched_wt += val["dispatched_weight"]
        total_net_pcs += net_qty
        total_net_wt += (val["received_weight"] - val["dispatched_weight"])

    item_stock = defaultdict(lambda: {"received": 0, "dispatched": 0, "net": 0})

    for row in rows:
        item_stock[row["item"]]["received"] += row["received_pcs"]
        item_stock[row["item"]]["dispatched"] += row["dispatched_pcs"]
        item_stock[row["item"]]["net"] += row["pcs"]

    graph_item_labels = list(item_stock.keys())
    graph_item_values = [d["net"] for d in item_stock.values()]

    graph_item_received = [d["received"] for d in item_stock.values()]
    graph_item_dispatched = [d["dispatched"] for d in item_stock.values()]

    first_day_of_month = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_prod_qty = StockTransaction.objects.filter(
        transaction_type__in=["packaging_in", "kitting_produce"],
        created_at__gte=first_day_of_month
    ).aggregate(total=Sum('quantity'))['total'] or 0

    available_cartons = Carton.objects.filter(status='READY').order_by('-created_at')

    context = {
        "rows": rows,
        "available_cartons": available_cartons,
        "total_received_pcs": total_received_pcs,
        "total_received_wt": round(total_received_wt, 3),
        "total_dispatched_pcs": total_dispatched_pcs,
        "total_dispatched_wt": round(total_dispatched_wt, 3),
        "total_net_pcs": max(0, total_net_pcs),
        "total_net_wt": max(0.0, round(total_net_wt, 3)),
        "month_prod_qty": month_prod_qty,
        "graph_item_labels": graph_item_labels,
        "graph_item_values": graph_item_values,
        "graph_item_received": graph_item_received,
        "graph_item_dispatched": graph_item_dispatched,
    }

    return render(request, "ready_stock.html", context)

@login_required
@require_role(['Production Operator', 'System Admin'])
def issue_machining(request):
    return redirect("machining_entry")
