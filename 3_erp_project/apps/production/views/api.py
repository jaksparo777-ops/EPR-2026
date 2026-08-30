import calendar
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET, require_POST
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.utils import timezone

from apps.master_data.models import LegalEntity, Client, Warehouse, Item, ItemComposition
from apps.authentication.models import Worker, ProcessType, SalaryModel, WorkerType
from django.db.models import Q
from apps.production.models import StockTransaction, TransactionType, ItemWorkerAllocation, Attendance, Loan, LaborPayment, PaymentType, Carton, CartonItem, Holiday, Notification

from apps.production import services

# =====================================================
# DYNAMIC COMPOSITION & ALLOCATION APIs
# =====================================================

@require_GET
def get_item_composition(request, item_id):
    try:
        item = Item.objects.get(id=item_id)
        compositions = item.components.all()
        data = []
        for comp in compositions:
            stock = services.get_stock_by_item(comp.component_item)
            data.append({
                'id': comp.component_item.id,
                'name': comp.component_item.name,
                'code': comp.component_item.code,
                'quantity': comp.quantity,
                'available': stock['polishing']
            })
        return JsonResponse({
            'name': item.name,
            'code': item.code,
            'category': item.category,
            'sub_category': item.sub_category or '',
            'variant': item.variant or '',
            'material': item.material or '',
            'client_name': item.client.name if item.client else '',
            'casting_required': item.casting_required,
            'machining_required': item.machining_required,
            'polishing_required': item.polishing_required,
            'packing_required': item.packing_required,
            'components': data
        })
    except Item.DoesNotExist:
        return JsonResponse({'error': 'Item not found'}, status=404)

def get_item_workers(request, item_id):
    item = Item.objects.filter(id=item_id).first()
    if not item:
        return JsonResponse({"workers": []})
        
    process_filter = request.GET.get('process')
    
    # Retrieve all allocations matching this item code (cross-company)
    allocations = list(ItemWorkerAllocation.objects.filter(item__code=item.code).select_related('item', 'worker', 'job_worker'))
    
    # Also inherit parent set allocations if this item code is a component of any parent set under the same company
    from apps.master_data.models import ItemComposition
    parent_compositions = ItemComposition.objects.filter(component_item__code=item.code, parent_item__company=item.company)
    for comp in parent_compositions:
        parent_allocs = ItemWorkerAllocation.objects.filter(item__code=comp.parent_item.code).select_related('item', 'worker', 'job_worker')
        allocations.extend(list(parent_allocs))
    
    performers = []
    seen_ids = set()
    for alloc in allocations:
        if alloc.worker:
            w_id = f"w_{alloc.worker.id}"
            if w_id in seen_ids:
                continue
            if process_filter and alloc.worker.process != process_filter:
                continue
            performers.append({
                "id": w_id,
                "name": alloc.worker.name,
                "process": alloc.worker.process,
                "type": "Internal",
                "rate": alloc.rate_per_piece
            })
            seen_ids.add(w_id)
        if alloc.job_worker:
            jw_id = f"jw_{alloc.job_worker.id}"
            if jw_id in seen_ids:
                continue
            if process_filter and alloc.job_worker.process != process_filter:
                continue
            performers.append({
                "id": jw_id,
                "name": alloc.job_worker.name,
                "process": alloc.job_worker.process,
                "type": "External",
                "rate": alloc.rate_per_piece
            })
            seen_ids.add(jw_id)
    return JsonResponse({"workers": performers})
    
def get_worker_items(request, worker_id):
    # Resolve company
    company = request.company
    
    process = None
    if worker_id.startswith('w_'):
        wid = worker_id.replace('w_', '')
        allocations = ItemWorkerAllocation.objects.filter(worker_id=wid).select_related('item')
        w = Worker.objects.filter(id=wid).first()
        if w: process = w.process
    else:
        jwid = worker_id.replace('jw_', '')
        allocations = ItemWorkerAllocation.objects.filter(worker_id=jwid).select_related('item')
        jw = Worker.objects.filter(id=jwid, worker_type=WorkerType.JOB_WORKER).first()
        if jw: process = jw.process
    
    # Resolve to company items by code
    company_items = {}
    if company:
        company_items = {it.code: it for it in Item.objects.filter(company=company)}
    else:
        # Fallback
        company_items = {it.code: it for it in Item.objects.all()}
        
    items = []
    seen_item_ids = set()
    for alloc in allocations:
        # Resolve to active company equivalent item
        resolved_item = company_items.get(alloc.item.code, alloc.item)
        
        # Filter by process requirements
        if process == 'machining' and not resolved_item.machining_required:
            continue
        if process == 'polishing' and not resolved_item.polishing_required and resolved_item.item_type != 'SET':
            continue
        
        # If the resolved item is a parent set (has components), include its sub-components
        if resolved_item.components.exists():
            for comp in resolved_item.components.all():
                comp_item = comp.component_item
                if comp_item.id in seen_item_ids:
                    continue
                items.append({
                    "id": comp_item.id,
                    "code": comp_item.code,
                    "name": comp_item.name,
                    "casting_weight": float(comp_item.casting_weight or 0),
                    "machining_weight": float(comp_item.machining_weight or 0),
                    "category": comp_item.category or 'OTHER',
                    "sub_category": comp_item.sub_category or 'OTHER'
                })
                seen_item_ids.add(comp_item.id)
        else:
            if resolved_item.id in seen_item_ids:
                continue
            items.append({
                "id": resolved_item.id,
                "code": resolved_item.code,
                "name": resolved_item.name,
                "casting_weight": float(resolved_item.casting_weight or 0),
                "machining_weight": float(resolved_item.machining_weight or 0),
                "category": resolved_item.category or 'OTHER',
                "sub_category": resolved_item.sub_category or 'OTHER'
            })
            seen_item_ids.add(resolved_item.id)
    return JsonResponse({"items": items})

# =====================================================
# LIVE WORKER PROFILE / STATS (AJAX)
# =====================================================

