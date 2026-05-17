import json
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Sum, Q
from django.utils import timezone

from .models import (
    Client,
    Item,
    Worker,
    JobWorker,
    Warehouse,
    StockTransaction,
    TransactionType,
    ItemWorkerAllocation,
    LaborPayment,
    Attendance
)
from .forms import CastingEntryForm, ItemForm, ClientForm, WorkerForm, JobWorkerForm
from . import services


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
# STOCK HELPERS
# =====================================================

def get_casting_stock(item):

    inward = StockTransaction.objects.filter(
        item=item,
        transaction_type__in=[
            "casting_in",
            "casting_entry"
        ]
    ).aggregate(total=Sum("quantity"))["total"] or 0

    outward = StockTransaction.objects.filter(
        item=item,
        transaction_type="machining_out"
    ).aggregate(total=Sum("quantity"))["total"] or 0

    return inward - outward


def get_machining_stock(item):

    inward = StockTransaction.objects.filter(
        item=item,
        transaction_type="machining_in"
    ).aggregate(total=Sum("quantity"))["total"] or 0

    outward = StockTransaction.objects.filter(
        item=item,
        transaction_type="polishing_out"
    ).aggregate(total=Sum("quantity"))["total"] or 0

    return inward - outward


def get_polishing_stock(item):

    inward = StockTransaction.objects.filter(
        item=item,
        transaction_type="polishing_in"
    ).aggregate(total=Sum("quantity"))["total"] or 0

    outward = StockTransaction.objects.filter(
        item=item,
        transaction_type="packaging_in"
    ).aggregate(total=Sum("quantity"))["total"] or 0

    return inward - outward


def get_ready_stock(item):

    inward = StockTransaction.objects.filter(
        item=item,
        transaction_type="packaging_in"
    ).aggregate(
        total=Sum("quantity")
    )["total"] or 0

    outward = StockTransaction.objects.filter(
        item=item,
        transaction_type="dispatch_out"
    ).aggregate(
        total=Sum("quantity")
    )["total"] or 0

    return inward - outward
# =====================================================
# DASHBOARD
# =====================================================

def dashboard(request):

    create_default_warehouses()

    # Use optimized service for overall stock metrics
    stock = services.get_overall_stock()

    items = Item.objects.all()
    stock_rows = []

    for item in items:
        # Get stock for each item at READY stage
        item_stock = services.get_stock_by_item(item)
        ready_qty = item_stock['ready']

        if ready_qty > 0:
            cartons = 0
            loose_pieces = ready_qty
            if item.lot_with_box and item.lot_with_box > 0:
                cartons = ready_qty // item.lot_with_box
                loose_pieces = ready_qty % item.lot_with_box

            stock_rows.append({
                "code": item.code,
                "item": item,  # Passing the whole item object
                "cartons": cartons,
                "loose_pieces": loose_pieces,
                "total_pieces": ready_qty,
                "weight": round(ready_qty * float(item.machining_weight or 0), 3)
            })

    today = timezone.now().date()

    today_casting = StockTransaction.objects.filter(
        transaction_type=TransactionType.CASTING_ENTRY,
        created_at__date=today
    )

    today_heats = today_casting.values("heat_no").distinct().count()
    today_pieces = today_casting.aggregate(total=Sum("quantity"))["total"] or 0
    today_weight = today_casting.aggregate(total=Sum("weight"))["total"] or 0

    today_dispatch = StockTransaction.objects.filter(
        transaction_type=TransactionType.DISPATCH_OUT,
        created_at__date=today
    ).select_related("item")
    
    dispatch_pieces = 0
    dispatch_cartons = 0
    dispatch_weight = 0

    for tx in today_dispatch:
        dispatch_pieces += tx.quantity or 0
        dispatch_weight += float(tx.weight or 0)
        if tx.item and tx.item.lot_with_box and tx.item.lot_with_box > 0:
            dispatch_cartons += (tx.quantity or 0) // tx.item.lot_with_box

    context = {
        "casting_stock": stock['casting_qty'],
        "casting_weight": stock['casting_weight'],
        "machining_stock": stock['machining_qty'],
        "machining_weight": stock['machining_weight'],
        "polishing_stock": stock['polishing_qty'],
        "polishing_weight": stock['polishing_weight'],
        "ready_stock": stock['ready_qty'],
        "ready_weight": stock['ready_weight'],

        "today_heats": today_heats,
        "today_pieces": today_pieces,
        "today_weight": today_weight,

        "dispatch_cartons": dispatch_cartons,
        "dispatch_pieces": dispatch_pieces,
        "dispatch_weight": dispatch_weight,

        "stock_rows": stock_rows,
    }

    return render(request, "dashboard.html", context)

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
    from django.utils import timezone
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

    if request.method == "POST":

        direction = request.POST.get("direction")
        item_id = request.POST.get("item")
        worker_id = request.POST.get("worker")
        quantity = int(request.POST.get("quantity") or 0)
        rejection_quantity = int(request.POST.get("rejection_quantity") or 0)
        weight = float(request.POST.get("weight") or 0)

        if not direction or not item_id:
            messages.error(request, "Please choose an item and direction.")
            return redirect("machining_entry")

        try:
            item = Item.objects.get(id=item_id)
        except Item.DoesNotExist:
            messages.error(request, "Selected item not found.")
            return redirect("machining_entry")

        worker_obj = None
        job_worker_obj = None
        if worker_id:
            if worker_id.startswith('w_'):
                worker_obj = Worker.objects.filter(id=worker_id.replace('w_', '')).first()
            elif worker_id.startswith('jw_'):
                job_worker_obj = JobWorker.objects.filter(id=worker_id.replace('jw_', '')).first()

        edit_id = request.POST.get("edit_id")
        if edit_id:
            try:
                tx = StockTransaction.objects.get(id=edit_id)
                tx.transaction_type = direction
                tx.item = item
                tx.worker = worker_obj
                tx.job_worker = job_worker_obj
                tx.quantity = quantity
                tx.rejection_quantity = rejection_quantity
                tx.weight = weight
                tx.save()
                messages.success(request, "Updated successfully.")
            except StockTransaction.DoesNotExist:
                messages.error(request, "Transaction not found.")
        else:
            StockTransaction.objects.create(
                transaction_type=direction,
                item=item,
                worker=worker_obj,
                job_worker=job_worker_obj,
                quantity=quantity,
                rejection_quantity=rejection_quantity,
                weight=weight
            )
            messages.success(request, "Saved successfully.")

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
                    "item_name": item.name,
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
    from .models import ItemWorkerAllocation
    allocations = ItemWorkerAllocation.objects.all().select_related('worker', 'job_worker')
    smart_allocations = {}
    for a in allocations:
        item_id = str(a.item_id)
        if item_id not in smart_allocations:
            smart_allocations[item_id] = []
        
        w_id = f"w_{a.worker_id}" if a.worker_id else f"jw_{a.job_worker_id}"
        w_name = a.worker.name if a.worker_id else a.job_worker.name
        
        smart_allocations[item_id].append({"id": w_id, "name": w_name})

    context = {
        "workers": workers,
        "job_workers": job_workers,
        "items": items,
        "recent": recent,
        "worker_ledger": dict(worker_ledger),
        "machining_stock": machining_stock,
        "worker_wip": worker_wip,
        "smart_allocations": json.dumps(smart_allocations),
        "today": timezone.now()
    }

    return render(
        request,
        "machining.html",
        context
    )

