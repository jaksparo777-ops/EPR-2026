from django.db import models
from django.utils import timezone


# =========================================
# ITEM MASTER
# =========================================

# =========================================
# ITEM MASTER
# =========================================

class ProcessType(models.TextChoices):
    CASTING = "casting", "Casting"
    MACHINING = "machining", "Machining"
    POLISHING = "polishing", "Polishing"
    PACKAGING = "packaging", "Packaging"

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


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name_plural = "Categories"


class Material(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name_plural = "Materials"


class Item(models.Model):

    client = models.ForeignKey(

        "Client",

        on_delete=models.SET_NULL,

        blank=True,

        null=True

    )

    code = models.CharField(
        max_length=50,
        unique=True
    )

    name = models.CharField(
        max_length=100
    )

    category = models.CharField(
        max_length=100,
        default="OTHER"
    )

    sub_category = models.CharField(
        max_length=100,
        blank=True,
        null=True
    )

    material = models.CharField(
        max_length=100,
        default="OTHER",
        blank=True,
        null=True
    )

    variant = models.CharField(
        max_length=100,
        blank=True,
        null=True
    )

    item_type = models.CharField(
        max_length=100,
        default='REGULAR'
    )

    casting_weight = models.FloatField(
        default=0
    )

    machining_weight = models.FloatField(
        default=0
    )


    lot_size = models.IntegerField(
        default=0
    )

    lot_with_box = models.IntegerField(
        default=0
    )

    process = models.CharField(
        max_length=50,
        choices=ProcessType.choices,
        blank=True,
        null=True
    )
    casting_required = models.BooleanField(
        default=True
    )

    machining_required = models.BooleanField(
        default=True
    )

    polishing_required = models.BooleanField(
        default=True
    )

    packing_required = models.BooleanField(
        default=True
    )

    rate_per_piece = models.FloatField(
        default=0
    )

    notes = models.TextField(
        blank=True,
        null=True
    )

    active = models.BooleanField(
        default=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):

        return f"{self.code} - {self.name}"

    def get_category_display(self):
        return self.category

    def get_material_display(self):
        return self.material

    def calculate_cartons_and_loose(self, quantity):
        """
        Smart divisor selector to calculate cartons and loose pieces.
        If quantity is a perfect multiple of lot_size, use lot_size.
        If quantity is a perfect multiple of lot_with_box, use lot_with_box.
        Otherwise, select whichever fits best by minimizing the remainder/loose pieces.
        """
        divisor = self.lot_with_box or self.lot_size or 1
        
        if self.lot_size and self.lot_with_box:
            if quantity % self.lot_size == 0:
                divisor = self.lot_size
            elif quantity % self.lot_with_box == 0:
                divisor = self.lot_with_box
            else:
                rem_size = quantity % self.lot_size
                rem_box = quantity % self.lot_with_box
                # Minimize remainder (loose pieces)
                if rem_size < rem_box:
                    divisor = self.lot_size
                else:
                    divisor = self.lot_with_box
                    
        cartons = quantity // divisor if divisor > 0 else 0
        loose = quantity % divisor if divisor > 0 else quantity
        return cartons, loose
# =========================================
# CLIENT MASTER
# =========================================

class Client(models.Model):

    name = models.CharField(
        max_length=100
    )

    phone = models.CharField(
        max_length=20,
        blank=True,
        null=True
    )

    email = models.EmailField(
        blank=True,
        null=True
    )

    city = models.CharField(
        max_length=100,
        blank=True,
        null=True
    )

    address = models.TextField(
        blank=True,
        null=True
    )

    gst_number = models.CharField(
        max_length=15,
        blank=True,
        null=True
    )

    active = models.BooleanField(
        default=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):

        return self.name


# =========================================
# WORKER MASTER
# =========================================

class SalaryModel(models.TextChoices):
    DAILY = "DAILY", "Daily Wage"
    FIXED = "FIXED", "Monthly Fixed"
    HOURLY = "HOURLY", "Hourly/Time Based"

class Worker(models.Model):
    
    name = models.CharField(
        max_length=100
    )
    salary_model = models.CharField(
        max_length=20,
        choices=SalaryModel.choices,
        default=SalaryModel.DAILY
    )
    daily_rate = models.FloatField(
        default=0,
        help_text="Rate per day for Daily Wage workers"
    )
    monthly_fixed_salary = models.FloatField(
        default=0,
        help_text="Fixed monthly salary for Fixed model"
    )
    overtime_rate = models.FloatField(
        default=0,
        help_text="Rate per hour of overtime"
    )
    monthly_allowance = models.FloatField(
        default=0,
        help_text="Automated monthly allowance added to salary"
    )

    process = models.CharField(
        max_length=50,
        choices=ProcessType.choices,
        default="machining"
    )
    phone = models.CharField(
        max_length=20,
        blank=True,
        null=True
    )

    # New Professional HR Fields
    employee_id = models.CharField(max_length=50, blank=True, null=True, unique=True)
    designation = models.CharField(max_length=100, blank=True, null=True)
    joining_date = models.DateField(blank=True, null=True)
    
    # Shift Settings
    standard_shift_hours = models.FloatField(default=8, help_text="Standard working hours per day")
    
    # Personal Info & Compliance
    identity_number = models.CharField(max_length=100, blank=True, null=True, help_text="Aadhar / Govt ID")
    emergency_contact_name = models.CharField(max_length=100, blank=True, null=True)
    emergency_contact_phone = models.CharField(max_length=20, blank=True, null=True)
    blood_group = models.CharField(max_length=10, blank=True, null=True)

    active = models.BooleanField(
        default=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def save(self, *args, **kwargs):
        if not self.employee_id or not str(self.employee_id).strip():
            # Try to use current ID if editing, otherwise next available
            if self.id:
                self.employee_id = f"EMP-{1000 + self.id}"
            else:
                last_w = Worker.objects.order_by("-id").first()
                base_id = (last_w.id + 1) if last_w else 1
                while True:
                    code = f"EMP-{1000 + base_id}"
                    if not Worker.objects.filter(employee_id=code).exists():
                        self.employee_id = code
                        break
                    base_id += 1
        
        # Auto-calculate OT rate if it's 0 and we have a daily rate/shift hours
        if self.overtime_rate == 0 and self.salary_model == "DAILY" and self.standard_shift_hours > 0:
            self.overtime_rate = round(self.daily_rate / self.standard_shift_hours, 2)
            
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.employee_id or '---'} - {self.name}"
# =========================================
# JOB WORKER MASTER
# =========================================

class JobWorker(models.Model):

    name = models.CharField(
        max_length=100
    )

    process = models.CharField(
        max_length=50,
        choices=ProcessType.choices
    )

    phone = models.CharField(
        max_length=20,
        blank=True,
        null=True
    )

    address = models.TextField(
        blank=True,
        null=True
    )

    email = models.EmailField(
        blank=True,
        null=True
    )

    gst_number = models.CharField(
        max_length=15,
        blank=True,
        null=True
    )

    active = models.BooleanField(
        default=True
    )

    jw_code = models.CharField(max_length=50, blank=True, null=True, unique=True)
    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def save(self, *args, **kwargs):
        if not self.jw_code or not str(self.jw_code).strip():
            last_jw = JobWorker.objects.order_by("-id").first()
            base_id = (last_jw.id + 1) if last_jw else 1
            while True:
                code = f"JW-{1000 + base_id}"
                if not JobWorker.objects.filter(jw_code=code).exists():
                    self.jw_code = code
                    break
                base_id += 1
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.jw_code or '---'} - {self.name}"

