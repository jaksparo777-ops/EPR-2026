from django.db import models
from apps.products.models import Item, Client

class Carton(models.Model):
    class CartonStatus(models.TextChoices):
        READY = "READY", "In Warehouse"
        DISPATCHED = "DISPATCHED", "Dispatched"

    class CartonType(models.TextChoices):
        SINGLE = "SINGLE", "Single Item"
        SET = "SET", "Set Item"
        MIXED = "MIXED", "Mixed Carton"

    carton_number = models.CharField(max_length=50, unique=True, blank=True)
    carton_type = models.CharField(
        max_length=20,
        choices=CartonType.choices,
        default=CartonType.SINGLE
    )
    carton_label = models.CharField(max_length=200, blank=True, null=True)

    # Process checklist
    cleaning = models.BooleanField(default=False)
    labeling = models.BooleanField(default=False)
    packing = models.BooleanField(default=False)

    # Metrics
    total_quantity = models.IntegerField(default=0)
    total_weight = models.FloatField(default=0.0)

    # Status & Logistics
    status = models.CharField(
        max_length=20,
        choices=CartonStatus.choices,
        default=CartonStatus.READY
    )
    client = models.ForeignKey(
        Client,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='cartons'
    )
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
    carton = models.ForeignKey(
        Carton,
        on_delete=models.CASCADE,
        related_name='items'
    )
    item = models.ForeignKey(
        Item,
        on_delete=models.CASCADE,
        related_name='carton_contents'
    )
    quantity = models.IntegerField(default=0)
    weight = models.FloatField(default=0.0)

    def __str__(self):
        return f"{self.item.code} x {self.quantity} in {self.carton.carton_number}"