# =====================================================
# POLISHING
# =====================================================

def polishing_entry(request):

    workers = Worker.objects.filter(process="polishing", active=True)
    job_workers = JobWorker.objects.filter(process="polishing", active=True)
    items = Item.objects.all()

    from . import services

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
        if item.item_type == 'SET':
            from .models import ItemComposition
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
        
        import json
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

                # Get correct lot size based on packaging
                lot_size = item.lot_with_box if packaging == "box" else item.lot_size
                lot_size = lot_size or 0
                total_quantity = (lots * lot_size) + manual

                if total_quantity <= 0:
                    continue

                # If it's a SET item, consume components (only for OUT transactions)
                if direction == "polishing_out" and item.item_type == 'SET':
                    from .models import Warehouse
                    from_wh = Warehouse.objects.filter(code='MACHINING').first()
                    
                    components = row.get("components", [])
                    for comp_row in components:
                        comp_id = comp_row.get("component_id")
                        total_qty = int(comp_row.get("total_qty") or 0)
                        
                        if total_qty <= 0:
                            continue
                            
                        try:
                            comp_item = Item.objects.get(id=comp_id)
                        except Item.DoesNotExist:
                            continue
                            
                        StockTransaction.objects.create(
                            transaction_type="kitting_consume",
                            item=comp_item,
                            quantity=total_qty,
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
                if direction == "polishing_out" and item.item_type == 'SET':
                    from .models import ItemComposition, Warehouse
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

    context = {

        "workers": workers,
        "job_workers": job_workers,
        "items": items,
        "recent": recent,
        "available_data": available_data,
        "completed_ids": completed_ids,

    }

    return render(
        request,
        "polishing.html",
        context
    )
# =====================================================
# PACKAGING
# =====================================================
def packaging_view(request):

    items = Item.objects.all()

    # =====================================
    # PACKAGING QUEUE
    # =====================================

    packaging_queue = []

    polishing_in_entries = StockTransaction.objects.filter(
        transaction_type="polishing_in"
    ).order_by("-created_at")

    for entry in polishing_in_entries:

        already_packed = StockTransaction.objects.filter(
            notes=f"PACKED #{entry.id}"
        ).exists()

        if not already_packed:

            packaging_queue.append(entry)

    # =====================================
    # PACK NOW BUTTON
    # =====================================

    pack_id = request.GET.get("pack")

    if pack_id:

        try:

            polishing_entry = StockTransaction.objects.get(
                id=pack_id,
                transaction_type="polishing_in"
            )

            already_done = StockTransaction.objects.filter(
                notes=f"PACKED #{polishing_entry.id}"
            ).exists()

            if not already_done:

                StockTransaction.objects.create(

                    transaction_type="packaging_in",

                    item=polishing_entry.item,

                    quantity=polishing_entry.quantity,
                    weight=polishing_entry.weight,

                    notes=f"PACKED #{polishing_entry.id}"

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
    # READY STOCK
    # =====================================

    ready_stock = StockTransaction.objects.filter(
        transaction_type="packaging_in"
    ).order_by("-created_at")

    completed_ids = []

    for row in packaging_queue:

        done = StockTransaction.objects.filter(
            notes=f"PACKED #{row.id}"
        ).exists()

        if done:
            completed_ids.append(row.id)

    context = {

        "items": items,
        "packaging_queue": packaging_queue,
        "ready_stock": ready_stock,
        "completed_ids": completed_ids,

    }

    return render(
        request, "packaging.html", context
    )
# =====================================================
# MASTER DATA
# =====================================================

@staff_member_required
def master_data(request):
    from .models import ItemWorkerAllocation, ItemComposition
    active_tab = request.GET.get("tab", "items")
    
    # Handle GET/POST data for editing
    edit_id = request.POST.get("edit_id") or request.GET.get("edit")
    edit_item = Item.objects.filter(id=edit_id).first() if edit_id else None
    
    edit_client = Client.objects.filter(id=request.GET.get("edit_client")).first()
    edit_worker = Worker.objects.filter(id=request.GET.get("edit_worker")).first()
    edit_job_worker = JobWorker.objects.filter(id=request.GET.get("edit_job_worker")).first()

    if request.method == "POST":
        form_type = request.POST.get("form_type")
        
        if form_type == "item":
            data = request.POST.copy()
            
            # Default empty numeric fields to 0
            if not data.get('casting_weight'): data['casting_weight'] = 0
            if not data.get('machining_weight'): data['machining_weight'] = 0
            if not data.get('lot_size'): data['lot_size'] = 0
            if not data.get('lot_with_box'): data['lot_with_box'] = 0
            
            if data.get('custom_client'):
                client = Client.objects.filter(name=data.get('custom_client')).first()
                if client:
                    data['client'] = client.id
            if data.get('custom_material'):
                data['material'] = data.get('custom_material')
            
            # Checkboxes handle False state
            data['casting_required'] = 'casting_required' in request.POST
            data['machining_required'] = 'machining_required' in request.POST
            data['polishing_required'] = 'polishing_required' in request.POST
            data['packing_required'] = 'packing_required' in request.POST
            
            form = ItemForm(data, instance=edit_item)
            if form.is_valid():
                item = form.save()
                ItemWorkerAllocation.objects.filter(item=item).delete()
                
                worker_ids = request.POST.getlist('worker_id[]')
                worker_rates = request.POST.getlist('worker_rate[]')
                
                for wid, rate in zip(worker_ids, worker_rates):
                    if wid and rate:
                        try:
                            # Handle prefixes for Internal vs Job Worker
                            if wid.startswith('w_'):
                                ItemWorkerAllocation.objects.create(
                                    item=item,
                                    worker_id=wid.replace('w_', ''),
                                    rate_per_piece=float(rate)
                                )
                            elif wid.startswith('jw_'):
                                ItemWorkerAllocation.objects.create(
                                    item=item,
                                    job_worker_id=wid.replace('jw_', ''),
                                    rate_per_piece=float(rate)
                                )
                            else:
                                # Fallback
                                ItemWorkerAllocation.objects.create(
                                    item=item,
                                    job_worker_id=wid,
                                    rate_per_piece=float(rate)
                                )
                        except Exception:
                            pass

                # Handle Item Composition (BOM)
                ItemComposition.objects.filter(parent_item=item).delete()
                if item.item_type == 'SET':
                    comp_ids = request.POST.getlist('component_id[]')
                    comp_qtys = request.POST.getlist('component_qty[]')
                    for cid, qty in zip(comp_ids, comp_qtys):
                        if cid and qty:
                            try:
                                ItemComposition.objects.create(
                                    parent_item=item,
                                    component_item_id=cid,
                                    quantity=int(qty)
                                )
                            except Exception:
                                pass
                            
                messages.success(request, f"Item {'updated' if edit_item else 'created'} successfully.")
                return redirect(f"{reverse('master_data')}?tab=items")
            else:
                print("ITEM FORM ERRORS:", form.errors)
                messages.error(request, f"Error saving item: {form.errors}")

        elif form_type == "client":
            data = request.POST.copy()
            data['name'] = data.get('client_name')
            data['phone'] = data.get('client_phone')
            data['email'] = data.get('client_email')
            data['city'] = data.get('client_city')
            data['address'] = data.get('client_address')
            data['gst_number'] = data.get('client_gst')
            
            # Prioritize hidden ID from POST for edits
            client_id = request.POST.get('client_id')
            instance = None
            if client_id:
                instance = Client.objects.filter(id=client_id).first()
            elif edit_client:
                instance = edit_client
                
            form = ClientForm(data, instance=instance)
            if form.is_valid():
                form.save()
                messages.success(request, f"Client {'updated' if edit_client else 'created'} successfully.")
                return redirect(f"{reverse('master_data')}?tab=clients")
            else:
                messages.error(request, "Error saving client.")

        elif form_type == "worker":
            data = request.POST.copy()
            data['name'] = data.get('worker_name')
            data['process'] = data.get('worker_process')
            data['daily_rate'] = data.get('worker_daily_rate', 0)
            data['phone'] = data.get('worker_phone')
            
            # Professional HR Fields
            data['employee_id'] = data.get('worker_employee_id')
            data['designation'] = data.get('worker_designation')
            data['joining_date'] = data.get('worker_joining_date') or None
            data['standard_shift_hours'] = data.get('worker_shift_hours', 8)
            data['identity_number'] = data.get('worker_identity_no')
            data['emergency_contact_name'] = data.get('worker_emergency_name')
            data['emergency_contact_phone'] = data.get('worker_emergency_phone')
            data['blood_group'] = data.get('worker_blood_group')
            
            # Salary Fields
            data['salary_model'] = data.get('worker_salary_model', 'DAILY')
            data['monthly_fixed_salary'] = data.get('worker_fixed_salary', 0)
            data['monthly_allowance'] = data.get('worker_monthly_allowance', 0)
            data['overtime_rate'] = data.get('worker_ot_rate', 0)
            
            # Prioritize hidden ID from POST for edits
            worker_id = request.POST.get('worker_id')
            instance = None
            if worker_id:
                instance = Worker.objects.filter(id=worker_id).first()
            elif edit_worker:
                instance = edit_worker
                
            form = WorkerForm(data, instance=instance)
            if form.is_valid():
                form.save()
                messages.success(request, f"Worker {'updated' if edit_worker else 'created'} successfully.")
                return redirect(f"{reverse('master_data')}?tab=workers&sub=internal")
            else:
                messages.error(request, f"Error saving worker: {form.errors}")

        elif form_type == "job_worker":
            data = request.POST.copy()
            data['name'] = data.get('jw_name')
            data['process'] = data.get('jw_process')
            data['jw_code'] = data.get('jw_code')
            data['phone'] = data.get('jw_phone')
            data['email'] = data.get('jw_email')
            data['address'] = data.get('jw_address')
            data['gst_number'] = data.get('jw_gst')
            
            # Prioritize hidden ID over GET param for edits
            jw_id = request.POST.get('jw_id')
            instance = None
            if jw_id:
                instance = JobWorker.objects.filter(id=jw_id).first()
            elif edit_job_worker:
                instance = edit_job_worker

            form = JobWorkerForm(data, instance=instance)
            if form.is_valid():
                instance = form.save()
                
                # Process Item Allocations
                item_ids = request.POST.getlist('assigned_item_id[]')
                item_rates = request.POST.getlist('assigned_item_rate[]')
                
                if item_ids:
                    ItemWorkerAllocation.objects.filter(job_worker=instance).delete()
                    for i_id, i_rate in zip(item_ids, item_rates):
                        if i_id and i_rate:
                            ItemWorkerAllocation.objects.create(
                                job_worker=instance,
                                item_id=i_id,
                                rate_per_piece=float(i_rate)
                            )

                msg = f"Job Worker {'updated' if jw_id else 'created'} successfully."
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'status': 'success', 'message': msg})
                messages.success(request, msg)
                return redirect(f"{reverse('master_data')}?tab=workers&sub=job")
            else:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'status': 'error', 'errors': form.errors.as_json()}, status=400)
                messages.error(request, "Error saving job worker.")

        elif form_type == "bom":
            parent_id = request.POST.get('parent_item_id')
            new_set_name = request.POST.get('new_set_name')
            
            try:
                if new_set_name:
                    # Create a NEW Item for the Set
                    parent_item = Item.objects.create(
                        name=new_set_name,
                        code=request.POST.get('new_set_code'),
                        category=request.POST.get('category', 'OTHER'),
                        item_type='SET'
                    )
                else:
                    parent_item = Item.objects.get(id=parent_id)

                ItemComposition.objects.filter(parent_item=parent_item).delete()
                
                # Ensure it's marked as SET
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
                
                # Update parent weight and lot_size from components
                parent_item.machining_weight = total_weight
                
                # PRIMARY COMPONENT RULE: Inherit lot size from the first component
                if comp_ids:
                    first_comp = Item.objects.filter(id=comp_ids[0]).first()
                    if first_comp:
                        parent_item.lot_size = first_comp.lot_size
                        parent_item.lot_with_box = first_comp.lot_with_box
                
                parent_item.save()
                
                messages.success(request, f"BOM for {parent_item.name} saved successfully with calculated weight {total_weight}kg.")
                return redirect(f"{reverse('master_data')}?tab=items&sub=bom")
            except Exception as e:
                messages.error(request, f"Error saving BOM: {str(e)}")
                return redirect(f"{reverse('master_data')}?tab=items&sub=bom")

        elif form_type == "delete_bom":
            from .models import ItemComposition
            parent_id = request.POST.get('parent_item_id')
            try:
                parent_item = Item.objects.get(id=parent_id)
                item_name = parent_item.name
                parent_item.delete()  # This also deletes ItemComposition via CASCADE
                messages.success(request, f"Set '{item_name}' and its BOM deleted successfully.")
            except Exception as e:
                messages.error(request, f"CRITICAL ERROR: Could not delete Set. Details: {str(e)}")
            return redirect(f"{reverse('master_data')}?tab=items&sub=bom")

    all_items = Item.objects.all()
    
    # Filter items by client if requested
    client_filter_id = request.GET.get('client_filter')
    items_to_display = all_items
    if client_filter_id and client_filter_id.strip():
        items_to_display = all_items.filter(client_id=client_filter_id)
    
    # Items for the BOM tab (only those marked as SET)
    bom_items = Item.objects.filter(item_type='SET').prefetch_related('components__component_item')

    # Client Stats for the dashboard
    from django.db.models import Count
    client_list = Client.objects.annotate(
        item_count=Count('item')
    ).order_by('name')
    
    client_stats = {
        'total': client_list.count(),
        'cities': client_list.values('city').distinct().count(),
        'active': client_list.filter(active=True).count(),
    }

    context = {
        "clients": client_list,
        "client_stats": client_stats,
        "items": items_to_display,             # Show filtered or all items
        "bom_items": bom_items,         # Only actual sets in the BOM tab
        "all_items": all_items,         # For the Quick Set Creator
        "workers": Worker.objects.all(),
        "job_workers": JobWorker.objects.all(),
        "edit_item_data": edit_item,
        "edit_client_data": edit_client,
        "edit_worker_data": edit_worker,
        "edit_job_worker_data": edit_job_worker,
        "active_tab": active_tab,
        "active_client_filter": client_filter_id,
    }
    return render(request, "master_data.html", context)

