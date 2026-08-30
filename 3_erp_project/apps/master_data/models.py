import uuid
from django.db import models
from django.db.models import Max

class LegalEntity(models.Model):
    """
    Represents a company or business unit (e.g., Company 1: Casting, Company 2: Finishing).
    """
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, null=True, blank=True)

    name = models.CharField(max_length=255, unique=True)
    gst_number = models.CharField(max_length=15, blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    address = models.TextField()
    letterhead_title = models.CharField(max_length=255, blank=True, null=True)
    
    # Workflow Delegation Flags
    handles_casting = models.BooleanField(default=True)
    handles_machining = models.BooleanField(default=False)
    handles_polishing = models.BooleanField(default=False)
    handles_packaging = models.BooleanField(default=False)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    WEEKDAY_CHOICES = [
        (0, 'Monday'),
        (1, 'Tuesday'),
        (2, 'Wednesday'),
        (3, 'Thursday'),
        (4, 'Friday'),
        (5, 'Saturday'),
        (6, 'Sunday'),
        (7, 'None'),
    ]
    weekly_off = models.IntegerField(choices=WEEKDAY_CHOICES, default=6)
    is_weekly_off_paid = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Legal Entity"
        verbose_name_plural = "Legal Entities"

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


class Client(models.Model):
    """
    Represents a client or customer. Scoped strictly to a LegalEntity (Company).
    """
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, null=True, blank=True)

    name = models.CharField(max_length=255)
    client_code = models.CharField(max_length=50, blank=True, null=True, unique=True)
    company = models.ForeignKey(LegalEntity, on_delete=models.PROTECT, related_name="clients")
    phone = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    PACKING_CHOICES = [
        ('BOX_PREF', 'Box Lot Preferred & Flexible'),
        ('REG_PREF', 'Regular Preferred & Flexible'),
        ('BOX_STRICT', 'Strict Box Lot Only'),
        ('REG_STRICT', 'Strict Regular Only'),
        ('ANY', 'Fully Flexible / Any'),
    ]
    packing_preference = models.CharField(max_length=20, choices=PACKING_CHOICES, default='ANY')

    gst_number = models.CharField(max_length=15, blank=True, null=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('name', 'company')
        ordering = ['name']

    def save(self, *args, **kwargs):
        if not self.client_code or not str(self.client_code).strip():
            max_id = Client.objects.filter(client_code__startswith='CL-').aggregate(Max('id'))['id__max'] or 1000
            self.client_code = f"CL-{max_id + 1}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.client_code or '---'} - {self.name} ({self.company.name})"



class Warehouse(models.Model):
    """
    Represents a physical or process warehouse stage (e.g., CASTING, MACHINING, READY).
    """
    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=100)
    company = models.ForeignKey(LegalEntity, on_delete=models.PROTECT, blank=True, null=True, related_name="warehouses")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} [{self.code}]"


