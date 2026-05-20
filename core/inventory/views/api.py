from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET, require_POST
from django.contrib.admin.views.decorators import staff_member_required
from django.utils import timezone

from inventory.models import (
    Item,
    ItemWorkerAllocation,
    Worker,
    JobWorker,
    Attendance,
    LaborPayment,
    StockTransaction,
    Loan
)
from inventory import services

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

# =====================================================
# LIVE WORKER PROFILE / STATS (AJAX)
# =====================================================

@staff_member_required
@require_GET
def get_internal_worker_profile(request, worker_id):
    worker = get_object_or_404(Worker, id=worker_id)
    
    # 1. Get Attendance for current month
    now = timezone.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    attendance = Attendance.objects.filter(worker=worker, date__gte=month_start).order_by('-date')
    
    # 2. Get Payments
    payments = LaborPayment.objects.filter(worker=worker).order_by('-date')[:20]
    
    # 3. Calculate Monthly Stats
    days_present = attendance.filter(status='PRESENT').count()
    days_half = attendance.filter(status='HALF_DAY').count()
    days_absent = attendance.filter(status='ABSENT').count()
    total_ot = sum(a.overtime_hours for a in attendance)
    
    # Wage Calculation
    earned_wages = 0
    if worker.salary_model == 'DAILY':
        earned_wages = (days_present * worker.daily_rate) + (days_half * 0.5 * worker.daily_rate)
    elif worker.salary_model == 'FIXED':
        daily_deduct = worker.monthly_fixed_salary / 30
        earned_wages = worker.monthly_fixed_salary - (days_absent * daily_deduct)
    
    # Add Overtime
    earned_wages += (total_ot * worker.overtime_rate)
    
    # Total Paid
    total_paid = sum(p.amount for p in payments)
    
    return JsonResponse({
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
        'month': timezone.now().month,
        'year': timezone.now().year,
        'stats': {
            'present': days_present,
            'half': days_half,
            'absent': days_absent,
            'ot': total_ot,
            'earned': round(earned_wages, 2),
            'paid': round(total_paid, 2),
            'balance': round(earned_wages - total_paid, 2)
        },
        'attendance': [
            {
                'date': a.date.strftime('%d %b, %Y'),
                'raw_date': a.date.strftime('%Y-%m-%d'),
                'status': a.get_status_display(),
                'raw_status': a.status,
                'ot': a.overtime_hours,
                'notes': a.notes
            } for a in attendance
        ],
        'payments': [
            {
                'date': p.date.strftime('%d %b, %Y'),
                'amount': p.amount,
                'mode': p.payment_mode,
                'type': p.get_payment_type_display()
            } for p in payments
        ]
    })

@staff_member_required
@require_GET
def get_job_worker_profile(request, jw_id):
    try:
        jw = JobWorker.objects.get(id=jw_id)
        allocations = ItemWorkerAllocation.objects.filter(job_worker=jw).select_related('item')
        
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

        # 2. Ledger History (Recent)
        transactions = StockTransaction.objects.filter(job_worker=jw).order_by('-created_at')[:30]
        payments = LaborPayment.objects.filter(job_worker=jw).order_by('-date')[:20]
        
        ledger = []
        for tx in transactions:
            val = 0
            has_rate = True
            is_inward = tx.transaction_type in ['machining_in', 'polishing_in', 'packaging_in']
            if is_inward:
                alloc = allocations.filter(item=tx.item).first()
                if alloc:
                    val = float(tx.quantity) * float(alloc.rate_per_piece)
                else:
                    has_rate = False
            
            ledger.append({
                'date': tx.created_at.strftime('%Y-%m-%d'),
                'type': 'STOCK',
                'description': f"{tx.get_transaction_type_display()} - {tx.item.code}",
                'qty': tx.quantity,
                'earned': val,
                'paid': 0,
                'is_inward': is_inward,
                'has_rate': has_rate
            })
            
        for p in payments:
            ledger.append({
                'date': p.date.strftime('%Y-%m-%d'),
                'type': 'PAYMENT',
                'description': f"Payment: {p.get_payment_type_display()} ({p.payment_mode})",
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
            'ledger': ledger[:30]
        }
        return JsonResponse(data)
    except JobWorker.DoesNotExist:
        return JsonResponse({'error': 'Job Worker not found'}, status=404)

# =====================================================
# ALLOCATION & ATTENDANCE ACTION CODES
# =====================================================

@staff_member_required
@require_POST
def add_worker_allocation(request):
    try:
        worker_id_str = request.POST.get('worker_id')
        item_id = request.POST.get('item_id')
        rate = request.POST.get('rate')
        
        if not worker_id_str or not item_id or not rate:
            return JsonResponse({'error': 'Missing data'}, status=400)
            
        item = Item.objects.get(id=item_id)
        
        # Prevent duplicates
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

@staff_member_required
@require_POST
def delete_worker_allocation(request, alloc_id):
    try:
        ItemWorkerAllocation.objects.filter(id=alloc_id).delete()
        return JsonResponse({'status': 'success'})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@staff_member_required
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

@staff_member_required
@require_GET
def get_attendance_for_date(request):
    date_str = request.GET.get('date')
    if not date_str:
        return JsonResponse({'error': 'Date is required'}, status=400)
    
    records = Attendance.objects.filter(date=date_str)
    data = {
        str(r.worker.id): {
            'status': r.status,
            'ot': r.overtime_hours
        } for r in records
    }
    return JsonResponse({'attendance': data})

@staff_member_required
@require_POST
def record_labor_payment(request):
    try:
        target_id = request.POST.get('target_id') # e.g. w_5 or jw_3
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
