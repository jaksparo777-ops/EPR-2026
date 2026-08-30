from django.urls import path
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from apps.authentication.views import select_company

from .views.production import (
    casting_entry, machining_entry, polishing_entry,
    packaging_view, issue_machining, purchases_view,
    delete_purchase, log_casting_weight
)
from .views.master import (
    master_data, delete_item, delete_items_bulk, delete_client,
    delete_worker, delete_job_worker, edit_item, delete_holiday,
    toggle_worker_active, toggle_job_worker_active
)
from .views.import_export_hub import (
    master_bulk_import, download_template, export_current_data,
    export_database_backup, import_database_backup, factory_reset_database,
    save_maintenance_settings, dry_run_audit, purge_selective_data
)
from .views.logistics import (
    dashboard, casting_stock, machined_stock, polished_stock,
    ready_stock, dispatch_view, assembly_view
)
from .views.api import (
    get_item_workers, get_worker_items, get_item_composition,
    get_internal_worker_profile, get_job_worker_profile,
    add_worker_allocation, update_worker_allocation_rate, delete_worker_allocation, edit_matrix_cell,
    mark_attendance, mark_all_attendance, record_labor_payment, delete_labor_payment, edit_labor_payment, delete_stock_transaction_api, bulk_delete_stock_transactions_api,
    get_attendance_for_date, get_warehouse_stock, get_all_warehouse_stock, adjust_stock, get_notifications, mark_notification_read,
    get_recipient_dues_api
)
from .views.hr_ledger import (
    labor_ledger, job_worker_monthly_report, worker_monthly_report,
    attendance_view, worker_monthly_report_all, job_worker_monthly_report_all,
    toggle_settlement_lock
)
from .views.global_search import global_search_api
from .views.sql_explorer import sql_explorer_view, sql_explorer_run_api

