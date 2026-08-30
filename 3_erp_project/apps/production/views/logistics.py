import json
from django.contrib import messages
from django.shortcuts import render, redirect
from django.urls import reverse
from django.db.models import Sum, Q
from django.utils import timezone

from apps.master_data.models import LegalEntity, Client, Warehouse, Item, ItemComposition
from apps.authentication.models import Worker, ProcessType, SalaryModel
from apps.production.models import StockTransaction, TransactionType, ItemWorkerAllocation, Attendance, Loan, LaborPayment, Carton, CartonItem

from apps.production import services
from .production import create_default_warehouses
from .master import merge_bom_component_details, sync_bom_worker_allocations

# =====================================================
# DASHBOARD
# =====================================================

def dashboard(request):
    create_default_warehouses()

    active_company = request.company
    # Use optimized service for overall stock metrics scoped by company
    stock = services.get_overall_stock(company=active_company)

    if active_company:
        items = Item.objects.filter(company=active_company)
        if active_company.id == 1:
            items = items.filter(casting_required=True)
    else:
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
    if active_company:
        today_casting = today_casting.filter(item__company=active_company)

    today_heats = today_casting.values("heat_no").distinct().count()
    today_pieces = today_casting.aggregate(total=Sum("quantity"))["total"] or 0
    today_weight = today_casting.aggregate(total=Sum("weight"))["total"] or 0

    today_dispatch = StockTransaction.objects.filter(
        transaction_type=TransactionType.DISPATCH_OUT,
        created_at__date=today
    ).select_related("item")
    if active_company:
        today_dispatch = today_dispatch.filter(item__company=active_company)
    
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

    from apps.orders.models import SalesOrder
    sales_orders = SalesOrder.objects.all()
    if active_company:
        sales_orders = sales_orders.filter(client__company=active_company)
    total_pos_count = sales_orders.count()
    active_pos_count = sales_orders.filter(status__in=['OPEN', 'PARTIAL']).count()
    pending_pos_count = sales_orders.filter(status='OPEN').count()
    partial_pos_count = sales_orders.filter(status='PARTIAL').count()
    urgent_pos_count = sales_orders.filter(status__in=['OPEN', 'PARTIAL'], priority='URGENT').count()

    context = {
        "casting_stock": stock['casting_qty'],
        "casting_weight": stock['casting_weight'],
        "machining_stock": stock['machining_qty'],
        "machining_weight": stock['machining_weight'],
        "polishing_stock": stock['polishing_qty'],
        "polishing_weight": stock['polishing_weight'],
        "ready_stock": stock['ready_qty'],
        "ready_weight": stock['ready_weight'],
        "total_pos_count": total_pos_count,
        "active_pos_count": active_pos_count,
        "pending_pos_count": pending_pos_count,
        "partial_pos_count": partial_pos_count,
        "urgent_pos_count": urgent_pos_count,

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
        "ready_cartons": sum(row['cartons'] for row in stock_rows),
        "ready_skus": len(stock_rows),
    }

    # Fetch last safety audit fail/skipped delete run to display a dashboard warning banner
    try:
        from apps.master_data.models import MaintenanceSettings, MaintenanceLog
        settings_obj = MaintenanceSettings.objects.first()
        if settings_obj and settings_obj.auto_delete_enabled:
            blocked_maintenance = MaintenanceLog.objects.filter(status="skipped", event_type="audit_fail").order_by("-timestamp").first()
        else:
            blocked_maintenance = None
        context["blocked_maintenance"] = blocked_maintenance
    except Exception:
        context["blocked_maintenance"] = None

    return render(request, "dashboard.html", context)

# =====================================================
# STOCK PAGES
# =====================================================

