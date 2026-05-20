from django.urls import path
from django.contrib.auth import views as auth_views

from inventory.views import (

    dashboard,

    casting_entry,

    master_data,

    casting_stock,

    machining_stock,
    
    polishing_stock,
    
    ready_stock,

    machining_entry,

    polishing_entry,

    packaging_view,

    issue_machining,

    delete_item,
    delete_items_bulk,
    delete_client,
    delete_worker,
    delete_job_worker,
    edit_item,

    dispatch_view,

    get_item_workers,
    get_worker_items,

    assembly_view,

    get_item_composition,

    get_internal_worker_profile,
    get_job_worker_profile,
    add_worker_allocation,
    delete_worker_allocation,
    labor_ledger,
    mark_attendance,
    record_labor_payment,
    job_worker_monthly_report,
    get_attendance_for_date,
    worker_monthly_report,
)

urlpatterns = [

    path(
        'login/',
        auth_views.LoginView.as_view(template_name='login.html'),
        name='login'
    ),

    path(
        'logout/',
        auth_views.LogoutView.as_view(),
        name='logout'
    ),

    path(
        '',
        dashboard,
        name='dashboard'
    ),

    path(
        'casting/',
        casting_entry,
        name='casting_entry'
    ),

    path(
        'machining/',
        machining_entry,
        name='machining_entry'
    ),

    path(
        'polishing/',
        polishing_entry,
        name='polishing_entry'
    ),

    path(
        'packaging/',
        packaging_view,
        name='packaging'
    ),

    path(
        'assembly/',
        assembly_view,
        name='assembly'
    ),

    path(
        'master-data/',
        master_data,
        name='master_data'
    ),

    path(
        'casting-stock/',
        casting_stock,
        name='casting_stock'
    ),

    path(
        'machining-stock/',
        machining_stock,
        name='machining_stock'
    ),

    path(
        'polishing-stock/',
        polishing_stock,
        name='polishing_stock'
    ),

    path(
        'ready-stock/',
        ready_stock,
        name='ready_stock'
    ),

    path(
        'issue-machining/',
        issue_machining,
        name='issue_machining'
    ),

    path(
        'delete-item/<int:item_id>/',
        delete_item,
        name='delete_item'
    ),
    path(
        'delete-items-bulk/',
        delete_items_bulk,
        name='delete_items_bulk'
    ),
    path(
        'delete-client/<int:client_id>/',
        delete_client,
        name='delete_client'
    ),
    path(
        'delete-worker/<int:worker_id>/',
        delete_worker,
        name='delete_worker'
    ),
    path(
        'delete-job-worker/<int:job_worker_id>/',
        delete_job_worker,
        name='delete_job_worker'
    ),

    path(
        'edit-item/<int:item_id>/',
        edit_item,
        name='edit_item'
    ),

    path(
        'dispatch/',
        dispatch_view,
        name='dispatch'
    ),
    
    path(
        'api/item/<int:item_id>/workers/',
        get_item_workers,
        name='get_item_workers'
    ),
    path(
        'api/worker/<str:worker_id>/items/',
        get_worker_items,
        name='get_worker_items'
    ),
    
    path(
        'api/item/<int:item_id>/composition/',
        get_item_composition,
        name='get_item_composition'
    ),
    path(
        'api/worker/<int:worker_id>/profile/',
        get_internal_worker_profile,
        name='get_internal_worker_profile'
    ),

    path(
        'api/job-worker/<int:jw_id>/profile/',
        get_job_worker_profile,
        name='get_job_worker_profile'
    ),
    path(
        'api/allocation/add/',
        add_worker_allocation,
        name='add_worker_allocation'
    ),
    path(
        'api/allocation/<int:alloc_id>/delete/',
        delete_worker_allocation,
        name='delete_worker_allocation'
    ),
    path(
        'ledger/',
        labor_ledger,
        name='labor_ledger'
    ),
    path(
        'api/attendance/mark/',
        mark_attendance,
        name='mark_attendance'
    ),
    path(
        'api/payment/record/',
        record_labor_payment,
        name='record_labor_payment'
    ),

    path(
        'ledger/job-worker/<int:jw_id>/report/',
        job_worker_monthly_report,
        name='job_worker_report'
    ),
    path('api/attendance/fetch/', get_attendance_for_date, name='get_attendance_for_date'),
    path('worker/<int:worker_id>/report/', worker_monthly_report, name='worker_monthly_report'),
]