@login_required
@require_GET
@login_required
@require_GET
def get_internal_worker_profile(request, worker_id):
    try:
        worker = get_object_or_404(Worker, id=worker_id)
        
        month_str = request.GET.get('month', '').strip() or timezone.now().strftime('%Y-%m')
        filter_type = request.GET.get('filter_type', 'all')  # 'all', 'work', 'payment'
        
        from apps.production.views.hr_ledger import get_worker_report_data, get_worker_rate_for_date
        
        # Determine date scope
        att_qs = Attendance.objects.filter(worker=worker)
        pay_qs = LaborPayment.objects.filter(worker=worker)
        
        report_data = None
        if month_str not in ['all', 'last_payment']:
            report_data = get_worker_report_data(worker, month_str)
        else:
            report_data = get_worker_report_data(worker, timezone.now().strftime('%Y-%m'))
            
        if month_str == 'all':
            pass
        elif month_str == 'last_payment':
            latest_p = LaborPayment.objects.filter(worker=worker).order_by('-date', '-id').first()
            if latest_p:
                att_qs = att_qs.filter(date__gte=latest_p.date)
                pay_qs = pay_qs.filter(date__gte=latest_p.date)
        else:
            try:
                m_dt = datetime.strptime(month_str, '%Y-%m')
                m_start = m_dt.date().replace(day=1)
                n_days = calendar.monthrange(m_dt.year, m_dt.month)[1]
                m_end = m_dt.date().replace(day=n_days)
                att_qs = att_qs.filter(date__gte=m_start, date__lte=m_end)
                pay_qs = pay_qs.filter(
                    Q(settlement_period=month_str) |
                    Q(settlement_period__isnull=True, date__gte=m_start, date__lte=m_end) |
                    Q(settlement_period='', date__gte=m_start, date__lte=m_end)
                )
            except Exception:
                pass

        # Build Statement History Ledger
        ledger = []
        
        # 1. Attendance / Wages / Work Entries
        if filter_type in ['all', 'work', 'stock', 'attendance']:
            # Calculate daily rate for attendance ledger
            ref_date = timezone.now().date()
            if month_str not in ['all', 'last_payment']:
                try:
                    ref_dt = datetime.strptime(month_str, '%Y-%m')
                    ref_n_days = calendar.monthrange(ref_dt.year, ref_dt.month)[1]
                    ref_date = ref_dt.date().replace(day=ref_n_days)
                except Exception:
                    pass
            
            rates = get_worker_rate_for_date(worker, ref_date)
            w_daily_rate = rates['daily_rate']
            w_fixed_salary = rates['monthly_fixed_salary']
            w_ot_rate = rates['overtime_rate']
            
            att_records = att_qs.order_by('-date')[:150]
            for a in att_records:
                day_earned = 0.0
                desc_parts = [f"Attendance: {a.get_status_display()}"]
                
                if worker.salary_model == 'DAILY':
                    if a.status == 'PRESENT':
                        day_earned += w_daily_rate
                    elif a.status == 'HALF_DAY':
                        day_earned += (w_daily_rate * 0.5)
                elif worker.salary_model == 'FIXED':
                    calc_mode = getattr(worker, 'fixed_salary_calc_mode', 'PRO_RATA')
                    if calc_mode != 'FIXED_FULL':
                        # Dynamic pro-rata daily deduction
                        net_days = 26
                        if report_data and report_data.get('stats', {}).get('working_days'):
                            net_days = report_data['stats']['working_days']
                        daily_wage = (w_fixed_salary / net_days) if net_days > 0 else (w_fixed_salary / 30.0)
                        if a.status == 'PRESENT':
                            day_earned += daily_wage
                        elif a.status == 'HALF_DAY':
                            day_earned += (daily_wage * 0.5)
                
                if a.overtime_hours > 0:
                    ot_pay = float(a.overtime_hours) * float(w_ot_rate)
                    day_earned += ot_pay
                    desc_parts.append(f"OT: +{a.overtime_hours}h")
                
                if a.notes:
                    desc_parts.append(f"({a.notes})")
                
                ledger.append({
                    'id': a.id,
                    'date': a.date.strftime('%Y-%m-%d'),
                    'type': 'ATTENDANCE',
                    'description': " | ".join(desc_parts),
                    'qty': 1,
                    'earned': round(day_earned, 2),
                    'paid': 0,
                    'status': a.get_status_display(),
                    'raw_status': a.status,
                    'ot': a.overtime_hours
                })
            
            # Casting work if casting rate is defined
            if worker.casting_rate_per_kg > 0:
                c_qs = StockTransaction.objects.filter(
                    worker=worker,
                    transaction_type=TransactionType.CASTING_ENTRY
                )
                if month_str not in ['all', 'last_payment']:
                    try:
                        c_qs = c_qs.filter(created_at__date__gte=m_start, created_at__date__lte=m_end)
                    except Exception:
                        pass
                elif month_str == 'last_payment' and latest_p:
                    c_qs = c_qs.filter(created_at__date__gte=latest_p.date)
                    
                for tx in c_qs.order_by('-created_at')[:100]:
                    wt = tx.actual_scale_weight if tx.actual_scale_weight > 0 else tx.weight
                    c_val = wt * float(worker.casting_rate_per_kg)
                    ledger.append({
                        'id': tx.id,
                        'date': tx.created_at.strftime('%Y-%m-%d'),
                        'type': 'STOCK',
                        'description': f"Casting Work - {tx.item.name or tx.item.code} ({wt:.1f} kg @ ₹{float(worker.casting_rate_per_kg)}/kg)",
                        'qty': wt,
                        'earned': round(c_val, 2),
                        'paid': 0,
                        'is_inward': True,
                        'has_rate': True
                    })
            
            # Fixed Salary Full & Monthly Allowance entries when in month view
            if month_str not in ['all', 'last_payment']:
                if worker.salary_model == 'FIXED' and getattr(worker, 'fixed_salary_calc_mode', 'PRO_RATA') == 'FIXED_FULL':
                    ledger.append({
                        'id': 0,
                        'date': m_end.strftime('%Y-%m-%d'),
                        'type': 'SALARY',
                        'description': f"Monthly Fixed Salary ({m_dt.strftime('%B %Y')})",
                        'qty': 1,
                        'earned': round(float(w_fixed_salary), 2),
                        'paid': 0
                    })
                if report_data and report_data.get('stats', {}).get('monthly_allowance', 0) > 0:
                    ledger.append({
                        'id': 0,
                        'date': m_end.strftime('%Y-%m-%d'),
                        'type': 'ALLOWANCE',
                        'description': f"Monthly Allowance ({m_dt.strftime('%B %Y')})",
                        'qty': 1,
                        'earned': round(float(report_data['stats']['monthly_allowance']), 2),
                        'paid': 0
                    })

        # 2. Payment Entries
        if filter_type in ['all', 'payment']:
            payments = pay_qs.order_by('-date')[:150]
            for p in payments:
                desc = f"Payment: {p.get_payment_type_display()} ({p.payment_mode})"
                if p.notes:
                    desc += f" - {p.notes}"
                ledger.append({
                    'id': p.id,
                    'date': p.date.strftime('%Y-%m-%d'),
                    'type': 'PAYMENT',
                    'description': desc,
                    'payment_type': p.payment_type,
                    'payment_mode': p.payment_mode,
                    'raw_date': p.date.strftime('%Y-%m-%d'),
                    'raw_type': p.payment_type,
                    'amount': p.amount,
                    'qty': 0,
                    'earned': 0,
                    'paid': p.amount
                })

        ledger.sort(key=lambda x: (x['date'], x.get('id') or 0), reverse=True)

        # Monthly Stats
        all_att = Attendance.objects.filter(worker=worker)
        if month_str not in ['all', 'last_payment']:
            try:
                all_att = all_att.filter(date__gte=m_start, date__lte=m_end)
            except Exception:
                pass
        elif month_str == 'last_payment' and latest_p:
            all_att = all_att.filter(date__gte=latest_p.date)
            
        days_present = all_att.filter(status='PRESENT').count()
        days_half = all_att.filter(status='HALF_DAY').count()
        days_absent = all_att.filter(status='ABSENT').count()
        total_ot = sum(a.overtime_hours for a in all_att)
        
        stats_earned = report_data['total_earned'] if report_data else sum(x['earned'] for x in ledger)
        stats_paid = report_data['total_paid'] if report_data else sum(x['paid'] for x in ledger)
        stats_bal = report_data['balance'] if report_data else max(0.0, stats_earned - stats_paid)

        # Recent raw payments list for backwards compatibility
        raw_payments = [
            {
                'id': p.id,
                'date': p.date.strftime('%d %b, %Y'),
                'raw_date': p.date.strftime('%Y-%m-%d'),
                'amount': p.amount,
                'mode': p.payment_mode,
                'type': p.get_payment_type_display(),
                'raw_type': p.payment_type
            } for p in pay_qs.order_by('-date')[:30]
        ]

        m_dt_obj = datetime.now()
        if month_str not in ['all', 'last_payment']:
            try:
                m_dt_obj = datetime.strptime(month_str, '%Y-%m')
            except Exception:
                pass

        return JsonResponse({
            'id': worker.id,
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
            'month': m_dt_obj.month,
            'year': m_dt_obj.year,
            'month_num': m_dt_obj.month,
            'year_num': m_dt_obj.year,
            'month_str': month_str,
            'month_name': report_data.get('month_name', m_dt_obj.strftime('%B %Y')) if report_data else m_dt_obj.strftime('%B %Y'),
            'month_val': month_str if month_str not in ['all', 'last_payment'] else timezone.now().strftime('%Y-%m'),
            'stats': {
                'present': days_present,
                'half': days_half,
                'absent': days_absent,
                'ot': total_ot,
                'earned': round(stats_earned, 2),
                'paid': round(stats_paid, 2),
                'balance': round(stats_bal, 2),
                'loan_balance': report_data.get('stats', {}).get('loan_balance', 0) if report_data else 0
            },
            'attendance': [
                {
                    'date': a.date.strftime('%d %b, %Y'),
                    'raw_date': a.date.strftime('%Y-%m-%d'),
                    'status': a.get_status_display(),
                    'raw_status': a.status,
                    'ot': a.overtime_hours,
                    'notes': a.notes
                } for a in all_att.order_by('-date')
            ],
            'calendar_weeks': report_data.get('calendar_weeks') if report_data else None,
            'payments': raw_payments,
            'ledger': ledger[:250]
        })
    except Worker.DoesNotExist:
        return JsonResponse({'error': 'Worker not found'}, status=404)


