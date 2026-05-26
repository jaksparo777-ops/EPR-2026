from django.urls import path
from apps.workforce.views import (
    delete_worker,
    delete_job_worker,
    get_internal_worker_profile,
    get_job_worker_profile,
    mark_attendance,
    get_attendance_for_date,
)

urlpatterns = [
    path('delete/<int:worker_id>/', delete_worker, name='delete_worker'),
    path('job-delete/<int:job_worker_id>/', delete_job_worker, name='delete_job_worker'),
    path('profile/<int:worker_id>/', get_internal_worker_profile, name='get_internal_worker_profile'),
    path('job-profile/<int:jw_id>/', get_job_worker_profile, name='get_job_worker_profile'),
    path('mark-attendance/', mark_attendance, name='mark_attendance'),
    path('attendance-for-date/', get_attendance_for_date, name='get_attendance_for_date'),
]
