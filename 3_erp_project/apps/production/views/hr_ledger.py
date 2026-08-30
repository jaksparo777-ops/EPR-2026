import calendar
from datetime import datetime, timedelta
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Q
from django.utils import timezone

from apps.master_data.models import LegalEntity, Client, Warehouse, Item, ItemComposition
from apps.authentication.models import Worker, ProcessType, SalaryModel, WorkerType
from apps.production.models import StockTransaction, TransactionType, ItemWorkerAllocation, Attendance, Loan, LaborPayment, Carton, CartonItem, Holiday, AttendanceStatus


# =====================================================
# LABOR LEDGER / ATTENDANCE MATRIX / PAYROLL
# =====================================================
def get_holiday_for_date(dt, company, month_holidays):
    """
    Determines if a date is a holiday or a weekly off for a company.
    Returns a dict with 'name' and 'is_paid' if it is, otherwise None.
    """
    comp_holiday = None
    global_holiday = None
    for h in month_holidays:
        if h.date == dt:
            if company and h.company_id == company.id:
                comp_holiday = h
            elif h.company_id is None:
                global_holiday = h

    h = comp_holiday or global_holiday
    if h:
        if h.is_working_day_override:
            # Overrides weekly off to treat this specific date as a normal working day
            return None
        return {'name': h.name, 'is_paid': h.is_paid}

    # Fallback to weekly off configuration
    if company and company.weekly_off == dt.weekday():
        return {
            'name': "Weekly Off",
            'is_paid': company.is_weekly_off_paid
        }

    return None


def get_worker_rate_for_date(worker, target_date):
    """
    Looks up historical worker daily_rate, monthly_fixed_salary, overtime_rate, monthly_allowance
    effective on target_date. Falls back to earliest historical rate or current worker fields.
    """
    from apps.authentication.models import WorkerRateHistory
    history = WorkerRateHistory.objects.filter(
        worker=worker,
        effective_from__lte=target_date
    ).order_by('-effective_from', '-created_at').first()
    if history:
        return {
            'daily_rate': float(history.daily_rate),
            'monthly_fixed_salary': float(history.monthly_fixed_salary),
            'overtime_rate': float(history.overtime_rate),
            'monthly_allowance': float(history.monthly_allowance),
        }
    
    # Fallback to earliest historical rate entry if available before live worker fields
    earliest = WorkerRateHistory.objects.filter(
        worker=worker
    ).order_by('effective_from', 'created_at').first()
    if earliest:
        return {
            'daily_rate': float(earliest.daily_rate),
            'monthly_fixed_salary': float(earliest.monthly_fixed_salary),
            'overtime_rate': float(earliest.overtime_rate),
            'monthly_allowance': float(earliest.monthly_allowance),
        }

    return {
        'daily_rate': float(worker.daily_rate),
        'monthly_fixed_salary': float(worker.monthly_fixed_salary),
        'overtime_rate': float(worker.overtime_rate),
        'monthly_allowance': float(worker.monthly_allowance),
    }


def get_jw_item_rate_for_date(job_worker, item, target_date, fallback_rate=0.0):
    """
    Looks up historical ItemWorkerRateHistory effective on target_date.
    Falls back to earliest historical rate, current ItemWorkerAllocation or fallback_rate.
    """
    from apps.production.models import ItemWorkerRateHistory, ItemWorkerAllocation
    if not item:
        return float(fallback_rate)
    history = ItemWorkerRateHistory.objects.filter(
        worker=job_worker,
        item=item,
        effective_from__lte=target_date
    ).order_by('-effective_from', '-created_at').first()
    if history:
        return float(history.rate_per_piece)
    
    earliest = ItemWorkerRateHistory.objects.filter(
        worker=job_worker,
        item=item
    ).order_by('effective_from', 'created_at').first()
    if earliest:
        return float(earliest.rate_per_piece)

    alloc = ItemWorkerAllocation.objects.filter(worker=job_worker, item=item).first()
    if alloc:
        return float(alloc.rate_per_piece)
    return float(fallback_rate)


