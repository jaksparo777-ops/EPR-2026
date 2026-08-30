from django.http import JsonResponse
from django.db.models import Sum, Q
from django.contrib.auth.decorators import login_required
from apps.authentication.models import Worker, WorkerType
from apps.master_data.models import Item, Client
from apps.orders.models import SalesOrder, SalesOrderItem
from apps.production.models import StockTransaction, TransactionType, Carton, CartonItem
from apps.production import services

# Define pages for quick navigation search
NAVIGATION_PAGES = [
    {"title": "📊 Dashboard / Overview", "url": "/"},
    {"title": "📅 Attendance Entry", "url": "/attendance/"},
    {"title": "🔥 Casting Entry (Production Logs)", "url": "/casting/"},
    {"title": "⚙ Machining Entry (Issues & Receipts)", "url": "/machining/"},
    {"title": "✨ Polishing Entry (Issues & Receipts)", "url": "/polishing/"},
    {"title": "📦 Packaging & Mixed Carton Board", "url": "/packaging/"},
    {"title": "📥 Purchases Log (Raw Stock)", "url": "/purchases/"},
    {"title": "🛠 Casting Warehouse Stock Ledger", "url": "/casting-stock/"},
    {"title": "🛠 Machining WIP Stock Ledger", "url": "/machined-stock/"},
    {"title": "🛠 Polishing WIP Stock Ledger", "url": "/polished-stock/"},
    {"title": "🛠 Packed Ready Stock Inventory", "url": "/ready-stock/"},
    {"title": "📋 Customer POs / Order Board", "url": "/orders/"},
    {"title": "🚚 Dispatch & Sales Log", "url": "/dispatch/"},
    {"title": "⚙ Master Data Management", "url": "/master-data/"},
    {"title": "💹 Labor Ledger", "url": "/ledger/"},
]

