from django.contrib import admin
from .models import Item, StockTransaction

admin.site.register(Item)
admin.site.register(StockTransaction)