@login_required
def labor_ledger(request):
    # Context data
    month_raw = request.GET.get('month', '').strip()
    month_dt = None
    if month_raw:
        for fmt in ('%Y-%m', '%Y-%m-%d', '%Y/%m', '%Y/%m/%d'):
            try:
                month_dt = datetime.strptime(month_raw[:10] if len(month_raw) >= 10 else month_raw, fmt)
                break
            except ValueError:
                pass
    if not month_dt:
        month_dt = datetime.now()
    
    month_str = month_dt.strftime('%Y-%m')
    selected_date = month_dt.date()

    month_start = selected_date.replace(day=1)
    num_days = calendar.monthrange(month_dt.year, month_dt.month)[1]
    month_end = selected_date.replace(day=num_days)
    
    curr_month_str = timezone.now().strftime('%Y-%m')
    is_current_month = (month_str == curr_month_str)
    
    # Fetch all holidays for this month
    month_holidays = list(Holiday.objects.filter(date__gte=month_start, date__lte=month_end))
    
    # 0. RESOLVE ACTIVE COMPANY/TEAM FROM WORKSPACE
    from django.db.models import Q
    if request.company:
        active_team = 'c1' if request.company.id == 2 else 'c2'
        company_id = request.company.id
        internal_workers = Worker.objects.filter(company_id=company_id, worker_type=WorkerType.IN_HOUSE).filter(
            Q(active=True) |
            Q(attendance_records__date__gte=month_start, attendance_records__date__lte=month_end) |
            Q(laborpayment__date__gte=month_start, laborpayment__date__lte=month_end)
        ).distinct()
    else:
        active_team = 'all'
        company_id = None
        internal_workers = Worker.objects.filter(worker_type=WorkerType.IN_HOUSE).filter(
            Q(active=True) |
            Q(attendance_records__date__gte=month_start, attendance_records__date__lte=month_end) |
            Q(laborpayment__date__gte=month_start, laborpayment__date__lte=month_end)
        ).distinct()
    staff_ledger = []
    for w in internal_workers:
        # Attendance this month
        attendance_records = Attendance.objects.filter(worker=w, date__gte=month_start, date__lte=month_end)
        days_present = attendance_records.filter(status='PRESENT').count()
        half_days = attendance_records.filter(status='HALF_DAY').count()
        days_absent = attendance_records.filter(status='ABSENT').count()
        total_ot = sum(a.overtime_hours for a in attendance_records)
        
        # Calculate paid holiday pay for daily workers who did not work or worked half day
        holiday_pay_days = 0.0
        for day_num in range(1, num_days + 1):
            dt = month_start.replace(day=day_num)
            h_info = get_holiday_for_date(dt, w.company, month_holidays)
            if h_info and h_info['is_paid']:
                att_rec = attendance_records.filter(date=dt).first()
                if att_rec:
                    if att_rec.status == 'ABSENT':
                        pass
                    elif att_rec.status == 'HALF_DAY':
                        # Work half day + paid holiday = full day rate (Option B minimum guarantee)
                        holiday_pay_days += 0.5
                    elif att_rec.status == 'PRESENT':
                        pass
                    elif att_rec.status == 'HOLIDAY':
                        holiday_pay_days += 1.0
                else:
                    holiday_pay_days += 1.0

        # Wage Calculation based on Model
        earnings = 0
        # Calculate Working Days for the month (Total days - Holidays/Offs)
        month_off_days = 0
        for d_num in range(1, num_days + 1):
            dt_chk = month_start.replace(day=d_num)
            if get_holiday_for_date(dt_chk, w.company, month_holidays):
                month_off_days += 1
        net_working_days = max(1, num_days - month_off_days)
        eff_present = days_present + (0.5 * half_days)

        if w.salary_model == 'DAILY':
            earnings = ((days_present + holiday_pay_days) * w.daily_rate) + (half_days * 0.5 * w.daily_rate)
        elif w.salary_model == 'FIXED':
            calc_mode = getattr(w, 'fixed_salary_calc_mode', 'PRO_RATA')
            if calc_mode == 'FIXED_FULL':
                earnings = float(w.monthly_fixed_salary)
            elif calc_mode == 'CALENDAR_30':
                daily_deduct = w.monthly_fixed_salary / 30.0
                payable_days = days_present + (0.5 * half_days) + holiday_pay_days
                earnings = payable_days * daily_deduct
            else: # PRO_RATA (Net Working Days)
                dynamic_daily_rate = w.monthly_fixed_salary / net_working_days if net_working_days > 0 else (w.monthly_fixed_salary / 30.0)
                payable_days = days_present + (0.5 * half_days) + holiday_pay_days
                earnings = payable_days * dynamic_daily_rate
        
        # Add Overtime & Allowance
        earnings += (total_ot * w.overtime_rate)
        
        if getattr(w, 'allowance_calc_mode', 'FIXED') == 'PRO_RATA' and w.monthly_allowance > 0:
            earned_allowance = round((w.monthly_allowance / net_working_days) * eff_present, 2)
        else:
            earned_allowance = float(w.monthly_allowance)

        earnings += earned_allowance
        
        # Casting weight-based pay
        casting_pay = 0
        total_casting_wt = 0
        if w.casting_rate_per_kg > 0:
            casting_txs = StockTransaction.objects.filter(
                worker=w,
                transaction_type=TransactionType.CASTING_ENTRY,
                created_at__date__gte=month_start,
                created_at__date__lte=month_end
            )
            total_casting_wt = sum(tx.actual_scale_weight if tx.actual_scale_weight > 0 else tx.weight for tx in casting_txs)
            casting_pay = total_casting_wt * w.casting_rate_per_kg
            earnings += casting_pay

        # Payments & Repayments this month
        payments_qs = LaborPayment.objects.filter(worker=w).filter(
            Q(settlement_period=month_str) |
            Q(settlement_period__isnull=True, date__gte=month_start, date__lte=month_end) |
            Q(settlement_period='', date__gte=month_start, date__lte=month_end)
        )
        total_paid_explicit = sum(p.amount for p in payments_qs.exclude(payment_type__in=['LOAN_REPAYMENT', 'NEW_LOAN']))
        total_repaid_explicit = sum(p.amount for p in payments_qs.filter(payment_type='LOAN_REPAYMENT'))
        
        # Standard Half-Up Whole Rupee Rounding (Standard Payroll Rule: >= .50 round up to 1, < .50 round down)
        prior_earned = 0.0
        prior_unpaid_bal = 0.0
        prev_month_str = (month_start - timedelta(days=1)).strftime('%Y-%m')
        if prev_month_str >= '2026-05':
            r_prev = get_worker_report_data(w, prev_month_str)
            prior_due = round(r_prev['total_earned'])
            if r_prev['status_code'] == 'FULLY_PAID':
                prior_earned = max(prior_due, round(r_prev['total_paid'] + r_prev['total_repaid']))
                prior_unpaid_bal = 0.0
            else:
                prior_earned = prior_due
                prior_unpaid_bal = max(0.0, float(r_prev.get('balance', 0.0)))
        all_w_pmts_to_date = round(sum(p.amount for p in LaborPayment.objects.filter(worker=w).exclude(payment_type__in=['NEW_LOAN', 'LOAN_REPAYMENT'])))
        avail_pmt_pool = max(0.0, all_w_pmts_to_date - prior_earned)

        gross_due = earnings + prior_unpaid_bal
        if gross_due > 0:
            eff_discharged = max(total_paid_explicit + total_repaid_explicit, min(gross_due, avail_pmt_pool + total_repaid_explicit))
            total_paid = max(total_paid_explicit, eff_discharged - total_repaid_explicit)
            if total_paid < 1.0:
                total_paid = 0.0
            total_repaid = total_repaid_explicit
            total_discharged = total_paid + total_repaid
            bal = max(0.0, round(gross_due) - round(total_discharged))
        else:
            total_paid = total_paid_explicit
            total_repaid = total_repaid_explicit
            total_discharged = total_paid
            bal = 0.0
        if abs(bal) < 1.0:
            bal = 0.0

        active_loan = w.loans.filter(is_active=True).first()
        staff_cum_gross = earnings + prior_earned
        has_explicit_settlement = payments_qs.filter(payment_type__in=['SALARY', 'JOB_WORK', 'SETTLEMENT']).exists()
        has_advance_only = payments_qs.filter(payment_type='ADVANCE').exists() and not has_explicit_settlement

        if is_current_month and has_explicit_settlement and total_discharged >= staff_cum_gross and staff_cum_gross > 0:
            settled_voucher_amount = round(staff_cum_gross)
            display_earned = max(0.0, round(staff_cum_gross) - settled_voucher_amount)
            display_paid = max(0.0, round(total_discharged) - settled_voucher_amount)
            display_bal = max(0.0, display_earned - display_paid)
            status_code = 'FULLY_PAID'
            has_settled_voucher = True
        else:
            is_staff_settled = (bal <= 0 and (earnings > 0 or prior_unpaid_bal > 0 or staff_cum_gross > 0) and (has_explicit_settlement or total_discharged >= staff_cum_gross or total_paid > 0))
            settled_voucher_amount = round(staff_cum_gross) if (is_staff_settled and staff_cum_gross > 0) else 0.0
            display_earned = round(earnings)
            display_paid = round(total_paid + total_repaid) if is_staff_settled else round(total_paid)
            display_bal = bal
            has_settled_voucher = (is_staff_settled and staff_cum_gross > 0)
            if earnings == 0 and prior_unpaid_bal == 0 and total_paid_explicit == 0:
                status_code = 'NO_ACTIVITY'
            elif is_staff_settled or bal <= 0:
                status_code = 'FULLY_PAID'
            elif has_advance_only:
                status_code = 'ADVANCE_PAID'
            elif total_discharged > 0 and bal > 0:
                status_code = 'PARTIAL'
            else:
                status_code = 'PENDING'

        from apps.authentication.models import MonthlySettlementLock
        lock_obj = MonthlySettlementLock.objects.filter(worker=w, month_str=month_str).first()
        if not lock_obj and (status_code == 'FULLY_PAID'):
            lock_obj, _ = MonthlySettlementLock.objects.get_or_create(
                worker=w,
                month_str=month_str,
                defaults={
                    'is_locked': True,
                    'locked_earnings': float(display_earned),
                    'locked_paid': float(display_paid)
                }
            )
        is_locked = bool(lock_obj and lock_obj.is_locked)

        staff_ledger.append({
            'worker': w,
            'days_present': days_present,
            'half_days': half_days,
            'days_absent': days_absent,
            'ot_hours': total_ot,
            'earnings': display_earned,
            'opening_bal': prior_unpaid_bal,
            'gross_payable': display_earned,
            'raw_earnings': earnings,
            'raw_total_paid': total_paid,
            'total_paid': display_paid,
            'total_repaid': total_repaid,
            'active_loan': active_loan,
            'casting_pay': casting_pay,
            'balance': display_bal,
            'status_code': status_code,
            'is_fully_paid': (status_code == 'FULLY_PAID'),
            'is_locked': is_locked,
            'has_settled_voucher': has_settled_voucher,
            'settled_voucher_amount': settled_voucher_amount,
        })
     
    # 2. JOB WORK PAYABLES (EXTERNAL)
    if company_id:
        job_workers = Worker.objects.filter(company_id=company_id, worker_type=WorkerType.JOB_WORKER).filter(
            Q(active=True) |
            Q(stocktransaction__created_at__date__gte=month_start, stocktransaction__created_at__date__lte=month_end) |
            Q(laborpayment__date__gte=month_start, laborpayment__date__lte=month_end)
        ).distinct()
    else:
        job_workers = Worker.objects.filter(worker_type=WorkerType.JOB_WORKER).filter(
            Q(active=True) |
            Q(stocktransaction__created_at__date__gte=month_start, stocktransaction__created_at__date__lte=month_end) |
            Q(laborpayment__date__gte=month_start, laborpayment__date__lte=month_end)
        ).distinct()
    jw_ledger = []
    for jw in job_workers:
        # Calculate Total Earned from Received transactions in selected month
        transactions = StockTransaction.objects.filter(
            worker=jw, 
            transaction_type__in=['machining_in', 'polishing_in', 'packaging_in'],
            created_at__date__gte=month_start,
            created_at__date__lte=month_end
        )
        
        total_earned = 0
        for tx in transactions:
            if tx.item.is_raw_material and tx.item.derived_items.exists():
                continue
            # Find the rate for this item (by code) and this job worker
            alloc = ItemWorkerAllocation.objects.filter(item__code=tx.item.code, worker=jw).first()
            rate = float(alloc.rate_per_piece) if alloc else 0.0
            if not rate and (tx.item.item_type == 'SET' or tx.item.components.exists()):
                comp_sum = 0.0
                has_comp_alloc = False
                for comp in tx.item.components.all():
                    c_alloc = ItemWorkerAllocation.objects.filter(worker=jw, item=comp.component_item).first()
                    if c_alloc:
                        comp_sum += comp.quantity * float(c_alloc.rate_per_piece)
                        has_comp_alloc = True
                if has_comp_alloc:
                    rate = comp_sum

            total_earned += (tx.quantity * rate)
        
        # Casting weight-based pay
        casting_pay = 0
        total_casting_wt = 0
        if jw.casting_rate_per_kg > 0:
            casting_txs = StockTransaction.objects.filter(
                worker=jw,
                transaction_type=TransactionType.CASTING_ENTRY,
                created_at__date__gte=month_start,
                created_at__date__lte=month_end
            )
            total_casting_wt = sum(tx.actual_scale_weight if tx.actual_scale_weight > 0 else tx.weight for tx in casting_txs)
            casting_pay = total_casting_wt * jw.casting_rate_per_kg
            total_earned += casting_pay
 
        # Payments to this JW for selected month
        payments = LaborPayment.objects.filter(worker=jw).filter(
            Q(settlement_period=month_str) |
            Q(settlement_period__isnull=True, date__gte=month_start, date__lte=month_end) |
            Q(settlement_period='', date__gte=month_start, date__lte=month_end)
        )
        total_paid = payments.exclude(payment_type__in=['LOAN_REPAYMENT', 'NEW_LOAN']).aggregate(Sum('amount'))['amount__sum'] or 0
        total_repaid = payments.filter(payment_type='LOAN_REPAYMENT').aggregate(Sum('amount'))['amount__sum'] or 0
        
        # Loan Status
        active_loan = jw.loans.filter(is_active=True).first()
        
        # Calculate opening financial balance before month_start
        opening_bal = 0.0
        prev_jw_txs = StockTransaction.objects.filter(worker=jw, created_at__date__lt=month_start)
        for tx in prev_jw_txs.filter(transaction_type__endswith='_in'):
            if tx.item.is_raw_material and tx.item.derived_items.exists():
                continue
            alloc = ItemWorkerAllocation.objects.filter(worker=jw, item=tx.item).first()
            rate = float(alloc.rate_per_piece) if alloc else 0.0
            if not rate and (tx.item.item_type == 'SET' or tx.item.components.exists()):
                comp_sum = 0.0
                has_comp_alloc = False
                for comp in tx.item.components.all():
                    c_alloc = ItemWorkerAllocation.objects.filter(worker=jw, item=comp.component_item).first()
                    if c_alloc:
                        comp_sum += comp.quantity * float(c_alloc.rate_per_piece)
                        has_comp_alloc = True
                if has_comp_alloc:
                    rate = comp_sum

            opening_bal += (tx.quantity * rate)
        
        if jw.casting_rate_per_kg > 0:
            prev_casting = prev_jw_txs.filter(transaction_type=TransactionType.CASTING_ENTRY)
            prev_casting_wt = sum(tx.actual_scale_weight if tx.actual_scale_weight > 0 else tx.weight for tx in prev_casting)
            opening_bal += prev_casting_wt * float(jw.casting_rate_per_kg)
            
        prev_payments = LaborPayment.objects.filter(worker=jw).filter(
            Q(settlement_period__lt=month_str) |
            Q(settlement_period__isnull=True, date__lt=month_start) |
            Q(settlement_period='', date__lt=month_start)
        ).exclude(payment_type__in=['NEW_LOAN', 'LOAN_REPAYMENT'])
        opening_bal -= sum(p.amount for p in prev_payments)

        prior_jw_earned = 0.0
        prev_month_str = (month_start - timedelta(days=1)).strftime('%Y-%m')
        if prev_month_str >= '2026-05':
            r7_jw = get_job_worker_report_data(jw, prev_month_str)
            prior_due = round(r7_jw['financial_opening_bal'] + r7_jw['total_earned'])
            if r7_jw['status_code'] == 'FULLY_PAID':
                prior_jw_earned = max(prior_due, round(r7_jw['total_discharged']))
                opening_bal = 0.0
            else:
                prior_jw_earned = prior_due
                opening_bal = max(0.0, float(r7_jw.get('net_balance', 0.0)))
        
        cum_gross_due = max(0.0, opening_bal + total_earned)
        all_jw_pmts_to_date = round(sum(p.amount for p in LaborPayment.objects.filter(worker=jw).exclude(payment_type__in=['NEW_LOAN', 'LOAN_REPAYMENT'])))
        avail_jw_pmt_pool = max(0.0, all_jw_pmts_to_date - prior_jw_earned)

        if cum_gross_due > 0:
            eff_jw_discharged = max(total_paid + total_repaid, min(cum_gross_due, avail_jw_pmt_pool + total_repaid))
            total_paid = max(total_paid, eff_jw_discharged - total_repaid)
            if total_paid < 1.0:
                total_paid = 0.0
            total_discharged = total_paid + total_repaid
            jw_bal = max(0.0, round(cum_gross_due) - round(total_discharged))
        else:
            total_paid = total_paid
            total_discharged = total_paid
            jw_bal = 0.0
        if abs(jw_bal) < 1.0:
            jw_bal = 0.0

        jw_payments_qs = LaborPayment.objects.filter(worker=jw, date__gte=month_start, date__lte=month_end)
        has_jw_explicit_settlement = jw_payments_qs.filter(payment_type__in=['SALARY', 'JOB_WORK', 'SETTLEMENT']).exists()
        has_jw_advance_only = jw_payments_qs.filter(payment_type='ADVANCE').exists() and not has_jw_explicit_settlement

        if is_current_month and has_jw_explicit_settlement and total_discharged >= cum_gross_due and cum_gross_due > 0:
            settled_voucher_amount = round(cum_gross_due)
            display_earned = max(0.0, round(cum_gross_due) - settled_voucher_amount)
            display_paid = max(0.0, round(total_discharged) - settled_voucher_amount)
            display_bal = max(0.0, display_earned - display_paid)
            jw_status_code = 'FULLY_PAID'
            has_settled_voucher = True
        else:
            is_jw_settled = (jw_bal <= 0 and (total_earned > 0 or opening_bal > 0 or cum_gross_due > 0) and (has_jw_explicit_settlement or total_discharged >= cum_gross_due or total_paid > 0))
            settled_voucher_amount = round(cum_gross_due) if (is_jw_settled and cum_gross_due > 0) else 0.0
            display_earned = round(total_earned)
            display_paid = round(total_paid + total_repaid) if is_jw_settled else round(total_paid)
            display_bal = jw_bal
            has_settled_voucher = (is_jw_settled and cum_gross_due > 0)
            if total_earned == 0 and opening_bal == 0 and total_paid == 0:
                jw_status_code = 'NO_ACTIVITY'
            elif is_jw_settled or jw_bal <= 0:
                jw_status_code = 'FULLY_PAID'
            elif has_jw_advance_only:
                jw_status_code = 'ADVANCE_PAID'
            elif total_discharged > 0 and jw_bal > 0:
                jw_status_code = 'PARTIAL'
            else:
                jw_status_code = 'PENDING'

        jw_ledger.append({
            'jw': jw,
            'total_earned': display_earned,
            'opening_bal': opening_bal,
            'gross_payable': display_earned,
            'raw_total_earned': total_earned,
            'raw_total_paid': total_paid,
            'total_paid': display_paid,
            'total_repaid': total_repaid,
            'active_loan': active_loan,
            'casting_pay': casting_pay,
            'balance': display_bal,
            'status_code': jw_status_code,
            'is_fully_paid': (jw_status_code == 'FULLY_PAID'),
            'has_settled_voucher': has_settled_voucher,
            'settled_voucher_amount': settled_voucher_amount,
        })
     
    total_staff_earnings = int(round(sum(e['gross_payable'] for e in staff_ledger)))
    total_staff_paid = int(round(sum(e['total_paid'] + e['total_repaid'] for e in staff_ledger)))
    total_staff_due = int(round(sum(max(0.0, e['balance']) for e in staff_ledger)))
    staff_settlement_pct = min(100.0, max(0.0, round((total_staff_paid / total_staff_earnings * 100.0), 1))) if total_staff_earnings > 0 else 100.0

    total_jw_gross = int(round(sum(e['gross_payable'] for e in jw_ledger)))
    total_jw_paid = int(round(sum(min(e['gross_payable'], e['total_paid'] + e['total_repaid']) for e in jw_ledger)))
    total_jw_due = int(round(sum(max(0.0, e['balance']) for e in jw_ledger)))
    jw_settlement_pct = min(100.0, max(0.0, round((total_jw_paid / total_jw_gross * 100.0), 1))) if total_jw_gross > 0 else 100.0
    
    # Summary Counters for Status Badges & Progress Indicators (Excludes NO_ACTIVITY zero-work workers)
    staff_settled_count = sum(1 for e in staff_ledger if e['status_code'] == 'FULLY_PAID')
    staff_pending_count = sum(1 for e in staff_ledger if e['status_code'] in ['PARTIAL', 'PENDING'])
    staff_active_count = sum(1 for e in staff_ledger if e['status_code'] != 'NO_ACTIVITY')
    staff_total_count = staff_active_count if staff_active_count > 0 else len(staff_ledger)

    jw_settled_count = sum(1 for e in jw_ledger if e['status_code'] == 'FULLY_PAID')
    jw_pending_count = sum(1 for e in jw_ledger if e['status_code'] in ['PARTIAL', 'PENDING'])
    jw_active_count = sum(1 for e in jw_ledger if e['status_code'] != 'NO_ACTIVITY')
    jw_total_count = jw_active_count if jw_active_count > 0 else len(jw_ledger)
     
    # 3. Monthly Attendance Matrix (for the Full Sheet view)
    attendance_matrix = []
    days_range = range(1, num_days + 1)
    
    for w in internal_workers:
        row = {'worker': w, 'days': []}
        att_records = Attendance.objects.filter(worker=w, date__gte=month_start, date__lte=month_end)
        att_dict = {r.date.day: r for r in att_records}
        
        for d in days_range:
            dt = selected_date.replace(day=d)
            record = att_dict.get(d)
            h_info = get_holiday_for_date(dt, w.company, month_holidays)
            date_str = dt.strftime('%Y-%m-%d')
            
            status_val = None
            if record:
                status_val = record.status
            elif h_info:
                status_val = AttendanceStatus.HOLIDAY
                
            row['days'].append({
                'day': d,
                'date_str': date_str,
                'status': status_val,
                'ot': record.overtime_hours if record else 0
            })
        attendance_matrix.append(row)
     
    company1 = LegalEntity.objects.filter(id=2).first()
    company2 = LegalEntity.objects.filter(id=1).first()
 
    curr_month_str = timezone.now().strftime('%Y-%m')
 
    context = {
        'staff_ledger': staff_ledger,
        'jw_ledger': jw_ledger,
        'attendance_matrix': attendance_matrix,
        'days_range': days_range,
        'total_staff_earnings': total_staff_earnings,
        'total_staff_paid': total_staff_paid,
        'total_staff_due': total_staff_due,
        'staff_settlement_pct': staff_settlement_pct,
        'total_jw_gross': total_jw_gross,
        'total_jw_paid': total_jw_paid,
        'total_jw_due': total_jw_due,
        'jw_settlement_pct': jw_settlement_pct,
        'staff_settled_count': staff_settled_count,
        'staff_pending_count': staff_pending_count,
        'staff_total_count': staff_total_count,
        'jw_settled_count': jw_settled_count,
        'jw_pending_count': jw_pending_count,
        'jw_total_count': jw_total_count,
        'items': Item.objects.all().order_by('code'),
        'today': selected_date,
        'month_name': month_dt.strftime('%B %Y'),
        'month_val': month_str,
        'current_month_val': curr_month_str,
        'is_current_month': (month_str == curr_month_str),
        'active_team': active_team,
        'active_tab': request.GET.get('tab', 'staff'),
        'active_drawer': request.GET.get('drawer', ''),
        'drawer_worker_id': request.GET.get('worker_id', ''),
        'drawer_jw_id': request.GET.get('jw_id', ''),
        'company1': company1,
        'company2': company2,
    }
    return render(request, 'labor_ledger.html', context)
 