@login_required
def global_search_api(request):
    try:
        query = request.GET.get("q", "").strip()
        if not query or len(query) < 2:
            return JsonResponse({"results": {"navigation": [], "items": [], "orders": [], "workers": []}})
        
        active_company = getattr(request, 'company', None)
        query_lower = query.lower()

        # 1. Navigation Pages Search
        nav_results = []
        for page in NAVIGATION_PAGES:
            if query_lower in page["title"].lower():
                nav_results.append(page)

        # 2. Purchase Orders Search
        orders_qs = SalesOrder.objects.all()
        if active_company:
            orders_qs = orders_qs.filter(client__company=active_company)
        
        orders_qs = orders_qs.filter(
            Q(order_number__icontains=query) | Q(client__name__icontains=query)
        ).select_related("client").order_by("-promised_date")[:5]

        order_results = []
        for order in orders_qs:
            order_results.append({
                "id": order.id,
                "order_number": order.order_number,
                "client_name": order.client.name,
                "status": order.status,
                "promised_date": order.promised_date.strftime("%d/%m/%Y") if order.promised_date else "N/A"
            })

        # 3. Item/SKU Search and Supply Chain Pipeline Compilation
        items_qs = Item.objects.all()
        if active_company:
            items_qs = items_qs.filter(company=active_company)
        
        items_qs = items_qs.filter(
            Q(code__icontains=query) | Q(name__icontains=query)
        ).order_by("code")[:30]

        # Helper function for search relevance scoring
        def get_relevance_score(code, name, q):
            code_l = code.lower()
            name_l = name.lower()
            q_l = q.lower()
            if code_l == q_l:
                return 0
            if code_l.startswith(q_l):
                return 1
            if q_l in code_l:
                return 2
            if name_l.startswith(q_l):
                return 3
            return 4

        sorted_items = sorted(
            items_qs,
            key=lambda it: (get_relevance_score(it.code, it.name, query), it.code.lower())
        )[:5]

        item_results = []
        for item in sorted_items:
            # Standard warehouse stock states via services
            stock_stats = services.get_stock_by_item(item)
            casting_avail = stock_stats.get('casting', 0)
            machining_avail = stock_stats.get('machining', 0)
            polishing_avail = stock_stats.get('polishing', 0)
            ready_avail = stock_stats.get('ready', 0)

            # A. Machining WIP calculation
            machining_out_qty = StockTransaction.objects.filter(
                item__code=item.code, transaction_type="machining_out"
            ).aggregate(total=Sum('quantity'))['total'] or 0
            machining_in_qty = StockTransaction.objects.filter(
                item__code=item.code, transaction_type="machining_in"
            ).aggregate(total=Sum('quantity'))['total'] or 0
            machining_rejections = StockTransaction.objects.filter(
                item__code=item.code, transaction_type="machining_in"
            ).aggregate(total=Sum('rejection_quantity'))['total'] or 0
            machining_wip = max(0, machining_out_qty - machining_in_qty - machining_rejections)

            # B. Polishing WIP calculation
            polishing_out_qty = StockTransaction.objects.filter(
                item__code=item.code, transaction_type="polishing_out"
            ).aggregate(total=Sum('quantity'))['total'] or 0
            polishing_in_qty = StockTransaction.objects.filter(
                item__code=item.code, transaction_type="polishing_in"
            ).aggregate(total=Sum('quantity'))['total'] or 0
            polishing_rejections = StockTransaction.objects.filter(
                item__code=item.code, transaction_type="polishing_in"
            ).aggregate(total=Sum('rejection_quantity'))['total'] or 0
            polishing_wip = max(0, polishing_out_qty - polishing_in_qty - polishing_rejections)

            # C. Packaging Queue calculation (Polishing Receipts + Purchased Semi-Finished Goods)
            polishing_entries = StockTransaction.objects.filter(
                item__code=item.code, transaction_type__in=["polishing_in", "purchase_entry"]
            )
            queue_qty = 0
            for entry in polishing_entries:
                packed_qty = StockTransaction.objects.filter(
                    transaction_type="packaging_in",
                    notes__contains=f"PACKED #{entry.id}"
                ).aggregate(total=Sum('quantity'))['total'] or 0
                rem_qty = entry.quantity - packed_qty - (entry.rejection_quantity or 0)
                queue_qty += max(0, rem_qty)

            # D. Carton stats
            cartons_count = CartonItem.objects.filter(
                item=item, carton__status='READY'
            ).values('carton').distinct().count()

            # E. Outstanding PO Demand
            po_items = SalesOrderItem.objects.filter(
                item=item, sales_order__status__in=['OPEN', 'PARTIAL']
            )
            total_demanded = sum(poi.ordered_quantity for poi in po_items)
            outstanding_demand = max(0, total_demanded - ready_avail)

            item_results.append({
                "id": item.id,
                "code": item.code,
                "name": item.name,
                "item_type": item.item_type,
                "company_id": item.company_id,
                "casting_avail": casting_avail if item.item_type != 'SET' else 0,
                "machining_wip": machining_wip if item.item_type != 'SET' else 0,
                "machining_avail": machining_avail if item.item_type != 'SET' else 0,
                "polishing_wip": polishing_wip,
                "casting_required": item.casting_required,
                "machining_required": item.machining_required,
                "polishing_required": item.polishing_required,
                "loose_buffer": item.buffer_stock,
                "packaging_queue": queue_qty,
                "ready_stock": ready_avail,
                "cartons_count": cartons_count,
                "demand": outstanding_demand
            })

        # 4. Workers & Job Workers Search
        workers_qs = Worker.objects.filter(worker_type=WorkerType.IN_HOUSE)
        job_workers_qs = Worker.objects.filter(worker_type=WorkerType.JOB_WORKER)
        if active_company:
            workers_qs = workers_qs.filter(company=active_company)
            job_workers_qs = job_workers_qs.filter(company=active_company)
        
        workers_qs = workers_qs.filter(name__icontains=query).order_by("name")[:5]
        job_workers_qs = job_workers_qs.filter(name__icontains=query).order_by("name")[:5]
        
        worker_results = []
        for w in workers_qs:
            worker_results.append({
                "id": w.id,
                "name": w.name,
                "type": "Internal",
                "process": w.get_process_display() if hasattr(w, 'get_process_display') else (w.process or 'General')
            })
        for jw in job_workers_qs:
            worker_results.append({
                "id": jw.id,
                "name": jw.name,
                "type": "External",
                "process": jw.get_process_display() if hasattr(jw, 'get_process_display') else (jw.process or 'General')
            })

        return JsonResponse({
            "results": {
                "navigation": nav_results,
                "items": item_results,
                "orders": order_results,
                "workers": worker_results
            }
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            "error": str(e),
            "results": {
                "navigation": [],
                "items": [],
                "orders": [],
                "workers": []
            }
        }, status=500)
