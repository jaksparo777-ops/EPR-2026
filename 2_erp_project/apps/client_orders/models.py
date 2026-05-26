from django.db import models
from django.utils import timezone

class LegalEntity(models.Model):
    name = models.CharField(max_length=100, unique=True)
    address = models.TextField()
    gst_number = models.CharField(max_length=15, blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    letterhead_title = models.CharField(
        max_length=100, 
        blank=True, 
        null=True, 
        help_text="Optional custom title for letters"
    )
    client_record = models.OneToOneField(
        'products.Client',
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='legal_entity',
        help_text="The corresponding Client record when this entity acts as a customer to another entity"
    )
    processes = models.CharField(
        max_length=255, 
        blank=True, 
        null=True, 
        default='', 
        help_text="Comma-separated list of active operational processes (CASTING, MACHINING, POLISHING, PACKAGING, DISPATCH)"
    )

    class Meta:
        verbose_name = 'Legal Entity'
        verbose_name_plural = 'Legal Entities'

    def __str__(self):
        return self.name

    @property
    def process_list(self):
        if self.processes:
            return [p.strip().upper() for p in self.processes.split(',') if p.strip()]
        return []


class ClientPO(models.Model):
    class StatusChoices(models.TextChoices):
        OPEN = 'OPEN', 'Open'
        CLOSED = 'CLOSED', 'Closed'
        CANCELLED = 'CANCELLED', 'Cancelled'

    po_number = models.CharField(max_length=100, unique=True)
    received_date = models.DateField(default=timezone.now)
    due_date = models.DateField(help_text="Committed delivery date")
    status = models.CharField(
        max_length=20, 
        choices=StatusChoices.choices, 
        default=StatusChoices.OPEN
    )
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    client = models.ForeignKey(
        'products.Client', 
        on_delete=models.PROTECT, 
        related_name='client_pos'
    )
    legal_entity = models.ForeignKey(
        'LegalEntity', 
        on_delete=models.PROTECT, 
        related_name='client_pos'
    )

    class Meta:
        verbose_name = 'Client Purchase Order'
        verbose_name_plural = 'Client Purchase Orders'

    def __str__(self):
        return f"{self.po_number} ({self.client.name})"


class ClientPOItem(models.Model):
    client_po = models.ForeignKey(
        'ClientPO', 
        on_delete=models.CASCADE, 
        related_name='items'
    )
    item = models.ForeignKey(
        'products.Item', 
        on_delete=models.PROTECT, 
        related_name='po_items'
    )
    quantity_ordered = models.IntegerField()
    quantity_dispatched = models.IntegerField(default=0)

    class Meta:
        verbose_name = 'Client PO Line Item'
        verbose_name_plural = 'Client PO Line Items'

    def __str__(self):
        return f"{self.item.name} in {self.client_po.po_number}"


class InterCompanyChallan(models.Model):
    challan_number = models.CharField(max_length=50, unique=True)
    date = models.DateField(default=timezone.now)
    vehicle_no = models.CharField(max_length=50, blank=True, null=True)
    driver_name = models.CharField(max_length=100, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    from_entity = models.ForeignKey(
        'LegalEntity', 
        on_delete=models.PROTECT, 
        related_name='sent_challans'
    )
    to_entity = models.ForeignKey(
        'LegalEntity', 
        on_delete=models.PROTECT, 
        related_name='received_challans'
    )

    class Meta:
        verbose_name = 'Inter-Company Challan'
        verbose_name_plural = 'Inter-Company Challans'

    def __str__(self):
        return self.challan_number


class InterCompanyChallanItem(models.Model):
    challan = models.ForeignKey(
        'InterCompanyChallan', 
        on_delete=models.CASCADE, 
        related_name='items'
    )
    item = models.ForeignKey(
        'products.Item', 
        on_delete=models.PROTECT, 
        related_name='challan_items'
    )
    quantity = models.IntegerField()
    weight = models.FloatField(default=0.0)

    class Meta:
        verbose_name = 'Inter-Company Challan Line Item'
        verbose_name_plural = 'Inter-Company Challan Line Items'

    def __str__(self):
        return f"{self.item.name} in {self.challan.challan_number}"
