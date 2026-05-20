import json
from django.contrib import messages
from django.shortcuts import render, redirect
from django.urls import reverse
from django.db.models import Sum
from django.utils import timezone

from inventory.models import (
    Client,
    Item,
    StockTransaction,
    TransactionType
)
from inventory import services
from .production import create_default_warehouses
from .master import merge_bom_component_details, sync_bom_worker_allocations

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
            cartons, loose_pieces = item.calculate_cartons_and_loose(ready_qty)

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

    # Advanced operational analytics
    casting_avg_weight = round(float(today_weight) / today_pieces, 3) if today_pieces > 0 else 0.0
    casting_avg_heat_pcs = round(float(today_pieces) / today_heats, 1) if today_heats > 0 else 0.0
    casting_unique_items = today_casting.values("item").distinct().count()

    dispatch_avg_weight = round(float(dispatch_weight) / dispatch_pieces, 3) if dispatch_pieces > 0 else 0.0
    dispatch_unique_clients = today_dispatch.values("client").distinct().count()
    dispatch_unique_items = today_dispatch.values("item").distinct().count()

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
        "casting_avg_weight": casting_avg_weight,
        "casting_avg_heat_pcs": casting_avg_heat_pcs,
        "casting_unique_items": casting_unique_items,

        "dispatch_cartons": dispatch_cartons,
        "dispatch_pieces": dispatch_pieces,
        "dispatch_weight": dispatch_weight,
        "dispatch_avg_weight": dispatch_avg_weight,
        "dispatch_unique_clients": dispatch_unique_clients,
        "dispatch_unique_items": dispatch_unique_items,

        "stock_rows": stock_rows,
    }

    return render(request, "dashboard.html", context)

# =====================================================
# STOCK PAGES
# =====================================================

def casting_stock(request):
    from collections import defaultdict
    from django.db.models import Sum
    from django.utils import timezone
    from inventory.models import StockTransaction, Item, Client

    # 1. Fetch casting entry (production) transactions
    casting_txs = StockTransaction.objects.filter(
        transaction_type__in=["casting_in", "casting_entry"]
    ).select_related("client", "item")

    # 2. Fetch machining issue transactions
    machining_out_txs = StockTransaction.objects.filter(
        transaction_type="machining_out"
    ).select_related("client", "item")

    grouped = defaultdict(lambda: {
        "cast_qty": 0,
        "cast_weight": 0.0,
        "issued_qty": 0,
        "issued_weight": 0.0,
    })

    # Aggregate casting production
    for tx in casting_txs:
        client_name = tx.client.name if tx.client else "NO CLIENT"
        item_code = tx.item.code if tx.item else "-"
        item_name = tx.item.name if tx.item else "-"
        key = (client_name, item_code, item_name)
        
        grouped[key]["cast_qty"] += tx.quantity or 0
        grouped[key]["cast_weight"] += float(tx.weight or 0)

    # Aggregate machining issues
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

    # Graph distributions
    client_stock = defaultdict(int)
    item_stock = defaultdict(lambda: {"cast": 0, "issued": 0, "net": 0})

    for row in rows:
        client_stock[row["client"]] += row["pcs"]
        item_stock[row["item"]]["cast"] += row["cast_pcs"]
        item_stock[row["item"]]["issued"] += row["issued_pcs"]
        item_stock[row["item"]]["net"] += row["pcs"]

    # Graph Client Stock Distribution
    graph_client_labels = list(client_stock.keys())
    graph_client_values = list(client_stock.values())

    # Graph Item stock comparison
    graph_item_labels = list(item_stock.keys())
    graph_item_cast = [d["cast"] for d in item_stock.values()]
    graph_item_issued = [d["issued"] for d in item_stock.values()]
    graph_item_net = [d["net"] for d in item_stock.values()]

    # Production run this month (casting_entry from 1st day of current month)
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

    return render(
        request,
        "casting_stock.html",
        context
    )

def machining_stock(request):
    from collections import defaultdict
    from django.db.models import Sum
    from django.utils import timezone
    from inventory.models import StockTransaction, Item, JobWorker, Worker

    # Fetch all machining transactions
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
        # Support both internal & external
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

    # Graph distributions
    worker_stock = defaultdict(int)
    item_stock = defaultdict(lambda: {"issued": 0, "received": 0, "net": 0})

    for row in rows:
        worker_stock[row["worker"]] += row["pcs"]
        item_stock[row["item"]]["issued"] += row["issued_pcs"]
        item_stock[row["item"]]["received"] += row["received_pcs"]
        item_stock[row["item"]]["net"] += row["pcs"]

    # Graph Worker Stock Distribution
    graph_worker_labels = list(worker_stock.keys())
    graph_worker_values = list(worker_stock.values())

    # Graph Item comparison
    graph_item_labels = list(item_stock.keys())
    graph_item_issued = [d["issued"] for d in item_stock.values()]
    graph_item_received = [d["received"] for d in item_stock.values()]
    graph_item_net = [d["net"] for d in item_stock.values()]

    # Production run this month (machining_in from 1st day of current month)
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

