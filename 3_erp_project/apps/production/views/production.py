import json
import re
from collections import defaultdict
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.db.models import Sum, Q
from django.utils import timezone

from apps.master_data.models import LegalEntity, Client, Warehouse, Item, ItemComposition
from apps.authentication.models import Worker, ProcessType, SalaryModel, WorkerType
from apps.authentication.utils import resolve_worker, filter_by_worker
from apps.production.models import StockTransaction, TransactionType, ItemWorkerAllocation, Attendance, Loan, LaborPayment, Carton, CartonItem, Holiday


from apps.production import services

# =====================================================
# DEFAULT WAREHOUSES
# =====================================================

def create_default_warehouses():
    warehouses = [
        ("CASTING", "Casting Stock"),
        ("MACHINING", "Machined Stock"),
        ("POLISHING", "Polished Stock"),
        ("READY", "Ready Stock"),
    ]
    for code, name in warehouses:
        w, created = Warehouse.objects.get_or_create(
            code=code,
            defaults={"name": name}
        )
        if not created and w.name != name:
            w.name = name
            w.save()

# =====================================================
# CASTING ENTRY
# =====================================================

def casting_entry(request):
    create_default_warehouses()

    active_company = request.company or LegalEntity.objects.get(id=1)
    clients = Client.objects.filter(company=active_company)
    items = Item.objects.filter(company=active_company, casting_required=True).exclude(item_type="SET").exclude(components__isnull=False).distinct()

    if request.method == "POST":
        date_str = request.POST.get("date") or request.GET.get("date")
    else:
        date_str = request.GET.get("date") or request.POST.get("date")
    selected_date = None
    if date_str:
        try:
            selected_date = timezone.datetime.strptime(date_str + " 12:00:00", "%Y-%m-%d %H:%M:%S")
            selected_date = timezone.make_aware(selected_date)
        except Exception:
            pass
    query_date = selected_date.date() if selected_date else timezone.now().date()

    if request.method == "POST":
        edit_id = request.POST.get("edit_id")
        heat_no = request.POST.get("heat_no")
        client_id = request.POST.get("client")
        notes = request.POST.get("notes")
        poured_by = request.POST.get("poured_by", "")

        worker_id = None
        job_worker_id = None
        if poured_by.startswith("w_"):
            worker_id = int(poured_by[2:])
        elif poured_by.startswith("jw_"):
            job_worker_id = int(poured_by[3:])

        try:
            client = Client.objects.get(id=client_id) if client_id else None
        except Client.DoesNotExist:
            client = None

        if edit_id:
            # Single update
            item_id = request.POST.get("item")
            client_id = request.POST.get("client")
            client_id = int(client_id) if client_id else None
            quantity = int(request.POST.get("quantity") or 0)
            weight = float(request.POST.get("weight") or 0)
            actual_scale_weight = float(request.POST.get("actual_scale_weight") or 0.0)
            
            if not item_id and actual_scale_weight > 0:
                general_item, _ = Item.objects.get_or_create(
                    code="GENERAL",
                    defaults={
                        "name": "General Casting Weight",
                        "category": "OTHER",
                        "casting_required": True,
                        "company_id": 1
                    }
                )
                item_id = general_item.id
            
            try:
                tx = StockTransaction.objects.get(id=edit_id)
                tx.client_id = client_id
                tx.item_id = item_id
                tx.quantity = quantity
                tx.weight = weight
                tx.actual_scale_weight = actual_scale_weight
                tx.heat_no = heat_no
                tx.notes = notes
                tx.worker_id = worker_id
                tx.save()
                if selected_date:
                    StockTransaction.objects.filter(pk=tx.pk).update(created_at=selected_date)
                messages.success(request, "Entry updated.")
            except StockTransaction.DoesNotExist:
                messages.error(request, "Not found.")
        else:
            # Multiple create
            item_ids = request.POST.getlist("item[]")
            client_ids = request.POST.getlist("client[]")
            quantities = request.POST.getlist("quantity[]")
            weights = request.POST.getlist("weight[]")
            scale_weights = request.POST.getlist("actual_scale_weight[]")

            for i in range(len(item_ids)):
                curr_item_id = item_ids[i] if i < len(item_ids) else None
                s_wt = float(scale_weights[i] or 0.0) if i < len(scale_weights) and scale_weights[i] else 0.0
                
                if not curr_item_id and not s_wt:
                    continue
                    
                if not curr_item_id and s_wt > 0:
                    general_item, _ = Item.objects.get_or_create(
                        code="GENERAL",
                        defaults={
                            "name": "General Casting Weight",
                            "category": "OTHER",
                            "casting_required": True,
                            "company_id": 1
                        }
                    )
                    curr_item_id = general_item.id
                
                # Handle client per row
                c_id = client_ids[i] if i < len(client_ids) and client_ids[i] else None
                
                tx = StockTransaction.objects.create(
                    transaction_type=TransactionType.CASTING_ENTRY,
                    client_id=c_id,
                    item_id=curr_item_id,
                    quantity=int(quantities[i] or 0) if i < len(quantities) and quantities[i] else 0,
                    weight=float(weights[i] or 0.0) if i < len(weights) and weights[i] else 0.0,
                    actual_scale_weight=s_wt,
                    heat_no=heat_no,
                    notes=notes,
                    worker_id=worker_id
                )
                if selected_date:
                    StockTransaction.objects.filter(pk=tx.pk).update(created_at=selected_date)
            messages.success(request, f"Saved {len(item_ids)} entries.")

        redirect_date = selected_date.strftime("%Y-%m-%d") if selected_date else date_str
        return redirect(reverse("casting_entry") + (f"?date={redirect_date}" if redirect_date else ""))

    # DELETE logic
    delete_id = request.GET.get("delete_id")
    if delete_id:
        try:
            StockTransaction.objects.get(id=delete_id).delete()
            messages.success(request, "Entry deleted successfully.")
        except StockTransaction.DoesNotExist:
            messages.error(request, "Entry not found.")
        return redirect(reverse("casting_entry") + (f"?date={date_str}" if date_str else ""))

    all_entries = StockTransaction.objects.filter(
        transaction_type=TransactionType.CASTING_ENTRY
    ).select_related("item", "client").order_by("-created_at")

    search_query = request.GET.get("search", "")
    date_from = request.GET.get("date_from", "")
    date_to = request.GET.get("date_to", "")
    active_tab = request.GET.get("tab", "entry")

    # Get heats used today for UI highlighting
    today = timezone.now().date()
    used_heats_today = list(StockTransaction.objects.filter(
        transaction_type=TransactionType.CASTING_ENTRY,
        created_at__date=query_date
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

    # Recent entries for query_date only
    recent_raw = all_entries.filter(created_at__date=query_date)
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
            "actual_scale_weight": r.actual_scale_weight or 0.0,
            "notes": r.notes or "",
            "poured_by": f"w_{r.worker.id}" if r.worker else ""
        }
        
        current_group['items'].append(item_data)
        current_group['total_pcs'] += item_data['quantity']
        current_group['total_wt'] += item_data['actual_scale_weight'] if item_data['actual_scale_weight'] > 0 else item_data['weight']

    if current_group:
        grouped_recent.append(current_group)

    # Day-specific stats for the analytics banner
    today_entries = all_entries.filter(created_at__date=query_date)
    today_total_weight = sum(t.actual_scale_weight if t.actual_scale_weight > 0 else t.weight for t in today_entries)
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

    import calendar
    month_str = request.GET.get("month")
    if month_str:
        try:
            parts = month_str.split('-')
            year = int(parts[0])
            month = int(parts[1])
        except Exception:
            year = query_date.year
            month = query_date.month
    else:
        year = query_date.year
        month = query_date.month
        
    num_days = calendar.monthrange(year, month)[1]
    
    # We fetch all casting entry transactions for this month
    month_start = timezone.datetime(year, month, 1)
    month_end = timezone.datetime(year, month, num_days, 23, 59, 59)
    month_start = timezone.make_aware(month_start)
    month_end = timezone.make_aware(month_end)
    
    month_txs = StockTransaction.objects.filter(
        transaction_type=TransactionType.CASTING_ENTRY,
        created_at__gte=month_start,
        created_at__lte=month_end
    ).select_related('worker')
    
    casting_workers = Worker.objects.filter(company_id=1, active=True, worker_type=WorkerType.IN_HOUSE)
    casting_job_workers = Worker.objects.filter(company_id=1, active=True, worker_type=WorkerType.JOB_WORKER)
    
    casters_list = []
    active_caster_ids = set()
    for tx in month_txs:
        if tx.worker:
            if tx.worker.worker_type == WorkerType.JOB_WORKER:
                active_caster_ids.add(f"jw_{tx.worker_id}")
            else:
                active_caster_ids.add(f"w_{tx.worker_id}")
        elif tx.worker_id:
            active_caster_ids.add(f"w_{tx.worker_id}")
            
    for w in casting_workers:
        if w.process == "casting" or w.process == "CASTING" or f"w_{w.id}" in active_caster_ids:
            casters_list.append({"id": f"w_{w.id}", "name": w.name, "type": "Worker"})
    for jw in casting_job_workers:
        if jw.process == "casting" or jw.process == "CASTING" or f"jw_{jw.id}" in active_caster_ids:
            casters_list.append({"id": f"jw_{jw.id}", "name": jw.name, "type": "Job Worker"})
            
    daily_weights = {}
    for tx in month_txs:
        day = tx.created_at.astimezone(timezone.get_current_timezone()).date().day
        c_id = None
        if tx.worker:
            if tx.worker.worker_type == WorkerType.JOB_WORKER:
                c_id = f"jw_{tx.worker_id}"
            else:
                c_id = f"w_{tx.worker_id}"
        elif tx.worker_id:
            c_id = f"w_{tx.worker_id}"

        if c_id:
            wt = tx.actual_scale_weight if tx.actual_scale_weight > 0 else tx.weight
            key = (c_id, day)
            daily_weights[key] = daily_weights.get(key, 0.0) + wt

    # Fetch holidays for this month to highlight weekly off days and official holidays
    holidays_qs = Holiday.objects.filter(
        date__year=year,
        date__month=month
    )
    if request.company:
        holidays_qs = holidays_qs.filter(Q(company=request.company) | Q(company__isnull=True))
    holiday_days = set(h.date.day for h in holidays_qs)
    
    # Determine the weekly off day dynamically from LegalEntity profile (0=Monday, 6=Sunday, 7=None)
    weekly_off_day = 6  # Default fallback to Sunday
    if request.company:
        weekly_off_day = request.company.weekly_off
    else:
        nc_company = LegalEntity.objects.filter(id=1).first()
        if nc_company:
            weekly_off_day = nc_company.weekly_off

    today_date = timezone.now().date()
    current_day = today_date.day if (year == today_date.year and month == today_date.month) else 1

    days_metadata = []
    for d in range(1, num_days + 1):
        weekday = timezone.datetime(year, month, d).weekday()
        is_weekly_off = (weekday == weekly_off_day) if weekly_off_day != 7 else False
        is_h = (d in holiday_days) or is_weekly_off
        is_today = (year == today_date.year and month == today_date.month and d == today_date.day)
        days_metadata.append({
            "day": d,
            "is_holiday": is_h,
            "is_today": is_today
        })
            
    sheet_data = []
    for caster in casters_list:
        days_data = []
        total_monthly_wt = 0.0
        for day_meta in days_metadata:
            d = day_meta["day"]
            d_wt = daily_weights.get((caster["id"], d), 0.0)
            total_monthly_wt += d_wt
            days_data.append({
                "day": d,
                "weight": round(d_wt, 3) if d_wt > 0 else None,
                "is_holiday": day_meta["is_holiday"]
            })
        sheet_data.append({
            "caster": caster,
            "days": days_data,
            "total_weight": round(total_monthly_wt, 3)
        })
        
    prev_year = year if month > 1 else year - 1
    prev_month = month - 1 if month > 1 else 12
    next_year = year if month < 12 else year + 1
    next_month = month + 1 if month < 12 else 1
    prev_month_str = f"{prev_year}-{prev_month:02d}"
    next_month_str = f"{next_year}-{next_month:02d}"
    month_name = timezone.datetime(year, month, 1).strftime("%B %Y")

    numeric_heats = [int(h) for h in used_heats_today if h and str(h).isdigit()]
    max_heat_count = max([10] + numeric_heats)
    heats_range = range(1, max_heat_count + 1)

    context = {
        "clients": clients,
        "items": items,
        "all_items": items,
        "casting_workers": casting_workers,
        "casting_job_workers": casting_job_workers,

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
        "heats_range": heats_range,
        "last_heat_items": json.dumps(last_heat_items),
        "selected_date": query_date.strftime("%Y-%m-%d"),
        
        "sheet_data": sheet_data,
        "days_metadata": days_metadata,
        "month_val": f"{year}-{month:02d}",
        "prev_month_str": prev_month_str,
        "next_month_str": next_month_str,
        "month_name": month_name,
        "current_day": current_day,
    }

    return render(request, "casting.html", context)

# =====================================================
# MACHINING
# =====================================================

def machining_entry(request):
    create_default_warehouses()

    workers = Worker.objects.filter(process="machining", active=True, worker_type=WorkerType.IN_HOUSE)
    job_workers = Worker.objects.filter(process="machining", active=True, worker_type=WorkerType.JOB_WORKER)
    active_company = request.company
    if active_company:
        items = Item.objects.filter(company=active_company).exclude(item_type="SET").exclude(components__isnull=False).distinct()
    else:
        items = Item.objects.filter(company_id=2).exclude(item_type="SET").exclude(components__isnull=False).distinct()

    if request.method == "POST":
        date_str = request.POST.get("date") or request.GET.get("date")
    else:
        date_str = request.GET.get("date") or request.POST.get("date")
    created_at_dt = None
    if date_str:
        try:
            created_at_dt = timezone.datetime.strptime(date_str + " 12:00:00", "%Y-%m-%d %H:%M:%S")
            created_at_dt = timezone.make_aware(created_at_dt)
        except Exception:
            pass
    query_date = created_at_dt.date() if created_at_dt else timezone.now().date()

    delete_id = request.GET.get("delete_id")
    if delete_id:
        try:
            tx = StockTransaction.objects.get(id=delete_id)
            if tx.linked_consumption:
                tx.linked_consumption.delete()
            tx.delete()
            messages.success(request, "Machining entry deleted successfully.")
        except StockTransaction.DoesNotExist:
            messages.error(request, "Machining transaction not found.")
        return redirect(reverse("machining_entry") + (f"?date={date_str}" if date_str else ""))

    if request.method == "POST":
        direction = request.POST.get("direction")
        worker_id = request.POST.get("worker")
        worker_obj = resolve_worker(worker_id)

        if not worker_id or not worker_obj:
            messages.error(request, "Failed to save: You must select a Worker or Job Worker.")
            return redirect(reverse("machining_entry") + (f"?date={date_str}" if date_str else ""))


        notes = request.POST.get("notes") or ""
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
                tx.quantity = quantity
                tx.rejection_quantity = rejection_quantity
                tx.weight = weight
                tx.notes = notes
                tx.notes = notes
                tx.save()
                if created_at_dt:
                    StockTransaction.objects.filter(pk=tx.pk).update(created_at=created_at_dt)

                # Update linked raw material consumption if posted
                raw_qty_str = request.POST.get('raw_material_qty')
                if raw_qty_str is not None:
                    try:
                        raw_qty = float(raw_qty_str)
                    except ValueError:
                        raw_qty = 0.0

                    if tx.linked_consumption:
                        if raw_qty > 0:
                            tx.linked_consumption.quantity = int(raw_qty)
                            tx.linked_consumption.worker = worker_obj
                            tx.linked_consumption.save()
                            if created_at_dt:
                                StockTransaction.objects.filter(pk=tx.linked_consumption.pk).update(created_at=created_at_dt)
                        else:
                            old_lc = tx.linked_consumption
                            tx.linked_consumption = None
                            tx.save()
                            old_lc.delete()
                    elif raw_qty > 0 and tx.item.raw_material:
                        raw_tx = StockTransaction.objects.create(
                            transaction_type="machining_in",
                            item=tx.item.raw_material,
                            worker=worker_obj,
                            quantity=int(raw_qty),
                            weight=0.0,
                            notes=f"Auto-consumed raw material for {quantity} pcs of {tx.item.code}."
                        )
                        if created_at_dt:
                            StockTransaction.objects.filter(pk=raw_tx.pk).update(created_at=created_at_dt)
                        tx.linked_consumption = raw_tx
                        tx.save()

                messages.success(request, "Updated successfully.")
            except StockTransaction.DoesNotExist:
                messages.error(request, "Transaction not found.")
        else:
            item_ids = request.POST.getlist("item[]")
            quantities = request.POST.getlist("quantity[]")
            rejection_quantities = request.POST.getlist("rejection_quantity[]")
            weights = request.POST.getlist("weight[]")
            raw_material_qtys = request.POST.getlist("raw_material_qty[]")

            count = 0
            for i in range(len(item_ids)):
                it_id = item_ids[i]
                if not it_id:
                    continue

                qty = int(quantities[i] or 0)
                wt = float(weights[i] or 0)
                rej_qty = int(rejection_quantities[i] or 0) if i < len(rejection_quantities) else 0

                deficit_mode = request.POST.get("deficit_mode", "none")
                allow_zero = (direction == "machining_in" and deficit_mode in ["correct_issue", "wastage"])

                if qty <= 0 and wt <= 0 and not allow_zero:
                    continue
                if qty <= 0 and wt > 0:
                    qty = int(wt)

                # Auto-adjust variance if requested
                deficit_mode = request.POST.get("deficit_mode", "none")
                if direction == "machining_in":
                    item_obj = Item.objects.filter(id=it_id).first()
                    if item_obj:
                        w_filter = {}
                        if worker_obj:
                            w_filter['worker'] = worker_obj
                        
                        issued_qty = StockTransaction.objects.filter(
                            item__code=item_obj.code,
                            transaction_type="machining_out",
                            **w_filter
                        ).aggregate(total=Sum('quantity'))['total'] or 0
                        
                        received_qty = StockTransaction.objects.filter(
                            item__code=item_obj.code,
                            transaction_type="machining_in",
                            **w_filter
                        ).aggregate(total=Sum('quantity'))['total'] or 0
                        
                        rejected_qty = StockTransaction.objects.filter(
                            item__code=item_obj.code,
                            transaction_type="machining_in",
                            **w_filter
                        ).aggregate(total=Sum('rejection_quantity'))['total'] or 0
                        
                        current_wip = issued_qty - received_qty - rejected_qty
                        new_wip = current_wip - (qty + rej_qty)
                        
                        if new_wip < 0: # Surplus / Direct Receive: auto-create matching OUT issue entry
                            surplus_qty = abs(new_wip)
                            comp_tx = StockTransaction.objects.create(
                                transaction_type="machining_out",
                                item_id=it_id,
                                worker=worker_obj,
                                quantity=surplus_qty,
                                weight=round(surplus_qty * (item_obj.casting_weight or 0.0), 3),
                                notes="Auto-issued to balance direct receive entry."
                            )
                            if created_at_dt:
                                StockTransaction.objects.filter(pk=comp_tx.pk).update(created_at=created_at_dt)
                        elif new_wip > 0: # Deficit: we received less than issued
                            deficit_qty = new_wip
                            if deficit_mode == "correct_issue":
                                # Reduce the original issue count to return pieces to Casting Stock
                                open_issues = StockTransaction.objects.filter(
                                    item_id=it_id,
                                    transaction_type="machining_out",
                                    **w_filter
                                ).order_by("-id")
                                remaining_reduction = deficit_qty
                                for issue_tx in open_issues:
                                    if remaining_reduction <= 0:
                                        break
                                    if issue_tx.quantity >= remaining_reduction:
                                        issue_tx.quantity -= remaining_reduction
                                        issue_tx.weight = issue_tx.quantity * (item_obj.casting_weight or 0.0)
                                        issue_tx.save()
                                        remaining_reduction = 0
                                    else:
                                        remaining_reduction -= issue_tx.quantity
                                        issue_tx.quantity = 0
                                        issue_tx.weight = 0.0
                                        issue_tx.save()
                            elif deficit_mode == "wastage":
                                # Merge counting variance deficit directly into rejection quantity of the entry
                                rej_qty += deficit_qty

                tx = StockTransaction.objects.create(
                    transaction_type=direction,
                    item_id=it_id,
                    worker=worker_obj,
                    quantity=qty,
                    rejection_quantity=rej_qty,
                    weight=wt,
                    notes=notes
                )
                if created_at_dt:
                    StockTransaction.objects.filter(pk=tx.pk).update(created_at=created_at_dt)

                # Auto-consume raw material for machining receive (machining_in)
                if direction == "machining_in":
                    item_obj = Item.objects.filter(id=it_id).first()
                    if item_obj and item_obj.raw_material:
                        raw_qty = 0.0
                        if i < len(raw_material_qtys) and raw_material_qtys[i]:
                            try:
                                raw_qty = float(raw_material_qtys[i])
                            except ValueError:
                                raw_qty = 0.0

                        if raw_qty > 0:
                            raw_tx = StockTransaction.objects.create(
                                transaction_type="machining_in",
                                item=item_obj.raw_material,
                                worker=worker_obj,
                                quantity=int(raw_qty),
                                weight=0.0,
                                notes=f"Auto-consumed raw material for {qty} pcs of {item_obj.code}."
                            )
                            if created_at_dt:
                                StockTransaction.objects.filter(pk=raw_tx.pk).update(created_at=created_at_dt)
                            tx.linked_consumption = raw_tx
                            tx.save()

                count += 1

            messages.success(request, f"Saved {count} movement entries.")

        redirect_date = created_at_dt.strftime("%Y-%m-%d") if created_at_dt else date_str
        return redirect(reverse("machining_entry") + (f"?date={redirect_date}" if redirect_date else ""))

    recent = StockTransaction.objects.filter(
        transaction_type__in=[
            "machining_out",
            "machining_in"
        ],
        created_at__date=query_date
    ).order_by("-id")

    machining_stock = []
    machining_stock_by_category = []

    wip_items = Item.objects.filter(company=active_company).distinct() if active_company else Item.objects.filter(company_id=2).distinct()
    bulk_stock = services.get_all_items_stock(company=active_company)

    # 1 Bulk query for all (item_code, worker) machining stats
    machining_tx_stats = StockTransaction.objects.filter(
        transaction_type__in=["machining_out", "machining_in"],
        worker__isnull=False
    ).values(
        'item__code', 'worker_id', 'worker__name', 'worker__worker_type', 'worker__jw_code', 'transaction_type'
    ).annotate(
        total_qty=Sum('quantity'),
        total_rej=Sum('rejection_quantity')
    )

    wip_by_item_worker = defaultdict(lambda: {'issued': 0, 'received': 0, 'rejected': 0, 'w_name': '', 'w_type': '', 'jw_code': ''})
    worker_totals = defaultdict(lambda: {'issued': 0, 'received': 0, 'rejected': 0})

    for s in machining_tx_stats:
        icode = s['item__code']
        wid = s['worker_id']
        ttype = s['transaction_type']
        qty = s['total_qty'] or 0
        rej = s['total_rej'] or 0

        d = wip_by_item_worker[(icode, wid)]
        d['w_name'] = s['worker__name']
        d['w_type'] = s['worker__worker_type']
        d['jw_code'] = s['worker__jw_code']

        wt = worker_totals[wid]
        if ttype == "machining_out":
            d['issued'] += qty
            wt['issued'] += qty
        elif ttype == "machining_in":
            d['received'] += qty
            d['rejected'] += rej
            wt['received'] += qty
            wt['rejected'] += rej

    for item in wip_items:
        available_qty = bulk_stock.get(item.id, {}).get('machining', 0)
        for (icode, wid), val in wip_by_item_worker.items():
            if icode == item.code:
                under_process = val['issued'] - val['received'] - val['rejected']
                if under_process > 0:
                    is_jw = (val['w_type'] == 'JOB_WORKER')
                    target_id = f"jw_{wid}" if is_jw else f"w_{wid}"
                    display_name = val['w_name'] if is_jw else f"{val['w_name']} (INT)"

                    machining_stock.append({
                        "item_id": item.id,
                        "item_name": f"{item.code} - {item.name}",
                        "item_category": item.category,
                        "item_uom": item.uom,
                        "is_raw_material": item.is_raw_material,
                        "worker_id": target_id,
                        "worker_name": display_name,
                        "under_process": under_process,
                        "available_qty": available_qty
                    })

    worker_wip = []
    for worker in list(workers) + list(job_workers):
        wt = worker_totals.get(worker.id, {'issued': 0, 'received': 0, 'rejected': 0})
        issued = wt['issued']
        received = wt['received']
        rejected = wt['rejected']
        pending = issued - received - rejected
        if issued > 0 or received > 0:
            w_label = f"{worker.name} (EXT)" if worker.worker_type == WorkerType.JOB_WORKER else worker.name
            worker_wip.append({
                "name": w_label,
                "issued": issued,
                "received": received,
                "rejected": rejected,
                "pending": pending
            })

    # Prepare Worker-wise Ledger
    worker_ledger = defaultdict(list)
    for r in recent:
        if r.worker:
            name = f"{r.worker.name} (EXT)" if r.worker.worker_type == WorkerType.JOB_WORKER else f"{r.worker.name} (INT)"
        else:
            name = "UNASSIGNED"
        worker_ledger[name].append(r)

    # Smart Worker Allocation Logic
    allocations = ItemWorkerAllocation.objects.filter(
        worker__process='machining'
    ).select_related('worker', 'item')
    company_items = {it.code: it.id for it in items}
    smart_allocations = {}
    for a in allocations:
        if a.worker and a.worker.process != 'machining':
            continue
            
        if a.worker_id:
            is_jw = (a.worker.worker_type == WorkerType.JOB_WORKER)
            w_id = f"jw_{a.worker_id}" if is_jw else f"w_{a.worker_id}"
            w_name = a.worker.name
        else:
            continue

        performer = {"id": w_id, "name": w_name}
        
        # Direct allocation mapping
        item_id = str(company_items.get(a.item.code, a.item.id))
        if item_id not in smart_allocations:
            smart_allocations[item_id] = []
        if performer not in smart_allocations[item_id]:
            smart_allocations[item_id].append(performer)
            
        # Inherit parent set allocations for sub-components (resolved via OM equivalent item)
        equivalent_item_id = company_items.get(a.item.code)
        if equivalent_item_id:
            from apps.master_data.models import ItemComposition
            for comp in ItemComposition.objects.filter(parent_item_id=equivalent_item_id):
                comp_id = str(comp.component_item_id)
                if comp_id not in smart_allocations:
                    smart_allocations[comp_id] = []
                if performer not in smart_allocations[comp_id]:
                    smart_allocations[comp_id].append(performer)

    # Calculate casting stock for each item from bulk stock map
    for item in items:
        st = bulk_stock.get(item.id, {})
        item.casting_stock = st.get('casting', 0)

    # Build worker_wip_by_item lookup map
    worker_wip_by_item = {}
    for entry in machining_stock:
        key = f"{entry['worker_id']}_{entry['item_id']}"
        worker_wip_by_item[key] = entry['under_process']

    # Create sorted copy of machining stock by category for Stock Tab
    machining_stock_by_category = list(machining_stock)
    wip_item_ids = {row["item_id"] for row in machining_stock}
    for item in items:
        if item.id not in wip_item_ids:
            st = bulk_stock.get(item.id, {})
            available_qty = st.get('machining', 0)
            if available_qty > 0:
                machining_stock_by_category.append({
                    "item_id": item.id,
                    "item_name": f"{item.code} - {item.name}",
                    "item_category": item.category,
                    "item_uom": item.uom,
                    "is_raw_material": item.is_raw_material,
                    "worker_id": "",
                    "worker_name": "Warehouse Stock",
                    "under_process": 0,
                    "available_qty": available_qty
                })
    machining_stock_by_category.sort(key=lambda x: x["item_category"])

    # Sort WIP stock by worker_name to support Django regroup template tag grouping
    machining_stock.sort(key=lambda x: x["worker_name"])

    context = {
        "workers": workers,
        "job_workers": job_workers,
        "items": items,
        "all_items": items,
        "recent": recent,
        "worker_ledger": dict(worker_ledger),
        "machining_stock": machining_stock,
        "machining_stock_by_category": machining_stock_by_category,
        "worker_wip": worker_wip,
        "smart_allocations": json.dumps(smart_allocations),
        "worker_wip_by_item_json": json.dumps(worker_wip_by_item),
        "today": timezone.now(),
        "selected_date": query_date.strftime("%Y-%m-%d"),
    }

    return render(request, "machining.html", context)

# =====================================================
# POLISHING
# =====================================================

def polishing_entry(request):
    workers = Worker.objects.filter(process="polishing", active=True, worker_type=WorkerType.IN_HOUSE)
    job_workers = Worker.objects.filter(process="polishing", active=True, worker_type=WorkerType.JOB_WORKER)
    active_company = request.company
    if active_company:
        items = Item.objects.filter(company=active_company).filter(Q(polishing_required=True) | Q(item_type='SET') | Q(components__isnull=False)).distinct()
    else:
        items = Item.objects.filter(company_id=2).filter(Q(polishing_required=True) | Q(item_type='SET') | Q(components__isnull=False)).distinct()

    if request.method == "POST":
        date_str = request.POST.get("date") or request.GET.get("date")
    else:
        date_str = request.GET.get("date") or request.POST.get("date")
    selected_date = None
    if date_str:
        try:
            selected_date = timezone.datetime.strptime(date_str + " 12:00:00", "%Y-%m-%d %H:%M:%S")
            selected_date = timezone.make_aware(selected_date)
        except Exception:
            pass
    query_date = selected_date.date() if selected_date else timezone.now().date()

    piece_stock = {}
    set_capacity = {}

    bulk_stock = services.get_all_items_stock(company=active_company)

    for item in items:
        stock = bulk_stock.get(item.id, {})
        current_machining_stock = stock.get('machining', 0)
        
        # Store individual piece stock
        piece_stock[item.id] = current_machining_stock
        item.current_stock = current_machining_stock

    # Second pass: Calculate Set Capacity based on piece stock
    for item in items:
        if item.components.exists():
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
        return redirect(reverse("polishing_entry") + (f"?date={date_str}" if date_str else ""))

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
        
        target_worker = None
        if worker_str:
            clean_id = worker_str
            if clean_id.startswith("jw_"):
                clean_id = clean_id[3:]
            elif clean_id.startswith("w_"):
                clean_id = clean_id[2:]
            target_worker = Worker.objects.filter(id=clean_id).first()
                
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
                
                if target_worker:
                    out_txs = out_txs.filter(worker=target_worker)
                    in_txs = in_txs.filter(worker=target_worker)
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
                        in_tx = StockTransaction.objects.create(
                            transaction_type="polishing_in",
                            item=tx.item,
                            worker=tx.worker,
                            quantity=q,
                            weight=w,
                            rejection_quantity=tx_rejections,
                            notes=f"IN for OUT #{tx.id}"
                        )
                        if selected_date:
                            in_tx.created_at = selected_date
                            in_tx.save()
                        remaining_rejections -= tx_rejections
                        count += 1
                        
                if count > 0:
                    rejection_suffix = f" (with {rejections} rejections recorded)" if rejections > 0 else ""
                    messages.success(request, f"Successfully marked IN {count} entries, perfectly preserving original issue lot sizes and weights{rejection_suffix}!")
                else:
                    messages.info(request, "No outstanding polishing issues to mark IN.")
            except Item.DoesNotExist:
                messages.error(request, "Selected item not found.")
                
        return redirect(reverse("polishing_entry") + (f"?date={date_str}" if date_str else ""))

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
                in_tx = StockTransaction.objects.create(
                    transaction_type="polishing_in",
                    item=out_entry.item,
                    worker=out_entry.worker,
                    quantity=out_entry.quantity,
                    weight=out_entry.weight,
                    rejection_quantity=rejections,
                    notes=f"IN for OUT #{out_entry.id}"
                )
                if selected_date:
                    in_tx.created_at = selected_date
                    in_tx.save()
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
        return redirect(reverse("polishing_entry") + (f"?date={date_str}" if date_str else ""))

    if request.method == "POST":
        worker_id = request.POST.get("worker")

        if not worker_id:
            messages.error(
                request,
                "Please select a worker before saving polishing entries."
            )
            return redirect("polishing_entry")

        worker_obj = resolve_worker(worker_id)

        if not worker_obj:
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

                deficit_mode = request.POST.get("deficit_mode", "none")
                allow_zero = (direction == "polishing_in" and deficit_mode in ["correct_issue", "wastage"])

                if total_quantity <= 0 and not allow_zero:
                    continue

                edit_id = request.POST.get("edit_id")
                if edit_id:
                    try:
                        tx = StockTransaction.objects.get(id=edit_id)
                        tx.transaction_type = direction
                        tx.item = item
                        tx.worker = worker_obj or job_worker_obj
                        tx.quantity = total_quantity
                        tx.weight = weight
                        tx.save()
                        if selected_date:
                            StockTransaction.objects.filter(pk=tx.pk).update(created_at=selected_date)

                        # Delete old component consumptions
                        StockTransaction.objects.filter(notes__startswith=f"Auto-consumed for Set Transaction #{tx.id}").delete()

                        # Delete old component extras and their associated polishing_in transactions
                        comp_extras = StockTransaction.objects.filter(notes=f"Component Extra for Set Transaction #{tx.id}")
                        for comp_tx in comp_extras:
                            StockTransaction.objects.filter(notes=f"IN for OUT #{comp_tx.id}").delete()
                        comp_extras.delete()

                        # Re-create child auto-consumption and component extras if applicable
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
                                    child_tx = StockTransaction.objects.create(
                                        transaction_type="kitting_consume",
                                        item=comp_item,
                                        quantity=base_qty,
                                        from_warehouse=from_wh,
                                        notes=f"Auto-consumed for Set Transaction #{tx.id}"
                                    )
                                    if selected_date:
                                        StockTransaction.objects.filter(pk=child_tx.pk).update(created_at=selected_date)
                                
                                if extra_qty > 0:
                                    child_tx = StockTransaction.objects.create(
                                        transaction_type="polishing_out",
                                        item=comp_item,
                                        worker=worker_obj,
                                        quantity=extra_qty,
                                        weight=extra_qty * (comp_item.machining_weight or 0.0),
                                        notes=f"Component Extra for Set Transaction #{tx.id}"
                                    )
                                    if selected_date:
                                        StockTransaction.objects.filter(pk=child_tx.pk).update(created_at=selected_date)
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

                    # Auto-adjust variance if requested
                    deficit_mode = request.POST.get("deficit_mode", "none")
                    if direction == "polishing_in":
                        w_filter = {}
                        if worker_obj:
                            w_filter['worker'] = worker_obj
                        
                        issued_qty = StockTransaction.objects.filter(
                            item=item,
                            transaction_type="polishing_out",
                            **w_filter
                        ).aggregate(total=Sum('quantity'))['total'] or 0
                        
                        received_qty = StockTransaction.objects.filter(
                            item=item,
                            transaction_type="polishing_in",
                            **w_filter
                        ).aggregate(total=Sum('quantity'))['total'] or 0
                        
                        rejected_qty = StockTransaction.objects.filter(
                            item=item,
                            transaction_type="polishing_in",
                            **w_filter
                        ).aggregate(total=Sum('rejection_quantity'))['total'] or 0
                        
                        current_wip = issued_qty - received_qty - rejected_qty
                        new_wip = current_wip - total_quantity
                        
                        if new_wip < 0: # Surplus / Direct Receive: auto-create matching OUT issue entry
                            surplus_qty = abs(new_wip)
                            comp_tx = StockTransaction.objects.create(
                                transaction_type="polishing_out",
                                item=item,
                                worker=worker_obj,
                                quantity=surplus_qty,
                                weight=round(surplus_qty * (item.machining_weight or 0.0), 3),
                                notes="Auto-issued to balance direct receive entry."
                            )
                            if selected_date:
                                StockTransaction.objects.filter(pk=comp_tx.pk).update(created_at=selected_date)
                        elif new_wip > 0: # Deficit: we received less than issued
                            deficit_qty = new_wip
                            if deficit_mode == "correct_issue":
                                # Reduce the original issue count to return pieces to Machined Stock
                                open_issues = StockTransaction.objects.filter(
                                    item=item,
                                    transaction_type="polishing_out",
                                    **w_filter
                                ).order_by("-id")
                                remaining_reduction = deficit_qty
                                for issue_tx in open_issues:
                                    if remaining_reduction <= 0:
                                        break
                                    if issue_tx.quantity >= remaining_reduction:
                                        issue_tx.quantity -= remaining_reduction
                                        issue_tx.weight = issue_tx.quantity * (item.machining_weight or 0.0)
                                        issue_tx.save()
                                        remaining_reduction = 0
                                    else:
                                        remaining_reduction -= issue_tx.quantity
                                        issue_tx.quantity = 0
                                        issue_tx.weight = 0.0
                                        issue_tx.save()
                            elif deficit_mode == "wastage":
                                # Variance deficit accounted for
                                pass

                    for sub_idx, (q, w) in enumerate(sub_transactions):
                        parent_tx = StockTransaction.objects.create(
                            transaction_type=direction,
                            item=item,
                            worker=worker_obj,
                            quantity=q,
                            weight=w
                        )
                        if selected_date:
                            StockTransaction.objects.filter(pk=parent_tx.pk).update(created_at=selected_date)

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
                                    child_tx = StockTransaction.objects.create(
                                        transaction_type="kitting_consume",
                                        item=comp_item,
                                        quantity=base_qty,
                                        from_warehouse=from_wh,
                                        notes=f"Auto-consumed for Set Transaction #{parent_tx.id}"
                                    )
                                    if selected_date:
                                        StockTransaction.objects.filter(pk=child_tx.pk).update(created_at=selected_date)
                                    
                                # Only attach component extra pieces once on the first sub-transaction
                                if extra_qty > 0 and sub_idx == 0:
                                    child_tx = StockTransaction.objects.create(
                                        transaction_type="polishing_out",
                                        item=comp_item,
                                        worker=worker_obj,
                                        quantity=extra_qty,
                                        weight=extra_qty * (comp_item.machining_weight or 0.0),
                                        notes=f"Component Extra for Set Transaction #{parent_tx.id}"
                                    )
                                    if selected_date:
                                        StockTransaction.objects.filter(pk=child_tx.pk).update(created_at=selected_date)
                    messages.success(request, f"Polishing { 'Issue' if direction == 'polishing_out' else 'Receipt' } saved successfully.")

            redirect_date = selected_date.strftime("%Y-%m-%d") if selected_date else date_str
            return redirect(reverse("polishing_entry") + (f"?date={redirect_date}" if redirect_date else ""))
        else:
            # Fallback to standard form fields (legacy support)
            rows = request.POST.getlist("item[]")
            packagings = request.POST.getlist("packaging[]")
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
                packaging = packagings[index] if index < len(packagings) else "regular"

                # Get correct lot size based on packaging (with fallback to lot_size if lot_with_box is 0 or None)
                if packaging == "box":
                    lot_size = item.lot_with_box if (item.lot_with_box and item.lot_with_box > 0) else item.lot_size
                else:
                    lot_size = item.lot_size
                lot_size = lot_size or 0
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
                        quantity=q,
                        weight=w
                    )
                    if selected_date:
                        parent_tx.created_at = selected_date
                        parent_tx.save()

                    if direction == "polishing_out" and item.components.exists():
                        comps = ItemComposition.objects.filter(parent_item=item)
                        from_wh = Warehouse.objects.filter(code='MACHINING').first()
                        for comp in comps:
                            comp_total_qty = comp.quantity * q
                            child_tx = StockTransaction.objects.create(
                                transaction_type="kitting_consume",
                                item=comp.component_item,
                                quantity=comp_total_qty,
                                from_warehouse=from_wh,
                                notes=f"Auto-consumed for Set: {item.name} (Polishing Out) [Set Transaction #{parent_tx.id}]"
                            )
                            if selected_date:
                                child_tx.created_at = selected_date
                                child_tx.save()

            messages.success(
                request,
                f"Polishing { 'Issue' if direction == 'polishing_out' else 'Receipt' } saved successfully."
            )
            return redirect(reverse("polishing_entry") + (f"?date={date_str}" if date_str else ""))

    recent = StockTransaction.objects.filter(
        transaction_type__in=[
            "polishing_out",
            "polishing_in"
        ],
        created_at__date=query_date
    ).order_by("-created_at")

    completed_ids = []

    recent_out_ids = [row.id for row in recent if row.transaction_type == "polishing_out"]
    completed_ids = []
    if recent_out_ids:
        in_notes = StockTransaction.objects.filter(
            transaction_type="polishing_in",
            notes__contains="IN for OUT #"
        ).values_list('notes', flat=True)
        completed_set = set()
        pattern = re.compile(r'IN for OUT #(\d+)')
        for note in in_notes:
            m = pattern.search(note or '')
            if m:
                completed_set.add(int(m.group(1)))

        auto_issued_ids = set(StockTransaction.objects.filter(
            transaction_type="polishing_out",
            notes__contains="Auto-issued"
        ).values_list('id', flat=True))

        all_outs = StockTransaction.objects.filter(
            transaction_type="polishing_out",
            worker__isnull=False
        ).order_by('id')

        all_ins_map = defaultdict(int)
        for s in StockTransaction.objects.filter(
            transaction_type="polishing_in",
            worker__isnull=False
        ).values('item_id', 'worker_id').annotate(tot=Sum('quantity'), rej=Sum('rejection_quantity')):
            all_ins_map[(s['item_id'], s['worker_id'])] = (s['tot'] or 0) + (s['rej'] or 0)

        fifo_completed = set(completed_set) | auto_issued_ids
        worker_consumed_in = defaultdict(int)

        for out_tx in all_outs:
            key = (out_tx.item_id, out_tx.worker_id)
            avail_in = all_ins_map[key] - worker_consumed_in[key]
            if avail_in >= out_tx.quantity:
                fifo_completed.add(out_tx.id)
                worker_consumed_in[key] += out_tx.quantity
            elif out_tx.id in completed_set or out_tx.id in auto_issued_ids:
                fifo_completed.add(out_tx.id)

        completed_ids = [oid for oid in recent_out_ids if oid in fifo_completed]

    # Calculate Polishing WIP Stock - Grouped by Worker in 1 Bulk Query
    polishing_stock = defaultdict(list)
    polishing_tx_stats = StockTransaction.objects.filter(
        transaction_type__in=["polishing_out", "polishing_in"],
        worker__isnull=False
    ).values(
        'item_id', 'item__code', 'item__name', 'worker_id', 'worker__name', 'worker__worker_type', 'worker__jw_code', 'transaction_type'
    ).annotate(
        total_qty=Sum('quantity'),
        total_rej=Sum('rejection_quantity')
    )

    wip_by_pol_item_worker = defaultdict(lambda: {'issued': 0, 'received': 0, 'rejected': 0, 'item_code': '', 'item_name': '', 'w_name': '', 'w_type': '', 'jw_code': ''})
    for s in polishing_tx_stats:
        key = (s['item_id'], s['worker_id'])
        d = wip_by_pol_item_worker[key]
        d['item_code'] = s['item__code']
        d['item_name'] = s['item__name']
        d['w_name'] = s['worker__name']
        d['w_type'] = s['worker__worker_type']
        d['jw_code'] = s['worker__jw_code']
        if s['transaction_type'] == "polishing_out":
            d['issued'] += s['total_qty'] or 0
        elif s['transaction_type'] == "polishing_in":
            d['received'] += s['total_qty'] or 0
            d['rejected'] += s['total_rej'] or 0

    for (item_id, wid), val in wip_by_pol_item_worker.items():
        under_process = val['issued'] - val['received'] - val['rejected']
        if under_process > 0:
            is_jw = (val['w_type'] == 'JOB_WORKER')
            target_id = f"jw_{wid}" if is_jw else f"w_{wid}"
            display_name = val['w_name'] if is_jw else f"{val['w_name']} (INT)"
            polishing_stock[display_name].append({
                "item_id": item_id,
                "item_code": val['item_code'],
                "item_name": val['item_name'],
                "worker_id": target_id,
                "under_process": under_process,
            })

    allocations = ItemWorkerAllocation.objects.filter(
        worker__process='polishing'
    ).select_related('item', 'worker')
    company_items = {it.code: it.id for it in items}
    resolved_allocations = []
    smart_allocations = {}

    for a in allocations:
        if not a.worker or a.worker.process != 'polishing':
            continue

        resolved_item_id = company_items.get(a.item.code, a.item.id)
        resolved_allocations.append({
            "item_id": resolved_item_id,
            "worker": a.worker
        })

        is_jw = (a.worker.worker_type == WorkerType.JOB_WORKER)
        w_id = f"jw_{a.worker_id}" if is_jw else f"w_{a.worker_id}"
        w_name = a.worker.name

        performer = {"id": w_id, "name": w_name}
        item_id_str = str(resolved_item_id)
        if item_id_str not in smart_allocations:
            smart_allocations[item_id_str] = []
        if performer not in smart_allocations[item_id_str]:
            smart_allocations[item_id_str].append(performer)

    worker_wip_by_item = {}
    for worker_name, items_list in polishing_stock.items():
        for entry in items_list:
            key = f"{entry['worker_id']}_{entry['item_id']}"
            worker_wip_by_item[key] = entry['under_process']

    context = {
        "workers": workers,
        "job_workers": job_workers,
        "items": items,
        "all_items": items,
        "recent": recent,
        "piece_stock": piece_stock,
        "set_capacity": set_capacity,
        "available_data": available_data,
        "completed_ids": completed_ids,
        "allocations": resolved_allocations,
        "smart_allocations": json.dumps(smart_allocations),
        "polishing_stock": dict(polishing_stock),
        "worker_wip_by_item_json": json.dumps(worker_wip_by_item),
        "selected_date": query_date.strftime("%Y-%m-%d"),
    }

    return render(request, "polishing.html", context)