def casting_stock(request):
    from collections import defaultdict
    from django.db.models import Sum
    from django.utils import timezone

    active_company = request.company

    # 1. Fetch casting entry (production) transactions
    casting_txs = StockTransaction.objects.filter(
        transaction_type=TransactionType.CASTING_ENTRY
    ).select_related("client", "item")

    # 2. Fetch machining issue transactions
    machining_out_txs = StockTransaction.objects.filter(
        transaction_type="machining_out"
    ).select_related("client", "item")

    # Scope transactions by active company
    if active_company:
        if active_company.id == 2:  # OM
            casting_txs = casting_txs.filter(client__name='OM')
            om_item_codes = Item.objects.filter(company_id=2).values_list('code', flat=True)
            machining_out_txs = machining_out_txs.filter(item__code__in=om_item_codes)
        else:  # NC
            casting_txs = casting_txs.exclude(Q(client__name='OM') | Q(item__client__name='OM'))
            machining_out_txs = machining_out_txs.filter(item__company=active_company).exclude(
                Q(client__name='OM') | Q(item__client__name='OM')
            )

    grouped = defaultdict(lambda: {
        "cast_qty": 0,
        "cast_weight": 0.0,
        "issued_qty": 0,
        "issued_weight": 0.0,
    })

    # Aggregate casting production
    for tx in casting_txs:
        client_name = tx.client.name if tx.client else (tx.item.client.name if (tx.item and tx.item.client) else ("OM" if active_company and active_company.id == 2 else "NO CLIENT"))
        item_code = tx.item.code if tx.item else "-"
        item_name = tx.item.name if tx.item else "-"
        key = (client_name, item_code, item_name)
        
        grouped[key]["cast_qty"] += tx.quantity or 0
        grouped[key]["cast_weight"] += float(tx.weight or 0)

    # Aggregate machining issues
    for tx in machining_out_txs:
        client_name = tx.client.name if tx.client else (tx.item.client.name if (tx.item and tx.item.client) else ("OM" if active_company and active_company.id == 2 else "NO CLIENT"))
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
        
        stock_qty = cast_qty - issued_qty
        stock_wt = round(value["cast_weight"] - value["issued_weight"], 3)

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
        client_stock[row["client"]] += max(0, row["pcs"])
        item_stock[row["item"]]["cast"] += row["cast_pcs"]
        item_stock[row["item"]]["issued"] += row["issued_pcs"]
        item_stock[row["item"]]["net"] += max(0, row["pcs"])

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
    month_prod_qs = StockTransaction.objects.filter(
        transaction_type=TransactionType.CASTING_ENTRY,
        created_at__gte=first_day_of_month
    )
    if active_company:
        if active_company.id == 2:
            month_prod_qs = month_prod_qs.filter(client__name='OM')
        else:
            month_prod_qs = month_prod_qs.exclude(client__name='OM')
    month_prod_qty = month_prod_qs.aggregate(total=Sum('quantity'))['total'] or 0

    if active_company:
        all_items = Item.objects.filter(company=active_company, active=True, casting_required=True).exclude(item_type="SET").exclude(components__isnull=False).distinct().order_by('code')
    else:
        all_items = Item.objects.filter(active=True, casting_required=True).exclude(item_type="SET").exclude(components__isnull=False).distinct().order_by('code')
    all_warehouses = Warehouse.objects.all().order_by('name')

    overall_stock = services.get_overall_stock(company=active_company)

    # Calculate item-wise warehouse available stock
    warehouse_rows = []
    for item in all_items:
        stock = services.get_stock_by_item(item)
        qty = stock['casting']
        if qty != 0: # Show items with active stock or transaction history
            warehouse_rows.append({
                "code": item.code,
                "item": item.name,
                "pcs": qty,
                "weight": round(qty * float(item.casting_weight or 0), 3)
            })

    context = {
        "rows": rows,
        "warehouse_rows": warehouse_rows,
        "total_cast_pcs": total_cast_pcs,
        "total_cast_wt": round(total_cast_wt, 3),
        "total_issued_pcs": total_issued_pcs,
        "total_issued_wt": round(total_issued_wt, 3),
        "total_stock_pcs": max(0, total_stock_pcs),
        "total_stock_wt": max(0.0, round(total_stock_wt, 3)),
        "available_casting_pcs": overall_stock['casting_qty'],
        "available_casting_wt": overall_stock['casting_weight'],
        "month_prod_qty": month_prod_qty,
        "graph_client_labels": graph_client_labels,
        "graph_client_values": graph_client_values,
        "graph_item_labels": graph_item_labels,
        "graph_item_cast": graph_item_cast,
        "graph_item_issued": graph_item_issued,
        "graph_item_net": graph_item_net,
        "all_items": all_items,
        "all_warehouses": all_warehouses,
    }

    return render(
        request,
        "casting_stock.html",
        context
    )

