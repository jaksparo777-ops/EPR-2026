from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.http import JsonResponse
from django.utils import timezone
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from core.security import require_role
from django.views.decorators.http import require_GET, require_POST

from apps.workforce.models import Worker, JobWorker, Attendance
from apps.ledger_pay.models import ItemWorkerAllocation, LaborPayment, Loan
from apps.production.models import StockTransaction


@login_required
@require_role(['HR & Accounts Manager', 'System Admin'])
def delete_worker(request, worker_id):
    try:
        worker = Worker.objects.get(id=worker_id)
        worker_name = worker.name
        worker.delete()
        messages.success(request, f"Worker '{worker_name}' deleted successfully.")
    except Worker.DoesNotExist:
        messages.error(request, "Worker could not be found.")
    except Exception as e:
        messages.error(request, f"Error deleting worker: {str(e)}")
    
    return redirect(f"{reverse('master_data')}?tab=workers&sub=internal")


@login_required
@require_role(['HR & Accounts Manager', 'System Admin'])
def delete_job_worker(request, job_worker_id):
    try:
        jw = JobWorker.objects.get(id=job_worker_id)
        jw_name = jw.name
        jw.delete()
        messages.success(request, f"Job Worker '{jw_name}' deleted successfully.")
    except JobWorker.DoesNotExist:
        messages.error(request, "Job Worker could not be found.")
    except Exception as e:
        messages.error(request, f"Error deleting job worker: {str(e)}")
    
    return redirect(f"{reverse('master_data')}?tab=workers&sub=job")


@login_required
@require_role(['HR & Accounts Manager', 'System Admin'])
@require_GET
def get_internal_worker_profile(request, worker_id):
    worker = get_object_or_404(Worker, id=worker_id)
    
    # 1. Get Attendance for current month
    now = timezone.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    attendance = Attendance.objects.filter(worker=worker, date__gte=month_start).order_by('-date')
    
    # 2. Get Payments (recent 20 for list display)
    payments = LaborPayment.objects.filter(worker=worker).order_by('-date')[:20]
    
    # Payments & Repayments this month for correct stats calculation
    payments_qs = LaborPayment.objects.filter(worker=worker, date__gte=month_start)
    total_paid_month = sum(p.amount for p in payments_qs.exclude(payment_type__in=['LOAN_REPAYMENT', 'NEW_LOAN']))
    total_repaid_month = sum(p.amount for p in payments_qs.filter(payment_type='LOAN_REPAYMENT'))
    
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
    
    return JsonResponse({
        'name': worker.name,
        'employee_id': worker.employee_id or '---',
        'designation': worker.designation or 'Worker',
        'salary_model': worker.get_salary_model_display(),
        'base_rate': float(worker.daily_rate) if worker.salary_model == 'DAILY' else float(worker.monthly_fixed_salary),
        'ot_rate': float(worker.overtime_rate),
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
            'paid': round(total_paid_month, 2),
            'balance': round(earned_wages - total_paid_month - total_repaid_month, 2)
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
                'amount': float(p.amount),
                'mode': p.payment_mode,
                'type': p.get_payment_type_display()
            } for p in payments
        ]
    })


@login_required
@require_role(['HR & Accounts Manager', 'System Admin'])
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
                'paid': float(p.amount)
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


@login_required
@require_role(['HR & Accounts Manager', 'System Admin'])
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
@require_role(['HR & Accounts Manager', 'System Admin'])
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
