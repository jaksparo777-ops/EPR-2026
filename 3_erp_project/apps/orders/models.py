import uuid
from django.db import models
from django.db.models import Max
from apps.master_data.models import Client, Item

class SalesOrder(models.Model):
    class OrderStatus(models.TextChoices):
        OPEN = "OPEN", "Open / Pending"
        PARTIAL = "PARTIAL", "Partially Dispatched"
        COMPLETED = "COMPLETED", "Completed"
        CANCELLED = "CANCELLED", "Cancelled"

    uuid = models.UUIDField(default=uuid.uuid4, editable=False, null=True, blank=True)

    order_number = models.CharField(max_length=50, unique=True, blank=True)  # SO-1000+
    client = models.ForeignKey(Client, on_delete=models.PROTECT, related_name='orders')
    external_po_number = models.CharField(max_length=100, blank=True, null=True, help_text="Client's PO Ref Number")
    order_date = models.DateField(auto_now_add=True)
    promised_date = models.DateField(help_text="Fulfillment Deadline")
    priority = models.CharField(max_length=20, choices=[('URGENT', 'Urgent'), ('NORMAL', 'Normal')], default='NORMAL')
    status = models.CharField(max_length=20, choices=OrderStatus.choices, default=OrderStatus.OPEN)
    notes = models.TextField(blank=True, null=True)

    def save(self, *args, **kwargs):
        if not self.order_number or not str(self.order_number).strip():
            max_id = SalesOrder.objects.filter(order_number__startswith='SO-').aggregate(Max('id'))['id__max'] or 1000
            self.order_number = f"SO-{max_id + 1}"
        if not self.external_po_number or not str(self.external_po_number).strip():
            self.external_po_number = self.order_number
        super().save(*args, **kwargs)


    @property
    def total_ordered_pieces(self):
        return sum(item.ordered_quantity for item in self.items.all())

    @property
    def total_dispatched_pieces(self):
        return sum(item.dispatched_quantity for item in self.items.all())

    @property
    def total_ready_pieces(self):
        return sum(item.ready_stock for item in self.items.all())

    @property
    def readiness_percentage(self):
        """
        Ready Stock / Remaining Needed Qty
        """
        if hasattr(self, 'cached_readiness_percentage'):
            return self.cached_readiness_percentage
        total_needed = sum(item.remaining_quantity for item in self.items.all())
        if total_needed == 0:
            return 100
        total_ready = sum(min(item.ready_stock, item.remaining_quantity) for item in self.items.all())
        return min(100, int((total_ready / total_needed) * 100))

    @property
    def coverage_percentage(self):
        """
        (Ready Stock + WIP Pipeline) / Remaining Needed Qty
        """
        if hasattr(self, 'cached_coverage_percentage'):
            return self.cached_coverage_percentage
        total_needed = sum(item.remaining_quantity for item in self.items.all())
        if total_needed == 0:
            return 100
        total_coverage = sum(min(item.ready_stock + item.pipeline_quantity, item.remaining_quantity) for item in self.items.all())
        return min(100, int((total_coverage / total_needed) * 100))

    def __str__(self):
        return f"{self.order_number} - {self.client.name} (PO: {self.external_po_number})"