@login_required
@require_GET
def get_job_worker_profile(request, jw_id):
    try:
        jw = Worker.objects.get(id=jw_id, worker_type=WorkerType.JOB_WORKER)
        allocations = ItemWorkerAllocation.objects.filter(worker=jw).select_related('item')
        
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

        # 2. Monthly Report Data & Scope Filtering
        month_str = request.GET.get('month', timezone.now().strftime('%Y-%m'))
        filter_type = request.GET.get('filter_type', 'all')  # 'all', 'stock', 'payment'
        
        from apps.production.views.hr_ledger import get_job_worker_report_data
        report_data = get_job_worker_report_data(jw, month_str)

        import calendar
        tx_qs = StockTransaction.objects.filter(worker=jw)
        pay_qs = LaborPayment.objects.filter(worker=jw)

        if month_str == 'all':
            pass
        elif month_str == 'last_payment':
            latest_p = LaborPayment.objects.filter(worker=jw).order_by('-date', '-id').first()
            if latest_p:
                tx_qs = tx_qs.filter(created_at__date__gte=latest_p.date)
                pay_qs = pay_qs.filter(date__gte=latest_p.date)
        else:
            try:
                m_dt = datetime.strptime(month_str, '%Y-%m')
                m_start = m_dt.date().replace(day=1)
                n_days = calendar.monthrange(m_dt.year, m_dt.month)[1]
                m_end = m_dt.date().replace(day=n_days)
                tx_qs = tx_qs.filter(created_at__date__gte=m_start, created_at__date__lte=m_end)
                pay_qs = pay_qs.filter(date__gte=m_start, date__lte=m_end)
            except Exception:
                pass

        ledger = []

        if filter_type in ['all', 'stock']:
            transactions = tx_qs.order_by('-created_at')[:150]
            for tx in transactions:
                val = 0
                has_rate = True
                is_inward = tx.transaction_type in ['machining_in', 'polishing_in', 'packaging_in']
                if is_inward:
                    is_conv = tx.item.is_raw_material and tx.item.derived_items.exists()
                    if is_conv:
                        val = 0.0
                        has_rate = True
                    else:
                        alloc = allocations.filter(item__code=tx.item.code).first()
                        rate = float(alloc.rate_per_piece) if alloc else 0.0
                        if not rate and (tx.item.item_type == 'SET' or tx.item.components.exists()):
                            comp_sum = 0.0
                            has_comp_alloc = False
                            for comp in tx.item.components.all():
                                c_alloc = allocations.filter(item=comp.component_item).first()
                                if c_alloc:
                                    comp_sum += comp.quantity * float(c_alloc.rate_per_piece)
                                    has_comp_alloc = True
                            if has_comp_alloc:
                                rate = comp_sum

                        if alloc or rate > 0:
                            val = float(tx.quantity) * rate
                            has_rate = True
                        else:
                            has_rate = False
                
                ledger.append({
                    'id': tx.id,
                    'date': tx.created_at.strftime('%Y-%m-%d'),
                    'type': 'STOCK',
                    'description': f"{tx.get_transaction_type_display()} - {tx.item.code}",
                    'qty': tx.quantity,
                    'earned': val,
                    'paid': 0,
                    'is_inward': is_inward,
                    'has_rate': has_rate,
                    'is_raw_material': tx.item.is_raw_material and tx.item.derived_items.exists()
                })

        if filter_type in ['all', 'payment']:
            payments = pay_qs.order_by('-date')[:100]
            for p in payments:
                ledger.append({
                    'id': p.id,
                    'date': p.date.strftime('%Y-%m-%d'),
                    'type': 'PAYMENT',
                    'description': f"Payment: {p.get_payment_type_display()} ({p.payment_mode})",
                    'payment_type': p.payment_type,
                    'payment_mode': p.payment_mode,
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
            'ledger': ledger[:200],
            'calendar_weeks': report_data['calendar_weeks'] if jw.process == 'casting' else None,
            'total_earned': report_data['total_earned'],
            'total_paid': report_data['total_paid'],
            'balance': report_data['balance'],
            'month_name': report_data['month_name'],
            'month_val': report_data['month_val'],
            'total_casting_wt': report_data['total_casting_wt'],
            'loan_balance': report_data['loan_balance'],
        }
        return JsonResponse(data)
    except Worker.DoesNotExist:
        return JsonResponse({'error': 'Job Worker not found'}, status=404)

# =====================================================
# ALLOCATION & ATTENDANCE ACTION CODES
# =====================================================

@staff_member_required
@require_POST
def add_worker_allocation(request):
    try:
        import json
        worker_id_str = request.POST.get('worker_id')
        allocations_json = request.POST.get('allocations')
        
        if not worker_id_str:
            return JsonResponse({'error': 'Worker ID is missing.'}, status=400)
            
        alloc_list = []
        if allocations_json:
            alloc_list = json.loads(allocations_json)
        else:
            item_id = request.POST.get('item_id')
            rate = request.POST.get('rate')
            if item_id and rate is not None and rate != '':
                alloc_list.append({'item_id': item_id, 'rate': rate})

        if not alloc_list:
            return JsonResponse({'error': 'Please select at least one Item and enter a valid rate.'}, status=400)

        saved_count = 0
        for alloc in alloc_list:
            item_id = alloc.get('item_id')
            rate = alloc.get('rate')
            if not item_id or rate is None or rate == '':
                continue
                
            item = Item.objects.get(id=item_id)
            
            if worker_id_str.startswith('w_'):
                internal_id = worker_id_str.replace('w_', '')
                existing = ItemWorkerAllocation.objects.filter(item=item, worker_id=internal_id).first()
                if existing:
                    existing.rate_per_piece = rate
                    existing.save()
                else:
                    ItemWorkerAllocation.objects.create(item=item, worker_id=internal_id, rate_per_piece=rate)
                saved_count += 1
            elif worker_id_str.startswith('jw_'):
                jw_id = worker_id_str.replace('jw_', '')
                existing = ItemWorkerAllocation.objects.filter(item=item, job_worker_id=jw_id).first()
                if existing:
                    existing.rate_per_piece = rate
                    existing.save()
                else:
                    ItemWorkerAllocation.objects.create(item=item, job_worker_id=jw_id, rate_per_piece=rate)
                saved_count += 1

        return JsonResponse({'status': 'success', 'saved_count': saved_count})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@staff_member_required
@require_POST
def edit_matrix_cell(request):
    if not (request.user.is_superuser or request.user.is_staff):
        return JsonResponse({'error': 'Permission denied. Only Owner/Admin can adjust matrix entries.'}, status=403)
        
    try:
        from datetime import datetime
        from django.utils import timezone
        jw_id = request.POST.get('job_worker_id')
        date_str = request.POST.get('date') # YYYY-MM-DD
        item_id = request.POST.get('item_id')
        new_qty_str = request.POST.get('new_qty')
        reason_code = request.POST.get('reason_code', 'typo') # 'typo', 'rejection', 'return_wip'
        
        if not jw_id or not date_str or not item_id or new_qty_str is None:
            return JsonResponse({'error': 'Missing required fields.'}, status=400)
            
        new_qty = int(float(new_qty_str))
        if new_qty < 0:
            return JsonResponse({'error': 'Quantity cannot be negative.'}, status=400)
            
        entry_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        date_start = timezone.make_aware(datetime.combine(entry_date, datetime.min.time()))
        date_end = timezone.make_aware(datetime.combine(entry_date, datetime.max.time()))

        jw = Worker.objects.get(id=jw_id, worker_type=WorkerType.JOB_WORKER)
        item = Item.objects.get(id=item_id)
        
        # Determine likely receive transaction type based on worker process
        default_tx_type = TransactionType.POLISHING_IN
        if jw.process == 'machining':
            default_tx_type = TransactionType.MACHINING_IN
        elif jw.process == 'casting':
            default_tx_type = TransactionType.CASTING_ENTRY
        elif jw.process == 'packaging':
            default_tx_type = TransactionType.PACKAGING_IN

        # Find receive transaction(s) for this worker, item, date range
        receive_types = [
            TransactionType.MACHINING_IN,
            TransactionType.POLISHING_IN,
            TransactionType.PACKAGING_IN,
            TransactionType.CASTING_ENTRY
        ]
        
        txs = StockTransaction.objects.filter(
            worker=jw,
            item=item,
            created_at__range=(date_start, date_end),
            transaction_type__in=receive_types
        )
        
        old_qty = sum(t.quantity or 0 for t in txs)
        delta = new_qty - old_qty
        
        if txs.exists():
            primary_tx = txs.first()
            primary_tx.quantity = new_qty
            primary_tx.notes = f"Owner adjusted from {old_qty} to {new_qty} (Reason: {reason_code})"
            
            # Handle difference based on reason code
            if delta < 0:
                diff = abs(delta)
                if reason_code == 'rejection':
                    primary_tx.rejection_quantity = (primary_tx.rejection_quantity or 0) + diff
                elif reason_code in ['typo', 'return_wip']:
                    # Adjust corresponding issue transactions so worker stock-in-hand balance reduces cleanly
                    issue_txs = StockTransaction.objects.filter(
                        worker=jw,
                        item=item,
                        transaction_type__endswith='_out'
                    ).order_by('-created_at')
                    
                    rem = diff
                    for itx in issue_txs:
                        if rem <= 0:
                            break
                        if itx.quantity >= rem:
                            itx.quantity -= rem
                            rem = 0
                            itx.save()
                        else:
                            rem -= itx.quantity
                            itx.quantity = 0
                            itx.save()
            primary_tx.save()
            txs.exclude(id=primary_tx.id).delete()
        else:
            primary_tx = StockTransaction.objects.create(
                worker=jw,
                item=item,
                created_at=date_start,
                quantity=new_qty,
                transaction_type=default_tx_type,
                notes=f"Owner manual entry ({reason_code})"
            )
            
        return JsonResponse({'status': 'success', 'old_qty': old_qty, 'new_qty': new_qty, 'delta': delta})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@staff_member_required
@require_POST
def update_worker_allocation_rate(request, alloc_id):
    if not (request.user.is_superuser or request.user.is_staff):
        return JsonResponse({'error': 'Permission denied. Only Owner/Superuser can update rates.'}, status=403)
    try:
        alloc = get_object_or_404(ItemWorkerAllocation, id=alloc_id)
        rate_str = request.POST.get('rate')
        if rate_str is None or rate_str == '':
            return JsonResponse({'error': 'Rate is required.'}, status=400)
        rate = float(rate_str)
        if rate < 0:
            return JsonResponse({'error': 'Rate cannot be negative.'}, status=400)
        alloc.rate_per_piece = rate
        alloc.save()
        return JsonResponse({'status': 'success', 'rate': alloc.rate_per_piece})
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

@login_required
@require_POST
def mark_attendance(request):
    try:
        worker_id = request.POST.get('worker_id')
        status = request.POST.get('status', 'PRESENT')
        date_str = request.POST.get('date', timezone.now().date())
        ot_hours = float(request.POST.get('ot_hours', 0) or 0)
        
        worker = Worker.objects.get(id=worker_id)
        if status == 'NONE' or not status:
            Attendance.objects.filter(worker=worker, date=date_str).delete()
        else:
            Attendance.objects.update_or_create(
                worker=worker,
                date=date_str,
                defaults={'status': status, 'overtime_hours': ot_hours}
            )
        return JsonResponse({'status': 'success'})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

@login_required
@require_POST
def mark_all_attendance(request):
    try:
        from django.db import transaction as db_transaction
        date_str = request.POST.get('date', timezone.now().date())
        status = request.POST.get('status', 'PRESENT')
        
        active_company = request.company
        if active_company:
            workers = Worker.objects.filter(company=active_company, active=True, worker_type='IN_HOUSE')
        else:
            workers = Worker.objects.filter(active=True, worker_type='IN_HOUSE')
            
        saved_count = 0
        with db_transaction.atomic():
            for worker in workers:
                Attendance.objects.update_or_create(
                    worker=worker,
                    date=date_str,
                    defaults={'status': status, 'overtime_hours': 0.0}
                )
                saved_count += 1
                
        return JsonResponse({'status': 'success', 'saved_count': saved_count})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

@login_required
@require_GET
def get_attendance_for_date(request):
    date_str = request.GET.get('date')
    if not date_str:
        return JsonResponse({'error': 'Date is required'}, status=400)
    
    try:
        from datetime import datetime
        dt = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return JsonResponse({'error': 'Invalid date format'}, status=400)

    active_company = request.company
    if active_company:
        workers_qs = Worker.objects.filter(company=active_company, active=True, worker_type='IN_HOUSE')
        holiday = Holiday.objects.filter(date=dt).filter(Q(company=active_company) | Q(company__isnull=True)).first()
    else:
        workers_qs = Worker.objects.filter(active=True, worker_type='IN_HOUSE')
        holiday = Holiday.objects.filter(date=dt).first()

    records = Attendance.objects.filter(date=date_str, worker__worker_type='IN_HOUSE')
    if active_company:
        records = records.filter(worker__company=active_company)

    data = {
        str(r.worker.id): {
            'status': r.status,
            'ot': r.overtime_hours
        } for r in records
    }

    total_workers = workers_qs.count()
    marked_count = len(data)
    is_saved = marked_count > 0

    holiday_data = None
    if holiday:
        if not holiday.is_working_day_override:
            holiday_data = {
                'name': holiday.name,
                'is_paid': holiday.is_paid
            }
    elif active_company and active_company.weekly_off == dt.weekday():
        holiday_data = {
            'name': "Weekly Off",
            'is_paid': active_company.is_weekly_off_paid
        }

    return JsonResponse({
        'attendance': data,
        'holiday': holiday_data,
        'is_saved': is_saved,
        'marked_count': marked_count,
        'total_workers': total_workers
    })

from datetime import datetime
from django.contrib import messages

@login_required
def get_recipient_dues_api(request):
    try:
        target_id = request.GET.get('target_id', '')
        month_str = request.GET.get('month', '') or timezone.now().strftime('%Y-%m')
        
        monthly_due = 0.0
        running_due = 0.0
        recipient_name = ""
        
        from .hr_ledger import get_job_worker_report_data, get_worker_report_data
        
        if target_id.startswith('jw_'):
            jwid = target_id.replace('jw_', '')
            jw = Worker.objects.filter(id=jwid, worker_type=WorkerType.JOB_WORKER).first()
            if jw:
                recipient_name = jw.name
                m_data = get_job_worker_report_data(jw, month_str)
                monthly_due = max(0.0, float(m_data.get('balance', 0.0)))
                
                r_data = get_job_worker_report_data(jw, 'SINCE_LAST')
                running_due = max(0.0, float(r_data.get('balance', 0.0)))
        elif target_id.startswith('w_'):
            wid = target_id.replace('w_', '')
            w = Worker.objects.filter(id=wid).first()
            if w:
                recipient_name = w.name
                m_data = get_worker_report_data(w, month_str)
                m_stats = m_data.get('stats', {}) if isinstance(m_data, dict) else {}
                monthly_due = max(0.0, float(m_stats.get('balance', m_data.get('balance', 0.0))))
                
                r_data = get_worker_report_data(w, 'SINCE_LAST')
                r_stats = r_data.get('stats', {}) if isinstance(r_data, dict) else {}
                running_due = max(0.0, float(r_stats.get('balance', r_data.get('balance', 0.0))))
                
        return JsonResponse({
            'status': 'success',
            'monthly_due': round(monthly_due),
            'running_due': round(running_due),
            'recipient_name': recipient_name
        })
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)


