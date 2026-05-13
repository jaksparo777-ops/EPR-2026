from django.contrib import messages
from django.shortcuts import render, redirect
from django.urls import reverse
from django.db.models import Sum
from django.utils import timezone

from .models import (
    Client,
    Item,
    Worker,
    JobWorker,
    Warehouse,
    StockTransaction,
    TransactionType
)
from .forms import CastingEntryForm, ItemForm, ClientForm, WorkerForm
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
            stock_rows.append({
                "code": item.code,
                "item": item,  # Passing the whole item object
                "pieces": ready_qty,
                "weight": round(ready_qty * float(item.weight_per_piece or 0), 3)
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

        client_id = request.POST.get("client")
        item_id = request.POST.get("item")

        if not client_id or not item_id:
            messages.error(
                request,
                "Client and item are required for casting entry."
            )
            return redirect("casting_entry")

        try:
            client = Client.objects.get(id=client_id)
            item = Item.objects.get(id=item_id)
        except (Client.DoesNotExist, Item.DoesNotExist):
            messages.error(
                request,
                "Selected client or item was not found."
            )
            return redirect("casting_entry")

        quantity = int(
            request.POST.get("quantity") or 0
        )

        weight = float(
            request.POST.get("weight") or 0
        )

        heat_no = request.POST.get("heat_no")

        notes = request.POST.get("notes")

        StockTransaction.objects.create(

            transaction_type=TransactionType.CASTING_ENTRY,

            client=client,
            item=item,

            quantity=quantity,
            weight=weight,

            heat_no=heat_no,
            notes=notes

        )

        messages.success(
            request,
            "Casting entry saved successfully."
        )

        return redirect("casting_entry")

    recent_raw = StockTransaction.objects.filter(
        transaction_type__in=[
            "casting_in",
            "casting_entry"
        ]
    ).order_by("-id")[:20]

    recent = []

    for r in recent_raw:

        recent.append({

            "date": (
                r.created_at.strftime("%d/%m/%Y")
                if r.created_at else "-"
            ),

            "heat_no": (
                r.heat_no
                if r.heat_no else "-"
            ),

            "item": (
                r.item.name
                if r.item else "-"
            ),

            "client": (
                r.client.name
                if r.client else "-"
            ),

            "quantity": r.quantity or 0,
            "weight": r.weight or 0,

        })

    total_entries = recent_raw.count()

    total_pcs = recent_raw.aggregate(
        total=Sum("quantity")
    )["total"] or 0

    total_weight = recent_raw.aggregate(
        total=Sum("weight")
    )["total"] or 0

    context = {

        "clients": clients,
        "items": items,

        "recent": recent,

        "total_entries": total_entries,
        "total_pcs": total_pcs,
        "total_weight": total_weight,

    }

    return render(request, "casting.html", context)

# =====================================================
# MACHINING
# =====================================================

def machining_entry(request):

    create_default_warehouses()

    workers = JobWorker.objects.filter(
    process="machining"
)
    items = Item.objects.all()

    if request.method == "POST":

        direction = request.POST.get("direction")

        item_id = request.POST.get("item")
        worker_id = request.POST.get("worker")

        if not direction or not item_id:
            messages.error(
                request,
                "Please choose an item and direction before saving machining activity."
            )
            return redirect("machining_entry")

        try:
            item = Item.objects.get(id=item_id)
        except Item.DoesNotExist:
            messages.error(
                request,
                "Selected item was not found."
            )
            return redirect("machining_entry")

        quantity = int(
            request.POST.get("quantity") or 0
        )

        weight = float(
            request.POST.get("weight") or 0
        )

        job_worker = None

        if worker_id:
            try:
                job_worker = JobWorker.objects.get(id=worker_id)
            except JobWorker.DoesNotExist:
                messages.error(
                    request,
                    "Selected job worker was not found."
                )
                return redirect("machining_entry")

        StockTransaction.objects.create(

            transaction_type=direction,

            item=item,
            job_worker=job_worker,

            quantity=quantity,
            weight=weight

        )

        messages.success(
            request,
            "Machining transaction saved successfully."
        )

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

        workers_data = StockTransaction.objects.filter(
            item=item,
            transaction_type="machining_out"
        )

        worker_summary = {}

        for row in workers_data:

            worker_name = (
                row.job_worker.name
                if row.job_worker else "NO WORKER"
            )

            if worker_name not in worker_summary:
                worker_summary[worker_name] = 0

            worker_summary[worker_name] += row.quantity or 0

        for worker_name, issued_qty in worker_summary.items():

            received_qty = StockTransaction.objects.filter(
                item=item,
                job_worker__name=worker_name,
                transaction_type="machining_in"
            ).aggregate(
                total=Sum("quantity")
            )["total"] or 0

            under_process = issued_qty - received_qty

            machining_stock.append({

                "item": item,
                "worker": worker_name,
                "under_process": under_process,
                "available_qty": available_qty

            })

    worker_wip = []

    for worker in workers:

        issued = StockTransaction.objects.filter(
            job_worker=worker,
            transaction_type="machining_out"
        ).aggregate(
            total=Sum("quantity")
        )["total"] or 0

        received = StockTransaction.objects.filter(
            job_worker=worker,
            transaction_type="machining_in"
        ).aggregate(
            total=Sum("quantity")
        )["total"] or 0

        pending = issued - received

        if issued > 0 or received > 0:

            worker_wip.append({

                "worker": worker,
                "issued": issued,
                "received": received,
                "pending": pending

            })

    context = {

        "workers": workers,
        "items": items,

        "recent": recent,

        "machining_stock": machining_stock,

        "worker_wip": worker_wip,

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

    workers = Worker.objects.all()
    items = Item.objects.all()

    available_data = {}

    for item in items:

        machining_in_qty = StockTransaction.objects.filter(
            item=item,
            transaction_type="machining_in"
        ).aggregate(
            total=Sum("quantity")
        )["total"] or 0

        polishing_out_qty = StockTransaction.objects.filter(
            item=item,
            transaction_type="polishing_out"
        ).aggregate(
            total=Sum("quantity")
        )["total"] or 0

        available_qty = machining_in_qty - polishing_out_qty

        available_data[item.id] = available_qty

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

        try:

            worker = Worker.objects.get(
                id=worker_id
            )

        except Worker.DoesNotExist:

            messages.error(
                request,
                "Selected worker was not found."
            )
            return redirect("polishing_entry")

        rows = request.POST.getlist("item[]")

        for index, item_id in enumerate(rows):

            if not item_id:
                continue

            item = Item.objects.get(id=item_id)

            lots = int(
                request.POST.getlist("lots[]")[index] or 0
            )

            manual = int(
                request.POST.getlist("manual[]")[index] or 0
            )

            weight = float(
                request.POST.getlist("weight[]")[index] or 0
            )

            quantity = manual

            if lots > 0 and item.lot_size:

                quantity = lots * item.lot_size

            StockTransaction.objects.create(

                transaction_type="polishing_out",

                item=item,
                worker=worker,

                quantity=quantity,
                weight=weight

            )

        messages.success(
            request,
            "Polishing entries saved successfully."
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
        request,
        "packaging.html",
        context
    )
# =====================================================
# MASTER DATA
# =====================================================

def master_data(request):
    active_tab = request.GET.get("tab", "items")
    
    # Handle GET data for editing
    edit_item = Item.objects.filter(id=request.GET.get("edit")).first()
    edit_client = Client.objects.filter(id=request.GET.get("edit_client")).first()
    edit_worker = Worker.objects.filter(id=request.GET.get("edit_worker")).first()

    if request.method == "POST":
        form_type = request.POST.get("form_type")
        
        if form_type == "item":
            data = request.POST.copy()
            if data.get('custom_client'):
                client = Client.objects.filter(name=data.get('custom_client')).first()
                if client:
                    data['client'] = client.id
            if data.get('custom_material'):
                data['material'] = data.get('custom_material')
            
            form = ItemForm(data, instance=edit_item)
            if form.is_valid():
                form.save()
                messages.success(request, f"Item {'updated' if edit_item else 'created'} successfully.")
                return redirect(f"{reverse('master_data')}?tab=items")
            else:
                messages.error(request, "Error saving item. Please check the form.")

        elif form_type == "client":
            data = request.POST.copy()
            data['name'] = data.get('client_name')
            data['phone'] = data.get('client_phone')
            data['city'] = data.get('client_city')
            
            form = ClientForm(data, instance=edit_client)
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
            data['phone'] = data.get('worker_phone')
            
            form = WorkerForm(data, instance=edit_worker)
            if form.is_valid():
                form.save()
                messages.success(request, f"Worker {'updated' if edit_worker else 'created'} successfully.")
                return redirect(f"{reverse('master_data')}?tab=workers")
            else:
                messages.error(request, "Error saving worker.")

    context = {
        "clients": Client.objects.all(),
        "items": Item.objects.all(),
        "workers": Worker.objects.all(),
        "edit_item_data": edit_item,
        "edit_client_data": edit_client,
        "edit_worker_data": edit_worker,
        "active_tab": active_tab,
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

        "job_worker",
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

        if tx.job_worker:

            worker_name = tx.job_worker.name

        elif tx.worker:

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
def delete_item(request, item_id):

    try:
        item = Item.objects.get(
            id=item_id
        )
        item.delete()
        messages.success(
            request,
            "Item deleted successfully."
        )
    except Item.DoesNotExist:
        messages.error(
            request,
            "Item could not be found for deletion."
        )

    return redirect(
        "master_data"
    )
def edit_item(request, item_id):

    item = Item.objects.get(id=item_id)

    if request.method == "POST":

        item.name = request.POST.get("item_name")
        item.code = request.POST.get("item_code")
        item.category = request.POST.get("category")
        item.weight_per_piece = float(
            request.POST.get("weight_per_piece") or 0
        )

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
        pieces = int(request.POST.get("quantity") or 0)
        weight = float(request.POST.get("weight") or 0)

        if not client_id or not item_id or pieces <= 0:
            messages.error(request, "Client, Item, and valid Quantity (Pieces) are required.")
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
            if item.lot_with_box and item.lot_with_box > 0:
                cartons = ready_qty // item.lot_with_box
                
            # Only show if there's at least 1 full carton, or if the user doesn't use cartons
            if cartons > 0 or not item.lot_with_box:
                stock_rows.append({
                    "item": item,
                    "cartons": cartons,
                    "pieces": ready_qty,
                    "weight": round(ready_qty * float(item.weight_per_piece or 0), 3)
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