class Item(models.Model):
    """
    Represents raw material, component, or finished set.
    Can be scoped to a company or be a global item.
    """
    CATEGORY_CHOICES = [
        ('BRASS', 'Brass'),
        ('MORTAR', 'Mortar'),
        ('PESTLE', 'Pestle'),
        ('CHOPPING_BOARD', 'Chopping Board'),
        ('OTHER', 'Other'),
    ]

    PROCESS_CHOICES = [
        ('MACHINING', 'Machining'),
        ('POLISHING', 'Polishing'),
        ('PACKAGING', 'Packaging'),
        ('NONE', 'None'),
    ]

    code = models.CharField(max_length=100)
    name = models.CharField(max_length=255)
    category = models.CharField(max_length=50, default='OTHER')
    sub_category = models.CharField(max_length=100, blank=True, null=True)
    material = models.CharField(max_length=100, default='OTHER', blank=True, null=True)
    variant = models.CharField(max_length=100, blank=True, null=True)
    item_type = models.CharField(max_length=100, default='REGULAR')
    notes = models.TextField(blank=True, null=True)
    company = models.ForeignKey(LegalEntity, on_delete=models.PROTECT, blank=True, null=True, related_name="items")
    client = models.ForeignKey(Client, on_delete=models.SET_NULL, blank=True, null=True, related_name="items")
    
    # Process & Weight Route sheet
    casting_required = models.BooleanField(default=True)
    machining_required = models.BooleanField(default=False)
    polishing_required = models.BooleanField(default=False)
    packing_required = models.BooleanField(default=False)
    
    casting_weight = models.FloatField(default=0.0)
    machining_weight = models.FloatField(default=0.0)
    
    # Packing specs
    lot_size = models.IntegerField(default=1)
    lot_with_box = models.IntegerField(default=1)
    rate_per_piece = models.FloatField(default=0.0)
    
    # Stock Alert Thresholds
    min_casting_stock = models.IntegerField(default=0)
    min_machining_stock = models.IntegerField(default=0)
    min_polishing_stock = models.IntegerField(default=0)
    min_ready_stock = models.IntegerField(default=0)
    
    # Conversion & Yield Properties
    is_raw_material = models.BooleanField(default=False)
    raw_material = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='derived_items')
    yield_pcs_per_unit = models.FloatField(default=1.0)
    uom = models.CharField(
        max_length=20, 
        default='PCS', 
        choices=[
            ('PCS', 'Pieces (Pcs)'),
            ('KG', 'Kilograms (Kg)'),
            ('CHAAD', 'Pipes (Chaad)'),
            ('FEET', 'Feet (Ft)'),
            ('INCH', 'Inches (In)'),
            ('CM', 'Centimeters (Cm)'),
            ('MM', 'Millimeters (Mm)')
        ]
    )
    
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['code']
        unique_together = ('company', 'code')

    def __str__(self):
        return f"{self.code} - {self.name}"

    def save(self, *args, **kwargs):
        if self.client and not self.company:
            self.company = self.client.company
        super().save(*args, **kwargs)
        
        # Auto-clone items created for client 'OM' under NC (Company 1) to OM (Company 2)
        if self.company_id == 1 and self.client and self.client.name.strip().upper() == 'OM':
            om_company = LegalEntity.objects.filter(id=2).first() or LegalEntity.objects.filter(name__icontains='OM').first()
            if om_company:
                om_item_exists = Item.objects.filter(company=om_company, code=self.code).exists()
                if not om_item_exists:
                    # Resolve raw material on cloned side by matching code
                    cloned_raw_material = None
                    if self.raw_material:
                        cloned_raw_material = Item.objects.filter(company=om_company, code=self.raw_material.code).first()
                        
                    Item.objects.create(
                        code=self.code,
                        name=self.name,
                        category=self.category,
                        sub_category=self.sub_category,
                        material=self.material,
                        variant=self.variant,
                        item_type=self.item_type,
                        notes=self.notes,
                        company=om_company,
                        client=None,  # Leave client empty on OM's side
                        casting_required=False,
                        machining_required=self.machining_required,
                        polishing_required=self.polishing_required,
                        packing_required=self.packing_required,
                        casting_weight=self.casting_weight,
                        machining_weight=self.machining_weight,
                        lot_size=self.lot_size,
                        lot_with_box=self.lot_with_box,
                        rate_per_piece=self.rate_per_piece,
                        min_casting_stock=self.min_casting_stock,
                        min_machining_stock=self.min_machining_stock,
                        min_polishing_stock=self.min_polishing_stock,
                        min_ready_stock=self.min_ready_stock,
                        is_raw_material=self.is_raw_material,
                        raw_material=cloned_raw_material,
                        yield_pcs_per_unit=self.yield_pcs_per_unit,
                        uom=self.uom,
                        active=self.active
                    )


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

    @property
    def buffer_stock(self):
        from apps.production.models import StockTransaction, TransactionType
        from django.db.models import Sum
        buffer_in = StockTransaction.objects.filter(
            item=self,
            transaction_type=TransactionType.PACKAGING_IN,
            notes__contains='[DEDICATED BUFFER]',
            quantity__gt=0
        ).aggregate(total=Sum('quantity'))['total'] or 0
        
        buffer_out = -(StockTransaction.objects.filter(
            item=self,
            transaction_type=TransactionType.PACKAGING_IN,
            notes__contains='[DEDICATED BUFFER]',
            quantity__lt=0
        ).aggregate(total=Sum('quantity'))['total'] or 0)
        
        return max(0, buffer_in - buffer_out)