@staff_member_required
@require_POST
@login_required
def record_labor_payment(request):
    try:
        target_id = request.POST.get('target_id') # e.g. w_5 or jw_3
        amount = request.POST.get('amount')
        p_type = request.POST.get('payment_type', 'ADVANCE')
        date_str = request.POST.get('date')
        settlement_scope = request.POST.get('settlement_scope', 'MONTHLY')
        
        enable_loan_deduct = request.POST.get('enable_loan_deduct')
        loan_cut_val = request.POST.get('loan_deduction_amount', '0')
        try:
            loan_cut = float(loan_cut_val) if (enable_loan_deduct and loan_cut_val and loan_cut_val.strip()) else 0.0
        except ValueError:
            loan_cut = 0.0

        total_amount = float(amount)
        if loan_cut > 0 and loan_cut < total_amount:
            cash_amount = total_amount - loan_cut
        else:
            cash_amount = total_amount
            loan_cut = 0.0

        settlement_period = request.POST.get('settlement_period')
        sp_val = settlement_period.strip() if (settlement_scope == 'MONTHLY' and settlement_period and settlement_period.strip()) else None

        payment_data = {
            'amount': cash_amount,
            'payment_type': p_type,
            'payment_mode': request.POST.get('payment_mode', 'CASH'),
            'notes': request.POST.get('notes', ''),
            'settlement_period': sp_val
        }

        if date_str and date_str.strip():
            ds = date_str.strip()
            parsed_date = None
            for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y', '%d-%m-%Y'):
                try:
                    parsed_date = datetime.strptime(ds, fmt).date()
                    break
                except ValueError:
                    pass
            if parsed_date:
                payment_data['date'] = parsed_date

        issued_date_val = payment_data.get('date', timezone.now().date())
        recipient_name = "Worker"
        
        if target_id.startswith('w_'):
            wid = target_id.replace('w_', '')
            payment_data['worker_id'] = wid
            w_obj = Worker.objects.filter(id=wid).first()
            if w_obj:
                recipient_name = w_obj.name
            
            if p_type == 'LOAN_REPAYMENT':
                loan = Loan.objects.filter(worker_id=wid, is_active=True).first()
                if loan:
                    loan.remaining_balance -= float(amount)
                    if loan.remaining_balance <= 0:
                        loan.remaining_balance = 0
                        loan.is_active = False
                    loan.save()
            elif p_type == 'NEW_LOAN':
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
                    remaining_balance=float(amount),
                    issued_date=issued_date_val
                )
            elif loan_cut > 0:
                loan = Loan.objects.filter(worker_id=wid, is_active=True).first()
                if loan:
                    loan.remaining_balance -= loan_cut
                    if loan.remaining_balance <= 0:
                        loan.remaining_balance = 0
                        loan.is_active = False
                    loan.save()
                    
        elif target_id.startswith('jw_'):
            jwid = target_id.replace('jw_', '')
            payment_data['worker_id'] = jwid
            jw_obj = Worker.objects.filter(id=jwid, worker_type=WorkerType.JOB_WORKER).first()
            if jw_obj:
                recipient_name = jw_obj.name
            
            if p_type == 'LOAN_REPAYMENT':
                loan = Loan.objects.filter(worker_id=jwid, is_active=True).first()
                if loan:
                    loan.remaining_balance -= float(amount)
                    if loan.remaining_balance <= 0:
                        loan.remaining_balance = 0
                        loan.is_active = False
                    loan.save()
            elif p_type == 'NEW_LOAN':
                Loan.objects.filter(worker_id=jwid, is_active=True).update(is_active=False)
                
                emi_val = request.POST.get('emi_amount', '0')
                try:
                    emi_amount = float(emi_val) if emi_val.strip() else 0
                except ValueError:
                    emi_amount = 0

                Loan.objects.create(
                    worker_id=jwid,
                    total_amount=float(amount),
                    emi_amount=emi_amount,
                    remaining_balance=float(amount),
                    issued_date=issued_date_val
                )
            elif loan_cut > 0:
                loan = Loan.objects.filter(worker_id=jwid, is_active=True).first()
                if loan:
                    loan.remaining_balance -= loan_cut
                    if loan.remaining_balance <= 0:
                        loan.remaining_balance = 0
                        loan.is_active = False
                    loan.save()
            
        LaborPayment.objects.create(**payment_data)

        if loan_cut > 0:
            loan_pay_data = payment_data.copy()
            loan_pay_data['amount'] = loan_cut
            loan_pay_data['payment_type'] = 'LOAN_REPAYMENT'
            base_notes = payment_data.get('notes', '')
            loan_pay_data['notes'] = f"Loan recovery deducted from settlement (Ref: {base_notes})".strip()
            LaborPayment.objects.create(**loan_pay_data)

        try:
            p_type_display = dict(PaymentType.choices).get(p_type, p_type)
            if loan_cut > 0:
                messages.success(request, f"Recorded settlement for {recipient_name}: ₹{cash_amount:,.2f} Cash/Bank + ₹{loan_cut:,.2f} Loan Repayment (Total: ₹{total_amount:,.2f}).")
            else:
                messages.success(request, f"Recorded {p_type_display} transaction of ₹{float(amount):,.2f} for {recipient_name} successfully.")
        except Exception:
            pass
        return JsonResponse({'status': 'success'})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@staff_member_required