def machined_stock(request):
    active_company = request.company
    from collections import defaultdict
    from django.db.models import Sum
    from django.utils import timezone

    # Fetch all machining transactions
    txs = StockTransaction.objects.filter(
        transaction_type__in=["machining_out", "machining_in"]
    ).select_related("worker", "job_worker", "item")

    grouped = defaultdict(lambda: {
        "issued_qty": 0,
        "issued_weight": 0.0,
        "received_qty": 0,
        "received_weight": 0.0,
        "rejected_qty": 0,
        "unit_weight": 0.0,
    })

    for tx in txs:
        # Support both internal & external
        if tx.worker:
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
            grouped[key]["rejected_qty"] += tx.rejection_quantity or 0

        if tx.item:
            grouped[key]["unit_weight"] = float(tx.item.machining_weight or tx.item.casting_weight or 0.0)

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
        wip_qty = max(0, issued_qty - received_qty - val["rejected_qty"])
        rejected_wt = val["rejected_qty"] * val["unit_weight"]
        wip_wt = max(0.0, round(val["issued_weight"] - val["received_weight"] - rejected_wt, 3))

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

    if active_company:
        all_items = Item.objects.filter(company=active_company, active=True, machining_required=True).exclude(item_type="SET").exclude(components__isnull=False).exclude(is_raw_material=True).distinct().order_by('code')
    else:
        all_items = Item.objects.filter(active=True, machining_required=True).exclude(item_type="SET").exclude(components__isnull=False).exclude(is_raw_material=True).distinct().order_by('code')
    all_warehouses = Warehouse.objects.all().order_by('name')

    overall_stock = services.get_overall_stock(company=active_company)

    # Calculate item-wise warehouse available stock
    warehouse_rows = []
    for item in all_items:
        stock = services.get_stock_by_item(item)
        qty = stock['machining']
        if qty != 0: # Show items with active stock or transaction history
            warehouse_rows.append({
                "code": item.code,
                "item": item.name,
                "pcs": qty,
                "weight": round(qty * float(item.machining_weight or 0), 3)
            })

    context = {
        "rows": rows,
        "warehouse_rows": warehouse_rows,
        "total_issued_pcs": total_issued_pcs,
        "total_issued_wt": round(total_issued_wt, 3),
        "total_received_pcs": total_received_pcs,
        "total_received_wt": round(total_received_wt, 3),
        "total_wip_pcs": max(0, total_wip_pcs),
        "total_wip_wt": max(0.0, round(total_wip_wt, 3)),
        "available_machining_pcs": overall_stock['machining_qty'],
        "available_machining_wt": overall_stock['machining_weight'],
        "month_prod_qty": month_prod_qty,
        "graph_worker_labels": graph_worker_labels,
        "graph_worker_values": graph_worker_values,
        "graph_item_labels": graph_item_labels,
        "graph_item_issued": graph_item_issued,
        "graph_item_received": graph_item_received,
        "graph_item_net": graph_item_net,
        "all_items": all_items,
        "all_warehouses": all_warehouses,
    }

    return render(request, "machined_stock.html", context)