# =====================================================
# STOCK PAGES
# =====================================================

def casting_stock(request):

    from collections import defaultdict

    rows = []

    transactions = StockTransaction.objects.filter(
        transaction_type__in=[
            "casting_in",
            "casting_entry"
        ]
    ).select_related(
        "client",
        "item"
    )

    grouped = defaultdict(lambda: {
        "pcs": 0,
        "weight": 0
    })

    for tx in transactions:

        client_name = (
            tx.client.name
            if tx.client else "NO CLIENT"
        )

        item_code = (
            tx.item.code
            if tx.item else "-"
        )

        item_name = (
            tx.item.name
            if tx.item else "-"
        )

        key = (
            client_name,
            item_code,
            item_name
        )

        grouped[key]["pcs"] += tx.quantity or 0

        grouped[key]["weight"] += float(
            tx.weight or 0
        )

    for key, value in grouped.items():

        rows.append({

            "client": key[0],
            "code": key[1],
            "item": key[2],

            "pcs": value["pcs"],

            "weight": round(
                value["weight"],
                3
            )

        })

    graph_labels = []
    graph_values = []

    item_summary = defaultdict(int)

    for row in rows:

        item_summary[row["item"]] += row["pcs"]

    for item_name, pcs in item_summary.items():

        graph_labels.append(item_name)
        graph_values.append(pcs)

    context = {

        "rows": rows,

        "graph_labels": graph_labels,
        "graph_values": graph_values,

    }

    return render(
        request,
        "casting_stock.html",
        context
    )

