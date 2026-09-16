from django.http import JsonResponse
from django.db.models import Sum, Q
from django.contrib.auth.decorators import login_required
from apps.authentication.models import Worker, WorkerType
from apps.master_data.models import Item, Client
from apps.orders.models import SalesOrder, SalesOrderItem
from apps.production.models import StockTransaction, TransactionType, Carton, CartonItem
from apps.production import services

# Define pages for quick navigation search with module mappings
NAVIGATION_PAGES = [
    {"title": "📊 Dashboard / Overview", "url": "/", "module": None},
    {"title": "📅 Attendance Entry", "url": "/attendance/", "module": "attendance"},
    {"title": "🔥 Casting Entry (Production Logs)", "url": "/casting/", "module": "casting"},
    {"title": "⚙ Machining Entry (Issues & Receipts)", "url": "/machining/", "module": "machining"},
    {"title": "✨ Polishing Entry (Issues & Receipts)", "url": "/polishing/", "module": "polishing"},
    {"title": "📦 Packaging & Mixed Carton Board", "url": "/packaging/", "module": "packaging"},
    {"title": "📥 Purchases Log (Raw Stock)", "url": "/purchases/", "module": "purchases"},
    {"title": "🛠 Casting Warehouse Stock Ledger", "url": "/casting-stock/", "module": "casting"},
    {"title": "🛠 Machining WIP Stock Ledger", "url": "/machined-stock/", "module": "machining"},
    {"title": "🛠 Polishing WIP Stock Ledger", "url": "/polished-stock/", "module": "polishing"},
    {"title": "🛠 Packed Ready Stock Inventory", "url": "/ready-stock/", "module": "packaging"},
    {"title": "📋 Customer POs / Order Board", "url": "/orders/", "module": "orders"},
    {"title": "🚚 Dispatch & Sales Log", "url": "/dispatch/", "module": "dispatch"},
    {"title": "⚙ Master Data Management", "url": "/master-data/", "module": "master_data"},
    {"title": "💹 Labor Ledger", "url": "/ledger/", "module": "labor_ledger"},
    {"title": "👥 User Control & Access Hub", "url": "/users/", "module": "user_management"},
    {"title": "⚡ SQL Explorer & Data Flow", "url": "/sql-explorer/", "module": "sql_explorer"},
]

import re

def compute_text_relevance(text, query):
    """
    Returns an integer relevance score (lower is higher priority):
    0: Exact match (case-insensitive)
    1: Direct prefix match (string starts with query)
    2: Word prefix match (a word inside the string starts with query, e.g. 'Raw' in 'Purchases Log (Raw Stock)')
    3: Query is a substring (e.g. 'paras' contains 'ra')
    99: No match
    """
    if not text or not query:
        return 99
    t = text.lower().strip()
    q = query.lower().strip()
    
    # Strip leading icons/emojis/punctuation for clean prefix checking
    t_clean = re.sub(r'^[^\w\s]+', '', t).strip()
    
    if t == q or t_clean == q:
        return 0
    if t.startswith(q) or t_clean.startswith(q):
        return 1
    
    # Check if any individual word in the text starts with the query
    words = re.findall(r'\b\w+', t)
    if any(w.startswith(q) for w in words):
        return 2
    
    if q in t:
        return 3
    
    return 99