def polished_stock(request):
    active_company = request.company
    from collections import defaultdict
    from django.db.models import Sum
    from django.utils import timezone

    # Fetch all polishing transactions
    txs = StockTransaction.objects.filter(
        transaction_type__in=["polishing_out", "polishing_in"]
    ).select_related("worker", "job_worker", "item")

    grouped = defaultdict(lambda: {
        "issued_qty": 0,
        "issued_weight": 0.0,
        "received_qty": 0,
        "received_weight": 0.0,
        "rejected_qty": 0,
        "unit_weight": 0.0,
    })

    for tx in txs:
        # Support both internal & external
        if tx.worker:
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
            grouped[key]["rejected_qty"] += tx.rejection_quantity or 0

        if tx.item:
            grouped[key]["unit_weight"] = float(tx.item.machining_weight or tx.item.casting_weight or 0.0)

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
        wip_qty = max(0, issued_qty - received_qty - val["rejected_qty"])
        rejected_wt = val["rejected_qty"] * val["unit_weight"]
        wip_wt = max(0.0, round(val["issued_weight"] - val["received_weight"] - rejected_wt, 3))

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

    if active_company:
        all_items = Item.objects.filter(company=active_company, active=True).filter(Q(polishing_required=True) | Q(item_type='SET') | Q(components__isnull=False)).distinct().order_by('code')
    else:
        all_items = Item.objects.filter(active=True).filter(Q(polishing_required=True) | Q(item_type='SET') | Q(components__isnull=False)).distinct().order_by('code')
    all_warehouses = Warehouse.objects.all().order_by('name')

    overall_stock = services.get_overall_stock(company=active_company)

    # Calculate item-wise warehouse available stock
    warehouse_rows = []
    for item in all_items:
        stock = services.get_stock_by_item(item)
        qty = stock['polishing']
        if qty != 0: # Show items with active stock or transaction history
            warehouse_rows.append({
                "code": item.code,
                "item": item.name,
                "pcs": qty,
                "weight": round(qty * float(item.machining_weight or 0), 3) # using machining_weight as single reference
            })

    context = {
        "rows": rows,
        "warehouse_rows": warehouse_rows,
        "total_issued_pcs": total_issued_pcs,
        "total_issued_wt": round(total_issued_wt, 3),
        "total_received_pcs": total_received_pcs,
        "total_received_wt": round(total_received_wt, 3),
        "total_wip_pcs": max(0, total_wip_pcs),
        "total_wip_wt": max(0.0, round(total_wip_wt, 3)),
        "available_polishing_pcs": overall_stock['polishing_qty'],
        "available_polishing_wt": overall_stock['polishing_weight'],
        "month_prod_qty": month_prod_qty,
        "graph_worker_labels": graph_worker_labels,
        "graph_worker_values": graph_worker_values,
        "graph_item_labels": graph_item_labels,
        "graph_item_issued": graph_item_issued,
        "graph_item_received": graph_item_received,
        "graph_item_net": graph_item_net,
        "all_items": all_items,
        "all_warehouses": all_warehouses,
    }

    return render(request, "polished_stock.html", context)

