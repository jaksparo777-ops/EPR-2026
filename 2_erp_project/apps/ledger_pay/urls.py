from django.urls import path
from apps.ledger_pay.views import (
    labor_ledger,
    worker_monthly_report,
    job_worker_monthly_report,
    add_worker_allocation,
    delete_worker_allocation,
    get_item_workers,
    get_worker_items,
    record_labor_payment,
)

urlpatterns = [
    path('labor-ledger/', labor_ledger, name='labor_ledger'),
    path('worker-report/<int:worker_id>/', worker_monthly_report, name='worker_report'),
    path('job-worker-report/<int:jw_id>/', job_worker_monthly_report, name='job_worker_report'),
    path('add-allocation/', add_worker_allocation, name='add_worker_allocation'),
    path('delete-allocation/<int:alloc_id>/', delete_worker_allocation, name='delete_worker_allocation'),
    path('item-workers/<int:item_id>/', get_item_workers, name='get_item_workers'),
    path('worker-items/<str:worker_id>/', get_worker_items, name='get_worker_items'),
    path('record-payment/', record_labor_payment, name='record_labor_payment'),
]
