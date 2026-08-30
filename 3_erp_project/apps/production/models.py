import uuid
from django.db import models
from django.db.models import F
from django.utils import timezone
from apps.master_data.models import LegalEntity, Item, Warehouse, Client, ItemStock
from apps.authentication.models import Worker, ProcessType


class TransactionType(models.TextChoices):
    CASTING_ENTRY = "casting_entry", "Casting Entry"
    MACHINING_OUT = "machining_out", "Machining Issue"
    MACHINING_IN = "machining_in", "Machining Receive"
    POLISHING_OUT = "polishing_out", "Polishing Issue"
    POLISHING_IN = "polishing_in", "Polishing Receive"
    PACKAGING_IN = "packaging_in", "Packaging Receive"
    DISPATCH_OUT = "dispatch_out", "Dispatch Out"
    KITTING_CONSUME = "kitting_consume", "Assembly Consume"
    KITTING_PRODUCE = "kitting_produce", "Assembly Produce"
    STOCK_ADJUSTMENT = "stock_adjustment", "Stock Adjustment"
    PURCHASE_ENTRY = "purchase_entry", "Purchase Entry"


class StockTransaction(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, null=True, blank=True)

    item = models.ForeignKey(Item, on_delete=models.CASCADE)
    transaction_type = models.CharField(max_length=50, choices=TransactionType.choices)
    from_warehouse = models.ForeignKey(
        Warehouse, on_delete=models.SET_NULL, related_name='from_transactions', blank=True, null=True
    )
    to_warehouse = models.ForeignKey(
        Warehouse, on_delete=models.SET_NULL, related_name='to_transactions', blank=True, null=True
    )
    worker = models.ForeignKey(Worker, on_delete=models.SET_NULL, blank=True, null=True)
    client = models.ForeignKey(Client, on_delete=models.SET_NULL, blank=True, null=True)
    heat_no = models.CharField(max_length=50, blank=True, null=True)
    quantity = models.IntegerField(default=0)
    rejection_quantity = models.IntegerField(default=0)
    weight = models.FloatField(default=0.0)
    actual_scale_weight = models.FloatField(default=0.0)
    lot_quantity = models.IntegerField(default=0)
    notes = models.TextField(blank=True, null=True)
    linked_consumption = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='linked_production')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.item.code} - {self.get_transaction_type_display()}"


class ItemWorkerAllocation(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, null=True, blank=True)
    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name='worker_allocations')
    worker = models.ForeignKey(Worker, on_delete=models.CASCADE, related_name='item_allocations', null=True, blank=True)
    rate_per_piece = models.FloatField(default=0.0)

    class Meta:
        verbose_name = "Item Worker Rate"
        verbose_name_plural = "Item Worker Rates"

    def __str__(self):
        worker_name = self.worker.name if self.worker else "Unknown"
        return f"{self.item.name} - {worker_name} @ ₹{self.rate_per_piece}"


class ItemWorkerRateHistory(models.Model):
    allocation = models.ForeignKey(ItemWorkerAllocation, on_delete=models.CASCADE, related_name="rate_history", null=True, blank=True)
    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name="rate_history")
    worker = models.ForeignKey(Worker, on_delete=models.CASCADE, related_name="item_rate_history", null=True, blank=True)
    rate_per_piece = models.FloatField(default=0.0)
    effective_from = models.DateField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-effective_from', '-created_at']

    def __str__(self):
        w_name = self.worker.name if self.worker else "Unknown"
        return f"{self.item.code} - {w_name}: ₹{self.rate_per_piece} (Eff: {self.effective_from})"


class AttendanceStatus(models.TextChoices):
    PRESENT = "PRESENT", "Present"
    ABSENT = "ABSENT", "Absent"
    HALF_DAY = "HALF_DAY", "Half Day"
    HOLIDAY = "HOLIDAY", "Holiday"


class Attendance(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, null=True, blank=True)
    worker = models.ForeignKey(Worker, on_delete=models.CASCADE, related_name='attendance_records')
    date = models.DateField(default=timezone.now)
    status = models.CharField(max_length=20, choices=AttendanceStatus.choices, default=AttendanceStatus.PRESENT)
    overtime_hours = models.FloatField(default=0.0)
    notes = models.TextField(blank=True, null=True)

    class Meta:
        unique_together = ('worker', 'date')
        verbose_name_plural = "Attendance Logs"