def machining_stock(request):

    from collections import defaultdict

    rows = []

    transactions = StockTransaction.objects.filter(

        transaction_type__in=[
            "machining_out",
            "machining_in"
        ]

    ).select_related(

        "worker",
        "item"

    )

    grouped = defaultdict(lambda: {

        "pcs": 0,
        "weight": 0

    })

    for tx in transactions:

        # =====================================
        # SUPPORT OLD + NEW DATA
        # =====================================

        if tx.worker:

            worker_name = tx.worker.name

        else:

            worker_name = "NO JOB WORKER"

        # =====================================
        # ITEM DETAILS
        # =====================================

        item_code = (
            tx.item.code
            if tx.item else "-"
        )

        item_name = (
            tx.item.name
            if tx.item else "-"
        )

        key = (
            worker_name,
            item_code,
            item_name
        )

        # =====================================
        # STOCK CALCULATION
        # =====================================

        if tx.transaction_type == "machining_out":

            grouped[key]["pcs"] += (
                tx.quantity or 0
            )

            grouped[key]["weight"] += float(
                tx.weight or 0
            )

        elif tx.transaction_type == "machining_in":

            grouped[key]["pcs"] -= (
                tx.quantity or 0
            )

            grouped[key]["weight"] -= float(
                tx.weight or 0
            )

    # =====================================
    # FINAL TABLE ROWS
    # =====================================

    for key, value in grouped.items():

        if value["pcs"] > 0:

            rows.append({

                "worker": key[0],

                "code": key[1],

                "item": key[2],

                "pcs": value["pcs"],

                "weight": round(
                    value["weight"],
                    3
                )

            })

    # =====================================
    # PIE CHART DATA
    # =====================================

    graph_labels = []
    graph_values = []

    item_summary = defaultdict(int)

    for row in rows:

        item_summary[
            row["item"]
        ] += row["pcs"]

    for item_name, pcs in item_summary.items():

        graph_labels.append(item_name)

        graph_values.append(pcs)

    context = {

        "rows": rows,

        "graph_labels": graph_labels,

        "graph_values": graph_values,

    }

    return render(

        request,

        "machining_stock.html",

        context

    )
# =====================================================
# OLD URL SUPPORT
# =====================================================

def issue_machining(request):

    return redirect("machining_entry")
@staff_member_required
def delete_item(request, item_id):
    try:
        item = Item.objects.get(id=item_id)
        item.delete()
        messages.success(request, "Item deleted successfully.")
    except Item.DoesNotExist:
        messages.error(request, "Item could not be found for deletion.")

    next_url = request.GET.get('next', 'master_data')
    if next_url == 'bom':
        target = f"{reverse('master_data')}?tab=items&sub=bom"
    else:
        target = reverse('master_data')

    return redirect(target)

@staff_member_required
def delete_client(request, client_id):
    try:
        client = Client.objects.get(id=client_id)
        client_name = client.name
        client.delete()
        messages.success(request, f"Client '{client_name}' deleted successfully.")
    except Client.DoesNotExist:
        messages.error(request, "Client could not be found.")
    except Exception as e:
        messages.error(request, f"Error deleting client: {str(e)}")
    
    return redirect(f"{reverse('master_data')}?tab=clients")

@staff_member_required
def delete_worker(request, worker_id):
    try:
        worker = Worker.objects.get(id=worker_id)
        worker_name = worker.name
        worker.delete()
        messages.success(request, f"Worker '{worker_name}' deleted successfully.")
    except Worker.DoesNotExist:
        messages.error(request, "Worker could not be found.")
    except Exception as e:
        messages.error(request, f"Error deleting worker: {str(e)}")
    
    return redirect(f"{reverse('master_data')}?tab=workers&sub=internal")

@staff_member_required
def delete_job_worker(request, job_worker_id):
    try:
        jw = JobWorker.objects.get(id=job_worker_id)
        jw_name = jw.name
        jw.delete()
        messages.success(request, f"Job Worker '{jw_name}' deleted successfully.")
    except JobWorker.DoesNotExist:
        messages.error(request, "Job Worker could not be found.")
    except Exception as e:
        messages.error(request, f"Error deleting job worker: {str(e)}")
    
    return redirect(f"{reverse('master_data')}?tab=workers&sub=job")

@staff_member_required
def edit_item(request, item_id):

    item = Item.objects.get(id=item_id)

    if request.method == "POST":

        item.name = request.POST.get("item_name")
        item.code = request.POST.get("item_code")
        item.category = request.POST.get("category")
        item.casting_weight = float(request.POST.get("casting_weight") or 0)
        item.machining_weight = float(request.POST.get("machining_weight") or 0)

        try:
            item.save()
            messages.success(
                request,
                "Item updated successfully."
            )
        except Exception:
            messages.error(
                request,
                "Item could not be updated. Please try again."
            )

        return redirect("master_data")

    context = {
        "item": item
    }

    return render(
        request,
        "inventory/edit_item.html",
        context
    )

# =====================================================
# DISPATCH & SALES
# =====================================================

