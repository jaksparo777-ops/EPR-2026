from django.contrib import admin
from .models import SalesOrder, SalesOrderItem, Dispatch, DispatchItem

class SalesOrderItemInline(admin.TabularInline):
    model = SalesOrderItem
    extra = 1

@admin.register(SalesOrder)
class SalesOrderAdmin(admin.ModelAdmin):
    list_display = ('order_number', 'client', 'external_po_number', 'order_date', 'promised_date', 'priority', 'status')
    list_filter = ('status', 'priority', 'client')
    search_fields = ('order_number', 'external_po_number', 'client__name')
    inlines = [SalesOrderItemInline]

class DispatchItemInline(admin.TabularInline):
    model = DispatchItem
    extra = 1

@admin.register(Dispatch)
class DispatchAdmin(admin.ModelAdmin):
    list_display = ('dispatch_number', 'sales_order', 'client', 'dispatch_date')
    list_filter = ('client', 'dispatch_date')
    search_fields = ('dispatch_number', 'sales_order__order_number', 'client__name')
    inlines = [DispatchItemInline]