class Holiday(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, null=True, blank=True)
    date = models.DateField()
    name = models.CharField(max_length=255)
    company = models.ForeignKey(
        LegalEntity,
        on_delete=models.CASCADE,
        related_name='holidays',
        null=True,
        blank=True,
        help_text="The company this holiday applies to. Leave empty for a global holiday."
    )
    is_paid = models.BooleanField(default=True, help_text="Whether this holiday is paid for daily-wage workers.")
    is_working_day_override = models.BooleanField(
        default=False, 
        help_text="If checked, this day is treated as a regular working day, overriding any company weekly off configuration."
    )

    class Meta:
        unique_together = ('date', 'company')
        ordering = ['-date']

    def __str__(self):
        comp_str = f" ({self.company.name})" if self.company else " (Global)"
        return f"{self.date} - {self.name}{comp_str}"


class Loan(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, null=True, blank=True)
    worker = models.ForeignKey(Worker, on_delete=models.CASCADE, related_name='loans', null=True, blank=True)
    total_amount = models.FloatField()
    emi_amount = models.FloatField(help_text="Standard monthly deduction")
    remaining_balance = models.FloatField()
    issued_date = models.DateField(default=timezone.now)
    is_active = models.BooleanField(default=True)
    description = models.TextField(blank=True, null=True)

    def recalculate_balance(self):
        if not self.worker:
            return self.remaining_balance
        repayments = LaborPayment.objects.filter(
            worker=self.worker,
            payment_type=PaymentType.LOAN_REPAYMENT,
            date__gte=self.issued_date
        )
        total_repaid = sum(p.amount for p in repayments)
        self.remaining_balance = max(0.0, round(float(self.total_amount) - float(total_repaid), 2))
        self.is_active = (self.remaining_balance > 0)
        self.save(update_fields=['remaining_balance', 'is_active'])
        return self.remaining_balance

    def __str__(self):
        name = self.worker.name if self.worker else "Unknown"
        return f"Loan for {name} (Remaining: ₹{self.remaining_balance})"


class PaymentType(models.TextChoices):
    SALARY = "SALARY", "Salary Settlement"
    ADVANCE = "ADVANCE", "Advance Paid"
    NEW_LOAN = "NEW_LOAN", "New Loan Given"
    JOB_WORK = "JOB_WORK", "Job Work Settlement"
    LOAN_REPAYMENT = "LOAN_REPAYMENT", "Loan Repayment"


class LaborPayment(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, null=True, blank=True)
    worker = models.ForeignKey(Worker, on_delete=models.SET_NULL, null=True, blank=True)
    amount = models.FloatField()
    date = models.DateField(default=timezone.now)
    payment_type = models.CharField(max_length=20, choices=PaymentType.choices)
    payment_mode = models.CharField(max_length=50, default="CASH")
    reference_no = models.CharField(max_length=100, blank=True, null=True)
    settlement_period = models.CharField(max_length=7, blank=True, null=True, help_text="Y-m period being settled e.g. 2026-07")
    notes = models.TextField(blank=True, null=True)


