from django.contrib import admin
from .models import (
    StockTransaction, ItemWorkerAllocation, Attendance, 
    Loan, LaborPayment, Carton, CartonItem, Holiday
)

@admin.register(StockTransaction)
class StockTransactionAdmin(admin.ModelAdmin):
    list_display = ('item', 'transaction_type', 'from_warehouse', 'to_warehouse', 'worker', 'quantity', 'weight', 'created_at')
    list_filter = ('transaction_type', 'from_warehouse', 'to_warehouse')
    search_fields = ('item__code', 'item__name', 'heat_no')

@admin.register(ItemWorkerAllocation)
class ItemWorkerAllocationAdmin(admin.ModelAdmin):
    list_display = ('item', 'worker', 'rate_per_piece')
    list_filter = ('item', 'worker')

@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ('worker', 'date', 'status', 'overtime_hours')
    list_filter = ('date', 'status')

@admin.register(Holiday)
class HolidayAdmin(admin.ModelAdmin):
    list_display = ('date', 'name', 'company', 'is_paid', 'is_working_day_override')
    list_filter = ('company', 'is_paid', 'is_working_day_override')
    search_fields = ('name',)


@admin.register(Loan)
class LoanAdmin(admin.ModelAdmin):
    list_display = ('worker', 'total_amount', 'emi_amount', 'remaining_balance', 'is_active')
    list_filter = ('is_active',)

@admin.register(LaborPayment)
class LaborPaymentAdmin(admin.ModelAdmin):
    list_display = ('worker', 'amount', 'date', 'payment_type', 'payment_mode')
    list_filter = ('date', 'payment_type', 'payment_mode')

class CartonItemInline(admin.TabularInline):
    model = CartonItem
    extra = 1

@admin.register(Carton)
class CartonAdmin(admin.ModelAdmin):
    list_display = ('carton_number', 'carton_type', 'client', 'total_quantity', 'total_weight', 'status', 'dispatched_at')
    list_filter = ('carton_type', 'status', 'client')
    inlines = [CartonItemInline]
    search_fields = ('carton_number', 'carton_label')
