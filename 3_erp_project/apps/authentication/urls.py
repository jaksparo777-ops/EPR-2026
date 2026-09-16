from django.urls import path
from apps.authentication.views import (
    select_company,
    user_management_view,
    user_create_api,
    user_edit_api,
    user_toggle_active_api,
    user_reset_password_api,
    device_check_status_api,
    device_register_api,
    device_approve_api,
    device_reject_api,
    device_revoke_api,
    device_rename_api,
    device_purge_stale_api,
    device_deduplicate_api,
    device_delete_api,
    device_update_hardware_api,
    device_quick_trust_api,
    device_set_security_mode_api,
    audit_logs_api,
    clear_audit_alerts_api,
    live_activity_stream_api,
    heartbeat_api,
    session_keep_alive_api,
    admin_emergency_reset_api,
    admin_update_recovery_key_api,
    device_master_key_unlock_api
)

urlpatterns = [
    path('select-company/', select_company, name='select_company'),
    path('users/', user_management_view, name='user_management'),
    path('api/users/create/', user_create_api, name='user_create_api'),
    path('api/users/<int:user_id>/edit/', user_edit_api, name='user_edit_api'),
    path('api/users/<int:user_id>/toggle-active/', user_toggle_active_api, name='user_toggle_active_api'),
    path('api/users/<int:user_id>/reset-password/', user_reset_password_api, name='user_reset_password_api'),
    
    # Admin Emergency Recovery APIs
    path('api/admin/emergency-reset/', admin_emergency_reset_api, name='admin_emergency_reset_api'),
    path('api/admin/update-recovery-key/', admin_update_recovery_key_api, name='admin_update_recovery_key_api'),
    
    # Device Security API Endpoints
    path('api/devices/check-status/', device_check_status_api, name='device_check_status_api'),
    path('api/devices/register/', device_register_api, name='device_register_api'),
    path('api/devices/master-key-unlock/', device_master_key_unlock_api, name='device_master_key_unlock_api'),
    path('api/devices/<int:device_pk>/approve/', device_approve_api, name='device_approve_api'),
    path('api/devices/<int:device_pk>/reject/', device_reject_api, name='device_reject_api'),
    path('api/devices/<int:device_pk>/revoke/', device_revoke_api, name='device_revoke_api'),
    path('api/devices/<int:device_pk>/rename/', device_rename_api, name='device_rename_api'),
    path('api/devices/<int:device_pk>/delete/', device_delete_api, name='device_delete_api'),
    path('api/devices/purge-stale/', device_purge_stale_api, name='device_purge_stale_api'),
    path('api/devices/deduplicate/', device_deduplicate_api, name='device_deduplicate_api'),
    path('api/devices/update-hardware/', device_update_hardware_api, name='device_update_hardware_api'),
    path('api/devices/quick-trust/', device_quick_trust_api, name='device_quick_trust_api'),
    path('api/devices/set-security-mode/', device_set_security_mode_api, name='device_set_security_mode_api'),
    
    # System Audit & Live Stream API Endpoints
    path('api/audit-logs/', audit_logs_api, name='audit_logs_api'),
    path('api/audit-logs/clear-alerts/', clear_audit_alerts_api, name='clear_audit_alerts_api'),
    path('api/live-activity/', live_activity_stream_api, name='live_activity_stream_api'),
    path('api/heartbeat/', heartbeat_api, name='heartbeat_api'),
    path('api/session/keep-alive/', session_keep_alive_api, name='session_keep_alive_api'),
]