def dispatch_view(request):
    clients = Client.objects.all()
    items = Item.objects.all()

    if request.method == "POST":
        client_id = request.POST.get("client")
        item_id = request.POST.get("item")
        cartons = int(request.POST.get("cartons") or 0)
        loose_pieces = int(request.POST.get("loose_pieces") or 0)
        weight = float(request.POST.get("weight") or 0)

        if not client_id or not item_id:
            messages.error(request, "Client and Item are required.")
            return redirect("dispatch")

        try:
            client = Client.objects.get(id=client_id)
            item = Item.objects.get(id=item_id)
        except (Client.DoesNotExist, Item.DoesNotExist):
            messages.error(request, "Selected client or item was not found.")
            return redirect("dispatch")

        lot_size = item.lot_with_box or 0
        pieces = (cartons * lot_size) + loose_pieces

        if pieces <= 0:
            messages.error(request, "Valid quantity (Cartons or Loose Pieces) is required.")
            return redirect("dispatch")

        try:
            client = Client.objects.get(id=client_id)
            item = Item.objects.get(id=item_id)
        except (Client.DoesNotExist, Item.DoesNotExist):
            messages.error(request, "Selected client or item was not found.")
            return redirect("dispatch")

        # Create dispatch transaction
        StockTransaction.objects.create(
            transaction_type=TransactionType.DISPATCH_OUT,
            client=client,
            item=item,
            quantity=pieces,
            weight=weight,
            notes=f"Dispatched {pieces} pcs to {client.name}"
        )

        messages.success(request, f"Successfully dispatched {pieces} pcs of {item.name} to {client.name}.")
        return redirect("dispatch")

    # Get Ready Stock summary
    stock_rows = []
    for item in items:
        item_stock = services.get_stock_by_item(item)
        ready_qty = item_stock['ready']
        if ready_qty > 0:
            cartons = 0
            loose_pieces = ready_qty
            if item.lot_with_box and item.lot_with_box > 0:
                cartons = ready_qty // item.lot_with_box
                loose_pieces = ready_qty % item.lot_with_box
                
            stock_rows.append({
                "item": item,
                "cartons": cartons,
                "loose_pieces": loose_pieces,
                "total_pieces": ready_qty,
                "weight": round(ready_qty * float(item.machining_weight or 0), 3)
            })

    recent_dispatches = StockTransaction.objects.filter(
        transaction_type=TransactionType.DISPATCH_OUT
    ).order_by("-created_at")[:20]

    context = {
        "clients": clients,
        "items": items,
        "stock_rows": stock_rows,
        "recent_dispatches": recent_dispatches,
    }
    return render(request, "dispatch.html", context)


from django.http import JsonResponse
from django.views.decorators.http import require_GET

def assembly_view(request):
    items = Item.objects.filter(item_type='SET', active=True)
    if request.method == 'POST':
        item_id = request.POST.get('item_id')
        quantity = int(request.POST.get('quantity') or 0)
        
        if not item_id or quantity <= 0:
            messages.error(request, "Please select an item and enter a valid quantity.")
            return redirect('assembly')

        try:
            item = Item.objects.get(id=item_id)
            compositions = item.components.all()
            
            # Check stock for components
            from .services import get_stock_by_item
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
                # Create Transactions
                from .models import Warehouse
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
                return redirect('assembly')
        except Exception as e:
            messages.error(request, f"Error: {str(e)}")
            
    return render(request, 'assembly.html', {'items': items, 'active_page': 'assembly'})

@require_GET
def get_item_composition(request, item_id):
    try:
        item = Item.objects.get(id=item_id)
        compositions = item.components.all()
        data = []
        from .services import get_stock_by_item
        for comp in compositions:
            stock = get_stock_by_item(comp.component_item)
            data.append({
                'id': comp.component_item.id,
                'name': comp.component_item.name,
                'code': comp.component_item.code,
                'quantity': comp.quantity,
                'available': stock['polishing']
            })
        return JsonResponse({'components': data})
    except Item.DoesNotExist:
        return JsonResponse({'error': 'Item not found'}, status=404)

def get_item_workers(request, item_id):
    item = Item.objects.filter(id=item_id).first()
    if not item:
        return JsonResponse({"workers": []})
        
    process_filter = request.GET.get('process')
    allocations = item.worker_allocations.all()
    
    performers = []
    for alloc in allocations:
        if alloc.worker:
            if process_filter and alloc.worker.process != process_filter:
                continue
            performers.append({
                "id": f"w_{alloc.worker.id}",
                "name": alloc.worker.name,
                "process": alloc.worker.process,
                "type": "Internal",
                "rate": alloc.rate_per_piece
            })
        if alloc.job_worker:
            if process_filter and alloc.job_worker.process != process_filter:
                continue
            performers.append({
                "id": f"jw_{alloc.job_worker.id}",
                "name": alloc.job_worker.name,
                "process": alloc.job_worker.process,
                "type": "External",
                "rate": alloc.rate_per_piece
            })
        
    return JsonResponse({"workers": performers})
    
def get_worker_items(request, worker_id):
    from .models import ItemWorkerAllocation
    if worker_id.startswith('w_'):
        wid = worker_id.replace('w_', '')
        allocations = ItemWorkerAllocation.objects.filter(worker_id=wid)
    else:
        jwid = worker_id.replace('jw_', '')
        allocations = ItemWorkerAllocation.objects.filter(job_worker_id=jwid)
    
    # Filter out sets (items with components)
    allocations = allocations.filter(item__components__isnull=True)
        
    items = []
    for alloc in allocations:
        items.append({
            "id": alloc.item.id,
            "code": alloc.item.code,
            "name": alloc.item.name,
            "casting_weight": float(alloc.item.casting_weight or 0),
            "machining_weight": float(alloc.item.machining_weight or 0)
        })
    return JsonResponse({"items": items})

@staff_member_required
@require_GET
def get_internal_worker_profile(request, worker_id):
    from django.shortcuts import get_object_or_404
    worker = get_object_or_404(Worker, id=worker_id)
    
    # 1. Get Attendance for current month
    now = timezone.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    attendance = Attendance.objects.filter(worker=worker, date__gte=month_start).order_by('-date')
    
    # 2. Get Payments
    payments = LaborPayment.objects.filter(worker=worker).order_by('-date')[:20]
    
    # 3. Calculate Monthly Stats
    days_present = attendance.filter(status='PRESENT').count()
    days_half = attendance.filter(status='HALF_DAY').count()
    days_absent = attendance.filter(status='ABSENT').count()
    total_ot = sum(a.overtime_hours for a in attendance)
    
    # Wage Calculation
    earned_wages = 0
    if worker.salary_model == 'DAILY':
        earned_wages = (days_present * worker.daily_rate) + (days_half * 0.5 * worker.daily_rate)
    elif worker.salary_model == 'FIXED':
        # Simple daily deduction for fixed salary (Fixed / 30)
        daily_deduct = worker.monthly_fixed_salary / 30
        earned_wages = worker.monthly_fixed_salary - (days_absent * daily_deduct)
    
    # Add Overtime
    earned_wages += (total_ot * worker.overtime_rate)
    
    # Total Paid
    total_paid = sum(p.amount for p in payments)
    
    return JsonResponse({
        'name': worker.name,
        'employee_id': worker.employee_id or '---',
        'designation': worker.designation or 'Worker',
        'salary_model': worker.get_salary_model_display(),
        'base_rate': worker.daily_rate if worker.salary_model == 'DAILY' else worker.monthly_fixed_salary,
        'ot_rate': worker.overtime_rate,
        'process': worker.get_process_display(),
        'joining_date': worker.joining_date.strftime('%d %b, %Y') if worker.joining_date else '---',
        'identity_no': worker.identity_number or '---',
        'blood_group': worker.blood_group or '---',
        'shift_hours': worker.standard_shift_hours,
        'month': timezone.now().month,
        'year': timezone.now().year,
        'stats': {
            'present': days_present,
            'half': days_half,
            'absent': days_absent,
            'ot': total_ot,
            'earned': round(earned_wages, 2),
            'paid': round(total_paid, 2),
            'balance': round(earned_wages - total_paid, 2)
        },
        'attendance': [
            {
                'date': a.date.strftime('%d %b, %Y'),
                'raw_date': a.date.strftime('%Y-%m-%d'),
                'status': a.get_status_display(),
                'raw_status': a.status,
                'ot': a.overtime_hours,
                'notes': a.notes
            } for a in attendance
        ],
        'payments': [
            {
                'date': p.date.strftime('%d %b, %Y'),
                'amount': p.amount,
                'mode': p.payment_mode,
                'type': p.get_payment_type_display()
            } for p in payments
        ]
    })

