from django.db import models
from django.utils import timezone
from apps.products.models import Item
from apps.workforce.models import Worker, JobWorker

class ItemWorkerAllocation(models.Model):
    item = models.ForeignKey(
        Item,
        on_delete=models.CASCADE,
        related_name='worker_allocations'
    )
    worker = models.ForeignKey(
        Worker,
        on_delete=models.CASCADE,
        related_name='item_allocations',
        null=True,
        blank=True
    )
    job_worker = models.ForeignKey(
        JobWorker,
        on_delete=models.CASCADE,
        related_name='external_item_allocations',
        null=True,
        blank=True
    )
    rate_per_piece = models.FloatField(default=0)

    class Meta:
        verbose_name = "Item Worker Rate"

    def __str__(self):
        try:
            worker_name = self.worker.name if self.worker else (self.job_worker.name if self.job_worker else "Unknown")
        except getattr(Worker, 'DoesNotExist', Exception):
            worker_name = "Deleted Worker"
        except getattr(JobWorker, 'DoesNotExist', Exception):
            worker_name = "Deleted Job Worker"
        except Exception:
            worker_name = "Deleted Worker"
            
        try:
            item_name = self.item.name
        except Exception:
            item_name = "Deleted Item"
            
        return f"{item_name} - {worker_name} @ ₹{self.rate_per_piece}"



class Loan(models.Model):
    worker = models.ForeignKey(Worker, on_delete=models.CASCADE, related_name='loans', null=True, blank=True)
    job_worker = models.ForeignKey(JobWorker, on_delete=models.CASCADE, related_name='loans', null=True, blank=True)
    total_amount = models.FloatField()
    emi_amount = models.FloatField(help_text="Standard monthly deduction")
    remaining_balance = models.FloatField()
    issued_date = models.DateField(default=timezone.now)
    is_active = models.BooleanField(default=True)
    description = models.TextField(blank=True, null=True)

    def __str__(self):
        name = self.worker.name if self.worker else self.job_worker.name
        return f"Loan for {name} (Remaining: ₹{self.remaining_balance})"


class PaymentType(models.TextChoices):
    SALARY = "SALARY", "Salary"
    ADVANCE = "ADVANCE", "Advance"
    NEW_LOAN = "NEW_LOAN", "New Loan"
    JOB_WORK = "JOB_WORK", "Job Work Payment"
    LOAN_REPAYMENT = "LOAN_REPAYMENT", "Loan Repayment"


class LaborPayment(models.Model):
    worker = models.ForeignKey(Worker, on_delete=models.SET_NULL, null=True, blank=True)
    job_worker = models.ForeignKey(JobWorker, on_delete=models.SET_NULL, null=True, blank=True)
    amount = models.FloatField()
    date = models.DateField(default=timezone.now)
    payment_type = models.CharField(max_length=20, choices=PaymentType.choices)
    payment_mode = models.CharField(max_length=50, default="CASH")
    reference_no = models.CharField(max_length=100, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)

    def __str__(self):
        name = self.worker.name if self.worker else (self.job_worker.name if self.job_worker else "Unknown")
        return f"{self.payment_type} of ₹{self.amount} for {name}"