def ready_stock(request):
    from collections import defaultdict
    from django.db.models import Sum
    from django.utils import timezone

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

    # Fetch ready cartons grouped logically by Carton Label / Item
    from collections import defaultdict
    raw_ready_cartons = Carton.objects.filter(status='READY').prefetch_related('items__item', 'client', 'sales_order').order_by('-created_at')
    
    cartons_grouped = defaultdict(list)
    for carton in raw_ready_cartons:
        lbl = carton.carton_label if carton.carton_label else carton.carton_number
        cartons_grouped[lbl].append(carton)
        
    grouped_cartons = []
    total_ready_cartons_count = raw_ready_cartons.count()
    
    for lbl, group_cartons in cartons_grouped.items():
        first_c = group_cartons[0]
        total_group_qty = sum(c.total_quantity for c in group_cartons)
        total_group_wt = sum(float(c.total_weight or 0.0) for c in group_cartons)
        
        per_carton_wt = round(float(first_c.total_weight or 0.0), 3)
        per_carton_pcs = first_c.total_quantity
        
        carton_numbers_list = [c.carton_number for c in group_cartons]
        carton_numbers_str = ", ".join(carton_numbers_list)
        
        nested_items = []
        if first_c.items.exists():
            for ci in first_c.items.all():
                nested_items.append({
                    'code': ci.item.code,
                    'name': ci.item.name,
                    'qty': ci.quantity,
                    'weight': round(float(ci.weight or 0.0), 3)
                })

        grouped_cartons.append({
            'carton_label': lbl,
            'carton_type': first_c.carton_type,
            'carton_type_display': first_c.get_carton_type_display(),
            'carton_numbers': carton_numbers_list,
            'carton_numbers_str': carton_numbers_str,
            'cartons_count': len(group_cartons),
            'per_carton_pcs': per_carton_pcs,
            'per_carton_wt': per_carton_wt,
            'total_qty': total_group_qty,
            'total_weight': round(total_group_wt, 3),
            'status': first_c.status,
            'status_display': first_c.get_status_display(),
            'client_name': first_c.client.name if first_c.client else 'Global Client',
            'sales_order_number': first_c.sales_order.order_number if first_c.sales_order else None,
            'nested_items': nested_items,
        })

    # Fetch global master items and warehouses to populate correction drawers
    active_company = request.company
    if active_company:
        all_items = Item.objects.filter(company=active_company, active=True).order_by('code')
    else:
        all_items = Item.objects.filter(active=True).order_by('code')
    all_warehouses = Warehouse.objects.all().order_by('name')
    # Detailed Component and Loose Piece Stock Breakdown
    from apps.production import services
    piece_rows = []
    for item in all_items:
        stk = services.get_stock_by_item(item)
        r_qty = stk.get('ready', 0)
        unit_wt = float(item.machining_weight or item.casting_weight or 0.0)
        r_wt = round(r_qty * unit_wt, 3)
        piece_rows.append({
            'id': item.id,
            'code': item.code,
            'name': item.name,
            'category': item.category or 'OTHER',
            'sub_category': item.sub_category or 'OTHER',
            'item_type': item.item_type,
            'pcs': max(0, r_qty),
            'weight': max(0.0, r_wt)
        })

    recent_dispatches = StockTransaction.objects.filter(
        transaction_type="dispatch_out"
    ).select_related('client', 'item').order_by("-created_at")[:50]

    context = {
        "rows": rows,
        "piece_rows": piece_rows,
        "recent_dispatches": recent_dispatches,
        "available_cartons": grouped_cartons,
        "total_received_pcs": total_received_pcs,
        "total_received_wt": round(total_received_wt, 3),
        "total_dispatched_pcs": total_dispatched_pcs,
        "total_dispatched_wt": round(total_dispatched_wt, 3),
        "total_net_pcs": max(0, total_net_pcs),
        "total_net_wt": max(0.0, round(total_net_wt, 3)),
        "month_prod_qty": month_prod_qty,
        "total_ready_cartons": total_ready_cartons_count,
        "total_ready_items": sum(1 for row in rows if row["pcs"] > 0),
        "graph_item_labels": graph_item_labels,
        "graph_item_values": graph_item_values,
        "graph_item_received": graph_item_received,
        "graph_item_dispatched": graph_item_dispatched,
        "all_items": all_items,
        "all_warehouses": all_warehouses,
    }

    return render(request, "ready_stock.html", context)

# =====================================================
# DISPATCH & SALES
# =====================================================