@staff_member_required
@require_GET
def get_job_worker_profile(request, jw_id):
    try:
        from .models import JobWorker, ItemWorkerAllocation, StockTransaction, LaborPayment
        jw = JobWorker.objects.get(id=jw_id)
        allocations = ItemWorkerAllocation.objects.filter(job_worker=jw).select_related('item')
        
        # 1. Price List
        items_data = []
        for alloc in allocations:
            items_data.append({
                'id': alloc.id,
                'item_id': alloc.item.id,
                'item_name': alloc.item.name,
                'item_code': alloc.item.code,
                'rate': str(alloc.rate_per_piece)
            })

        # 2. Ledger History (Recent)
        transactions = StockTransaction.objects.filter(job_worker=jw).order_by('-created_at')[:30]
        payments = LaborPayment.objects.filter(job_worker=jw).order_by('-date')[:20]
        
        ledger = []
        for tx in transactions:
            val = 0
            if tx.transaction_type in ['machining_in', 'polishing_in', 'packaging_in']:
                alloc = allocations.filter(item=tx.item).first()
                if alloc:
                    val = float(tx.quantity) * float(alloc.rate_per_piece)
            
            ledger.append({
                'date': tx.created_at.strftime('%Y-%m-%d'),
                'type': 'STOCK',
                'description': f"{tx.get_transaction_type_display()} - {tx.item.code}",
                'qty': tx.quantity,
                'earned': val,
                'paid': 0
            })
            
        for p in payments:
            ledger.append({
                'date': p.date.strftime('%Y-%m-%d'),
                'type': 'PAYMENT',
                'description': f"Payment: {p.get_payment_type_display()} ({p.payment_mode})",
                'qty': 0,
                'earned': 0,
                'paid': p.amount
            })
            
        ledger.sort(key=lambda x: x['date'], reverse=True)

        data = {
            'id': jw.id,
            'name': jw.name,
            'process': jw.process,
            'phone': jw.phone or '---',
            'email': jw.email or '---',
            'address': jw.address or '---',
            'gst': jw.gst_number or 'N/A',
            'items': items_data,
            'ledger': ledger[:30]
        }
        return JsonResponse(data)
    except JobWorker.DoesNotExist:
        return JsonResponse({'error': 'Job Worker not found'}, status=404)

@staff_member_required
def job_worker_monthly_report(request, jw_id):
    from .models import JobWorker, StockTransaction, LaborPayment, ItemWorkerAllocation
    from datetime import datetime
    
    jw = JobWorker.objects.get(id=jw_id)
    month_str = request.GET.get('month', timezone.now().strftime('%Y-%m'))
    month_dt = datetime.strptime(month_str, '%Y-%m')
    
    # 1. Filter Transactions for the month
    transactions = StockTransaction.objects.filter(
        job_worker=jw, 
        created_at__year=month_dt.year, 
        created_at__month=month_dt.month
    ).order_by('created_at')
    
    # 2. Filter Payments
    payments = LaborPayment.objects.filter(
        job_worker=jw,
        date__year=month_dt.year,
        date__month=month_dt.month
    )
    
    # 3. Aggregate by Item & Calculate Balances
    all_jw_tx = StockTransaction.objects.filter(job_worker=jw).order_by('created_at')
    
    # Track running balances for ALL time to get accurate current BAL
    item_balances = {}
    for tx in all_jw_tx:
        in_qty = tx.quantity if tx.transaction_type.endswith('_out') else 0
        out_qty = tx.quantity if tx.transaction_type.endswith('_in') else 0
        
        if tx.item_id not in item_balances:
            item_balances[tx.item_id] = 0
        item_balances[tx.item_id] += (in_qty - out_qty)

    # Filter for the current month and aggregate by (Item, Date)
    item_ledger = {}
    for tx in all_jw_tx.filter(created_at__year=month_dt.year, created_at__month=month_dt.month):
        date_key = tx.created_at.date()
        key = (tx.item_id, date_key)
        
        if key not in item_ledger:
            item_ledger[key] = {
                'name': tx.item.name,
                'code': tx.item.code,
                'date': date_key,
                'in': 0,
                'out': 0,
                'bal': 0, # Will fill this after
                'earned': 0
            }
        
        if tx.transaction_type.endswith('_out'):
            item_ledger[key]['in'] += tx.quantity
        elif tx.transaction_type.endswith('_in'):
            item_ledger[key]['out'] += tx.quantity
            alloc = ItemWorkerAllocation.objects.filter(job_worker=jw, item=tx.item).first()
            rate = float(alloc.rate_per_piece) if alloc else 0
            item_ledger[key]['earned'] += (tx.quantity * rate)

    # Calculate balances chronologically for the displayed keys
    # To get accurate balances, we need to sort the keys by date
    sorted_keys = sorted(item_ledger.keys(), key=lambda x: x[1])
    
    # We also need the opening balances for each item at the start of the month
    opening_balances = {}
    previous_tx = all_jw_tx.filter(created_at__lt=month_dt)
    for tx in previous_tx:
        in_qty = tx.quantity if tx.transaction_type.endswith('_out') else 0
        out_qty = tx.quantity if tx.transaction_type.endswith('_in') else 0
        opening_balances[tx.item_id] = opening_balances.get(tx.item_id, 0) + (in_qty - out_qty)

    current_item_balances = opening_balances.copy()
    for key in sorted_keys:
        item_id = key[0]
        item_ledger[key]['bal'] = current_item_balances.get(item_id, 0) + item_ledger[key]['in'] - item_ledger[key]['out']
        current_item_balances[item_id] = item_ledger[key]['bal']

    total_earned = sum(item['earned'] for item in item_ledger.values())
    total_paid = sum(p.amount for p in payments)
    
    # Final sorted list for template
    ledger_entries = sorted(item_ledger.values(), key=lambda x: x['date'])

    context = {
        'jw': jw,
        'month_name': month_dt.strftime('%B %Y'),
        'month_val': month_str,
        'item_ledger': ledger_entries,
        'payments': payments,
        'total_earned': total_earned,
        'total_paid': total_paid,
        'balance': total_earned - total_paid,
        'today': timezone.now(),
    }
    return render(request, 'job_worker_report.html', context)