class SalesOrderItem(models.Model):
    sales_order = models.ForeignKey(SalesOrder, on_delete=models.CASCADE, related_name='items')
    item = models.ForeignKey(Item, on_delete=models.PROTECT)
    ordered_quantity = models.IntegerField()
    rate_per_piece = models.FloatField(default=0.0, help_text="Agreed contractual rate for this order")
    remarks = models.CharField(max_length=200, blank=True, null=True)

    @property
    def dispatched_quantity(self):
        """
        Sum up all quantity of DispatchItems associated with this order item
        """
        if hasattr(self, 'cached_dispatched_quantity'):
            return self.cached_dispatched_quantity
        from apps.orders.models import DispatchItem
        dispatched_items = DispatchItem.objects.filter(dispatch__sales_order=self.sales_order, item=self.item)
        return sum(i.quantity for i in dispatched_items)

    @property
    def remaining_quantity(self):
        if hasattr(self, 'cached_remaining_quantity'):
            return self.cached_remaining_quantity
        return max(0, self.ordered_quantity - self.dispatched_quantity)

    @property
    def remaining_qty_breakdown_text(self):
        qty = self.remaining_quantity
        if qty <= 0:
            return "0 pcs needed"
            
        divisor = self.item.lot_with_box or self.item.lot_size or 1
        if divisor <= 1:
            return f"{qty} pcs needed"
            
        cartons, loose = self.item.calculate_cartons_and_loose(qty)
        
        parts = []
        if cartons > 0:
            parts.append(f"{cartons} ctn")
        if loose > 0:
            parts.append(f"{loose} pcs")
            
        emoji = "📦 " if cartons > 0 else ""
        return f"{emoji}{' + '.join(parts)} ({qty} pcs) needed"

    @property
    def ready_stock(self):
        """
        Computes physical finished ready stock currently available in the warehouse.
        Only counts generic (unlabeled) cartons and cartons reserved specifically for this SalesOrder.
        """
        if hasattr(self, 'cached_ready_stock'):
            return self.cached_ready_stock
        from apps.production.models import Carton
        
        # 1. Carton pieces tagged to this SalesOrder
        tagged_cartons = Carton.objects.filter(status='READY', sales_order=self.sales_order)
        tagged_pcs = 0
        for c in tagged_cartons:
            ci = c.items.filter(item=self.item).first()
            if ci:
                tagged_pcs += ci.quantity
                
        # 2. Carton pieces that are generic (not tagged to any SalesOrder)
        generic_cartons = Carton.objects.filter(status='READY', sales_order__isnull=True)
        generic_pcs = 0
        for c in generic_cartons:
            ci = c.items.filter(item=self.item).first()
            if ci:
                generic_pcs += ci.quantity
                
        return tagged_pcs + generic_pcs

    @property
    def ready_stock_breakdown(self):
        from apps.production.models import Carton, StockTransaction
        # Fetch all READY cartons in the warehouse containing this item that are either generic or reserved for this SalesOrder
        cartons = Carton.objects.filter(status='READY', items__item=self.item).filter(
            models.Q(sales_order=self.sales_order) | models.Q(sales_order__isnull=True)
        )
        carton_count = cartons.count()
        
        # Calculate pieces in cartons
        carton_pcs = 0
        for c in cartons:
            ci = c.items.filter(item=self.item).first()
            if ci:
                carton_pcs += ci.quantity
                
        # Calculate loose pieces from transactions minus all ready cartons
        txs = StockTransaction.objects.filter(item=self.item, transaction_type__in=["packaging_in", "kitting_produce", "dispatch_out"])
        received = sum(tx.quantity or 0 for tx in txs if tx.transaction_type in ["packaging_in", "kitting_produce"])
        dispatched = sum(tx.quantity or 0 for tx in txs if tx.transaction_type == "dispatch_out")
        total_ready = max(0, received - dispatched)
        
        all_ready_cartons = Carton.objects.filter(status='READY')
        all_carton_pcs = 0
        for c in all_ready_cartons:
            ci = c.items.filter(item=self.item).first()
            if ci:
                all_carton_pcs += ci.quantity
        loose_pieces = max(0, total_ready - all_carton_pcs)
        
        return {
            'cartons': carton_count,
            'carton_pcs': carton_pcs,
            'loose': loose_pieces,
            'total': carton_pcs
        }

    @property
    def pipeline_quantity(self):
        """
        Computes active WIP pieces inside Casting, Machining, and Polishing pipeline layers
        """
        if hasattr(self, 'cached_pipeline_quantity'):
            return self.cached_pipeline_quantity
        from apps.production.models import StockTransaction
        
        # Casting WIP (cast but not machining-issued)
        casting_txs = StockTransaction.objects.filter(item=self.item, transaction_type__in=["casting_entry", "machining_out"])
        casting_inflow = sum(tx.quantity for tx in casting_txs if tx.transaction_type == "casting_entry")
        casting_outflow = sum(tx.quantity for tx in casting_txs if tx.transaction_type == "machining_out")
        casting_wip = max(0, casting_inflow - casting_outflow)

        # Machining WIP (issued to machining but not yet completed)
        machining_txs = StockTransaction.objects.filter(item=self.item, transaction_type__in=["machining_out", "machining_in"])
        machining_inflow = sum(tx.quantity for tx in machining_txs if tx.transaction_type == "machining_out")
        machining_outflow = sum(tx.quantity for tx in machining_txs if tx.transaction_type == "machining_in")
        machining_wip = max(0, machining_inflow - machining_outflow)

        # Polishing WIP (issued to polishing but not yet completed)
        polishing_txs = StockTransaction.objects.filter(item=self.item, transaction_type__in=["polishing_out", "polishing_in"])
        polishing_inflow = sum(tx.quantity for tx in polishing_txs if tx.transaction_type == "polishing_out")
        polishing_outflow = sum(tx.quantity for tx in polishing_txs if tx.transaction_type == "polishing_in")
        polishing_wip = max(0, polishing_inflow - polishing_outflow)

        return casting_wip + machining_wip + polishing_wip

    def __str__(self):
        return f"{self.sales_order.order_number} - {self.item.name} x {self.ordered_quantity}"

class Dispatch(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, null=True, blank=True)

    dispatch_number = models.CharField(max_length=50, unique=True, blank=True)  # DSP-1000+
    sales_order = models.ForeignKey(SalesOrder, on_delete=models.PROTECT, related_name='dispatches')
    client = models.ForeignKey(Client, on_delete=models.PROTECT)
    dispatch_date = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True, null=True)

    def save(self, *args, **kwargs):
        if not self.dispatch_number or not str(self.dispatch_number).strip():
            max_id = Dispatch.objects.filter(dispatch_number__startswith='DSP-').aggregate(Max('id'))['id__max'] or 1000
            self.dispatch_number = f"DSP-{max_id + 1}"
        super().save(*args, **kwargs)


    @property
    def total_pieces(self):
        return sum(item.quantity for item in self.items.all())

    @property
    def total_weight(self):
        return sum(item.weight for item in self.items.all())

    def __str__(self):
        return f"{self.dispatch_number} - {self.client.name} (SO: {self.sales_order.order_number})"

class DispatchItem(models.Model):
    dispatch = models.ForeignKey(Dispatch, on_delete=models.CASCADE, related_name='items')
    item = models.ForeignKey(Item, on_delete=models.PROTECT)
    quantity = models.IntegerField()
    weight = models.FloatField(default=0.0)

    def __str__(self):
        return f"{self.dispatch.dispatch_number} - {self.item.name} x {self.quantity}"
