from django.shortcuts import render, redirect
from datetime import date

from .models import (
    StockTransaction,
    Item,
    Client,
    Worker,
    Warehouse
)

from .forms import CastingEntryForm


# =========================================
# CREATE DEFAULT WAREHOUSES
# =========================================

def create_default_warehouses():

    Warehouse.objects.get_or_create(
        code='CASTING',
        defaults={
            'name': 'Casting Stock'
        }
    )

    Warehouse.objects.get_or_create(
        code='MACHINING',
        defaults={
            'name': 'Machining Stock'
        }
    )

    Warehouse.objects.get_or_create(
        code='READY',
        defaults={
            'name': 'Ready Stock'
        }
    )


# =========================================
# DASHBOARD
# =========================================

def dashboard(request):

    create_default_warehouses()

    casting_stock = StockTransaction.objects.filter(
        to_warehouse__code='CASTING'
    )

    machining_stock = StockTransaction.objects.filter(
        to_warehouse__code='MACHINING'
    )

    ready_stock = StockTransaction.objects.filter(
        to_warehouse__code='READY'
    )

    casting_pcs = 0
    casting_weight = 0

    for row in casting_stock:

        casting_pcs += row.quantity or 0
        casting_weight += float(row.weight or 0)

    machining_pcs = 0
    machining_weight = 0

    for row in machining_stock:

        machining_pcs += row.quantity or 0
        machining_weight += float(row.weight or 0)

    ready_pcs = 0
    ready_weight = 0

    for row in ready_stock:

        ready_pcs += row.quantity or 0
        ready_weight += float(row.weight or 0)

    context = {

        'casting_pcs': casting_pcs,
        'casting_weight': round(casting_weight, 3),

        'machining_pcs': machining_pcs,
        'machining_weight': round(machining_weight, 3),

        'ready_pcs': ready_pcs,
        'ready_weight': round(ready_weight, 3),

    }

    return render(
        request,
        'dashboard.html',
        context
    )


# =========================================
# CASTING ENTRY
# =========================================

def casting_entry(request):

    create_default_warehouses()

    casting_warehouse = Warehouse.objects.get(
        code='CASTING'
    )

    # =====================================
    # SAVE ENTRY
    # =====================================

    if request.method == 'POST':

        form = CastingEntryForm(request.POST)

        if form.is_valid():

            entry = form.save(commit=False)

            entry.transaction_type = 'casting_entry'

            entry.to_warehouse = casting_warehouse

            entry.save()

            return redirect('casting_entry')

    else:

        form = CastingEntryForm()

    # =====================================
    # ALL ENTRIES
    # =====================================

    entries = StockTransaction.objects.filter(
        transaction_type='casting_entry'
    ).order_by('-created_at')

    # =====================================
    # TOP TOTALS
    # =====================================

    total_entries = entries.count()

    total_pcs = 0
    total_weight = 0

    for entry in entries:

        total_pcs += entry.quantity or 0
        total_weight += float(entry.weight or 0)

    # =====================================
    # SUMMARY DATE FILTER
    # =====================================

    today = date.today()

    first_day = today.replace(day=1)

    from_date = request.GET.get(
        'from_date'
    ) or str(first_day)

    to_date = request.GET.get(
        'to_date'
    ) or str(today)

    summary_entries = StockTransaction.objects.filter(

        transaction_type='casting_entry',

        created_at__date__gte=from_date,

        created_at__date__lte=to_date

    )

    # =====================================
    # SUMMARY TOTALS
    # =====================================

    summary_heats = summary_entries.exclude(
        heat_no__isnull=True
    ).values(
        'heat_no'
    ).distinct().count()

    summary_pieces = 0
    summary_weight = 0

    for entry in summary_entries:

        summary_pieces += entry.quantity or 0
        summary_weight += float(entry.weight or 0)

    # =====================================
    # ITEM SUMMARY
    # =====================================

    item_summary = []

    items = Item.objects.all()

    for item in items:

        item_entries = summary_entries.filter(
            item=item
        )

        pcs = 0
        wt = 0

        for entry in item_entries:

            pcs += entry.quantity or 0
            wt += float(entry.weight or 0)

        if pcs > 0:

            item_summary.append({

                'item__code': item.code,
                'item__name': item.name,
                'total_pcs': pcs,
                'total_weight': round(wt, 3),

            })

    # =====================================
    # CLIENT SUMMARY
    # =====================================

    client_summary = []

    clients = Client.objects.all()

    for client in clients:

        client_entries = summary_entries.filter(
            client=client
        )

        pcs = 0
        wt = 0

        for entry in client_entries:

            pcs += entry.quantity or 0
            wt += float(entry.weight or 0)

        if pcs > 0:

            client_summary.append({

                'client__name': client.name,
                'total_pcs': pcs,
                'total_weight': round(wt, 3),

            })

    workers = Worker.objects.all()

    context = {

        'form': form,

        'entries': entries,

        'items': items,

        'clients': clients,

        'workers': workers,

        'total_entries': total_entries,

        'total_pcs': total_pcs,

        'total_weight': round(total_weight, 3),

        'from_date': from_date,

        'to_date': to_date,

        'summary_heats': summary_heats,

        'summary_pieces': summary_pieces,

        'summary_weight': round(summary_weight, 3),

        'item_summary': item_summary,

        'client_summary': client_summary,

    }

    return render(
        request,
        'casting.html',
        context
    )


# =========================================
# MASTER DATA
# =========================================

def master_data(request):

    active_tab = 'items'

    # =====================================
    # ADD ITEM
    # =====================================

    if request.method == 'POST' and request.POST.get('form_type') == 'item':

        active_tab = 'items'

        Item.objects.create(

            code=request.POST.get('code'),

            name=request.POST.get('name'),

            category=request.POST.get('category'),

            variant=request.POST.get('variant'),

            item_type=request.POST.get('item_type'),

            weight_per_piece=request.POST.get('weight_per_piece') or 0,

            lot_size=request.POST.get('lot_size') or 0,

            lot_with_box=request.POST.get('lot_with_box') or 0,

            process=request.POST.get('process'),

            rate_per_piece=request.POST.get('rate_per_piece') or 0,

        )

    # =====================================
    # ADD CLIENT
    # =====================================

    if request.method == 'POST' and request.POST.get('form_type') == 'client':

        active_tab = 'clients'

        Client.objects.create(

            name=request.POST.get('client_name'),

            phone=request.POST.get('client_phone'),

            city=request.POST.get('client_city'),

        )

    # =====================================
    # ADD WORKER
    # =====================================

    if request.method == 'POST' and request.POST.get('form_type') == 'worker':

        active_tab = 'workers'

        Worker.objects.create(

            name=request.POST.get('worker_name'),

            process=request.POST.get('worker_process'),

            phone=request.POST.get('worker_phone'),

        )

    items = Item.objects.all().order_by('name')

    workers = Worker.objects.all().order_by('name')

    clients = Client.objects.all().order_by('name')

    context = {

        'items': items,

        'workers': workers,

        'clients': clients,

        'active_tab': active_tab,

    }

    return render(

        request,

        'master_data.html',

        context

    )