# =====================================================
# WORKER MONTHLY REPORT (PAY SLIP & CALENDAR)
# =====================================================
 
def get_worker_report_data(worker, month_str):
    try:
        month_dt = datetime.strptime(month_str, '%Y-%m')
        selected_date = month_dt.date()
    except Exception:
        month_str = timezone.now().strftime('%Y-%m')
        month_dt = datetime.strptime(month_str, '%Y-%m')
        selected_date = month_dt.date()
        
    month_start = selected_date.replace(day=1)
    num_days = calendar.monthrange(month_dt.year, month_dt.month)[1]
    month_end = selected_date.replace(day=num_days)
    
    attendance = Attendance.objects.filter(worker=worker, date__gte=month_start, date__lte=month_end).order_by('date')
    payments = LaborPayment.objects.filter(worker=worker).filter(
        Q(settlement_period=month_str) |
        Q(settlement_period__isnull=True, date__gte=month_start, date__lte=month_end) |
        Q(settlement_period='', date__gte=month_start, date__lte=month_end)
    ).order_by('date')
    
    days_present = attendance.filter(status='PRESENT').count()
    half_days = attendance.filter(status='HALF_DAY').count()
    days_absent = attendance.filter(status='ABSENT').count()
    total_ot = sum(a.overtime_hours for a in attendance)
    
    attendance_ledger = []
    earned_wages = 0
    daily_rate = worker.daily_rate if worker.salary_model == 'DAILY' else (worker.monthly_fixed_salary / 30)
    month_holidays = list(Holiday.objects.filter(date__gte=month_start, date__lte=month_end))
    att_by_date = {a.date: a for a in attendance}
    
    days_range_dt = [month_start.replace(day=d) for d in range(1, num_days + 1)]
    holiday_count = 0
    
    for dt in days_range_dt:
        a = att_by_date.get(dt)
        h_info = get_holiday_for_date(dt, worker.company, month_holidays)
        
        if h_info:
            holiday_count += 1
            
        if not a and not h_info:
            continue
            
        day_earned = 0
        status_display = ""
        ot_hours = 0.0
        
        if worker.salary_model == 'DAILY':
            if a:
                ot_hours = a.overtime_hours
                if a.status == 'PRESENT':
                    day_earned = daily_rate
                    status_display = "Present"
                elif a.status == 'HALF_DAY':
                    if h_info and h_info['is_paid']:
                        day_earned = daily_rate
                    else:
                        day_earned = daily_rate * 0.5
                    status_display = "Half Day"
                elif a.status == 'ABSENT':
                    day_earned = 0
                    status_display = "Absent"
                elif a.status == 'HOLIDAY':
                    day_earned = daily_rate if (h_info and h_info['is_paid']) else 0
                    status_display = f"Holiday: {h_info['name']}" if h_info else "Holiday"
            else:
                day_earned = daily_rate if (h_info and h_info['is_paid']) else 0
                status_display = f"Holiday: {h_info['name']}" if h_info else "Holiday"
        else:
            status_display = a.get_status_display() if a else (f"Holiday: {h_info['name']}" if h_info else "Holiday")
            ot_hours = a.overtime_hours if a else 0.0
            if a and a.status == 'ABSENT':
                day_earned = 0
            else:
                day_earned = daily_rate
        
        day_earned += (ot_hours * worker.overtime_rate)
        earned_wages += day_earned
        
        attendance_ledger.append({
            'date': dt,
            'status': status_display,
            'ot': ot_hours,
            'rate': daily_rate,
            'earned': day_earned,
            'holiday_name': h_info['name'] if h_info else None,
            'is_paid_holiday': h_info['is_paid'] if h_info else False
        })
    
    # Look up rate effective on month_end
    rates = get_worker_rate_for_date(worker, month_end)
    worker_daily_rate = rates['daily_rate']
    worker_fixed_salary = rates['monthly_fixed_salary']
    worker_ot_rate = rates['overtime_rate']
    worker_allowance = rates['monthly_allowance']

    # Calculate Working Days for the month (Total days - Holidays/Offs)
    net_working_days = max(1, num_days - holiday_count)
    daily_rate = worker_daily_rate if worker.salary_model == 'DAILY' else (worker_fixed_salary / net_working_days if net_working_days > 0 else worker_fixed_salary / 30)

    if worker.salary_model == 'FIXED':
        calc_mode = getattr(worker, 'fixed_salary_calc_mode', 'PRO_RATA')
        if calc_mode == 'FIXED_FULL':
            earned_wages = worker_fixed_salary + (total_ot * worker_ot_rate)
        elif calc_mode == 'CALENDAR_30':
            daily_deduct = worker_fixed_salary / 30.0
            payable_days = days_present + (0.5 * half_days)
            earned_wages = (payable_days * daily_deduct) + (total_ot * worker_ot_rate)
        else: # PRO_RATA
            dynamic_daily_rate = worker_fixed_salary / net_working_days if net_working_days > 0 else (worker_fixed_salary / 30.0)
            payable_days = days_present + (0.5 * half_days)
            earned_wages = (payable_days * dynamic_daily_rate) + (total_ot * worker_ot_rate)

    # Calculate Allowance (Fixed vs Pro-Rata Attendance Based)
    eff_present = days_present + (0.5 * half_days)
    is_pro_rata = getattr(worker, 'allowance_calc_mode', 'FIXED') == 'PRO_RATA'

    if is_pro_rata and worker_allowance > 0:
        earned_allowance = round((worker_allowance / net_working_days) * eff_present, 2)
    else:
        earned_allowance = worker_allowance

    earned_wages += earned_allowance

    # Casting weight-based pay
    casting_pay = 0
    total_casting_wt = 0
    casting_txs_detailed = []
    if worker.casting_rate_per_kg > 0:
        casting_txs = StockTransaction.objects.filter(
            worker=worker,
            transaction_type=TransactionType.CASTING_ENTRY,
            created_at__date__gte=month_start,
            created_at__date__lte=month_end
        ).order_by('created_at')
        total_casting_wt = sum(tx.actual_scale_weight if tx.actual_scale_weight > 0 else tx.weight for tx in casting_txs)
        casting_pay = total_casting_wt * float(worker.casting_rate_per_kg)
        for tx in casting_txs:
            wt = tx.actual_scale_weight if tx.actual_scale_weight > 0 else tx.weight
            casting_txs_detailed.append({
                'date': tx.created_at,
                'item_name': tx.item.name,
                'item_code': tx.item.code,
                'weight': wt,
                'rate': float(worker.casting_rate_per_kg),
                'earnings': wt * float(worker.casting_rate_per_kg)
            })
        
    earned_wages += casting_pay

    total_paid_regular = sum(p.amount for p in payments.exclude(payment_type__in=['LOAN_REPAYMENT', 'NEW_LOAN']))
    loan_repaid_this_month = sum(p.amount for p in payments.filter(payment_type='LOAN_REPAYMENT'))
    
    first_day_of_month = month_start.weekday()
    first_day_of_month = (first_day_of_month + 1) % 7
    calendar_weeks = []
    current_week = [None] * first_day_of_month
    att_by_day = {a.date.day: a for a in attendance}
    
    for d in range(1, num_days + 1):
        dt = month_start.replace(day=d)
        record = att_by_day.get(d)
        h_info = get_holiday_for_date(dt, worker.company, month_holidays)
        current_week.append({
            'day': d,
            'status': record.status if record else (AttendanceStatus.HOLIDAY if h_info else None),
            'ot': record.overtime_hours if record else 0,
            'holiday_name': h_info['name'] if h_info else None,
            'is_paid_holiday': h_info['is_paid'] if h_info else False
        })
        if len(current_week) == 7:
            calendar_weeks.append(current_week)
            current_week = []
    
    if current_week:
        while len(current_week) < 7:
            current_week.append(None)
        calendar_weeks.append(current_week)

    active_loan = worker.loans.filter(is_active=True).first()
    prior_earned = 0.0
    prev_month_str = (month_start - timedelta(days=1)).strftime('%Y-%m')
    if prev_month_str >= '2026-05':
        r_prev = get_worker_report_data(worker, prev_month_str)
        prior_due = round(r_prev['total_earned'])
        if r_prev['status_code'] == 'FULLY_PAID':
            prior_earned = max(prior_due, round(r_prev['total_paid'] + r_prev['total_repaid']))
        else:
            prior_earned = prior_due
    all_w_pmts_to_date = round(sum(p.amount for p in LaborPayment.objects.filter(worker=worker).exclude(payment_type__in=['NEW_LOAN', 'LOAN_REPAYMENT'])))
    avail_pmt_pool = max(0.0, all_w_pmts_to_date - prior_earned)

    if earned_wages > 0:
        eff_w_discharged = max(total_paid_regular + loan_repaid_this_month, min(earned_wages, avail_pmt_pool + loan_repaid_this_month))
        total_paid_regular = max(total_paid_regular, eff_w_discharged - loan_repaid_this_month)
        if total_paid_regular < 1.0:
            total_paid_regular = 0.0
        total_discharged = total_paid_regular + loan_repaid_this_month
        worker_bal = max(0.0, round(earned_wages) - round(total_discharged))
    else:
        total_paid_regular = total_paid_regular
        total_discharged = total_paid_regular
        worker_bal = 0.0
    if abs(worker_bal) < 1.0:
        worker_bal = 0.0

    # Settlement Lock Integration
    from apps.authentication.models import MonthlySettlementLock
    lock_obj = MonthlySettlementLock.objects.filter(worker=worker, month_str=month_str).first()
    is_settlement_locked = False

    if lock_obj and lock_obj.is_locked:
        is_settlement_locked = True
        worker_status_code = 'FULLY_PAID'
        if lock_obj.locked_earnings > 0 or lock_obj.locked_paid > 0:
            earned_wages = lock_obj.locked_earnings
            total_paid_regular = lock_obj.locked_paid - loan_repaid_this_month
            total_discharged = lock_obj.locked_paid
        else:
            # Self-heal lock_obj if stored with 0.0
            if earned_wages > 0 or total_discharged > 0:
                lock_obj.locked_earnings = float(earned_wages)
                lock_obj.locked_paid = float(total_discharged)
                lock_obj.save(update_fields=['locked_earnings', 'locked_paid'])
        worker_bal = 0.0
    else:
        if earned_wages == 0 and total_paid_regular == 0:
            worker_status_code = 'NO_ACTIVITY'
        elif worker_bal <= 0 and (earned_wages > 0 or total_paid_regular > 0):
            worker_status_code = 'FULLY_PAID'
            is_settlement_locked = True
            # Auto-lock settlement when fully paid with exact non-zero amounts
            MonthlySettlementLock.objects.update_or_create(
                worker=worker,
                month_str=month_str,
                defaults={
                    'is_locked': True,
                    'locked_earnings': float(earned_wages),
                    'locked_paid': float(total_discharged)
                }
            )
        elif total_discharged > 0 and worker_bal > 0:
            worker_status_code = 'PARTIAL'
        else:
            worker_status_code = 'PENDING'

    return {
        'worker': worker,
        'balance': worker_bal,
        'total_earned': earned_wages,
        'total_paid': total_paid_regular,
        'total_repaid': loan_repaid_this_month,
        'is_locked': is_settlement_locked,
        'lock_obj': lock_obj,
        'stats': {
            'present': days_present,
            'half': half_days,
            'absent': days_absent,
            'holiday': holiday_count,
            'working_days': net_working_days,
            'eff_present': eff_present,
            'ot': total_ot,
            'earned': earned_wages,
            'monthly_allowance': earned_allowance,
            'base_allowance': float(worker.monthly_allowance),
            'is_pro_rata_allowance': is_pro_rata,
            'loan_repaid': loan_repaid_this_month,
            'loan_balance': active_loan.remaining_balance if active_loan else 0,
            'balance': worker_bal,
            'status_code': worker_status_code,
            'is_fully_paid': (worker_status_code == 'FULLY_PAID'),
            'casting_pay': casting_pay,
            'total_casting_wt': total_casting_wt,
        },
        'status_code': worker_status_code,
        'is_fully_paid': (worker_status_code == 'FULLY_PAID'),
        'calendar_weeks': calendar_weeks,
        'attendance_ledger': attendance_ledger,
        'payments': payments,
        'month_name': selected_date.strftime('%B %Y'),
        'month_val': month_str,
        'today': timezone.now(),
        'casting_txs_detailed': casting_txs_detailed,
    }


