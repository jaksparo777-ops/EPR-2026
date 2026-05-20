from django.db.models import Sum, Q
from .models import StockTransaction


def get_stock(stage):
    data = (
        StockTransaction.objects
        .filter(stage=stage)
        .values('item__id', 'item__code', 'item__name')
        .annotate(
            total_in=Sum('quantity', filter=Q(direction='in')),
            total_out=Sum('quantity', filter=Q(direction='out')),
        )
    )

    result = []

    for d in data:
        qty = (d['total_in'] or 0) - (d['total_out'] or 0)

        if qty > 0:
            result.append({
                "id": d['item__id'],
                "code": d['item__code'],
                "name": d['item__name'],
                "qty": qty
            })

    return result
