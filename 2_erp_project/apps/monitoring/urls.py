from django.urls import path
from apps.monitoring.views import monitoring_dashboard, terminate_session, export_audit_logs

urlpatterns = [
    path('monitoring/', monitoring_dashboard, name='monitoring_dashboard'),
    path('monitoring/export-logs/', export_audit_logs, name='export_audit_logs'),
    path('monitoring/terminate-session/<int:session_id>/', terminate_session, name='terminate_session'),
]

