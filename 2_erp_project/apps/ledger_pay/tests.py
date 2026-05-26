from django.test import TestCase
from django.utils import timezone
from apps.workforce.models import Worker, Attendance, SalaryModel, AttendanceStatus
from apps.ledger_pay.models import Loan, LaborPayment, PaymentType

class LedgerPayTestCase(TestCase):
    def setUp(self):
        # Create a Daily Wage Worker
        self.daily_worker = Worker.objects.create(
            name="Ramesh Kumar",
            salary_model=SalaryModel.DAILY,
            daily_rate=600.0,
            standard_shift_hours=8,
            monthly_allowance=100.0
        )
        
        # Create a Fixed Salary Worker
        self.fixed_worker = Worker.objects.create(
            name="Suresh Singh",
            salary_model=SalaryModel.FIXED,
            monthly_fixed_salary=18000.0,
            standard_shift_hours=8,
            overtime_rate=100.0,
            monthly_allowance=200.0
        )

    def test_overtime_rate_calculation_on_save(self):
        # If overtime_rate is 0 and DAILY is used, overtime_rate is calculated as daily_rate / standard_shift_hours
        # 600 / 8 = 75.0
        self.assertEqual(self.daily_worker.overtime_rate, 75.0)

    def test_daily_wage_earnings_calculation(self):
        # Setup attendance records for daily worker
        today = timezone.now().date()
        
        # 2 present days, 1 half day, 1 absent day, and 2 OT hours
        Attendance.objects.create(worker=self.daily_worker, date=today.replace(day=1), status=AttendanceStatus.PRESENT, overtime_hours=2)
        Attendance.objects.create(worker=self.daily_worker, date=today.replace(day=2), status=AttendanceStatus.PRESENT, overtime_hours=0)
        Attendance.objects.create(worker=self.daily_worker, date=today.replace(day=3), status=AttendanceStatus.HALF_DAY, overtime_hours=0)
        Attendance.objects.create(worker=self.daily_worker, date=today.replace(day=4), status=AttendanceStatus.ABSENT, overtime_hours=0)

        # Let's compute earnings mimicking views.py labor_ledger:
        # present: 2, half: 1, absent: 1, total_ot: 2
        # earnings = (2 * 600) + (1 * 0.5 * 600) + (2 * 75.0) + 100.0 = 1200 + 300 + 150 + 100 = 1750
        attendance_records = Attendance.objects.filter(worker=self.daily_worker)
        days_present = attendance_records.filter(status='PRESENT').count()
        half_days = attendance_records.filter(status='HALF_DAY').count()
        total_ot = sum(a.overtime_hours for a in attendance_records)
        
        earnings = (days_present * self.daily_worker.daily_rate) + (half_days * 0.5 * self.daily_worker.daily_rate)
        earnings += (total_ot * self.daily_worker.overtime_rate)
        earnings += self.daily_worker.monthly_allowance
        
        self.assertEqual(earnings, 1750.0)

    def test_fixed_wage_earnings_calculation(self):
        # Setup attendance records for fixed worker
        today = timezone.now().date()
        
        # 1 day absent, 3 hours OT
        Attendance.objects.create(worker=self.fixed_worker, date=today.replace(day=1), status=AttendanceStatus.ABSENT)
        Attendance.objects.create(worker=self.fixed_worker, date=today.replace(day=2), status=AttendanceStatus.PRESENT, overtime_hours=3)

        # Let's compute earnings mimicking views.py labor_ledger:
        # daily_deduct = 18000 / 30 = 600
        # days_absent = 1
        # OT = 3 hrs * 100 rate = 300
        # allowance = 200
        # earnings = 18000 - (1 * 600) + 300 + 200 = 17900
        attendance_records = Attendance.objects.filter(worker=self.fixed_worker)
        days_absent = attendance_records.filter(status='ABSENT').count()
        total_ot = sum(a.overtime_hours for a in attendance_records)
        
        daily_deduct = self.fixed_worker.monthly_fixed_salary / 30
        earnings = self.fixed_worker.monthly_fixed_salary - (days_absent * daily_deduct)
        earnings += (total_ot * self.fixed_worker.overtime_rate)
        earnings += self.fixed_worker.monthly_allowance
        
        self.assertEqual(earnings, 17900.0)

    def test_loan_amortization_and_payments(self):
        # Create a new active loan
        loan = Loan.objects.create(
            worker=self.daily_worker,
            total_amount=5000.0,
            emi_amount=1000.0,
            remaining_balance=5000.0,
            is_active=True
        )
        
        # Issue a loan payment (repayment of 1500)
        payment = LaborPayment.objects.create(
            worker=self.daily_worker,
            amount=1500.0,
            payment_type=PaymentType.LOAN_REPAYMENT,
            payment_mode="CASH"
        )
        
        # Apply repayment logic (mimicking record_labor_payment view function)
        loan.remaining_balance -= payment.amount
        if loan.remaining_balance <= 0:
            loan.is_active = False
        loan.save()
        
        self.assertEqual(loan.remaining_balance, 3500.0)
        self.assertTrue(loan.is_active)

        # Repay remaining balance
        payment2 = LaborPayment.objects.create(
            worker=self.daily_worker,
            amount=4000.0,
            payment_type=PaymentType.LOAN_REPAYMENT,
            payment_mode="CASH"
        )
        loan.remaining_balance -= payment2.amount
        if loan.remaining_balance <= 0:
            loan.remaining_balance = 0
            loan.is_active = False
        loan.save()
        
        self.assertEqual(loan.remaining_balance, 0.0)
        self.assertFalse(loan.is_active)