@login_required
def worker_monthly_report(request, worker_id):
    worker = get_object_or_404(Worker, id=worker_id)
    month_str = request.GET.get('month', timezone.now().strftime('%Y-%m'))
    
    # If this is a Job Worker, redirect to Job Worker Statement Report
    if worker.worker_type == WorkerType.JOB_WORKER:
        return redirect(f"{reverse('job_worker_monthly_report', args=[worker.id])}?month={month_str}")

    active_company = request.company
    if active_company:
        all_workers = Worker.objects.filter(company=active_company, active=True, worker_type=WorkerType.IN_HOUSE).order_by('name')
    else:
        all_workers = Worker.objects.filter(active=True, worker_type=WorkerType.IN_HOUSE).order_by('name')

    if not all_workers.filter(id=worker.id).exists():
        all_workers = Worker.objects.filter(company=worker.company, active=True, worker_type=WorkerType.IN_HOUSE).order_by('name')

    worker_ids = list(all_workers.values_list('id', flat=True))
    prev_worker_id = None
    next_worker_id = None
    if len(worker_ids) > 1:
        try:
            curr_idx = worker_ids.index(worker.id)
            prev_worker_id = worker_ids[curr_idx - 1] if curr_idx > 0 else worker_ids[-1]
            next_worker_id = worker_ids[curr_idx + 1] if curr_idx < len(worker_ids) - 1 else worker_ids[0]
        except ValueError:
            pass

    context = get_worker_report_data(worker, month_str)
    context.update({
        'all_workers': all_workers,
        'prev_worker_id': prev_worker_id,
        'next_worker_id': next_worker_id,
    })
    return render(request, 'worker_report.html', context)