urlpatterns = [
    path('sql-explorer/', login_required(sql_explorer_view), name='sql_explorer'),
    path('api/sql-explorer/run/', login_required(sql_explorer_run_api), name='sql_explorer_run_api'),
    path('api/global-search/', global_search_api, name='global_search_api'),
    path('login/', auth_views.LoginView.as_view(template_name='login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    
    path('', login_required(dashboard), name='dashboard'),
    path('select-company/', login_required(select_company), name='select_company'),
    path('attendance/', login_required(attendance_view), name='attendance_entry'),
    path('casting/', login_required(casting_entry), name='casting_entry'),
    path('machining/', login_required(machining_entry), name='machining_entry'),
    path('polishing/', login_required(polishing_entry), name='polishing_entry'),
    path('packaging/', login_required(packaging_view), name='packaging'),
    path('purchases/', login_required(purchases_view), name='purchases'),
    path('purchases/delete/<int:tx_id>/', login_required(delete_purchase), name='delete_purchase'),
    path('assembly/', login_required(assembly_view), name='assembly'),
    path('master-data/', login_required(master_data), name='master_data'),
    path('master-data/bulk-import/', login_required(master_bulk_import), name='master_bulk_import'),
    path('master-data/bulk-import/template/<str:template_type>/', login_required(download_template), name='download_template'),
    path('master-data/bulk-import/export/<str:template_type>/', login_required(export_current_data), name='export_current_data'),
    
    # Database Maintenance System
    path('master-data/bulk-import/backup/export/', login_required(export_database_backup), name='export_database_backup'),
    path('master-data/bulk-import/backup/import/', login_required(import_database_backup), name='import_database_backup'),
    path('master-data/bulk-import/maintenance/reset/', login_required(factory_reset_database), name='factory_reset_database'),
    path('master-data/bulk-import/maintenance/purge-selective/', login_required(purge_selective_data), name='purge_selective_data'),
    path('master-data/bulk-import/maintenance/save-settings/', login_required(save_maintenance_settings), name='save_maintenance_settings'),
    path('master-data/bulk-import/maintenance/dry-run/', login_required(dry_run_audit), name='dry_run_audit'),
    
    path('casting-stock/', login_required(casting_stock), name='casting_stock'),
    path('machined-stock/', login_required(machined_stock), name='machined_stock'),
    path('polished-stock/', login_required(polished_stock), name='polished_stock'),
    path('ready-stock/', login_required(ready_stock), name='ready_stock'),
    path('issue-machining/', login_required(issue_machining), name='issue_machining'),
    
    path('delete-item/<int:item_id>/', login_required(delete_item), name='delete_item'),
    path('delete-items-bulk/', login_required(delete_items_bulk), name='delete_items_bulk'),
    path('delete-client/<int:client_id>/', login_required(delete_client), name='delete_client'),
    path('delete-worker/<int:worker_id>/', login_required(delete_worker), name='delete_worker'),
    path('toggle-worker/<int:worker_id>/', login_required(toggle_worker_active), name='toggle_worker_active'),
    path('delete-job-worker/<int:job_worker_id>/', login_required(delete_job_worker), name='delete_job_worker'),
    path('toggle-job-worker/<int:job_worker_id>/', login_required(toggle_job_worker_active), name='toggle_job_worker_active'),
    path('delete-holiday/<int:holiday_id>/', login_required(delete_holiday), name='delete_holiday'),
    path('edit-item/<int:item_id>/', login_required(edit_item), name='edit_item'),
    
    path('dispatch/', login_required(dispatch_view), name='dispatch'),
    
    # API endpoints
    path('api/item/<int:item_id>/workers/', login_required(get_item_workers), name='get_item_workers'),
    path('api/worker/<str:worker_id>/items/', login_required(get_worker_items), name='get_worker_items'),
    path('api/item/<int:item_id>/composition/', login_required(get_item_composition), name='get_item_composition'),
    path('api/worker/<int:worker_id>/profile/', login_required(get_internal_worker_profile), name='get_internal_worker_profile'),
    path('api/job-worker/<int:jw_id>/profile/', login_required(get_job_worker_profile), name='get_job_worker_profile'),
    path('api/allocation/add/', login_required(add_worker_allocation), name='add_worker_allocation'),
    path('api/allocation/<int:alloc_id>/update-rate/', login_required(update_worker_allocation_rate), name='update_worker_allocation_rate'),
    path('api/allocation/<int:alloc_id>/delete/', login_required(delete_worker_allocation), name='delete_worker_allocation'),
    path('api/attendance/mark/', login_required(mark_attendance), name='mark_attendance'),
    path('api/attendance/mark-all/', login_required(mark_all_attendance), name='mark_all_attendance'),
    path('api/casting/log-weight/', login_required(log_casting_weight), name='log_casting_weight'),
    path('api/payment/record/', login_required(record_labor_payment), name='record_labor_payment'),
    path('api/labor/get-recipient-dues/', login_required(get_recipient_dues_api), name='get_recipient_dues_api'),
    path('api/payment/<int:payment_id>/delete/', login_required(delete_labor_payment), name='delete_labor_payment'),
    path('api/payment/<int:payment_id>/edit/', login_required(edit_labor_payment), name='edit_labor_payment'),
    path('api/stock-transaction/<int:tx_id>/delete/', login_required(delete_stock_transaction_api), name='delete_stock_transaction_api'),
    path('api/stock-transaction/bulk-delete/', login_required(bulk_delete_stock_transactions_api), name='bulk_delete_stock_transactions_api'),
    path('api/attendance/fetch/', login_required(get_attendance_for_date), name='get_attendance_for_date'),
    path('api/stock/get-qty/', login_required(get_warehouse_stock), name='get_warehouse_stock'),
    path('api/stock/get-all-qty/', login_required(get_all_warehouse_stock), name='get_all_warehouse_stock'),
    path('api/stock/adjust/', login_required(adjust_stock), name='adjust_stock'),
    path('api/job-worker/report/edit-cell/', login_required(edit_matrix_cell), name='edit_matrix_cell'),
    
    # Ledger & Reports
    path('api/ledger/toggle-lock/', login_required(toggle_settlement_lock), name='toggle_settlement_lock'),
    path('ledger/', login_required(labor_ledger), name='labor_ledger'),
    path('ledger/job-worker/<int:jw_id>/report/', login_required(job_worker_monthly_report), name='job_worker_report'),
    path('worker/<int:worker_id>/report/', login_required(worker_monthly_report), name='worker_monthly_report'),
    path('worker/report/all/', login_required(worker_monthly_report_all), name='worker_monthly_report_all'),
    path('ledger/job-worker/report/all/', login_required(job_worker_monthly_report_all), name='job_worker_report_all'),
    
    # Unified Notification Hub APIs
    path('api/notifications/', login_required(get_notifications), name='get_notifications'),
    path('api/notifications/read/', login_required(mark_notification_read), name='mark_notification_read'),
]
