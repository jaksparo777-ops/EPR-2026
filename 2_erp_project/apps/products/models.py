from django.db import models
from apps.monitoring.soft_delete import SoftDeleteModel

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


class Client(SoftDeleteModel):
    companies = models.ManyToManyField(
        'client_orders.LegalEntity',
        blank=True,
        related_name='owned_clients',
        help_text="The companies this client belongs to. If empty, the client is global."
    )
    name = models.CharField(max_length=100)
    phone = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    gst_number = models.CharField(max_length=15, blank=True, null=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Item(SoftDeleteModel):
    companies = models.ManyToManyField(
        'client_orders.LegalEntity',
        blank=True,
        related_name='owned_items',
        help_text="The companies this item belongs to. If empty, the item is global."
    )
    client = models.ForeignKey(
        Client,
        on_delete=models.SET_NULL,
        blank=True,
        null=True
    )
    code = models.CharField(max_length=50, unique=True)

    name = models.CharField(max_length=100)
    category = models.CharField(max_length=100, default="OTHER")
    sub_category = models.CharField(max_length=100, blank=True, null=True)
    material = models.CharField(max_length=100, default="OTHER", blank=True, null=True)
    variant = models.CharField(max_length=100, blank=True, null=True)
    item_type = models.CharField(max_length=100, default='REGULAR')
    casting_weight = models.FloatField(default=0)
    machining_weight = models.FloatField(default=0)
    lot_size = models.IntegerField(default=0)
    lot_with_box = models.IntegerField(default=0)
    process = models.CharField(
        max_length=50,
        choices=ProcessType.choices,
        blank=True,
        null=True
    )
    casting_required = models.BooleanField(default=True)
    machining_required = models.BooleanField(default=True)
    polishing_required = models.BooleanField(default=True)
    packing_required = models.BooleanField(default=True)
    rate_per_piece = models.FloatField(default=0)
    notes = models.TextField(blank=True, null=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.code} - {self.name}"

    @property
    def active_allocations(self):
        return [
            alloc for alloc in self.worker_allocations.all()
            if (alloc.worker and not alloc.worker.is_deleted) or (alloc.job_worker and not alloc.job_worker.is_deleted)
        ]

    def get_category_display(self):
        return self.category

    def get_material_display(self):
        return self.material

    def calculate_cartons_and_loose(self, quantity):
        divisor = self.lot_with_box or self.lot_size or 1
        
        if self.lot_size and self.lot_with_box:
            if quantity % self.lot_size == 0:
                divisor = self.lot_size
            elif quantity % self.lot_with_box == 0:
                divisor = self.lot_with_box
            else:
                rem_size = quantity % self.lot_size
                rem_box = quantity % self.lot_with_box
                if rem_size < rem_box:
                    divisor = self.lot_size
                else:
                    divisor = self.lot_with_box
                    
        cartons = quantity // divisor if divisor > 0 else 0
        loose = quantity % divisor if divisor > 0 else quantity
        return cartons, loose


class Warehouse(models.Model):
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=50, unique=True)
    legal_entity = models.ForeignKey(
        'client_orders.LegalEntity',
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='warehouses'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name



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
    quantity = models.PositiveIntegerField(default=1)

    class Meta:
        unique_together = ('parent_item', 'component_item')

    def __str__(self):
        return f"{self.quantity} x {self.component_item.name} in {self.parent_item.name}"