@login_required
def worker_monthly_report_all(request):
    active_company = request.company
    if active_company:
        all_workers = Worker.objects.filter(company=active_company, active=True, worker_type=WorkerType.IN_HOUSE).order_by('name')
    else:
        all_workers = Worker.objects.filter(active=True, worker_type=WorkerType.IN_HOUSE).order_by('name')

    month_str = request.GET.get('month', timezone.now().strftime('%Y-%m'))
    try:
        month_dt = datetime.strptime(month_str, '%Y-%m')
    except Exception:
        month_str = timezone.now().strftime('%Y-%m')
        month_dt = datetime.strptime(month_str, '%Y-%m')

    reports = []
    for worker in all_workers:
        report_data = get_worker_report_data(worker, month_str)
        reports.append(report_data)

    context = {
        'reports': reports,
        'month_name': month_dt.strftime('%B %Y'),
        'month_val': month_str,
        'today': timezone.now(),
    }
    return render(request, 'worker_report_all.html', context)


def get_job_worker_report_data(jw, month_str):
    is_all_time = (month_str == 'all')
    is_since_last = (month_str == 'last_payment')
    
    from django.utils.timezone import make_aware
    
    if is_all_time:
        month_start = datetime(2000, 1, 1).date()
        month_end = timezone.now().date()
        month_start_dt = make_aware(datetime.combine(month_start, datetime.min.time()))
        month_end_dt = timezone.now()
        month_name = "All-Time / Cumulative"
        month_dt = None
        payments = LaborPayment.objects.filter(worker=jw)
        num_days = 0
    elif is_since_last:
        latest_payment = LaborPayment.objects.filter(worker=jw).order_by('-date', '-id').first()
        if latest_payment:
            month_start = latest_payment.date
        else:
            month_start = datetime(2000, 1, 1).date()
        month_end = timezone.now().date()
        month_start_dt = make_aware(datetime.combine(month_start, datetime.min.time()))
        month_end_dt = timezone.now()
        month_name = f"Since Last Payment ({month_start.strftime('%d %b %Y')})"
        month_dt = None
        payments = LaborPayment.objects.filter(worker=jw, date__gte=month_start)
        num_days = 0
    else:
        try:
            month_dt = datetime.strptime(month_str, '%Y-%m')
        except Exception:
            month_str = timezone.now().strftime('%Y-%m')
            month_dt = datetime.strptime(month_str, '%Y-%m')

        month_start = month_dt.date().replace(day=1)
        num_days = calendar.monthrange(month_dt.year, month_dt.month)[1]
        month_end = month_dt.date().replace(day=num_days)
        
        month_start_dt = make_aware(datetime.combine(month_start, datetime.min.time()))
        month_end_dt = make_aware(datetime.combine(month_end, datetime.max.time()))
        month_name = month_dt.strftime('%B %Y')
        payments = LaborPayment.objects.filter(worker=jw).filter(
            Q(settlement_period=month_str) |
            Q(settlement_period__isnull=True, date__year=month_dt.year, date__month=month_dt.month) |
            Q(settlement_period='', date__year=month_dt.year, date__month=month_dt.month)
        )
        
    financial_opening_bal = 0.0
    all_jw_tx = StockTransaction.objects.filter(worker=jw).order_by('created_at')
    
    # Calculate financial opening balance before month_start_dt
    from apps.production.models import ItemWorkerAllocation
    prev_txs = all_jw_tx.filter(created_at__lt=month_start_dt)
    
    # 1. Machining earnings before period
    for tx in prev_txs.filter(transaction_type__endswith='_in'):
        # Check if raw material is active for conversion
        if tx.item.is_raw_material and tx.item.derived_items.exists():
            continue
        alloc = ItemWorkerAllocation.objects.filter(worker=jw, item=tx.item).first()
        rate = float(alloc.rate_per_piece) if alloc else 0.0
        if not rate and (tx.item.item_type == 'SET' or tx.item.components.exists()):
            comp_sum = 0.0
            has_comp_alloc = False
            for comp in tx.item.components.all():
                c_alloc = ItemWorkerAllocation.objects.filter(worker=jw, item=comp.component_item).first()
                if c_alloc:
                    comp_sum += comp.quantity * float(c_alloc.rate_per_piece)
                    has_comp_alloc = True
            if has_comp_alloc:
                rate = comp_sum

        financial_opening_bal += tx.quantity * rate
        
    # 2. Casting earnings before period
    if jw.casting_rate_per_kg > 0:
        prev_casting = prev_txs.filter(transaction_type=TransactionType.CASTING_ENTRY)
        prev_casting_wt = sum(tx.actual_scale_weight if tx.actual_scale_weight > 0 else tx.weight for tx in prev_casting)
        financial_opening_bal += prev_casting_wt * float(jw.casting_rate_per_kg)
        
    # 3. Payments before period
    prev_payments = LaborPayment.objects.filter(worker=jw).filter(
        Q(settlement_period__lt=month_str) |
        Q(settlement_period__isnull=True, date__lt=month_start) |
        Q(settlement_period='', date__lt=month_start)
    ).exclude(payment_type='NEW_LOAN')
    financial_opening_bal -= sum(p.amount for p in prev_payments)
    
    # Include all transactions recorded for this Job Worker
    all_jw_tx = StockTransaction.objects.filter(worker=jw).order_by('created_at')
    
    # Group items by name (case-insensitive or exact name) to handle duplicate item records gracefully
    item_names = sorted(list(set(all_jw_tx.values_list('item__name', flat=True))))

    item_ledger = []
    total_earned = 0.0

    from apps.production.models import Item

    for item_name in item_names:
        # Find all Item database records with this exact name
        matching_items = Item.objects.filter(name=item_name)
        matching_item_ids = list(matching_items.values_list('id', flat=True))

        # Calculate opening balance across all duplicate items
        opening_bal = 0
        prev_tx = all_jw_tx.filter(item_id__in=matching_item_ids, created_at__lt=month_start_dt)
        for tx in prev_tx:
            in_qty = tx.quantity if tx.transaction_type.endswith('_out') else 0
            out_qty = tx.quantity if tx.transaction_type.endswith('_in') else 0
            rej_qty = tx.rejection_quantity if tx.transaction_type.endswith('_in') else 0
            opening_bal += (in_qty - out_qty - rej_qty)

        # Monthly transactions across all duplicate items
        month_tx = all_jw_tx.filter(
            item_id__in=matching_item_ids,
            created_at__gte=month_start_dt,
            created_at__lte=month_end_dt
        )
        
        issues = []
        for tx in month_tx.filter(transaction_type__endswith='_out'):
            issues.append({
                'date': timezone.localtime(tx.created_at).date(),
                'qty': tx.quantity
            })
            
        receipts = []
        total_raw_weight = 0.0
        raw_uom = ""
        for tx in month_tx.filter(transaction_type__endswith='_in').select_related('linked_consumption', 'linked_consumption__item'):
            raw_info = ""
            if tx.linked_consumption:
                raw_info = f"({tx.linked_consumption.quantity} {tx.linked_consumption.item.uom})"
                total_raw_weight += tx.linked_consumption.quantity
                raw_uom = tx.linked_consumption.item.uom
                
            receipts.append({
                'date': timezone.localtime(tx.created_at).date(),
                'qty': tx.quantity,
                'rejections': tx.rejection_quantity,
                'raw_info': raw_info
            })

        # Skip if no activity and no opening balance
        if len(issues) == 0 and len(receipts) == 0 and opening_bal == 0:
            continue

        total_issued = sum(x['qty'] for x in issues)
        total_received = sum(x['qty'] for x in receipts)
        total_rejected = sum(x['rejections'] for x in receipts)

        balance = opening_bal + total_issued - total_received - total_rejected
        
        # Get rate per piece (lookup historical rate effective on month_end, or sum component rates for sets)
        alloc = ItemWorkerAllocation.objects.filter(worker=jw, item_id__in=matching_item_ids).first()
        item = matching_items.first()
        rate = get_jw_item_rate_for_date(jw, item, month_end, alloc.rate_per_piece if alloc else 0.0)
        if not rate and item and (item.item_type == 'SET' or item.components.exists()):
            comp_sum = 0.0
            has_comp_alloc = False
            for comp in item.components.all():
                c_rate = get_jw_item_rate_for_date(jw, comp.component_item, month_end, 0.0)
                if c_rate > 0:
                    comp_sum += comp.quantity * c_rate
                    has_comp_alloc = True
            if has_comp_alloc:
                rate = comp_sum

        is_raw_conv = item and item.is_raw_material and item.derived_items.exists()
        if is_raw_conv:
            rate = 0.0
        
        earned = total_received * rate
        total_earned += earned

        # Representative item object to use in template (contains correct name, etc.)
        item = matching_items.first()

        item_ledger.append({
            'item': item,
            'rate': rate,
            'opening_bal': opening_bal,
            'issues': issues,
            'receipts': [] if is_raw_conv else receipts,
            'total_issued': total_issued,
            'total_received': 0 if is_raw_conv else total_received,
            'total_rejected': 0 if is_raw_conv else total_rejected,
            'balance': balance,
            'earned': earned,
            'total_raw_weight': total_raw_weight,
            'raw_uom': raw_uom,
        })

    # Sort ledger: raw materials first (is_raw_material=True), then by item name
    item_ledger = sorted(item_ledger, key=lambda x: (not x['item'].is_raw_material, x['item'].name))

    total_paid = sum(p.amount for p in payments if p.payment_type not in ['LOAN_REPAYMENT', 'NEW_LOAN'])
    total_repaid = sum(p.amount for p in payments if p.payment_type == 'LOAN_REPAYMENT')

    # Casting weight-based pay
    casting_pay = 0
    total_casting_wt = 0
    casting_txs_detailed = []
    casting_txs = []
    if jw.casting_rate_per_kg > 0:
        casting_txs = StockTransaction.objects.filter(
            worker=jw,
            transaction_type=TransactionType.CASTING_ENTRY,
            created_at__date__gte=month_start,
            created_at__date__lte=month_end
        ).order_by('created_at')
        total_casting_wt = sum(tx.actual_scale_weight if tx.actual_scale_weight > 0 else tx.weight for tx in casting_txs)
        casting_pay = total_casting_wt * float(jw.casting_rate_per_kg)
        for tx in casting_txs:
            wt = tx.actual_scale_weight if tx.actual_scale_weight > 0 else tx.weight
            casting_txs_detailed.append({
                'date': tx.created_at,
                'item_name': tx.item.name,
                'item_code': tx.item.code,
                'weight': wt,
                'rate': float(jw.casting_rate_per_kg),
                'earnings': wt * float(jw.casting_rate_per_kg)
            })

    total_earned += casting_pay

    # Fetch active loan balance for Job Worker
    active_loan = jw.loans.filter(is_active=True).first()
    loan_balance = active_loan.remaining_balance if active_loan else 0.0

    # Daily casting and payment aggregation for calendar view
    from collections import defaultdict
    daily_casting = defaultdict(float)
    daily_casting_details = defaultdict(list)
    for tx in casting_txs:
        tx_date = timezone.localtime(tx.created_at).date()
        wt = tx.actual_scale_weight if tx.actual_scale_weight > 0 else tx.weight
        daily_casting[tx_date] += wt
        daily_casting_details[tx_date].append({
            'item_name': tx.item.name,
            'item_code': tx.item.code,
            'weight': wt
        })

    daily_payments = defaultdict(float)
    for p in payments:
        daily_payments[p.date] += p.amount

    # Fetch holidays for the month to highlight calendar
    month_holidays = list(Holiday.objects.filter(date__gte=month_start, date__lte=month_end))

    first_day_of_month = month_start.weekday()
    first_day_of_month = (first_day_of_month + 1) % 7
    calendar_weeks = []
    current_week = [None] * first_day_of_month

    for d in range(1, num_days + 1):
        dt = month_start.replace(day=d)
        day_wt = daily_casting.get(dt, 0.0)
        day_pmt = daily_payments.get(dt, 0.0)

        # Get holiday info
        h_info = get_holiday_for_date(dt, jw.company, month_holidays)
        is_holiday = False
        holiday_name = None
        if h_info:
            is_holiday = True
            holiday_name = h_info['name']

        # Detail formatting for hover popup
        raw_details = daily_casting_details.get(dt, [])
        grouped_details = defaultdict(float)
        for item in raw_details:
            key = f"{item['item_name']} ({item['item_code']})"
            grouped_details[key] += item['weight']

        details_list = [{'item_key': k, 'weight': w} for k, w in grouped_details.items()]

        current_week.append({
            'day': d,
            'casting_weight': day_wt,
            'advance_paid': day_pmt,
            'details': details_list,
            'is_holiday': is_holiday,
            'holiday_name': holiday_name,
        })
        if len(current_week) == 7:
            calendar_weeks.append(current_week)
            current_week = []

    if current_week:
        while len(current_week) < 7:
            current_week.append(None)
        calendar_weeks.append(current_week)

    # Build Matrix Grid Data for 1-Page Compact Report Format (Idea 1: Work Done Grid + Stock Bar)
    matrix_items = []
    for entry in item_ledger:
        matrix_items.append({
            'id': entry['item'].id,
            'code': entry['item'].code,
            'name': entry['item'].name,
            'rate': entry['rate'],
            'total_pcs': entry['total_received'],
            'total_issued': entry['total_issued'],
            'total_rejected': entry['total_rejected'],
            'opening_bal': entry['opening_bal'],
            'stock_in_hand': entry['balance'],
            'earned': entry['earned'],
        })

    matrix_days = []
    payments_by_day = defaultdict(float)
    for p in payments:
        payments_by_day[p.date] += float(p.amount)

    tx_in_by_day = defaultdict(lambda: defaultdict(int))
    tx_out_by_day = defaultdict(lambda: defaultdict(int))

    for tx in all_jw_tx.filter(created_at__gte=month_start_dt, created_at__lte=month_end_dt):
        tx_date = timezone.localtime(tx.created_at).date()
        if tx.transaction_type.endswith('_in'):
            tx_in_by_day[tx_date][tx.item.code] += tx.quantity
        elif tx.transaction_type.endswith('_out'):
            tx_out_by_day[tx_date][tx.item.code] += tx.quantity

    if num_days > 0:
        for d in range(1, num_days + 1):
            dt = month_start.replace(day=d)
            day_name = dt.strftime('%a')
            is_sun = (dt.weekday() == 6)
            is_wed = (dt.weekday() == 2)
            
            item_qty_list = []
            row_has_activity = False
            for m_item in matrix_items:
                code = m_item['code']
                in_qty = tx_in_by_day[dt][code]
                out_qty = tx_out_by_day[dt][code]

                item_qty_list.append({
                    'item_id': m_item['id'],
                    'code': code,
                    'in_qty': in_qty,
                    'out_qty': out_qty,
                })
                if in_qty > 0 or out_qty > 0:
                    row_has_activity = True

            day_pmt = payments_by_day.get(dt, 0.0)

            matrix_days.append({
                'day': d,
                'date': dt,
                'date_str': dt.strftime('%Y-%m-%d'),
                'day_name': day_name,
                'is_sunday': is_sun,
                'is_wednesday': is_wed,
                'item_qty_list': item_qty_list,
                'advance_paid': day_pmt,
                'has_activity': row_has_activity or day_pmt > 0
            })

    prior_jw_earned = 0.0
    prev_month_str = (month_start - timedelta(days=1)).strftime('%Y-%m')
    if prev_month_str >= '2026-05':
        r7_jw = get_job_worker_report_data(jw, prev_month_str)
        prior_due = round(r7_jw['financial_opening_bal'] + r7_jw['total_earned'])
        if r7_jw['status_code'] == 'FULLY_PAID':
            prior_jw_earned = max(prior_due, round(r7_jw['total_discharged']))
            financial_opening_bal = 0.0
        else:
            prior_jw_earned = prior_due
            financial_opening_bal = max(0.0, float(r7_jw.get('net_balance', 0.0)))

    cum_gross_due = max(0.0, financial_opening_bal + total_earned)
    all_jw_pmts_to_date = round(sum(p.amount for p in LaborPayment.objects.filter(worker=jw).exclude(payment_type__in=['NEW_LOAN', 'LOAN_REPAYMENT'])))
    avail_jw_pmt_pool = max(0.0, all_jw_pmts_to_date - prior_jw_earned)

    if cum_gross_due > 0:
        eff_jw_discharged = max(total_paid + total_repaid, min(cum_gross_due, avail_jw_pmt_pool + total_repaid))
        total_paid = max(total_paid, eff_jw_discharged - total_repaid)
        if total_paid < 1.0:
            total_paid = 0.0
        total_discharged = total_paid + total_repaid
        net_balance = max(0.0, round(cum_gross_due) - round(total_discharged))
    else:
        total_paid = total_paid
        total_discharged = total_paid
        net_balance = 0.0
    if abs(net_balance) < 1.0:
        net_balance = 0.0
    if total_earned == 0 and financial_opening_bal <= 0.99 and total_paid == 0:
        status_code = 'NO_ACTIVITY'
    elif net_balance <= 0 and (total_earned > 0 or financial_opening_bal > 0.99 or total_paid > 0):
        status_code = 'FULLY_PAID'
    elif total_discharged > 0 and net_balance > 0:
        status_code = 'PARTIAL'
    else:
        status_code = 'PENDING'

    return {
        'jw': jw,
        'month_name': month_name,
        'month_val': month_str,
        'item_ledger': item_ledger,
        'payments': payments,
        'total_earned': total_earned,
        'total_paid': total_paid,
        'total_repaid': total_repaid,
        'total_discharged': total_discharged,
        'financial_opening_bal': financial_opening_bal,
        'balance': net_balance,
        'status_code': status_code,
        'is_fully_paid': (status_code == 'FULLY_PAID'),
        'loan_balance': loan_balance,
        'today': timezone.now(),
        'casting_pay': casting_pay,
        'total_casting_wt': total_casting_wt,
        'casting_txs_detailed': casting_txs_detailed,
        'calendar_weeks': calendar_weeks,
        'matrix_items': matrix_items,
        'matrix_days': matrix_days,
        'has_opening_stock': any(item.get('opening_bal', 0) > 0 for item in matrix_items),
    }


