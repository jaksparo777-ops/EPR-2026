from django.shortcuts import render, redirect
from django.db.models import Sum
from django.utils import timezone

from .models import (
    Client,
    Item,
    Worker,
    Warehouse,
    StockTransaction
)

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
    ).aggregate(total=Sum("quantity"))["total"] or 0

    return inward

# =====================================================

# DASHBOARD

# =====================================================


def dashboard(request):

    create_default_warehouses()

    items = Item.objects.all()

    casting_stock = 0
    machining_stock = 0
    polishing_stock = 0
    ready_stock = 0

    stock_rows = []

    for item in items:

        casting_qty = get_casting_stock(item)
        machining_qty = get_machining_stock(item)
        polishing_qty = get_polishing_stock(item)
        ready_qty = get_ready_stock(item)

        casting_stock += casting_qty
        machining_stock += machining_qty
        polishing_stock += polishing_qty
        ready_stock += ready_qty

        if casting_qty > 0:

            stock_rows.append({

                "code": item.code,
                "item": item.name,
                "pieces": casting_qty,
                "weight": round(
                    casting_qty * float(item.weight_per_piece or 0),
                    3
                )

            })

    today = timezone.now().date()

    today_casting = StockTransaction.objects.filter(
        transaction_type__in=[
            "casting_in",
            "casting_entry"
        ],
        created_at__date=today
    )

    today_heats = today_casting.values(
        "heat_no"
    ).distinct().count()

    today_pieces = today_casting.aggregate(
        total=Sum("quantity")
    )["total"] or 0

    today_weight = today_casting.aggregate(
        total=Sum("weight")
    )["total"] or 0

    context = {

        "casting_stock": casting_stock,
        "machining_stock": machining_stock,
        "polishing_stock": polishing_stock,
        "ready_stock": ready_stock,

        "today_heats": today_heats,
        "today_pieces": today_pieces,
        "today_weight": today_weight,

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

        client = Client.objects.get(
            id=request.POST.get("client")
        )

        item = Item.objects.get(
            id=request.POST.get("item")
        )

        quantity = int(
            request.POST.get("quantity") or 0
        )

        weight = float(
            request.POST.get("weight") or 0
        )

        heat_no = request.POST.get("heat_no")

        notes = request.POST.get("notes")

        StockTransaction.objects.create(

            transaction_type="casting_in",

            client=client,
            item=item,

            quantity=quantity,
            weight=weight,

            heat_no=heat_no,
            notes=notes

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

    workers = Worker.objects.all()
    items = Item.objects.all()

    if request.method == "POST":

        direction = request.POST.get("direction")

        item_id = request.POST.get("item")
        worker_id = request.POST.get("worker")

        quantity = int(
            request.POST.get("quantity") or 0
        )

        weight = float(
            request.POST.get("weight") or 0
        )

        item = None
        worker = None

        if item_id:
            item = Item.objects.get(id=item_id)

        if worker_id:
            worker = Worker.objects.get(id=worker_id)

        StockTransaction.objects.create(

            transaction_type=direction,

            item=item,
            worker=worker,

            quantity=quantity,
            weight=weight

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
                row.worker.name
                if row.worker else "NO WORKER"
            )

            if worker_name not in worker_summary:
                worker_summary[worker_name] = 0

            worker_summary[worker_name] += row.quantity or 0

        for worker_name, issued_qty in worker_summary.items():

            received_qty = StockTransaction.objects.filter(
                item=item,
                worker__name=worker_name,
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
            worker=worker,
            transaction_type="machining_out"
        ).aggregate(
            total=Sum("quantity")
        )["total"] or 0

        received = StockTransaction.objects.filter(
            worker=worker,
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

    if request.method == "POST":

        worker_id = request.POST.get("worker")

        if not worker_id:
            return redirect("polishing")

        try:

            worker = Worker.objects.get(
                id=worker_id
            )

        except Worker.DoesNotExist:

            return redirect("polishing")

        direction = request.POST.get("direction")

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

            transaction_type = "polishing_out"

            if direction == "in":
                transaction_type = "polishing_in"

            StockTransaction.objects.create(

                transaction_type=transaction_type,

                item=item,
                worker=worker,

                quantity=quantity,
                weight=weight

            )

        return redirect("polishing_entry")

    recent = StockTransaction.objects.filter(
        transaction_type__in=[
            "polishing_out",
            "polishing_in"
        ]
    ).order_by("-created_at")[:20]

    context = {

        "workers": workers,
        "items": items,
        "recent": recent,
        "available_data": available_data,

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

    queue = []

    for item in items:

        available = get_polishing_stock(item)

        if available > 0:

            queue.append({

                "item": item,
                "available": available,
                "weight": round(
                    available * float(item.weight_per_piece or 0),
                    3
                )

            })

    if request.method == "POST":

        item = Item.objects.get(
            id=request.POST.get("item")
        )

        lots = int(
            request.POST.get("lots") or 0
        )

        manual_qty = int(
            request.POST.get("manual_qty") or 0
        )

        quantity = manual_qty

        if lots > 0 and item.lot_size:

            quantity = lots * item.lot_size

        weight = float(
            request.POST.get("weight") or 0
        )

        StockTransaction.objects.create(

            transaction_type="packaging_in",

            item=item,

            quantity=quantity,
            weight=weight,

            notes="Packaging Completed"

        )

        return redirect("packaging")

    recent = StockTransaction.objects.filter(
        transaction_type="packaging_in"
    ).order_by("-created_at")[:20]

    context = {

        "queue": queue,
        "recent": recent,

    }

    return render(request, "packaging.html", context)

# =====================================================

# MASTER DATA

# =====================================================


def master_data(request):

    if request.method == "POST":

    form_type = request.POST.get("form_type")

    if form_type == "client":

        Client.objects.create(

            name=request.POST.get("name")

        )

    elif form_type == "item":

        Item.objects.create(

            code=request.POST.get("code"),
            name=request.POST.get("name"),

            lot_size=request.POST.get("lot_size") or 0,

            weight_per_piece=request.POST.get(
                "weight_per_piece"
            ) or 0

        )

    elif form_type == "worker":

        Worker.objects.create(

            name=request.POST.get("name")

        )

    return redirect("master_data")

    context = {

        "clients": Client.objects.all(),
        "items": Item.objects.all(),
        "workers": Worker.objects.all(),

    }

    return render(request, "master_data.html", context)

# =====================================================

# STOCK PAGES

# =====================================================


def casting_stock(request):

    items = Item.objects.all()

    data = []

    for item in items:

    qty = get_casting_stock(item)

    if qty > 0:

        data.append({

            "item": item,
            "quantity": qty

        })

    return render(
        request,
        "casting_stock.html",
        {"data": data}
    )


def machining_stock(request):

    items = Item.objects.all()

    data = []

    for item in items:

    qty = get_machining_stock(item)

    if qty > 0:

        data.append({

            "item": item,
            "quantity": qty

        })

    return render(
        request,
        "machining_stock.html",
        {"data": data}
    )

# =====================================================

# OLD URL SUPPORT

# =====================================================


def issue_machining(request):

    return redirect("machining_entry")
