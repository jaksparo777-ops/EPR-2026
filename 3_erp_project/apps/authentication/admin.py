from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser, Worker

@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    list_display = ('username', 'email', 'role', 'company', 'is_staff', 'is_active')
    list_filter = ('role', 'company', 'is_staff', 'is_active')
    fieldsets = UserAdmin.fieldsets + (
        ('Custom Scope Info', {'fields': ('role', 'company')}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Custom Scope Info', {'fields': ('role', 'company')}),
    )

@admin.register(Worker)
class WorkerAdmin(admin.ModelAdmin):
    list_display = ('employee_id', 'jw_code', 'name', 'worker_type', 'company', 'process', 'salary_model', 'daily_rate', 'active')
    list_filter = ('worker_type', 'company', 'process', 'salary_model', 'active')
    search_fields = ('employee_id', 'jw_code', 'name')