# =========================================
# WAREHOUSE MASTER
# =========================================

class Warehouse(models.Model):

    name = models.CharField(
        max_length=100
    )

    code = models.CharField(
        max_length=50,
        unique=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):

        return self.name


# =========================================
# STOCK TRANSACTION
# =========================================

class StockTransaction(models.Model):

    item = models.ForeignKey(
        Item,
        on_delete=models.CASCADE
    )

    transaction_type = models.CharField(
        max_length=50,
        choices=TransactionType.choices
    )

    from_warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.SET_NULL,
        related_name='from_transactions',
        blank=True,
        null=True
    )

    to_warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.SET_NULL,
        related_name='to_transactions',
        blank=True,
        null=True
    )

    worker = models.ForeignKey(
        Worker,
        on_delete=models.SET_NULL,
        blank=True,
        null=True
    )

    job_worker = models.ForeignKey(
        JobWorker,
        on_delete=models.SET_NULL,
        blank=True,
        null=True
    )

    client = models.ForeignKey(
        Client,
        on_delete=models.SET_NULL,
        blank=True,
        null=True
    )

    heat_no = models.CharField(
        max_length=50,
        blank=True,
        null=True
    )

    quantity = models.IntegerField(
        default=0
    )

    rejection_quantity = models.IntegerField(
        default=0
    )

    weight = models.FloatField(
        default=0
    )

    lot_quantity = models.IntegerField(
        default=0
    )

    notes = models.TextField(
        blank=True,
        null=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):

        return f"{self.item} - {self.transaction_type}"