class Carton(models.Model):
    class CartonStatus(models.TextChoices):
        READY = "READY", "In Warehouse"
        DISPATCHED = "DISPATCHED", "Dispatched"

    class CartonType(models.TextChoices):
        SINGLE = "SINGLE", "Single Item"
        SET = "SET", "Set Item"
        MIXED = "MIXED", "Mixed Carton"

    uuid = models.UUIDField(default=uuid.uuid4, editable=False, null=True, blank=True)
    carton_number = models.CharField(max_length=50, unique=True, blank=True)
    carton_type = models.CharField(max_length=20, choices=CartonType.choices, default=CartonType.SINGLE)
    carton_label = models.CharField(max_length=200, blank=True, null=True)
    
    cleaning = models.BooleanField(default=False)
    labeling = models.BooleanField(default=False)
    packing = models.BooleanField(default=False)
    
    total_quantity = models.IntegerField(default=0)
    total_weight = models.FloatField(default=0.0)
    
    status = models.CharField(max_length=20, choices=CartonStatus.choices, default=CartonStatus.READY)
    client = models.ForeignKey(Client, on_delete=models.SET_NULL, null=True, blank=True, related_name='cartons')
    sales_order = models.ForeignKey('orders.SalesOrder', on_delete=models.SET_NULL, null=True, blank=True, related_name='cartons')
    dispatched_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.carton_number or not str(self.carton_number).strip():
            if self.id:
                self.carton_number = f"CTN-{10000 + self.id}"
            else:
                last_c = Carton.objects.order_by("-id").first()
                base_id = (last_c.id + 1) if last_c else 1
                while True:
                    code = f"CTN-{10000 + base_id}"
                    if not Carton.objects.filter(carton_number=code).exists():
                        self.carton_number = code
                        break
                    base_id += 1

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.carton_number} ({self.get_carton_type_display()}) - {self.get_status_display()}"


class CartonItem(models.Model):
    carton = models.ForeignKey(Carton, on_delete=models.CASCADE, related_name='items')
    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name='carton_contents')
    quantity = models.IntegerField(default=0)
    weight = models.FloatField(default=0.0)

    def __str__(self):
        return f"{self.item.code} x {self.quantity} in {self.carton.carton_number}"


from django.db.models.signals import post_save
from django.dispatch import receiver

@receiver(post_save, sender=StockTransaction)
def handle_stock_transaction_effects(sender, instance, created, **kwargs):
    if not created:
        return
        
    # 1. Update real-time ItemStock balance per warehouse
    if instance.to_warehouse:
        stock_to, _ = ItemStock.objects.get_or_create(
            item=instance.item, warehouse=instance.to_warehouse,
            defaults={'quantity_on_hand': 0}
        )
        ItemStock.objects.filter(pk=stock_to.pk).update(
            quantity_on_hand=F('quantity_on_hand') + instance.quantity
        )
        
    if instance.from_warehouse:
        stock_from, _ = ItemStock.objects.get_or_create(
            item=instance.item, warehouse=instance.from_warehouse,
            defaults={'quantity_on_hand': 0}
        )
        ItemStock.objects.filter(pk=stock_from.pk).update(
            quantity_on_hand=F('quantity_on_hand') - instance.quantity
        )
    
    # 2. Auto create labor allocation rates if a worker is specified
    if not instance.worker:
        return
        
    labor_types = [
        TransactionType.MACHINING_OUT,
        TransactionType.MACHINING_IN,
        TransactionType.POLISHING_OUT,
        TransactionType.POLISHING_IN,
        TransactionType.PACKAGING_IN,
    ]
    if instance.transaction_type not in labor_types:
        return
        
    worker_company = instance.worker.company
    
    from apps.master_data.models import Item
    if worker_company:
        target_items = Item.objects.filter(code=instance.item.code, company=worker_company)
    else:
        target_items = [instance.item]
    
    for item in target_items:
        existing = ItemWorkerAllocation.objects.filter(item=item, worker=instance.worker).first()
        if not existing:
            ItemWorkerAllocation.objects.create(
                item=item,
                worker=instance.worker,
                rate_per_piece=0.0
            )



class Notification(models.Model):
    title = models.CharField(max_length=255)
    message = models.TextField()
    notification_type = models.CharField(max_length=20, default='INFO') # INFO, SUCCESS, WARNING, ERROR
    link = models.CharField(max_length=255, blank=True, null=True)
    is_read = models.BooleanField(default=False)
    company = models.ForeignKey(LegalEntity, on_delete=models.CASCADE, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.notification_type}] {self.title}"


from django.db.models.signals import post_save, post_delete

@receiver([post_save, post_delete], sender=LaborPayment)
def handle_labor_payment_loan_sync(sender, instance, **kwargs):
    if instance.worker and instance.payment_type in [PaymentType.LOAN_REPAYMENT, PaymentType.NEW_LOAN]:
        loans = Loan.objects.filter(worker=instance.worker).order_by('-issued_date', '-id')
        for loan in loans:
            loan.recalculate_balance()