@staff_member_required
def worker_monthly_report(request, worker_id):
    from .models import Worker, Attendance, LaborPayment
    from django.utils import timezone
    import calendar
    
    worker = get_object_or_404(Worker, id=worker_id)
    today = timezone.now().date()
    month_start = today.replace(day=1)
    num_days = calendar.monthrange(today.year, today.month)[1]
    month_end = today.replace(day=num_days)
    
    attendance = Attendance.objects.filter(worker=worker, date__gte=month_start, date__lte=month_end).order_by('date')
    payments = LaborPayment.objects.filter(worker=worker, date__gte=month_start, date__lte=month_end).order_by('date')
    
    # Statistics
    days_present = attendance.filter(status='PRESENT').count()
    half_days = attendance.filter(status='HALF_DAY').count()
    days_absent = attendance.filter(status='ABSENT').count()
    total_ot = sum(a.overtime_hours for a in attendance)
    
    # Earnings Calculation (Consistent with labor_ledger logic)
    attendance_ledger = []
    earned_wages = 0
    
    daily_rate = worker.daily_rate if worker.salary_model == 'DAILY' else (worker.monthly_fixed_salary / 30)
    
    for a in attendance:
        day_earned = 0
        if a.status == 'PRESENT':
            day_earned = daily_rate
        elif a.status == 'HALF_DAY':
            day_earned = daily_rate * 0.5
        
        # Add OT for that day
        day_earned += (a.overtime_hours * worker.overtime_rate)
        earned_wages += day_earned
        
        attendance_ledger.append({
            'date': a.date,
            'status': a.status,
            'ot': a.overtime_hours,
            'rate': daily_rate,
            'earned': day_earned
        })
    
    # Adjust for FIXED salary if needed
    if worker.salary_model == 'FIXED':
        # In fixed model, we start with full salary and subtract absents
        daily_deduct = worker.monthly_fixed_salary / 30
        earned_wages = worker.monthly_fixed_salary - (days_absent * daily_deduct) + (total_ot * worker.overtime_rate)

    # Add Monthly Allowance
    earned_wages += worker.monthly_allowance

    total_paid = sum(p.amount for p in payments)
    
    # Calendar Logic for the printable report
    first_day_of_month = month_start.weekday() # Monday is 0, Sunday is 6
    # Adjust to Sunday as first day (Sunday=0, Monday=1, ...)
    first_day_of_month = (first_day_of_month + 1) % 7
    
    calendar_weeks = []
    current_week = [None] * first_day_of_month
    
    # Map attendance by day
    att_by_day = {a.date.day: a for a in attendance}
    
    for d in range(1, num_days + 1):
        record = att_by_day.get(d)
        current_week.append({
            'day': d,
            'status': record.status if record else None,
            'ot': record.overtime_hours if record else 0
        })
        if len(current_week) == 7:
            calendar_weeks.append(current_week)
            current_week = []
    
    if current_week:
        while len(current_week) < 7:
            current_week.append(None)
        calendar_weeks.append(current_week)

    # Loan context
    active_loan = worker.loans.filter(is_active=True).first()
    loan_repaid_this_month = sum(p.amount for p in payments if p.payment_type == 'LOAN_REPAYMENT')
    total_paid_regular = sum(p.amount for p in payments if p.payment_type not in ['LOAN_REPAYMENT', 'NEW_LOAN'])

    context = {
        'worker': worker,
        'stats': {
            'present': days_present,
            'half': half_days,
            'absent': days_absent,
            'ot': total_ot,
            'earned': earned_wages,
            'loan_repaid': loan_repaid_this_month,
            'loan_balance': active_loan.remaining_balance if active_loan else 0,
            'balance': earned_wages - total_paid_regular - loan_repaid_this_month
        },
        'calendar_weeks': calendar_weeks,
        'attendance_ledger': attendance_ledger,
        'payments': payments,
        'month_name': today.strftime('%B %Y'),
        'today': timezone.now()
    }
    return render(request, 'worker_report.html', context)

@staff_member_required
@require_POST
def add_worker_allocation(request):
    try:
        worker_id_str = request.POST.get('worker_id')
        item_id = request.POST.get('item_id')
        rate = request.POST.get('rate')
        
        if not worker_id_str or not item_id or not rate:
            return JsonResponse({'error': 'Missing data'}, status=400)
            
        item = Item.objects.get(id=item_id)
        
        # Prevent duplicates
        existing = None
        if worker_id_str.startswith('w_'):
            internal_id = worker_id_str.replace('w_', '')
            existing = ItemWorkerAllocation.objects.filter(item=item, worker_id=internal_id).first()
            if not existing:
                ItemWorkerAllocation.objects.create(item=item, worker_id=internal_id, rate_per_piece=rate)
        elif worker_id_str.startswith('jw_'):
            jw_id = worker_id_str.replace('jw_', '')
            existing = ItemWorkerAllocation.objects.filter(item=item, job_worker_id=jw_id).first()
            if not existing:
                ItemWorkerAllocation.objects.create(item=item, job_worker_id=jw_id, rate_per_piece=rate)
        
        if existing:
            return JsonResponse({'error': 'Item already assigned to this worker'}, status=400)
            
        return JsonResponse({'status': 'success'})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@staff_member_required
@require_POST
def delete_worker_allocation(request, alloc_id):
    try:
        ItemWorkerAllocation.objects.filter(id=alloc_id).delete()
        return JsonResponse({'status': 'success'})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@staff_member_required
