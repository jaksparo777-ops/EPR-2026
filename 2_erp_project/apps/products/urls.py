from django.urls import path
from django.contrib.auth import views as auth_views
from apps.products import views_dashboard, views_api
from apps.products.views import (
    dashboard,
    master_data,
    delete_item,
    delete_items_bulk,
    delete_client,
    edit_item,
    get_item_composition,
    download_item_template,
    download_worker_template,
    download_job_worker_template,
    preview_import_data,
    confirm_import_data,
    recover_deleted_record,
    permanent_delete_record,
)

urlpatterns = [
    path('login/', auth_views.LoginView.as_view(template_name='login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('', dashboard, name='dashboard'),
    path('unified-dashboard/', views_dashboard.unified_dashboard, name='unified_dashboard'),
    path('api/company/<int:company_id>/details/', views_api.company_details_api, name='company_details_api'),
    path('master-data/', master_data, name='master_data'),
    path('delete-item/<int:item_id>/', delete_item, name='delete_item'),

    path('delete-items-bulk/', delete_items_bulk, name='delete_items_bulk'),
    path('delete-client/<int:client_id>/', delete_client, name='delete_client'),
    path('edit-item/<int:item_id>/', edit_item, name='edit_item'),
    path('api/item/<int:item_id>/composition/', get_item_composition, name='get_item_composition'),
    
    # Trash/recovery urls
    path('master-data/trash/recover/<str:model_type>/<int:record_id>/', recover_deleted_record, name='recover_deleted_record'),
    path('master-data/trash/permanent-delete/<str:model_type>/<int:record_id>/', permanent_delete_record, name='permanent_delete_record'),
    
    # Bulk import urls
    path('master-data/items/template/', download_item_template, name='download_item_template'),
    path('master-data/workers/template/', download_worker_template, name='download_worker_template'),
    path('master-data/job-workers/template/', download_job_worker_template, name='download_job_worker_template'),
    path('master-data/import/preview/', preview_import_data, name='preview_import_data'),
    path('master-data/import/confirm/', confirm_import_data, name='confirm_import_data'),
]