@require_POST
def delete_labor_payment(request, payment_id):
    try:
        p = get_object_or_404(LaborPayment, id=payment_id)
        recipient_name = p.worker.name if p.worker else "Worker"
        amt = p.amount
        p_type = p.payment_type
        worker_ref = p.worker
        
        if p_type == 'NEW_LOAN' and worker_ref:
            Loan.objects.filter(worker=worker_ref, total_amount=amt).update(is_active=False)
                
        p.delete()

        if worker_ref:
            for loan in Loan.objects.filter(worker=worker_ref):
                loan.recalculate_balance()

        try:
            messages.success(request, f"Deleted payment entry of ₹{amt:,.2f} for {recipient_name} successfully.")
        except Exception:
            pass
        return JsonResponse({'status': 'success'})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@staff_member_required
@require_POST
def edit_labor_payment(request, payment_id):
    try:
        p = get_object_or_404(LaborPayment, id=payment_id)
        amount_str = request.POST.get('amount')
        date_str = request.POST.get('date')
        p_type = request.POST.get('payment_type')
        p_mode = request.POST.get('payment_mode')
        notes = request.POST.get('notes', '')

        if amount_str:
            p.amount = float(amount_str)
        if date_str and date_str.strip():
            try:
                p.date = datetime.strptime(date_str.strip(), '%Y-%m-%d').date()
            except ValueError:
                pass
        if p_type:
            p.payment_type = p_type
        if p_mode:
            p.payment_mode = p_mode
        p.notes = notes
        p.save()

        if p.worker:
            for loan in Loan.objects.filter(worker=p.worker):
                loan.recalculate_balance()

        recipient_name = p.worker.name if p.worker else "Worker"
        try:
            messages.success(request, f"Updated payment transaction for {recipient_name} successfully.")
        except Exception:
            pass
        return JsonResponse({'status': 'success'})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@staff_member_required