def labor_ledger(request):
    from .models import Worker, JobWorker, Attendance, LaborPayment, StockTransaction, ItemWorkerAllocation
    
    # Context data
    today = timezone.now().date()
    month_start = today.replace(day=1)
    
    # 1. STAFF PAYROLL (INTERNAL)
    internal_workers = Worker.objects.all()
    staff_ledger = []
    for w in internal_workers:
        # Attendance this month
        attendance_records = Attendance.objects.filter(worker=w, date__gte=month_start)
        days_present = attendance_records.filter(status='PRESENT').count()
        half_days = attendance_records.filter(status='HALF_DAY').count()
        days_absent = attendance_records.filter(status='ABSENT').count()
        total_ot = sum(a.overtime_hours for a in attendance_records)
        
        # Wage Calculation based on Model
        earnings = 0
        if w.salary_model == 'DAILY':
            earnings = (days_present * w.daily_rate) + (half_days * 0.5 * w.daily_rate)
        elif w.salary_model == 'FIXED':
            # Simple daily deduction for fixed salary (Fixed / 30)
            daily_deduct = w.monthly_fixed_salary / 30
            earnings = w.monthly_fixed_salary - (days_absent * daily_deduct)
        
        # Add Overtime & Allowance
        earnings += (total_ot * w.overtime_rate)
        earnings += w.monthly_allowance
        
        # Payments & Repayments this month
        payments_qs = LaborPayment.objects.filter(worker=w, date__gte=month_start)
        total_paid = sum(p.amount for p in payments_qs.exclude(payment_type__in=['LOAN_REPAYMENT', 'NEW_LOAN']))
        total_repaid = sum(p.amount for p in payments_qs.filter(payment_type='LOAN_REPAYMENT'))
        
        # Loan Status
        active_loan = w.loans.filter(is_active=True).first()
        
        staff_ledger.append({
            'worker': w,
            'days_present': days_present,
            'half_days': half_days,
            'days_absent': days_absent,
            'ot_hours': total_ot,
            'earnings': earnings,
            'total_paid': total_paid,
            'total_repaid': total_repaid,
            'active_loan': active_loan,
            'balance': earnings - total_paid - total_repaid
        })

    # 2. JOB WORK PAYABLES (EXTERNAL)
    job_workers = JobWorker.objects.all()
    jw_ledger = []
    for jw in job_workers:
        # Calculate Total Earned from Received transactions
        # This is a bit heavy, ideally we'd pre-calculate or cache this.
        # We need to find all transactions where jw was the source.
        # Let's check StockTransaction fields.
        transactions = StockTransaction.objects.filter(job_worker=jw, transaction_type__in=['machining_in', 'polishing_in', 'packaging_in'])
        
        total_earned = 0
        for tx in transactions:
            # Find the rate for this item and this job worker
            alloc = ItemWorkerAllocation.objects.filter(item=tx.item, job_worker=jw).first()
            if alloc:
                total_earned += (tx.quantity * alloc.rate_per_piece)
        
        # Payments to this JW
        payments = LaborPayment.objects.filter(job_worker=jw)
        total_paid = payments.exclude(payment_type__in=['LOAN_REPAYMENT', 'NEW_LOAN']).aggregate(Sum('amount'))['amount__sum'] or 0
        total_repaid = payments.filter(payment_type='LOAN_REPAYMENT').aggregate(Sum('amount'))['amount__sum'] or 0
        
        # Loan Status
        active_loan = jw.loans.filter(is_active=True).first()
        
        jw_ledger.append({
            'jw': jw,
            'total_earned': total_earned,
            'total_paid': total_paid,
            'total_repaid': total_repaid,
            'active_loan': active_loan,
            'balance': total_earned - total_paid - total_repaid
        })

    total_staff_earnings = sum(e['earnings'] for e in staff_ledger)
    total_jw_balance = sum(e['balance'] for e in jw_ledger)

    # 3. Monthly Attendance Matrix (for the Full Sheet view)
    import calendar
    num_days = calendar.monthrange(today.year, today.month)[1]
    days_range = range(1, num_days + 1)
    month_end = today.replace(day=num_days)
    
    attendance_matrix = []
    for w in internal_workers:
        row = {'worker': w, 'days': []}
        att_records = Attendance.objects.filter(worker=w, date__gte=month_start, date__lte=month_end)
        att_dict = {r.date.day: r for r in att_records}
        
        for d in days_range:
            record = att_dict.get(d)
            if record:
                row['days'].append({
                    'day': d,
                    'status': record.status,
                    'ot': record.overtime_hours
                })
            else:
                row['days'].append({'day': d, 'status': None, 'ot': 0})
        attendance_matrix.append(row)

    context = {
        'staff_ledger': staff_ledger,
        'jw_ledger': jw_ledger,
        'attendance_matrix': attendance_matrix,
        'days_range': days_range,
        'total_staff_earnings': total_staff_earnings,
        'total_jw_balance': total_jw_balance,
        'items': Item.objects.all(),
        'today': today,
        'month_name': today.strftime('%B %Y'),
    }
    return render(request, 'labor_ledger.html', context)

@staff_member_required
@require_POST
def mark_attendance(request):
    try:
        from .models import Attendance, Worker
        worker_id = request.POST.get('worker_id')
        status = request.POST.get('status', 'PRESENT')
        date_str = request.POST.get('date', timezone.now().date())
        ot_hours = float(request.POST.get('ot_hours', 0) or 0)
        
        worker = Worker.objects.get(id=worker_id)
        Attendance.objects.update_or_create(
            worker=worker,
            date=date_str,
            defaults={'status': status, 'overtime_hours': ot_hours}
        )
        return JsonResponse({'status': 'success'})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

@staff_member_required
@require_GET
def get_attendance_for_date(request):
    from .models import Attendance
    date_str = request.GET.get('date')
    if not date_str:
        return JsonResponse({'error': 'Date is required'}, status=400)
    
    records = Attendance.objects.filter(date=date_str)
    data = {
        str(r.worker.id): {
            'status': r.status,
            'ot': r.overtime_hours
        } for r in records
    }
    return JsonResponse({'attendance': data})

@staff_member_required
@require_POST
def record_labor_payment(request):
    try:
        from .models import LaborPayment, Worker, JobWorker
        target_id = request.POST.get('target_id') # e.g. w_5 or jw_3
        amount = request.POST.get('amount')
        p_type = request.POST.get('payment_type', 'ADVANCE')
        
        payment_data = {
            'amount': float(amount),
            'payment_type': p_type,
            'payment_mode': request.POST.get('payment_mode', 'CASH'),
            'notes': request.POST.get('notes', '')
        }
        
        if target_id.startswith('w_'):
            wid = target_id.replace('w_', '')
            payment_data['worker_id'] = wid
            
            if p_type == 'LOAN_REPAYMENT':
                from .models import Loan
                loan = Loan.objects.filter(worker_id=wid, is_active=True).first()
                if loan:
                    loan.remaining_balance -= float(amount)
                    if loan.remaining_balance <= 0:
                        loan.remaining_balance = 0
                        loan.is_active = False
                    loan.save()
            elif p_type == 'NEW_LOAN':
                from .models import Loan
                # Deactivate old loans if any
                Loan.objects.filter(worker_id=wid, is_active=True).update(is_active=False)
                
                emi_val = request.POST.get('emi_amount', '0')
                try:
                    emi_amount = float(emi_val) if emi_val.strip() else 0
                except ValueError:
                    emi_amount = 0

                Loan.objects.create(
                    worker_id=wid,
                    total_amount=float(amount),
                    emi_amount=emi_amount,
                    remaining_balance=float(amount)
                )
                    
        elif target_id.startswith('jw_'):
            jwid = target_id.replace('jw_', '')
            payment_data['job_worker_id'] = jwid
            
            if p_type == 'LOAN_REPAYMENT':
                from .models import Loan
                loan = Loan.objects.filter(job_worker_id=jwid, is_active=True).first()
                if loan:
                    loan.remaining_balance -= float(amount)
                    if loan.remaining_balance <= 0:
                        loan.remaining_balance = 0
                        loan.is_active = False
                    loan.save()
            elif p_type == 'NEW_LOAN':
                from .models import Loan
                Loan.objects.filter(job_worker_id=jwid, is_active=True).update(is_active=False)
                
                emi_val = request.POST.get('emi_amount', '0')
                try:
                    emi_amount = float(emi_val) if emi_val.strip() else 0
                except ValueError:
                    emi_amount = 0

                Loan.objects.create(
                    job_worker_id=jwid,
                    total_amount=float(amount),
                    emi_amount=emi_amount,
                    remaining_balance=float(amount)
                )
            
        LaborPayment.objects.create(**payment_data)
        return JsonResponse({'status': 'success'})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)