def polishing_stock(request):
    from collections import defaultdict
    from django.db.models import Sum
    from django.utils import timezone
    from inventory.models import StockTransaction, Item, JobWorker, Worker

    # Fetch all polishing transactions
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
        # Support both internal & external
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

    # Graph distributions
    worker_stock = defaultdict(int)
    item_stock = defaultdict(lambda: {"issued": 0, "received": 0, "net": 0})

    for row in rows:
        worker_stock[row["worker"]] += row["pcs"]
        item_stock[row["item"]]["issued"] += row["issued_pcs"]
        item_stock[row["item"]]["received"] += row["received_pcs"]
        item_stock[row["item"]]["net"] += row["pcs"]

    # Graph Worker Stock Distribution
    graph_worker_labels = list(worker_stock.keys())
    graph_worker_values = list(worker_stock.values())

    # Graph Item comparison
    graph_item_labels = list(item_stock.keys())
    graph_item_issued = [d["issued"] for d in item_stock.values()]
    graph_item_received = [d["received"] for d in item_stock.values()]
    graph_item_net = [d["net"] for d in item_stock.values()]

    # Production run this month (polishing_in from 1st day of current month)
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

def ready_stock(request):
    from collections import defaultdict
    from django.db.models import Sum
    from django.utils import timezone
    from inventory.models import StockTransaction, Item

    # Ready stock transactions: packaging_in, kitting_produce (inflows) and dispatch_out (outflows)
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

    # Graph distributions
    item_stock = defaultdict(lambda: {"received": 0, "dispatched": 0, "net": 0})

    for row in rows:
        item_stock[row["item"]]["received"] += row["received_pcs"]
        item_stock[row["item"]]["dispatched"] += row["dispatched_pcs"]
        item_stock[row["item"]]["net"] += row["pcs"]

    # Graph Item Wise Stock Percentage (Pie/Doughnut)
    graph_item_labels = list(item_stock.keys())
    graph_item_values = [d["net"] for d in item_stock.values()]

    # Graph Item comparison (Bar)
    graph_item_received = [d["received"] for d in item_stock.values()]
    graph_item_dispatched = [d["dispatched"] for d in item_stock.values()]

    # Production run this month (packaging_in + kitting_produce from 1st day of current month)
    first_day_of_month = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_prod_qty = StockTransaction.objects.filter(
        transaction_type__in=["packaging_in", "kitting_produce"],
        created_at__gte=first_day_of_month
    ).aggregate(total=Sum('quantity'))['total'] or 0

    context = {
        "rows": rows,
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
            cartons, loose_pieces = item.calculate_cartons_and_loose(ready_qty)
                
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

# =====================================================
# ASSEMBLY (BOM SET PRODUCTION)
# =====================================================

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
                    
                    # Create a NEW Item for the Set with custom process requirements
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
                    
                    # Update process requirements if submitted in the request
                    if any(x in request.POST for x in ['casting_required', 'machining_required', 'polishing_required', 'packing_required']):
                        parent_item.casting_required = request.POST.get('casting_required') == 'on'
                        parent_item.machining_required = request.POST.get('machining_required') == 'on'
                        parent_item.polishing_required = request.POST.get('polishing_required') == 'on'
                        parent_item.packing_required = request.POST.get('packing_required') == 'on'

                from inventory.models import ItemComposition
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
                
                # Auto-merge component details and map worker allocations
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
                
                # Check stock for components
                can_assemble = True
                missing = []
                for comp in compositions:
                    stock = services.get_stock_by_item(comp.component_item)
                    needed = comp.quantity * quantity
                    if stock['polishing'] < needed:
                        can_assemble = False
                        missing.append(f"{comp.component_item.name} (Need {needed}, Have {stock['polishing']})")
                
                if not can_assemble:
                    messages.error(request, f"Insufficient component stock: {', '.join(missing)}")
                else:
                    # Create Transactions
                    from inventory.models import Warehouse
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
