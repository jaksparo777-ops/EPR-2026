from django.contrib import admin
from .models import LegalEntity, Client, Warehouse, Item, Category, Material

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name',)

@admin.register(Material)
class MaterialAdmin(admin.ModelAdmin):
    list_display = ('name',)

@admin.register(LegalEntity)
class LegalEntityAdmin(admin.ModelAdmin):
    list_display = ('name', 'gst_number', 'phone', 'weekly_off', 'is_weekly_off_paid', 'created_at')
    search_fields = ('name', 'gst_number')

@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ('name', 'company', 'city', 'active', 'created_at')
    list_filter = ('company', 'active')
    search_fields = ('name', 'city')

@admin.register(Warehouse)
class WarehouseAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'company')
    list_filter = ('company',)
    search_fields = ('name', 'code')

@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'category', 'company', 'active', 'casting_weight', 'machining_weight')
    list_filter = ('company', 'category', 'active')
    search_fields = ('code', 'name')