@login_required
def job_worker_monthly_report(request, jw_id):
    jw = Worker.objects.filter(id=jw_id, worker_type=WorkerType.JOB_WORKER).first()
    if not jw:
        from django.http import Http404
        raise Http404("Job Worker not found")

    active_company = request.company
    if active_company:
        all_jws = list(Worker.objects.filter(company=active_company, worker_type=WorkerType.JOB_WORKER, active=True).order_by('name'))
    else:
        all_jws = list(Worker.objects.filter(worker_type=WorkerType.JOB_WORKER, active=True).order_by('name'))

    jw_ids = [j.id for j in all_jws]

    prev_jw_id = None
    next_jw_id = None
    if len(jw_ids) > 1:
        try:
            curr_idx = jw_ids.index(jw.id)
            prev_jw_id = jw_ids[curr_idx - 1] if curr_idx > 0 else jw_ids[-1]
            next_jw_id = jw_ids[curr_idx + 1] if curr_idx < len(jw_ids) - 1 else jw_ids[0]
        except ValueError:
            pass

    month_str = request.GET.get('month', timezone.now().strftime('%Y-%m'))
    context = get_job_worker_report_data(jw, month_str)
    context.update({
        'all_jws': all_jws,
        'prev_jw_id': prev_jw_id,
        'next_jw_id': next_jw_id,
    })
    return render(request, 'job_worker_report.html', context)