@require_POST
def delete_stock_transaction_api(request, tx_id):
    try:
        tx = get_object_or_404(StockTransaction, id=tx_id)
        item_code = tx.item.code if tx.item else ''
        
        # If it has linked consumption/receipts (e.g. in polishing/machining), delete linked as well
        if hasattr(tx, 'linked_consumption') and tx.linked_consumption:
            tx.linked_consumption.delete()
        if hasattr(tx, 'linked_receipt') and tx.linked_receipt:
            tx.linked_receipt.delete()
            
        tx.delete()
        try:
            messages.success(request, f"Deleted stock transaction ({item_code}) successfully.")
        except Exception:
            pass
        return JsonResponse({'status': 'success'})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@staff_member_required
@require_POST
def bulk_delete_stock_transactions_api(request):
    """
    Deletes multiple stock transactions or payment records in a single atomic database transaction.
    Restores inventory balances automatically.
    """
    try:
        import json
        data = json.loads(request.body)
        items_to_delete = data.get('items', []) # List of {id: 123, type: 'TX'|'PAYMENT'}
        
        if not items_to_delete:
            return JsonResponse({'error': 'No items selected for deletion'}, status=400)

        from django.db import transaction as db_transaction
        deleted_count = 0
        
        with db_transaction.atomic():
            for item in items_to_delete:
                entry_id = item.get('id')
                entry_type = item.get('type', 'TX')
                
                if entry_type == 'PAYMENT':
                    p_obj = LaborPayment.objects.filter(id=entry_id).first()
                    if p_obj:
                        p_obj.delete()
                        deleted_count += 1
                else:
                    tx_obj = StockTransaction.objects.filter(id=entry_id).first()
                    if tx_obj:
                        if hasattr(tx_obj, 'linked_consumption') and tx_obj.linked_consumption:
                            tx_obj.linked_consumption.delete()
                        if hasattr(tx_obj, 'linked_receipt') and tx_obj.linked_receipt:
                            tx_obj.linked_receipt.delete()
                        tx_obj.delete()
                        deleted_count += 1

        try:
            messages.success(request, f"Successfully deleted {deleted_count} selected record(s). Inventory restocked automatically.")
        except Exception:
            pass
            
        return JsonResponse({
            'status': 'success',
            'deleted_count': deleted_count,
            'message': f'Deleted {deleted_count} record(s) successfully.'
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

@staff_member_required
@require_GET
def get_warehouse_stock(request):
    """
    API endpoint to retrieve the current calculated stock level of a specific item in a specific warehouse stage.
    """
    item_id = request.GET.get('item_id')
    warehouse_code = request.GET.get('warehouse')
    if not item_id or not warehouse_code:
        return JsonResponse({'error': 'Both item_id and warehouse are required'}, status=400)
    
    item = get_object_or_404(Item, id=item_id)
    stock = services.get_stock_by_item(item)
    
    # Map warehouse stage code to the dictionary key in services
    wh_map = {
        'CASTING': 'casting',
        'MACHINING': 'machining',
        'POLISHING': 'polishing',
        'READY': 'ready'
    }
    
    key = wh_map.get(warehouse_code)
    if not key:
        return JsonResponse({'error': 'Invalid warehouse stage code'}, status=400)
        
    qty = stock.get(key, 0)
    return JsonResponse({'qty': qty})

@staff_member_required
@require_GET
def get_all_warehouse_stock(request):
    """
    API endpoint to retrieve calculated stock levels of all items for a specific warehouse stage in a single call.
    """
    warehouse_code = request.GET.get('warehouse')
    if not warehouse_code:
        return JsonResponse({'error': 'warehouse parameter is required'}, status=400)
        
    wh_map = {
        'CASTING': 'casting',
        'MACHINING': 'machining',
        'POLISHING': 'polishing',
        'READY': 'ready'
    }
    key = wh_map.get(warehouse_code)
    if not key:
        return JsonResponse({'error': 'Invalid warehouse stage code'}, status=400)
        
    active_company = request.company
    items = Item.objects.all()
    if active_company:
        items = items.filter(company=active_company)

    if key == 'machining':
        items = items.filter(machining_required=True).exclude(item_type="SET").exclude(components__isnull=False).exclude(is_raw_material=True).distinct()
    elif key == 'polishing':
        items = items.filter(Q(polishing_required=True) | Q(item_type='SET') | Q(components__isnull=False)).distinct()
    elif key == 'casting':
        items = items.filter(casting_required=True).exclude(item_type="SET").exclude(components__isnull=False).distinct()

    results = {}
    for item in items:
        stock = services.get_stock_by_item(item)
        results[item.id] = stock.get(key, 0)

    return JsonResponse({'qtys': results})

@staff_member_required
@require_POST
def adjust_stock(request):
    """
    API endpoint to securely correct/adjust pieces of an item in a specific warehouse.
    Calculates the correction delta, and appends a single STOCK_ADJUSTMENT StockTransaction record.
    Supports single or multiple item adjustments.
    """
    try:
        warehouse_code = request.POST.get('warehouse')
        notes = request.POST.get('notes', '')
        
        # Support both bulk list post and single post
        item_ids = request.POST.getlist('item_id')
        physical_counts = request.POST.getlist('physical_count')
        
        if not item_ids:
            item_id = request.POST.get('item_id')
            if item_id:
                item_ids = [item_id]
                physical_counts = [request.POST.get('physical_count')]

        if not warehouse_code or not item_ids:
            return JsonResponse({'error': 'Warehouse and at least one Item are required'}, status=400)
            
        wh = get_object_or_404(Warehouse, code=warehouse_code)
        
        wh_map = {
            'CASTING': 'casting',
            'MACHINING': 'machining',
            'POLISHING': 'polishing',
            'READY': 'ready'
        }
        key = wh_map.get(warehouse_code)
        
        adjustments_made = 0
        
        for item_id, physical_count_str in zip(item_ids, physical_counts):
            if not item_id or physical_count_str is None or physical_count_str == '':
                continue
                
            item = get_object_or_404(Item, id=item_id)
            
            try:
                physical_count = int(physical_count_str)
            except ValueError:
                return JsonResponse({'error': f"Physical count for item '{item.code}' must be a valid integer"}, status=400)
                
            if physical_count < 0:
                return JsonResponse({'error': f"Physical count for item '{item.code}' cannot be negative"}, status=400)
                
            stock = services.get_stock_by_item(item)
            current_qty = stock.get(key, 0)
            delta = physical_count - current_qty
            
            if delta == 0:
                continue
                
            # Determine weight delta
            weight_per_piece = float(item.machining_weight or item.casting_weight or 0.0)
            weight_delta = round(delta * weight_per_piece, 3)
            
            if delta > 0:
                from_wh = None
                to_wh = wh
                notes_final = f"Inventory Correction (Adjustment +{delta}): {notes}".strip()
            else:
                from_wh = wh
                to_wh = None
                notes_final = f"Inventory Correction (Adjustment {delta}): {notes}".strip()
                
            StockTransaction.objects.create(
                item=item,
                transaction_type=TransactionType.STOCK_ADJUSTMENT,
                from_warehouse=from_wh,
                to_warehouse=to_wh,
                quantity=abs(delta),
                weight=abs(weight_delta),
                notes=notes_final
            )
            adjustments_made += 1
            
        return JsonResponse({
            'status': 'success',
            'message': f"Successfully saved {adjustments_made} audit adjustments in {wh.name}."
        })
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_GET
def get_notifications(request):
    """
    Scans for low stock warnings dynamically, creates/removes corresponding notifications,
    and returns a JSON list of all unread notifications.
    """
    try:
        comp = request.company
        items = Item.objects.filter(company=comp) if comp else Item.objects.all()
        
        # Performance optimized scanning using our services module
        for item in items:
            stocks = services.get_stock_by_item(item)
            stages = [
                ('casting', item.min_casting_stock, 'Casting', '/casting/'),
                ('machining', item.min_machining_stock, 'Machining', '/machining/'),
                ('polishing', item.min_polishing_stock, 'Polishing', '/polishing/'),
                ('ready', item.min_ready_stock, 'Ready Stock', '/packaging/?tab=ready'),
            ]
            for stage_code, min_limit, stage_label, link_url in stages:
                current_qty = stocks.get(stage_code, 0)
                warning_title = f"Low {stage_label} Stock: {item.code}"
                
                # Try finding alert (read or unread)
                existing_alert = Notification.objects.filter(
                    title=warning_title,
                    company=comp
                ).first()
                
                if min_limit > 0 and current_qty < min_limit:
                    message_text = f"Item {item.code} - {item.name} stock in {stage_label} is {current_qty} pcs (Minimum required: {min_limit} pcs)."
                    if not existing_alert:
                        Notification.objects.create(
                            title=warning_title,
                            message=message_text,
                            notification_type='WARNING',
                            link=link_url,
                            company=comp
                        )
                    else:
                        if existing_alert.message != message_text:
                            existing_alert.message = message_text
                            existing_alert.save()
                else:
                    # Clean up / resolve if stock is fine or limit is 0
                    Notification.objects.filter(
                        title=warning_title,
                        company=comp
                    ).delete()

        # Query all unread notifications for this company scope
        notifs = Notification.objects.filter(company=comp, is_read=False) if comp else Notification.objects.filter(is_read=False)
        
        data = []
        for n in notifs:
            data.append({
                'id': n.id,
                'title': n.title,
                'message': n.message,
                'type': n.notification_type,
                'link': n.link or '',
                'created_at': n.created_at.strftime("%d/%m %H:%M")
            })
            
        return JsonResponse({'status': 'success', 'notifications': data})
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_POST
def mark_notification_read(request):
    """
    Marks a single notification as read, or marks all notifications as read.
    """
    try:
        notif_id = request.POST.get('id')
        comp = request.company
        
        if notif_id == 'all':
            qs = Notification.objects.filter(is_read=False)
            if comp:
                qs = qs.filter(company=comp)
            qs.update(is_read=True)
            return JsonResponse({'status': 'success', 'message': 'All notifications cleared.'})
        
        elif notif_id:
            qs = Notification.objects.filter(id=notif_id)
            if comp:
                qs = qs.filter(company=comp)
            notif = qs.first()
            if notif:
                notif.is_read = True
                notif.save()
                return JsonResponse({'status': 'success', 'message': 'Notification cleared.'})
            return JsonResponse({'error': 'Notification not found'}, status=404)
            
        return JsonResponse({'error': 'Missing notification ID'}, status=400)
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