def allocate_dispatch_to_sales_orders(client, item, quantity, weight):
    """
    Allocates dispatched items to the client's open / partial Sales Orders in FIFO order.
    Creates Dispatch and DispatchItem database records, and updates SalesOrder statuses.
    """
    from apps.orders.models import SalesOrder, SalesOrderItem, Dispatch, DispatchItem
    
    remaining_qty = quantity
    # Find active sales orders for this client that contain this item and are not completed
    open_order_items = SalesOrderItem.objects.filter(
        sales_order__client=client,
        sales_order__status__in=[SalesOrder.OrderStatus.OPEN, SalesOrder.OrderStatus.PARTIAL],
        item=item
    ).order_by('sales_order__promised_date', 'sales_order__id')
    
    for order_item in open_order_items:
        if remaining_qty <= 0:
            break
            
        needed = order_item.remaining_quantity
        if needed <= 0:
            continue
            
        allocated_qty = min(remaining_qty, needed)
        allocated_weight = round((allocated_qty / quantity) * weight, 3) if quantity > 0 else 0.0
        
        # Get or create Dispatch for this order
        dispatch_obj = Dispatch.objects.filter(sales_order=order_item.sales_order, client=client).first()
        if not dispatch_obj:
            dispatch_obj = Dispatch.objects.create(
                sales_order=order_item.sales_order,
                client=client,
                notes=f"Auto-generated dispatch from Carton/Manual fulfillment"
            )
            
        # Create DispatchItem
        DispatchItem.objects.create(
            dispatch=dispatch_obj,
            item=item,
            quantity=allocated_qty,
            weight=allocated_weight
        )
        
        remaining_qty -= allocated_qty
        
        # Update SalesOrder status
        order = order_item.sales_order
        total_remaining = sum(so_item.remaining_quantity for so_item in order.items.all())
        if total_remaining == 0:
            order.status = SalesOrder.OrderStatus.COMPLETED
        else:
            order.status = SalesOrder.OrderStatus.PARTIAL
        order.save()