# =========================================
# ITEM COMPOSITION (BOM)
# =========================================

class ItemComposition(models.Model):
    parent_item = models.ForeignKey(
        Item,
        on_delete=models.CASCADE,
        related_name='components'
    )
    component_item = models.ForeignKey(
        Item,
        on_delete=models.CASCADE,
        related_name='parent_sets'
    )
    quantity = models.PositiveIntegerField(
        default=1
    )

    class Meta:
        unique_together = ('parent_item', 'component_item')

    def __str__(self):
        return f"{self.quantity} x {self.component_item.name} in {self.parent_item.name}"



# =========================================
# ITEM WORKER ALLOCATION
# =========================================

class ItemWorkerAllocation(models.Model):
    item = models.ForeignKey(
        Item,
        on_delete=models.CASCADE,
        related_name='worker_allocations'
    )
    # Internal Worker
    worker = models.ForeignKey(
        Worker,
        on_delete=models.CASCADE,
        related_name='item_allocations',
        null=True,
        blank=True
    )
    # External Job Worker
    job_worker = models.ForeignKey(
        JobWorker,
        on_delete=models.CASCADE,
        related_name='external_item_allocations',
        null=True,
        blank=True
    )
    rate_per_piece = models.FloatField(
        default=0
    )

    class Meta:
        verbose_name = "Item Worker Rate"

    def __str__(self):
        worker_name = self.worker.name if self.worker else (self.job_worker.name if self.job_worker else "Unknown")
        return f"{self.item.name} - {worker_name} @ ₹{self.rate_per_piece}"
# =========================================
# LEDGER & PAYROLL
# =========================================

class AttendanceStatus(models.TextChoices):
    PRESENT = "PRESENT", "Present"
    ABSENT = "ABSENT", "Absent"
    HALF_DAY = "HALF_DAY", "Half Day"

class Attendance(models.Model):
    worker = models.ForeignKey(Worker, on_delete=models.CASCADE, related_name='attendance_records')
    date = models.DateField(default=timezone.now)
    status = models.CharField(max_length=20, choices=AttendanceStatus.choices, default=AttendanceStatus.PRESENT)
    overtime_hours = models.FloatField(default=0)
    notes = models.TextField(blank=True, null=True)

    class Meta:
        unique_together = ('worker', 'date')
        verbose_name_plural = "Attendance"

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
    # One of these will be set
    worker = models.ForeignKey(Worker, on_delete=models.SET_NULL, null=True, blank=True)
    job_worker = models.ForeignKey(JobWorker, on_delete=models.SET_NULL, null=True, blank=True)
    
    amount = models.FloatField()
    date = models.DateField(default=timezone.now)
    payment_type = models.CharField(max_length=20, choices=PaymentType.choices)
    payment_mode = models.CharField(max_length=50, default="CASH")
    reference_no = models.CharField(max_length=100, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)


# =========================================
# CARTONS & PACKAGING INVENTORY
# =========================================

class Carton(models.Model):
    class CartonStatus(models.TextChoices):
        READY = "READY", "In Warehouse"
        DISPATCHED = "DISPATCHED", "Dispatched"

    class CartonType(models.TextChoices):
        SINGLE = "SINGLE", "Single Item"
        SET = "SET", "Set Item"
        MIXED = "MIXED", "Mixed Carton"

    carton_number = models.CharField(max_length=50, unique=True, blank=True)
    carton_type = models.CharField(max_length=20, choices=CartonType.choices, default=CartonType.SINGLE)
    carton_label = models.CharField(max_length=200, blank=True, null=True)

    # Process checklist
    cleaning = models.BooleanField(default=False)
    labeling = models.BooleanField(default=False)
    packing = models.BooleanField(default=False)

    # Metrics
    total_quantity = models.IntegerField(default=0)
    total_weight = models.FloatField(default=0.0)

    # Status & Logistics
    status = models.CharField(max_length=20, choices=CartonStatus.choices, default=CartonStatus.READY)
    client = models.ForeignKey(Client, on_delete=models.SET_NULL, null=True, blank=True, related_name='cartons')
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

