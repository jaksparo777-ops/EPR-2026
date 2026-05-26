from django.db import models
from apps.products.models import Item, Warehouse, Client, TransactionType
from apps.workforce.models import Worker, JobWorker

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
    client_po = models.ForeignKey(
        'client_orders.ClientPO',
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='stock_transactions'
    )
    inter_company_challan = models.ForeignKey(
        'client_orders.InterCompanyChallan',
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='stock_transactions'
    )
    heat_no = models.CharField(
        max_length=50,
        blank=True,
        null=True
    )
    quantity = models.IntegerField(default=0)
    rejection_quantity = models.IntegerField(default=0)
    weight = models.FloatField(default=0)
    lot_quantity = models.IntegerField(default=0)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.item} - {self.transaction_type}"