# =====================================================
# PACKAGING
# =====================================================

def packaging_view(request):
    from django.db.models import Sum
    from apps.production import services
    from apps.master_data.models import ItemComposition
    import uuid

    if request.method == "POST":
        date_str = request.POST.get("date") or request.GET.get("date")
    else:
        date_str = request.GET.get("date") or request.POST.get("date")
    selected_date = None
    if date_str:
        try:
            selected_date = timezone.datetime.strptime(date_str + " 12:00:00", "%Y-%m-%d %H:%M:%S")
            selected_date = timezone.make_aware(selected_date)
        except Exception:
            pass
    query_date = selected_date.date() if selected_date else timezone.now().date()

    import re
    packed_txs = StockTransaction.objects.filter(
        transaction_type="packaging_in",
        notes__contains="PACKED #"
    ).values('notes').annotate(total=Sum('quantity'))
    
    packed_map = defaultdict(int)
    pattern = re.compile(r'PACKED\s*#(\d+)')
    for pt in packed_txs:
        notes = pt.get('notes') or ''
        qty = pt.get('total') or 0
        match = pattern.search(notes)
        if match:
            eid = int(match.group(1))
            packed_map[eid] += qty

    def get_polishing_entry_remaining_qty(entry):
        packed_qty = packed_map.get(entry.id, 0)
        remaining_qty = entry.quantity - packed_qty - (entry.rejection_quantity or 0)
        return max(0, remaining_qty)

    items = Item.objects.all()
    bulk_stock = services.get_all_items_stock(company=request.company)

    # Calculate live Polishing WIP Stock/Capacity for each item
    piece_stock = {}
    for item in items:
        # Fetch current polishing stock from bulk memory map
        piece_stock[item.id] = bulk_stock.get(item.id, {}).get('polishing', 0)
        item.available_polishing = piece_stock[item.id]
        
        if item.item_type == 'SET':
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
    # PACKAGING QUEUE (In-House Production)
    # =====================================
    packaging_queue = []

    polishing_in_entries = StockTransaction.objects.filter(
        transaction_type="polishing_in"
    ).select_related('item', 'worker').order_by("-created_at")

    for entry in polishing_in_entries:
        remaining_qty = get_polishing_entry_remaining_qty(entry)
        if remaining_qty > 0:
            orig_qty = entry.quantity
            orig_wt = entry.weight
            entry.quantity = remaining_qty
            entry.weight = round((remaining_qty / orig_qty) * orig_wt, 3) if orig_qty > 0 else 0.0
            packaging_queue.append(entry)

    # =====================================
    # PURCHASES QUEUE (Purchased Goods)
    # =====================================
    purchased_queue = []

    purchase_entries = StockTransaction.objects.filter(
        transaction_type="purchase_entry"
    ).select_related('item', 'worker').order_by("-created_at")

    for entry in purchase_entries:
        remaining_qty = get_polishing_entry_remaining_qty(entry)
        if remaining_qty > 0:
            orig_qty = entry.quantity
            orig_wt = entry.weight
            entry.quantity = remaining_qty
            entry.weight = round((remaining_qty / orig_qty) * orig_wt, 3) if orig_qty > 0 else 0.0
            purchased_queue.append(entry)

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
            associated_txs = StockTransaction.objects.filter(
                Q(notes__contains=f"[Carton #{carton.id}]") | Q(notes__contains=f"Carton #{carton.id}]")
            )
            for tx in associated_txs:
                StockTransaction.objects.filter(notes__contains=f"packaging ID: #{tx.id}").delete()
                tx.delete()
            carton.delete()
            messages.success(request, "Carton packaging log deleted successfully.")
        except Carton.DoesNotExist:
            messages.error(request, "Selected carton log could not be found.")
        return redirect(reverse("packaging") + (f"?date={date_str}" if date_str else ""))

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
        return redirect(reverse("packaging") + (f"?date={date_str}" if date_str else ""))

    # =====================================
    # PACK NOW BUTTON (GET Request Shortcut)
    # =====================================
    if pack_id:
        try:
            polishing_entry = StockTransaction.objects.get(
                id=pack_id,
                transaction_type__in=["polishing_in", "purchase_entry"]
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
                if selected_date:
                    carton.created_at = selected_date
                    carton.save()
                
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
                if selected_date:
                    new_tx.created_at = selected_date
                    new_tx.save()
                
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
        return redirect(reverse("packaging") + (f"?date={date_str}" if date_str else ""))

    # =====================================
    # BATCH PACK SEPARATE CARTONS SHORTCUT
    # =====================================
    pack_batch = request.GET.get("pack_batch")
    if pack_batch:
        try:
            ids = [int(i.strip()) for i in pack_batch.split(',') if i.strip().isdigit()]
            entries = StockTransaction.objects.filter(
                id__in=ids,
                transaction_type__in=["polishing_in", "purchase_entry"]
            )
            packed_count = 0
            for polishing_entry in entries:
                remaining_qty = get_polishing_entry_remaining_qty(polishing_entry)
                if remaining_qty > 0:
                    qty_to_pack = remaining_qty
                    weight_to_pack = round((qty_to_pack / polishing_entry.quantity) * polishing_entry.weight, 3) if polishing_entry.quantity > 0 else 0.0

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

                    carton = Carton.objects.create(
                        carton_type='SET' if item.item_type == 'SET' else 'SINGLE',
                        carton_label=label_val,
                        total_quantity=qty_to_pack,
                        total_weight=weight_to_pack,
                        cleaning=True, labeling=True, packing=True,
                        status='READY'
                    )
                    if selected_date:
                        carton.created_at = selected_date
                        carton.save()

                    CartonItem.objects.create(
                        carton=carton,
                        item=polishing_entry.item,
                        quantity=qty_to_pack,
                        weight=weight_to_pack
                    )

                    new_tx = StockTransaction.objects.create(
                        transaction_type="packaging_in",
                        item=polishing_entry.item,
                        quantity=qty_to_pack,
                        weight=weight_to_pack,
                        notes=f"PACKED #{polishing_entry.id} [Cleaning, Labeling, Packing] [Carton #{carton.id}]"
                    )
                    if selected_date:
                        new_tx.created_at = selected_date
                        new_tx.save()
                    packed_count += 1

            if packed_count > 0:
                messages.success(request, f"Successfully created {packed_count} separate individual cartons for selected items!")
            else:
                messages.info(request, "Selected entries were already fully packed.")
        except Exception as e:
            messages.error(request, f"Error batch packing entries: {e}")
        return redirect(reverse("packaging") + (f"?date={date_str}" if date_str else ""))

    # =====================================
    # TO BUFFER SHORTCUT (GET Request)
    # =====================================
    to_buffer_id = request.GET.get("to_buffer")
    if to_buffer_id:
        try:
            polishing_entry = StockTransaction.objects.get(
                id=to_buffer_id,
                transaction_type__in=["polishing_in", "purchase_entry"]
            )
            remaining_qty = get_polishing_entry_remaining_qty(polishing_entry)
            
            qty_to_move_str = request.GET.get("qty")
            qty_to_move = int(qty_to_move_str) if qty_to_move_str else remaining_qty
            qty_to_move = min(qty_to_move, remaining_qty)
            
            if qty_to_move > 0:
                weight_to_move = round((qty_to_move / polishing_entry.quantity) * polishing_entry.weight, 3) if polishing_entry.quantity > 0 else 0.0
                
                buffer_tx = StockTransaction.objects.create(
                    transaction_type="packaging_in",
                    item=polishing_entry.item,
                    quantity=qty_to_move,
                    weight=weight_to_move,
                    notes=f"PACKED #{polishing_entry.id} [DEDICATED BUFFER] Kept loose in warehouse"
                )
                if selected_date:
                    buffer_tx.created_at = selected_date
                    buffer_tx.save()
                
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
        return redirect(reverse("packaging") + (f"?date={date_str}" if date_str else ""))

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
        top_up_from_buffer = request.POST.get("top_up_from_buffer") == "YES"
        
        sales_order_id = request.POST.get("sales_order")
        sales_order = None
        client = None
        if sales_order_id:
            from apps.orders.models import SalesOrder
            sales_order = SalesOrder.objects.filter(id=sales_order_id).first()
            if sales_order:
                client = sales_order.client
        
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
                # Get the lot size for a single carton
                lot_size = item.lot_with_box if packaging_type == 'box' else item.lot_size
                if not lot_size or lot_size <= 0:
                    lot_size = 1 # fallback
                
                # Fetch ready_cartons and extra_pieces if available
                ready_cartons = int(request.POST.get("ready_cartons") or 0)
                extra_pieces = int(request.POST.get("extra_pieces") or 0)
                
                cartons_to_create = []
                piece_weight = item.machining_weight or 0.0
                
                if not edit_id and (ready_cartons > 0 or extra_pieces > 0):
                    for i in range(ready_cartons):
                        cartons_to_create.append({
                            'qty': lot_size,
                            'weight': round(lot_size * piece_weight, 3)
                        })
                    if extra_pieces > 0:
                        if top_up_from_buffer:
                            cartons_to_create.append({
                                'qty': lot_size,
                                'weight': round(lot_size * piece_weight, 3)
                            })
                        else:
                            cartons_to_create.append({
                                'qty': extra_pieces,
                                'weight': round(extra_pieces * piece_weight, 3)
                            })
                else:
                    # Fallback/edit case: just a single carton
                    cartons_to_create.append({
                        'qty': quantity,
                        'weight': weight
                    })

                # ========================================================
                # NEW VALIDATION LOGIC FOR BOTH SETS AND SINGLE ITEMS
                # ========================================================
                total_qty_to_pack = sum(c['qty'] for c in cartons_to_create)
                
                if item.item_type == "SET":
                    # Check parent set polishing_in entries in queue
                    set_queue_entries = StockTransaction.objects.filter(
                        item=item,
                        transaction_type__in=["polishing_in", "purchase_entry"]
                    ).order_by("created_at")
                    set_queue_sum = sum(get_polishing_entry_remaining_qty(entry) for entry in set_queue_entries)

                    # Validate component stocks: component is satisfied either from set queue or loose component buffer
                    for comp in ItemComposition.objects.filter(parent_item=item):
                        comp_item = comp.component_item
                        comp_qty_needed = total_qty_to_pack * comp.quantity
                        comp_avail_buffer = max(0, services.get_stock_by_item(comp_item).get('polishing', 0))
                        comp_total_avail = (set_queue_sum * comp.quantity) + comp_avail_buffer
                        if comp_total_avail < comp_qty_needed:
                            messages.error(request, f"Insufficient stock for component {comp_item.code}. Required: {comp_qty_needed} pcs, Available: {comp_total_avail} pcs.")
                            return redirect(reverse("packaging") + (f"?date={date_str}" if date_str else ""))
                else:
                    # Validate single item stock
                    polishing_in_entries = StockTransaction.objects.filter(
                        item=item,
                        transaction_type__in=["polishing_in", "purchase_entry"]
                    ).order_by("created_at")
                    queue_sum = sum(get_polishing_entry_remaining_qty(entry) for entry in polishing_in_entries)
                    needed_from_buffer = max(0, total_qty_to_pack - queue_sum)
                    
                    if needed_from_buffer > 0:
                        buffer_avail = services.get_stock_by_item(item).get('polishing', 0)
                        if buffer_avail < total_qty_to_pack:
                            messages.error(request, f"Insufficient stock for {item.code}. Required: {total_qty_to_pack} pcs, Available: {buffer_avail} pcs.")
                            return redirect(reverse("packaging") + (f"?date={date_str}" if date_str else ""))

                # ========================================================
                # PACKING EXECUTION
                # ========================================================
                if item.item_type == "SET":
                    # SET packing logic: Fetch set queue entries for FIFO consumption
                    outstanding_set_entries = []
                    polishing_in_entries = StockTransaction.objects.filter(
                        item=item,
                        transaction_type__in=["polishing_in", "purchase_entry"]
                    ).order_by("created_at")
                    
                    for entry in polishing_in_entries:
                        entry_remaining = get_polishing_entry_remaining_qty(entry)
                        if entry_remaining > 0:
                            outstanding_set_entries.append((entry, entry_remaining))

                    for idx, c_data in enumerate(cartons_to_create):
                        c_qty = c_data['qty']
                        c_wt = c_data['weight']
                        
                        if edit_id:
                            try:
                                carton = Carton.objects.get(id=edit_id)
                                # Delete old StockTransactions associated with this Carton
                                associated_txs = StockTransaction.objects.filter(notes__contains=f"[Carton #{carton.id}]")
                                for tx in associated_txs:
                                    StockTransaction.objects.filter(notes__contains=f"packaging ID: #{tx.id}").delete()
                                    tx.delete()
                                carton.items.all().delete()
                                
                                carton.carton_type = 'SET'
                                carton.carton_label = label_val
                                carton.cleaning = cleaning
                                carton.labeling = labeling
                                carton.packing = packing
                                carton.total_quantity = c_qty
                                carton.total_weight = c_wt
                                carton.sales_order = sales_order
                                carton.client = client
                                if selected_date:
                                    carton.created_at = selected_date
                                carton.save()
                            except Carton.DoesNotExist:
                                messages.error(request, "Selected carton log not found.")
                                return redirect(reverse("packaging") + (f"?date={date_str}" if date_str else ""))
                        else:
                            carton = Carton.objects.create(
                                carton_type='SET',
                                carton_label=label_val,
                                cleaning=cleaning,
                                labeling=labeling,
                                packing=packing,
                                total_quantity=c_qty,
                                total_weight=c_wt,
                                sales_order=sales_order,
                                client=client,
                                status='READY'
                            )
                            if selected_date:
                                carton.created_at = selected_date
                                carton.save()
                        
                        # Create CartonItem
                        CartonItem.objects.create(
                            carton=carton,
                            item=item,
                            quantity=c_qty,
                            weight=c_wt
                        )
                        
                        # FIFO queue consumption for Set item entries
                        remaining_set_to_pack = c_qty
                        for entry, entry_remaining in outstanding_set_entries:
                            if remaining_set_to_pack <= 0:
                                break
                            
                            entry_remaining = get_polishing_entry_remaining_qty(entry)
                            if entry_remaining <= 0:
                                continue
                            
                            pack_qty = min(entry_remaining, remaining_set_to_pack)
                            pack_wt = round((pack_qty / entry.quantity) * entry.weight, 3) if entry.quantity > 0 else 0.0
                            
                            new_tx = StockTransaction.objects.create(
                                transaction_type="packaging_in",
                                item=item,
                                quantity=pack_qty,
                                weight=pack_wt,
                                notes=f"PACKED #{entry.id}{steps_str} [Carton #{carton.id}]"
                            )
                            if selected_date:
                                new_tx.created_at = selected_date
                                new_tx.save()
                            
                            remaining_set_to_pack -= pack_qty

                        # Record any remaining quantity packed beyond polishing queue
                        if remaining_set_to_pack > 0:
                            rem_wt = round(remaining_set_to_pack * (c_wt / c_qty), 3) if c_qty > 0 else 0.0
                            new_tx = StockTransaction.objects.create(
                                transaction_type="packaging_in",
                                item=item,
                                quantity=remaining_set_to_pack,
                                weight=rem_wt,
                                notes=f"Manual Packaging{steps_str} [Carton #{carton.id}]"
                            )
                            if selected_date:
                                new_tx.created_at = selected_date
                                new_tx.save()

                            # Negative component transactions for set portion drawn from loose component buffer
                            for comp in ItemComposition.objects.filter(parent_item=item):
                                comp_item = comp.component_item
                                comp_qty_needed = remaining_set_to_pack * comp.quantity
                                comp_wt_needed = round(comp_qty_needed * (comp_item.machining_weight or 0.0), 3)
                                comp_tx = StockTransaction.objects.create(
                                    transaction_type="packaging_in",
                                    item=comp_item,
                                    quantity=-comp_qty_needed,
                                    weight=-comp_wt_needed,
                                    notes=f"[DEDICATED BUFFER] Consumed components for Set Carton #{carton.id}"
                                )
                                if selected_date:
                                    comp_tx.created_at = selected_date
                                    comp_tx.save()
                                
                    messages.success(request, f"Successfully packed {quantity} pcs of Set {item.name} into Carton(s)!")

                else:
                    # SINGLE item packing logic: Keep the existing FIFO queue loop and rejections logic
                    # Perform smart FIFO queue consumption of outstanding polishing entries
                    outstanding = []
                    polishing_in_entries = StockTransaction.objects.filter(
                        item=item,
                        transaction_type__in=["polishing_in", "purchase_entry"]
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

                    # Now create each Carton
                    for idx, c_data in enumerate(cartons_to_create):
                        c_qty = c_data['qty']
                        c_wt = c_data['weight']
                        
                        if edit_id:
                            try:
                                carton = Carton.objects.get(id=edit_id)
                                # Delete old StockTransactions associated with this Carton
                                associated_txs = StockTransaction.objects.filter(notes__contains=f"[Carton #{carton.id}]")
                                for tx in associated_txs:
                                    StockTransaction.objects.filter(notes__contains=f"packaging ID: #{tx.id}").delete()
                                    tx.delete()
                                carton.items.all().delete()
                                
                                carton.carton_type = 'SINGLE'
                                carton.carton_label = label_val
                                carton.cleaning = cleaning
                                carton.labeling = labeling
                                carton.packing = packing
                                carton.total_quantity = c_qty
                                carton.total_weight = c_wt
                                carton.sales_order = sales_order
                                carton.client = client
                                if selected_date:
                                    carton.created_at = selected_date
                                carton.save()
                            except Carton.DoesNotExist:
                                messages.error(request, "Selected carton log not found.")
                                return redirect(reverse("packaging") + (f"?date={date_str}" if date_str else ""))
                        else:
                            # Create a new Carton
                            carton = Carton.objects.create(
                                carton_type='SINGLE',
                                carton_label=label_val,
                                cleaning=cleaning,
                                labeling=labeling,
                                packing=packing,
                                total_quantity=c_qty,
                                total_weight=c_wt,
                                sales_order=sales_order,
                                client=client,
                                status='READY'
                            )
                            if selected_date:
                                carton.created_at = selected_date
                                carton.save()
                        
                        # Create CartonItem
                        CartonItem.objects.create(
                            carton=carton,
                            item=item,
                            quantity=c_qty,
                            weight=c_wt
                        )
                        
                        # Replacements from buffer (deduct from loose buffer stock)
                        if idx == 0 and replace_from_buffer and rejections > 0:
                            try:
                                comp_wt = round(rejections * (item.machining_weight or 0.0), 3)
                                buffer_tx = StockTransaction.objects.create(
                                    transaction_type="packaging_in",
                                    item=item,
                                    quantity=-rejections,
                                    weight=-comp_wt,
                                    notes=f"[DEDICATED BUFFER] Replaced defective {item.code} in Carton #{carton.id}"
                                )
                                if selected_date:
                                    buffer_tx.created_at = selected_date
                                    buffer_tx.save()
                            except Exception:
                                pass

                        remaining_to_pack = c_qty
                        is_first_tx = (idx == 0)
                        
                        for entry, entry_remaining in outstanding:
                            if remaining_to_pack <= 0:
                                break
                            
                            # Fetch fresh entry details (in case rejections or previous loops reduced it)
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
                            if selected_date:
                                new_tx.created_at = selected_date
                                new_tx.save()
                            
                            remaining_to_pack -= pack_qty

                            # If top_up_from_buffer is active, we ONLY draw from this single entry and top up the rest from buffer!
                            if top_up_from_buffer and remaining_to_pack > 0:
                                try:
                                    buffer_qty = remaining_to_pack
                                    buffer_wt = round(buffer_qty * (item.machining_weight or 0.0), 3)
                                    
                                    # For SINGLE items
                                    comp_tx = StockTransaction.objects.create(
                                        transaction_type="packaging_in",
                                        item=item,
                                        quantity=-buffer_qty,
                                        weight=-buffer_wt,
                                        notes=f"[DEDICATED BUFFER] Topped up item in Carton #{carton.id}"
                                    )
                                    if selected_date:
                                        comp_tx.created_at = selected_date
                                        comp_tx.save()
                                except Exception:
                                    pass
                                
                                remaining_to_pack = 0
                                break
                        
                        # Record any remaining quantity as standard manual packaging
                        if remaining_to_pack > 0:
                            rem_wt = max(0.0, c_wt - (c_qty - remaining_to_pack) * (item.machining_weight or 0.0))
                            new_tx = StockTransaction.objects.create(
                                transaction_type="packaging_in",
                                item=item,
                                quantity=remaining_to_pack,
                                weight=round(rem_wt, 3),
                                notes=f"Manual Packaging{steps_str} [Carton #{carton.id}]"
                            )
                            if selected_date:
                                new_tx.created_at = selected_date
                                new_tx.save()

                    messages.success(request, f"Successfully packed {quantity} pcs of {item.name} into Carton(s)!")
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
                    carton.sales_order = sales_order
                    carton.client = client
                    if selected_date:
                        carton.created_at = selected_date
                    carton.save()
                except Carton.DoesNotExist:
                    messages.error(request, "Selected carton log not found.")
                    return redirect(reverse("packaging") + (f"?date={date_str}" if date_str else ""))
            else:
                # Create a brand new Mixed Carton
                carton = Carton.objects.create(
                    carton_type='MIXED',
                    carton_label=carton_label,
                    cleaning=cleaning,
                    labeling=labeling,
                    packing=packing,
                    sales_order=sales_order,
                    client=client,
                    status='READY'
                )
                if selected_date:
                    carton.created_at = selected_date
                    carton.save()
            
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
                            transaction_type__in=["polishing_in", "purchase_entry"]
                        ).order_by("created_at")
                    else:
                        polishing_in_entries = StockTransaction.objects.filter(
                            item=item,
                            transaction_type__in=["polishing_in", "purchase_entry"]
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
                            notes=f"PACKED #{entry.id} [Carton #{carton.id}] [Mixed Carton: {carton_label}]{steps_str}{notes_suffix}"
                        )
                        if selected_date:
                            new_tx.created_at = selected_date
                            new_tx.save()
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
                        if selected_date:
                            new_tx.created_at = selected_date
                            new_tx.save()

                    packed_items_count += 1
            
            if packed_items_count > 0:
                carton.total_quantity = total_qty
                carton.total_weight = round(total_wt, 3)
                carton.save()
                messages.success(request, f"Successfully saved Mixed Carton '{carton_label}' ({carton.carton_number}) containing {total_qty} pcs across {packed_items_count} items!")
            else:
                carton.delete()
                messages.error(request, "No valid items or quantities were provided for the mixed carton.")
                
        return redirect(reverse("packaging") + (f"?date={date_str}" if date_str else ""))

    active_tab = request.GET.get("tab", "entry")
    has_date_param = bool(request.GET.get("date"))
    
    # Fetch Cartons and Spares
    if active_tab == "ready":
        cartons = Carton.objects.filter(status='READY', created_at__date__lte=query_date).select_related('sales_order', 'client').prefetch_related('items__item').order_by("-created_at")
        spares = []
    elif active_tab == "buffer":
        cartons = []
        if has_date_param:
            spares = StockTransaction.objects.filter(
                transaction_type="packaging_in",
                notes__contains="[DEDICATED BUFFER]",
                created_at__date=query_date
            ).select_related('item').order_by("-created_at")
        else:
            spares = StockTransaction.objects.filter(
                transaction_type="packaging_in",
                notes__contains="[DEDICATED BUFFER]"
            ).select_related('item').order_by("-created_at")
    else:
        cartons = Carton.objects.filter(created_at__date=query_date).select_related('sales_order', 'client').prefetch_related('items__item').order_by("-created_at")
        spares = StockTransaction.objects.filter(
            transaction_type="packaging_in",
            notes__contains="[DEDICATED BUFFER]",
            created_at__date=query_date
        ).select_related('item').order_by("-created_at")
    
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
            'sales_order_number': c.sales_order.order_number if c.sales_order else None,
            'client_name': c.client.name if c.client else None,
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
    ready_cartons = Carton.objects.filter(status='READY', created_at__date__lte=query_date).select_related('sales_order', 'client').prefetch_related('items__item').order_by("-created_at")
        
    ready_analytics = []
    total_pieces = 0
    total_weight = 0.0
    total_cartons = 0
    
    # Aggregating ready cartons by Carton Label/Name to keep view neat
    cartons_grouped = defaultdict(list)
    for carton in ready_cartons:
        lbl = carton.carton_label if carton.carton_label else carton.carton_number
        cartons_grouped[lbl].append(carton)
        
    for lbl, group_cartons in cartons_grouped.items():
        first_c = group_cartons[0]
        total_group_qty = sum(c.total_quantity for c in group_cartons)
        total_group_wt = sum(float(c.total_weight) for c in group_cartons)
        
        # Accumulate nested items quantities across all cartons in the group
        items_map = defaultdict(lambda: {'name': '', 'qty': 0, 'weight': 0.0})
        for c in group_cartons:
            for ci in c.items.all():
                code = ci.item.code
                items_map[code]['name'] = ci.item.name
                items_map[code]['qty'] += ci.quantity
                items_map[code]['weight'] += float(ci.weight)
                
        nested_items = []
        for code, details in items_map.items():
            nested_items.append({
                'code': code,
                'name': details['name'],
                'qty': details['qty'],
                'weight': round(details['weight'], 3)
            })
            
        steps = []
        if first_c.cleaning: steps.append("Cleaned")
        if first_c.labeling: steps.append("Labeled")
        if first_c.packing: steps.append("Packed")
        
        if len(steps) == 3:
            status = "Fully Prepared"
            status_color = "#10b981"
        elif len(steps) > 0:
            status = "In Prep"
            status_color = "#f59e0b"
        else:
            status = "Raw Box"
            status_color = "#8b5cf6"
            
        # Get list of specific physical carton numbers in the group
        carton_numbers_list = [c.carton_number for c in group_cartons]
        first_c_items = list(first_c.items.all())
        first_item = first_c_items[0].item if first_c_items else None
        if first_item:
            lot_size = first_item.lot_with_box if (first_c.carton_type == 'SET' and first_item.lot_with_box) else (first_item.lot_size or 0)
        else:
            lot_size = 0
            
        ready_analytics.append({
            'carton_label': lbl,
            'carton_type': first_c.carton_type,
            'carton_numbers': carton_numbers_list,
            'cartons_count': len(group_cartons),
            'nested_items': nested_items,
            'qty': total_group_qty,
            'weight': round(total_group_wt, 3),
            'status': status,
            'status_color': status_color,
            'created_at': first_c.created_at,
            'steps_str': ", ".join(steps) if steps else "None",
            'sales_order_number': first_c.sales_order.order_number if first_c.sales_order else None,
            'client_name': first_c.client.name if first_c.client else None,
            'lot_size': lot_size
        })
        
        total_pieces += total_group_qty
        total_weight += total_group_wt
        total_cartons += len(group_cartons)

    # Calculate top packed items (grouped by item) for sidebar visual analysis
    from django.db.models import Sum
    top_items_qs = CartonItem.objects.filter(
        carton__status='READY',
        carton__created_at__date__lte=query_date
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
        w_name = entry.worker.name if entry.worker else "Internal/House"
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
        'ready_items_count': CartonItem.objects.filter(carton__status='READY', carton__created_at__date__lte=query_date).values('item').distinct().count(),
        'active_queue_count': len(packaging_queue)
    }

    # Group items by sub_category for loose buffer stock tab (only showing available items > 0)
    buffer_groups = {}
    for item in items:
        if item.item_type != 'SET' and getattr(item, 'buffer_stock', 0) > 0:
            subcat = item.sub_category.strip() if item.sub_category else "OTHER"
            if not subcat:
                subcat = "OTHER"
            subcat = subcat.upper()
            if subcat not in buffer_groups:
                buffer_groups[subcat] = []
            buffer_groups[subcat].append(item)

    from apps.orders.models import SalesOrder
    active_orders = SalesOrder.objects.filter(
        status__in=[SalesOrder.OrderStatus.OPEN, SalesOrder.OrderStatus.PARTIAL]
    ).prefetch_related('items', 'items__item').select_related('client').order_by('promised_date')
    if request.company:
        active_orders = active_orders.filter(client__company=request.company)

    context = {
        "items": items,
        "single_items": single_items,
        "set_items": set_items,
        "buffer_groups": buffer_groups,
        "packaging_queue": packaging_queue,
        "purchased_queue": purchased_queue,
        "grouped_queue": grouped_queue,
        "ready_stock": ready_stock,
        "completed_ids": completed_ids,
        "active_tab": active_tab,
        "all_items": Item.objects.filter(company=request.company) if request.company else Item.objects.all(),
        "ready_analytics": ready_analytics,
        "top_packed_items": top_packed_items,
        "metrics": metrics,
        "active_orders": active_orders,
        "selected_date": query_date.strftime("%Y-%m-%d"),
    }

    return render(request, "packaging.html", context)


# =====================================================
# OLD URL SUPPORT
# =====================================================

def issue_machining(request):
    return redirect("machining_entry")


# =====================================================
# PURCHASES MODULE VIEWS
# =====================================================

def purchases_view(request):
    from apps.master_data.models import Item
    from apps.production.models import StockTransaction, TransactionType
    from django.contrib import messages
    
    if request.method == "POST":
        date_str = request.POST.get("date") or request.GET.get("date")
    else:
        date_str = request.GET.get("date") or request.POST.get("date")
    selected_date = None
    if date_str:
        try:
            selected_date = timezone.datetime.strptime(date_str + " 12:00:00", "%Y-%m-%d %H:%M:%S")
            selected_date = timezone.make_aware(selected_date)
        except Exception:
            pass
    query_date = selected_date.date() if selected_date else timezone.now().date()
    
    if request.method == "POST":
        edit_id = request.POST.get("edit_id")
        
        if edit_id:
            item_id = request.POST.get("item")
            qty = request.POST.get("quantity")
            weight = request.POST.get("weight")
            notes = request.POST.get("notes")
            
            try:
                tx = StockTransaction.objects.get(id=edit_id, transaction_type=TransactionType.PURCHASE_ENTRY)
                tx.item_id = item_id
                tx.quantity = int(qty or 0)
                tx.weight = float(weight or 0.0)
                tx.notes = notes
                tx.save()
                if selected_date:
                    StockTransaction.objects.filter(pk=tx.pk).update(created_at=selected_date)
                messages.success(request, "Purchase entry updated successfully.")
            except Exception as e:
                messages.error(request, f"Error updating purchase entry: {str(e)}")
        else:
            item_ids = request.POST.getlist("item[]")
            quantities = request.POST.getlist("quantity[]")
            weights = request.POST.getlist("weight[]")
            notes_list = request.POST.getlist("notes[]")
            
            count = 0
            for i in range(len(item_ids)):
                it_id = item_ids[i]
                if not it_id:
                    continue
                
                qty = int(quantities[i] or 0)
                wt = float(weights[i] or 0.0)
                notes = notes_list[i] if i < len(notes_list) else ""
                
                tx = StockTransaction.objects.create(
                    item_id=it_id,
                    transaction_type=TransactionType.PURCHASE_ENTRY,
                    quantity=qty,
                    weight=wt,
                    notes=notes or "Purchased semi-ready goods"
                )
                if selected_date:
                    StockTransaction.objects.filter(pk=tx.pk).update(created_at=selected_date)
                count += 1
            messages.success(request, f"Successfully recorded {count} purchase entries.")
            
        redirect_date = query_date.strftime('%Y-%m-%d')
        return redirect(f"/purchases/?date={redirect_date}")
        
    items = Item.objects.all().order_by("name")
    purchase_logs = StockTransaction.objects.filter(
        transaction_type=TransactionType.PURCHASE_ENTRY,
        created_at__date=query_date
    ).select_related("item").order_by("-created_at")
    
    all_entries = StockTransaction.objects.filter(
        transaction_type=TransactionType.PURCHASE_ENTRY
    ).select_related("item").order_by("-created_at")
    
    summary_data = StockTransaction.objects.filter(
        transaction_type=TransactionType.PURCHASE_ENTRY
    ).values("item__code", "item__name").annotate(
        total_pcs=Sum("quantity"),
        total_wt=Sum("weight")
    ).order_by("-total_pcs")
    
    today_stats = purchase_logs.aggregate(total_pcs=Sum("quantity"), total_wt=Sum("weight"))
    today_pcs = today_stats["total_pcs"] or 0
    today_weight = round(today_stats["total_wt"] or 0.0, 3)

    # Calculate live item-level stock for purchased items
    purchased_stock_ledger = []
    active_company = request.company
    company_items = Item.objects.filter(company=active_company) if active_company else Item.objects.all()
    company_items = company_items.order_by("name")

    total_purchased_stock_pcs = 0
    total_purchased_stock_weight = 0.0

    for it in company_items:
        purchased_totals = StockTransaction.objects.filter(
            item=it,
            transaction_type=TransactionType.PURCHASE_ENTRY
        ).aggregate(total_pcs=Sum("quantity"), total_wt=Sum("weight"))

        purchased_in_pcs = purchased_totals["total_pcs"] or 0
        purchased_in_wt = round(purchased_totals["total_wt"] or 0.0, 3)

        if purchased_in_pcs > 0:
            purchase_tx_ids = set(StockTransaction.objects.filter(
                item=it,
                transaction_type=TransactionType.PURCHASE_ENTRY
            ).values_list('id', flat=True))

            packed_from_purchase = 0
            for p_id in purchase_tx_ids:
                packed_from_purchase += StockTransaction.objects.filter(
                    transaction_type="packaging_in",
                    notes__contains=f"PACKED #{p_id}"
                ).aggregate(total=Sum('quantity'))['total'] or 0

            remaining_purchased_pcs = max(0, purchased_in_pcs - packed_from_purchase)
            weight_per_pc = float(it.machining_weight or it.casting_weight or 0.0)
            remaining_purchased_wt = round(remaining_purchased_pcs * weight_per_pc, 3)

            purchased_stock_ledger.append({
                "item_id": it.id,
                "code": it.code,
                "name": it.name,
                "category": it.category or "OTHER",
                "sub_category": it.sub_category or "OTHER",
                "purchased_in_pcs": purchased_in_pcs,
                "purchased_in_wt": purchased_in_wt,
                "current_stock_pcs": remaining_purchased_pcs,
                "current_stock_wt": remaining_purchased_wt,
            })
            total_purchased_stock_pcs += remaining_purchased_pcs
            total_purchased_stock_weight += remaining_purchased_wt

    total_purchased_stock_weight = round(total_purchased_stock_weight, 3)
    
    context = {
        "items": items,
        "purchase_logs": purchase_logs,
        "all_entries": all_entries,
        "summary_data": summary_data,
        "today_pcs": today_pcs,
        "today_weight": today_weight,
        "selected_date": query_date.strftime("%Y-%m-%d"),
        "purchased_stock_ledger": purchased_stock_ledger,
        "total_purchased_stock_pcs": total_purchased_stock_pcs,
        "total_purchased_stock_weight": total_purchased_stock_weight,
    }
    return render(request, "purchases.html", context)



def delete_purchase(request, tx_id):
    from apps.production.models import StockTransaction, TransactionType
    from django.contrib import messages
    try:
        tx = StockTransaction.objects.get(id=tx_id, transaction_type=TransactionType.PURCHASE_ENTRY)
        # Check if any cartons already consumed this purchase entry
        from apps.production.models import StockTransaction as ST
        packed_qty = ST.objects.filter(
            transaction_type="packaging_in",
            notes__contains=f"PACKED #{tx.id}"
        ).exists()
        if packed_qty:
            messages.error(request, "Cannot delete purchase entry because some items from it have already been packed into cartons.")
        else:
            tx.delete()
            messages.success(request, "Purchase entry deleted successfully.")
    except Exception as e:
        messages.error(request, f"Error deleting purchase entry: {str(e)}")
        
    date_str = request.GET.get("date") or ""
    return redirect(f"/purchases/?date={date_str}")


def log_casting_weight(request):
    from django.http import JsonResponse
    if request.method != "POST":
        return JsonResponse({"status": "error", "message": "Method not allowed"}, status=405)
    
    date_str = request.POST.get("date")
    caster_id = request.POST.get("caster_id", "")
    weight_val = request.POST.get("weight", "")
    
    if not date_str:
        return JsonResponse({"status": "error", "message": "Date is required"}, status=400)
    
    try:
        weight = float(weight_val) if weight_val else 0.0
    except ValueError:
        return JsonResponse({"status": "error", "message": "Invalid weight value"}, status=400)
        
    try:
        date_obj = timezone.datetime.strptime(date_str, "%Y-%m-%d")
        date_obj = timezone.make_aware(date_obj)
    except Exception:
        return JsonResponse({"status": "error", "message": "Invalid date format"}, status=400)
        
    w_id = caster_id
    if str(w_id).startswith("jw_"):
        w_id = w_id[3:]
    elif str(w_id).startswith("w_"):
        w_id = w_id[2:]
    worker = get_object_or_404(Worker, id=int(w_id))
    if worker.worker_type == WorkerType.JOB_WORKER:
        job_worker = worker
        
    general_item, _ = Item.objects.get_or_create(
        code="GENERAL",
        defaults={
            "name": "General Casting Weight",
            "category": "OTHER",
            "casting_required": True,
            "company_id": 1
        }
    )
    
    tx_filter = Q(
        transaction_type=TransactionType.CASTING_ENTRY,
        item=general_item,
        created_at__date=date_obj.date()
    )
    if worker:
        tx_filter &= Q(worker=worker)
        
    tx = StockTransaction.objects.filter(tx_filter).first()
    
    if weight == 0.0:
        if tx:
            tx.delete()
        return JsonResponse({"status": "success", "weight": 0.0})
        
    if tx:
        tx.actual_scale_weight = weight
        tx.save()
    else:
        tx = StockTransaction.objects.create(
            transaction_type=TransactionType.CASTING_ENTRY,
            item=general_item,
            worker=worker,
            actual_scale_weight=weight,
            weight=0.0,
            quantity=0,
            heat_no="1"
        )
        tx.created_at = date_obj
        tx.save()
        
    return JsonResponse({"status": "success", "weight": weight})