def dispatch_view(request):
    from django.contrib import messages
    from django.shortcuts import redirect, render
    from django.utils import timezone
    from apps.production import services

    if request.company:
        clients = Client.objects.filter(company=request.company)
        items = Item.objects.filter(company=request.company)
        if request.company.id == 1:
            items = items.filter(casting_required=True)
    else:
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
            carton_labels = request.POST.getlist("carton_label_select[]")
            carton_counts_raw = request.POST.getlist("carton_count[]")
            
            if not carton_labels:
                messages.error(request, "Please select at least one Carton Type.")
                return redirect("dispatch")

            dispatched_count = 0
            total_pieces = 0
            total_weight = 0.0
            error_occured = False

            for idx, label in enumerate(carton_labels):
                if not label:
                    continue
                
                try:
                    count = int(carton_counts_raw[idx])
                except (ValueError, IndexError):
                    continue
                    
                if count <= 0:
                    continue

                # Fetch oldest READY cartons matching name / label (FIFO style)
                matching_cartons = Carton.objects.filter(
                    status='READY',
                    carton_label=label
                ).order_by('created_at')[:count]

                if matching_cartons.count() < count:
                    messages.error(request, f"Lacking physical ready cartons in warehouse for '{label}'. Requested {count}, but only {matching_cartons.count()} are ready.")
                    error_occured = True
                    break

                for carton in matching_cartons:
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
                        allocate_dispatch_to_sales_orders(client, ci.item, ci.quantity, ci.weight)
                        total_pieces += ci.quantity
                        total_weight += ci.weight
                    dispatched_count += count

            if error_occured:
                # Symmetrically abort transaction / redirect back
                return redirect("dispatch")

            if dispatched_count > 0:
                messages.success(
                    request,
                    f"Successfully dispatched {dispatched_count} cartons ({total_pieces} pcs, {round(total_weight, 3)} kg) to {client.name} (FIFO Auto-picked)."
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
            allocate_dispatch_to_sales_orders(client, item, pieces, weight)

            messages.success(request, f"Successfully dispatched {pieces} pcs of {item.name} to {client.name} (Manual Override).")
            return redirect("dispatch")

    # GET Handler: Get Ready Stock summary via bulk aggregated queries
    ready_txs = StockTransaction.objects.filter(
        transaction_type__in=[
            TransactionType.PACKAGING_IN,
            TransactionType.KITTING_PRODUCE,
            TransactionType.DISPATCH_OUT,
            TransactionType.STOCK_ADJUSTMENT
        ]
    )
    if request.company:
        ready_txs = ready_txs.filter(item__company=request.company)

    from django.db.models import Sum
    tx_totals = ready_txs.values('item_id', 'transaction_type', 'from_warehouse__code', 'to_warehouse__code').annotate(total=Sum('quantity'))

    item_ready_map = {}
    for t in tx_totals:
        iid = t['item_id']
        ttype = t['transaction_type']
        from_wh = t['from_warehouse__code']
        to_wh = t['to_warehouse__code']
        qty = t['total'] or 0
        if iid not in item_ready_map:
            item_ready_map[iid] = 0
            
        if ttype in [TransactionType.PACKAGING_IN, TransactionType.KITTING_PRODUCE]:
            item_ready_map[iid] += qty
        elif ttype == TransactionType.DISPATCH_OUT:
            item_ready_map[iid] -= qty
        elif ttype == TransactionType.STOCK_ADJUSTMENT:
            if to_wh == 'READY':
                item_ready_map[iid] += qty
            if from_wh == 'READY':
                item_ready_map[iid] -= qty

    stock_rows = []
    for item in items:
        ready_qty = max(0, item_ready_map.get(item.id, 0))
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
    cartons_qs = Carton.objects.prefetch_related('items', 'items__item').select_related('sales_order', 'client').filter(status='READY').order_by('-created_at')

    # Group by name / label (e.g. K7D7-REG)
    from collections import defaultdict
    grouped = defaultdict(list)
    for c in cartons_qs:
        name = c.carton_label if c.carton_label else c.carton_number
        grouped[name].append(c)

    grouped_cartons = []
    for name, list_of_cartons in grouped.items():
        first_c = next((c for c in list_of_cartons if c.items.exists()), list_of_cartons[0])
        total_qty = sum(c.total_quantity for c in list_of_cartons)
        total_weight = sum(c.total_weight for c in list_of_cartons)
        carton_ids = ",".join(str(c.id) for c in list_of_cartons)

        # Get first carton items breakdown (they are identical type cartons)
        items_breakdown = []
        for ci in first_c.items.all():
            items_breakdown.append({
                'code': ci.item.code,
                'quantity': ci.quantity
            })

        # Calculate display sets/qty for the header item
        display_qty = total_qty
        is_set = first_c.carton_type == 'SET'
        if is_set and first_c.items.exists():
            # For SET cartons, use the component quantity of a single carton * number of cartons
            single_set_qty = first_c.items.first().quantity
            display_qty = single_set_qty * len(list_of_cartons)

        grouped_cartons.append({
            'name': name,
            'carton_type': first_c.carton_type,
            'count': len(list_of_cartons),
            'total_quantity': total_qty,
            'total_weight': round(total_weight, 3),
            'carton_ids': carton_ids,
            'is_set': is_set,
            'display_qty': display_qty,
            'items_breakdown': items_breakdown,
            'sales_order_id': first_c.sales_order_id if first_c.sales_order else None,
            'sales_order_number': first_c.sales_order.order_number if first_c.sales_order else None,
            'client_name': first_c.client.name if first_c.client else None,
            'sub_items': [{
                'id': c.id,
                'carton_number': c.carton_number,
                'total_quantity': c.total_quantity,
                'total_weight': c.total_weight,
                'display_qty': c.items.first().quantity if (c.carton_type == 'SET' and c.items.exists()) else c.total_quantity
            } for c in list_of_cartons]
        })

    recent_dispatches = StockTransaction.objects.filter(
        transaction_type=TransactionType.DISPATCH_OUT
    ).select_related('client', 'item').order_by("-created_at")

    # Load active customer POs (Customer Sales Orders)
    from apps.orders.models import SalesOrder
    active_orders = SalesOrder.objects.filter(
        status__in=[SalesOrder.OrderStatus.OPEN, SalesOrder.OrderStatus.PARTIAL]
    ).prefetch_related('items', 'items__item').select_related('client').order_by('promised_date')

    if request.company:
        recent_dispatches = recent_dispatches.filter(client__company=request.company)
        active_orders = active_orders.filter(client__company=request.company)

    recent_dispatches = recent_dispatches[:20]

    from apps.orders.views import bulk_fetch_order_metrics
    bulk_fetch_order_metrics(active_orders, company=request.company)

    context = {
        "clients": clients,
        "items": items,
        "stock_rows": stock_rows,
        "available_cartons": grouped_cartons,
        "recent_dispatches": recent_dispatches,
        "active_orders": active_orders,
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
