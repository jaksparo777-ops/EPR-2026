from django.db import models


# =========================================
# ITEM MASTER
# =========================================

class Item(models.Model):

    CATEGORY_CHOICES = [
        ("BRASS", "Brass"),
        ("MORTAR", "Mortar"),
        ("PESTLE", "Pestle"),
        ("CHOPPING", "Chopping Board"),
        ("OTHER", "Other"),
    ]

    PROCESS_CHOICES = [
        ("machining", "Machining"),
        ("polishing", "Polishing"),
        ("packaging", "Packaging"),
    ]

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
        choices=PROCESS_CHOICES,
        blank=True,
        null=True
    )

    rate_per_piece = models.FloatField(
        default=0
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

    PROCESS_CHOICES = [
        ("machining", "Machining"),
        ("polishing", "Polishing"),
        ("packaging", "Packaging"),
    ]

    name = models.CharField(
        max_length=100
    )

    process = models.CharField(
        max_length=50,
        choices=PROCESS_CHOICES
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

    TRANSACTION_TYPES = [

        ("casting_entry", "Casting Entry"),

        ("machining_issue", "Machining Issue"),

        ("machining_receive", "Machining Receive"),

        ("polishing_issue", "Polishing Issue"),

        ("polishing_receive", "Polishing Receive"),

        ("dispatch", "Dispatch"),

    ]

    item = models.ForeignKey(
        Item,
        on_delete=models.CASCADE
    )

    transaction_type = models.CharField(
        max_length=50,
        choices=TRANSACTION_TYPES
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