@login_required
def global_search_api(request):
    try:
        query = request.GET.get("q", "").strip()
        if not query or len(query) < 2:
            return JsonResponse({
                "results": {
                    "navigation": [],
                    "items": [],
                    "orders": [],
                    "workers": []
                },
                "section_scores": {
                    "navigation": 99,
                    "items": 99,
                    "orders": 99,
                    "workers": 99
                }
            })
        
        user = request.user
        active_company = getattr(request, 'company', None)
        can_view_financials = getattr(user, 'can_view_financials', True) or user.is_superuser or getattr(user, 'role', '') == 'ADMIN'

        # 1. Navigation Pages Search (Guarded by user's module permissions)
        nav_results = []
        for page in NAVIGATION_PAGES:
            mod = page.get("module")
            if mod and not user.has_module_access(mod):
                continue
            score = compute_text_relevance(page["title"], query)
            if score < 99:
                nav_results.append({
                    "title": page["title"],
                    "url": page["url"],
                    "score": score
                })
        nav_results.sort(key=lambda x: (x["score"], x["title"]))

        # 2. Purchase Orders Search (Guarded by orders module access)
        order_results = []
        if user.has_module_access("orders") and user.has_perm_node("orders.board.view"):
            orders_qs = SalesOrder.objects.all()
            if active_company:
                orders_qs = orders_qs.filter(client__company=active_company)
            
            orders_qs = orders_qs.filter(
                Q(order_number__icontains=query) | Q(client__name__icontains=query)
            ).select_related("client").order_by("-promised_date")[:20]

            for order in orders_qs:
                score_num = compute_text_relevance(order.order_number, query)
                score_cli = compute_text_relevance(order.client.name, query) if order.client else 99
                best_score = min(score_num, score_cli)
                if best_score < 99:
                    order_results.append({
                        "id": order.id,
                        "order_number": order.order_number,
                        "client_name": order.client.name if order.client else "N/A",
                        "status": order.status,
                        "promised_date": order.promised_date.strftime("%d/%m/%Y") if order.promised_date else "N/A",
                        "score": best_score
                    })
            order_results.sort(key=lambda x: (x["score"], -x["id"]))
            order_results = order_results[:5]

        # 3. Item/SKU Search and Supply Chain Pipeline Compilation
        items_qs = Item.objects.all()
        if active_company:
            items_qs = items_qs.filter(company=active_company)
        
        items_qs = items_qs.filter(
            Q(code__icontains=query) | Q(name__icontains=query)
        ).order_by("code")[:35]

        scored_items = []
        for it in items_qs:
            score_code = compute_text_relevance(it.code, query)
            score_name = compute_text_relevance(it.name, query)
            best_score = min(score_code, score_name)
            if best_score < 99:
                scored_items.append((best_score, it))

        scored_items.sort(key=lambda x: (x[0], x[1].code.lower()))
        sorted_items = [x[1] for x in scored_items[:5]]

        item_results = []
        for item in sorted_items:
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

            # C. Packaging Queue calculation
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

            item_score = min(compute_text_relevance(item.code, query), compute_text_relevance(item.name, query))

            item_results.append({
                "id": item.id,
                "code": item.code,
                "name": item.name,
                "item_type": item.item_type,
                "company_id": item.company_id,
                "score": item_score,
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
                "demand": outstanding_demand if can_view_financials else "***",
                "perms": {
                    "can_casting": user.has_module_access("casting"),
                    "can_machining_out": user.has_perm_node("machining.outsource.issue") or user.has_perm_node("machining.inhouse.create"),
                    "can_machining_in": user.has_perm_node("machining.outsource.receive") or user.has_perm_node("machining.inhouse.create"),
                    "can_machining_stk": user.has_perm_node("machining.stock.view"),
                    "can_polishing_out": user.has_perm_node("polishing.outsource.issue") or user.has_perm_node("polishing.inhouse.create"),
                    "can_polishing_in": user.has_perm_node("polishing.outsource.receive") or user.has_perm_node("polishing.inhouse.create"),
                    "can_packaging": user.has_module_access("packaging"),
                    "can_orders": user.has_module_access("orders")
                }
            })

        # 4. Workers & Job Workers Search (with Live Process WIP, Prefix Scoring and Permissions)
        worker_results = []
        can_view_workers = user.has_module_access("master_data") or user.has_module_access("labor_ledger") or user.has_module_access("machining") or user.has_module_access("polishing") or user.has_module_access("casting")
        
        if can_view_workers:
            workers_qs = Worker.objects.filter(
                Q(worker_type=WorkerType.IN_HOUSE) | Q(worker_type=WorkerType.JOB_WORKER)
            )
            if active_company:
                workers_qs = workers_qs.filter(company=active_company)
            
            workers_qs = workers_qs.filter(name__icontains=query)[:25]
            
            scored_workers = []
            for w in workers_qs:
                score = compute_text_relevance(w.name, query)
                if score < 99:
                    scored_workers.append((score, w))

            scored_workers.sort(key=lambda x: (x[0], x[1].name.lower()))
            
            for score, w in scored_workers[:6]:
                w_process = getattr(w, 'process', 'machining') or 'machining'
                wip_count = 0
                
                if w_process == 'machining':
                    out_qty = StockTransaction.objects.filter(worker=w, transaction_type="machining_out").aggregate(s=Sum('quantity'))['s'] or 0
                    in_qty = StockTransaction.objects.filter(worker=w, transaction_type="machining_in").aggregate(s=Sum('quantity'))['s'] or 0
                    rej_qty = StockTransaction.objects.filter(worker=w, transaction_type="machining_in").aggregate(s=Sum('rejection_quantity'))['s'] or 0
                    wip_count = max(0, out_qty - in_qty - rej_qty)
                elif w_process == 'polishing':
                    out_qty = StockTransaction.objects.filter(worker=w, transaction_type="polishing_out").aggregate(s=Sum('quantity'))['s'] or 0
                    in_qty = StockTransaction.objects.filter(worker=w, transaction_type="polishing_in").aggregate(s=Sum('quantity'))['s'] or 0
                    rej_qty = StockTransaction.objects.filter(worker=w, transaction_type="polishing_in").aggregate(s=Sum('rejection_quantity'))['s'] or 0
                    wip_count = max(0, out_qty - in_qty - rej_qty)

                worker_results.append({
                    "id": w.id,
                    "name": w.name,
                    "type": "Internal Staff" if w.worker_type == WorkerType.IN_HOUSE else "External Job Worker",
                    "process": w_process,
                    "process_display": w.get_process_display() if hasattr(w, 'get_process_display') else w_process.title(),
                    "wip_count": wip_count,
                    "score": score,
                    "perms": {
                        "can_machining_out": user.has_perm_node("machining.outsource.issue") or user.has_perm_node("machining.inhouse.create"),
                        "can_machining_in": user.has_perm_node("machining.outsource.receive") or user.has_perm_node("machining.inhouse.create"),
                        "can_polishing_out": user.has_perm_node("polishing.outsource.issue") or user.has_perm_node("polishing.inhouse.create"),
                        "can_polishing_in": user.has_perm_node("polishing.outsource.receive") or user.has_perm_node("polishing.inhouse.create"),
                        "can_casting_entry": user.has_perm_node("casting.inhouse.create") or user.has_module_access("casting"),
                        "can_view_statement": user.has_perm_node("labor_ledger.statements.view") or user.has_module_access("labor_ledger"),
                        "can_make_payment": (user.has_perm_node("labor_ledger.payment.create") or user.has_module_access("labor_ledger")) and can_view_financials,
                        "can_view_profile": user.has_perm_node("master_data.workers.view") or user.has_module_access("master_data"),
                        "can_view_attendance": user.has_module_access("attendance")
                    }
                })

        section_scores = {
            "workers": min([w["score"] for w in worker_results], default=99),
            "items": min([i["score"] for i in item_results], default=99),
            "navigation": min([n["score"] for n in nav_results], default=99),
            "orders": min([o["score"] for o in order_results], default=99),
        }

        return JsonResponse({
            "results": {
                "navigation": nav_results,
                "items": item_results,
                "orders": order_results,
                "workers": worker_results
            },
            "section_scores": section_scores
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
            },
            "section_scores": {
                "workers": 99,
                "items": 99,
                "navigation": 99,
                "orders": 99
            }
        }, status=500)
