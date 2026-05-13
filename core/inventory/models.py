from django.db import models


# =========================================
# ITEM MASTER
# =========================================

# =========================================
# ITEM MASTER
# =========================================

class ProcessType(models.TextChoices):
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


class Item(models.Model):

    CATEGORY_CHOICES = [
        ("BRASS", "Brass"),
        ("MORTAR", "Mortar"),
        ("PESTLE", "Pestle"),
        ("CHOPPING", "Chopping Board"),
        ("OTHER", "Other"),
    ]

    MATERIAL_CHOICES = [
        ("BRASS", "Brass"),
        ("SS", "Stainless Steel"),
        ("CI", "Cast Iron"),
        ("ALUMINIUM", "Aluminium"),
    ]

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
        max_length=50,
        choices=CATEGORY_CHOICES,
        default="OTHER"
    )

    material = models.CharField(
        max_length=50,
        choices=MATERIAL_CHOICES,
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
        blank=True,
        null=True
    )

    weight_per_piece = models.FloatField(
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

    city = models.CharField(
        max_length=100,
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

class Worker(models.Model):
    
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

    active = models.BooleanField(
        default=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):

        return self.name

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

    active = models.BooleanField(
        default=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):

        return self.name
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