@login_required
def job_worker_monthly_report_all(request):
    active_company = request.company
    if active_company:
        all_jws = Worker.objects.filter(company=active_company, worker_type=WorkerType.JOB_WORKER, active=True).order_by('name')
    else:
        all_jws = Worker.objects.filter(worker_type=WorkerType.JOB_WORKER, active=True).order_by('name')

    month_str = request.GET.get('month', timezone.now().strftime('%Y-%m'))
    try:
        month_dt = datetime.strptime(month_str, '%Y-%m')
    except Exception:
        month_str = timezone.now().strftime('%Y-%m')
        month_dt = datetime.strptime(month_str, '%Y-%m')

    reports = []
    for jw in all_jws:
        report_data = get_job_worker_report_data(jw, month_str)
        reports.append(report_data)

    context = {
        'reports': reports,
        'month_name': month_dt.strftime('%B %Y'),
        'month_val': month_str,
        'today': timezone.now(),
    }
    return render(request, 'job_worker_report_all.html', context)


@staff_member_required
@require_POST
def toggle_settlement_lock(request):
    """
    Toggles explicit settlement lock for a worker and month.
    Allows Admins to unlock a fully-paid month for corrections, or re-lock it.
    """
    worker_id = request.POST.get('worker_id')
    month_str = request.POST.get('month_str')
    action = request.POST.get('action', 'unlock')

    from apps.authentication.models import MonthlySettlementLock, Worker
    worker = get_object_or_404(Worker, id=worker_id)

    lock_obj, created = MonthlySettlementLock.objects.get_or_create(
        worker=worker,
        month_str=month_str
    )

    if action == 'unlock':
        lock_obj.is_locked = False
        lock_obj.unlocked_at = timezone.now()
        lock_obj.locked_by = request.user
        lock_obj.save()
        messages.success(request, f"🔓 Settlement for {worker.name} ({month_str}) has been UNLOCKED for data entry corrections.")
    else:
        # Re-lock settlement
        report = get_worker_report_data(worker, month_str)
        lock_obj.is_locked = True
        lock_obj.locked_earnings = float(report['total_earned'])
        lock_obj.locked_paid = float(report['total_paid'] + report['total_repaid'])
        lock_obj.locked_by = request.user
        lock_obj.save()
        messages.success(request, f"🔒 Settlement for {worker.name} ({month_str}) has been RE-LOCKED.")

    return redirect(f"{reverse('labor_ledger')}?month={month_str}&tab=staff")


@login_required
def attendance_view(request):
    active_company = request.company
    if active_company:
        active_team = 'c1' if active_company.id == 2 else 'c2'
        company_id = active_company.id
        workers = Worker.objects.filter(company_id=company_id, active=True, worker_type=WorkerType.IN_HOUSE).order_by('name')
    else:
        active_team = 'all'
        workers = Worker.objects.filter(active=True, worker_type=WorkerType.IN_HOUSE).order_by('name')
    
    company1 = LegalEntity.objects.filter(id=2).first()
    company2 = LegalEntity.objects.filter(id=1).first()
    
    context = {
        'workers': workers,
        'today': timezone.now().date().strftime('%Y-%m-%d'),
        'active_team': active_team,
        'company1': company1,
        'company2': company2,
    }
    return render(request, 'attendance.html', context)

