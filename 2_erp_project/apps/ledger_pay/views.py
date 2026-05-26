import calendar
import json
from datetime import datetime
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from core.security import require_role
from django.db.models import Sum
from django.utils import timezone

from apps.workforce.models import Worker, JobWorker, Attendance
from apps.ledger_pay.models import LaborPayment, Loan, ItemWorkerAllocation
from apps.products.models import Item
from apps.production.models import StockTransaction


@login_required
@require_role(['HR & Accounts Manager', 'System Admin'])
def labor_ledger(request):
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
        transactions = StockTransaction.objects.filter(
            job_worker=jw, 
            transaction_type__in=['machining_in', 'polishing_in', 'packaging_in']
        )
        
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
            date_str = today.replace(day=d).strftime('%Y-%m-%d')
            if record:
                row['days'].append({
                    'day': d,
                    'status': record.status,
                    'ot': record.overtime_hours,
                    'date_str': date_str
                })
            else:
                row['days'].append({
                    'day': d,
                    'status': None,
                    'ot': 0,
                    'date_str': date_str
                })
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


@login_required
@require_role(['HR & Accounts Manager', 'System Admin'])
def worker_monthly_report(request, worker_id):
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
        daily_deduct = worker.monthly_fixed_salary / 30
        earned_wages = worker.monthly_fixed_salary - (days_absent * daily_deduct) + (total_ot * worker.overtime_rate)

    # Add Monthly Allowance
    earned_wages += worker.monthly_allowance

    total_paid = sum(p.amount for p in payments)
    
    # Calendar Logic for the printable report
    first_day_of_month = month_start.weekday() # Monday is 0, Sunday is 6
    first_day_of_month = (first_day_of_month + 1) % 7
    
    calendar_weeks = []
    current_week = [None] * first_day_of_month
    
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


@login_required
@require_role(['HR & Accounts Manager', 'System Admin'])
def job_worker_monthly_report(request, jw_id):
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
    
    item_balances = {}
    for tx in all_jw_tx:
        in_qty = tx.quantity if tx.transaction_type.endswith('_out') else 0
        out_qty = tx.quantity if tx.transaction_type.endswith('_in') else 0
        
        if tx.item_id not in item_balances:
            item_balances[tx.item_id] = 0
        item_balances[tx.item_id] += (in_qty - out_qty)

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
                'bal': 0,
                'earned': 0
            }
        
        if tx.transaction_type.endswith('_out'):
            item_ledger[key]['in'] += tx.quantity
        elif tx.transaction_type.endswith('_in'):
            item_ledger[key]['out'] += tx.quantity
            alloc = ItemWorkerAllocation.objects.filter(job_worker=jw, item=tx.item).first()
            rate = float(alloc.rate_per_piece) if alloc else 0
            item_ledger[key]['earned'] += (tx.quantity * rate)

    sorted_keys = sorted(item_ledger.keys(), key=lambda x: x[1])
    
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


@login_required
@require_role(['HR & Accounts Manager', 'System Admin'])
@require_POST
def add_worker_allocation(request):
    try:
        worker_id_str = request.POST.get('worker_id')
        item_id = request.POST.get('item_id')
        rate = request.POST.get('rate')
        
        if not worker_id_str or not item_id or not rate:
            return JsonResponse({'error': 'Missing data'}, status=400)
            
        item = Item.objects.get(id=item_id)
        
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


@login_required
@require_role(['HR & Accounts Manager', 'System Admin'])
@require_POST
def delete_worker_allocation(request, alloc_id):
    try:
        ItemWorkerAllocation.objects.filter(id=alloc_id).delete()
        return JsonResponse({'status': 'success'})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_role(['HR & Accounts Manager', 'System Admin'])
@require_GET
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


@login_required
@require_role(['HR & Accounts Manager', 'System Admin'])
@require_GET
def get_worker_items(request, worker_id):
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


@login_required
@require_role(['HR & Accounts Manager', 'System Admin'])
@require_POST
def record_labor_payment(request):
    try:
        target_id = request.POST.get('target_id')
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
                loan = Loan.objects.filter(worker_id=wid, is_active=True).first()
                if loan:
                    loan.remaining_balance -= float(amount)
                    if loan.remaining_balance <= 0:
                        loan.remaining_balance = 0
                        loan.is_active = False
                    loan.save()
            elif p_type == 'NEW_LOAN':
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
                loan = Loan.objects.filter(job_worker_id=jwid, is_active=True).first()
                if loan:
                    loan.remaining_balance -= float(amount)
                    if loan.remaining_balance <= 0:
                        loan.remaining_balance = 0
                        loan.is_active = False
                    loan.save()
            elif p_type == 'NEW_LOAN':
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