class ItemComposition(models.Model):
    """
    Defines Bill of Materials (BOM) parent-to-component sets.
    """
    parent_item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name='components')
    component_item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name='parent_sets')
    quantity = models.PositiveIntegerField(default=1)

    class Meta:
        unique_together = ('parent_item', 'component_item')

    def __str__(self):
        return f"{self.quantity} x {self.component_item.name} in {self.parent_item.name}"


class MaintenanceSettings(models.Model):
    """
    Database settings for scheduling auto-backup and auto-deletion in ERP.
    """
    auto_backup_enabled = models.BooleanField(default=False)
    auto_backup_frequency = models.CharField(
        max_length=20,
        choices=[('daily', 'Daily'), ('weekly', 'Weekly'), ('monthly', 'Monthly')],
        default='weekly'
    )
    backup_retention_count = models.IntegerField(default=10)
    last_backup_run = models.DateTimeField(null=True, blank=True)

    auto_delete_enabled = models.BooleanField(default=False)
    auto_delete_frequency = models.CharField(
        max_length=20,
        choices=[('4_months', 'Every 4 Months'), ('6_months', 'Half-Year (6 Months)'), ('1_year', 'Every 1 Year')],
        default='6_months'
    )
    SECURITY_MODE_CHOICES = [
        ('DEV_AUTO_APPROVE', '🟢 Dev Auto-Approve (Local/Dev Networks Auto-Approved)'),
        ('FACTORY_LOCAL_AUTO_APPROVE', '🟡 Factory Wi-Fi Auto-Approve (Local LAN Approved, WAN Pending)'),
        ('STRICT_SECURITY', '🔴 Strict Production (Every Non-Admin Device Requires Approval)'),
        ('DISABLED', '⚪ Security Interceptor Disabled'),
    ]
    device_security_mode = models.CharField(
        max_length=30,
        choices=SECURITY_MODE_CHOICES,
        default='DEV_AUTO_APPROVE'
    )

    class Meta:
        verbose_name = "Maintenance Settings"
        verbose_name_plural = "Maintenance Settings"

    def __str__(self):
        return "System Maintenance Settings"


class MaintenanceLog(models.Model):
    """
    Immutable audit trail for ERP maintenance events.
    """
    timestamp = models.DateTimeField(auto_now_add=True)
    event_type = models.CharField(
        max_length=20,
        choices=[
            ('backup', 'Auto-Backup'),
            ('delete', 'Auto-Delete Purge'),
            ('audit_fail', 'Safety Audit Blocked'),
            ('restore', 'Database Restoration'),
            ('reset', 'Factory Reset')
        ]
    )
    status = models.CharField(
        max_length=20,
        choices=[('success', 'Success'), ('failed', 'Failed'), ('skipped', 'Skipped')]
    )
    message = models.TextField()
    details = models.TextField(blank=True, default='')

    class Meta:
        verbose_name = "Maintenance Log"
        verbose_name_plural = "Maintenance Logs"
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.get_event_type_display()} - {self.status} on {self.timestamp.strftime('%Y-%m-%d %H:%M')}"


class ItemStock(models.Model):
    """
    Real-time aggregated stock balance per (Item, Warehouse).
    Updated atomically via StockTransaction post_save signals.
    """
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, null=True, blank=True)

    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name='stock_balances')
    warehouse = models.ForeignKey(Warehouse, on_delete=models.CASCADE, related_name='item_balances')
    quantity_on_hand = models.IntegerField(default=0)
    reserved_quantity = models.IntegerField(default=0)
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('item', 'warehouse')
        verbose_name = "Item Stock Balance"
        verbose_name_plural = "Item Stock Balances"

    def __str__(self):
        return f"{self.item.code} @ {self.warehouse.code}: {self.quantity_on_hand} pcs"

