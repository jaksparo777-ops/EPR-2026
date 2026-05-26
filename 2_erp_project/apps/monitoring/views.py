import csv
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.utils import timezone
from django.db.models import Q, Count
from django.contrib.auth.models import User
from django.contrib.sessions.models import Session
from django.http import StreamingHttpResponse
from core.security import require_role
from apps.monitoring.models import UserSession, AuditLog

class Echo:
    """An object that implements just the write method of the file-like interface.
    Used for streaming large CSV responses without memory bloat.
    """
    def write(self, value):
        return value

@require_role('System Admin')
def monitoring_dashboard(request):
    """
    Renders the central security control panel dashboard.
    Restricted to System Admin role operators.
    """
    # Active Session Window: 15 minutes of inactivity threshold
    inactivity_threshold = timezone.now() - timezone.timedelta(minutes=15)
    
    # Active sessions
    active_sessions = UserSession.objects.filter(
        is_active=True,
        last_activity__gte=inactivity_threshold
    ).select_related('user')
    
    # Audit Logs filtering
    query = request.GET.get('q', '').strip()
    dept_filter = request.GET.get('dept', '').strip()
    action_filter = request.GET.get('action', '').strip()
    
    logs = AuditLog.objects.all().select_related('user')
    
    if query:
        logs = logs.filter(
            Q(user__username__icontains=query) |
            Q(details__icontains=query) |
            Q(object_repr__icontains=query)
        )
        
    if dept_filter:
        logs = logs.filter(department=dept_filter)
        
    if action_filter:
        logs = logs.filter(action=action_filter)
        
    # Get last 150 log entries for performance in the dashboard stream
    sliced_logs = logs[:150]
    
    # KPI metrics calculation
    today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    
    active_ops_count = active_sessions.values('user').distinct().count()
    total_active_devices = active_sessions.count()
    
    alerts_today = AuditLog.objects.filter(
        timestamp__gte=today_start,
        action__in=['DELETE', 'TERMINATE']
    ).count()
    
    # Analytics breakdown calculations for Chart.js
    dept_counts = AuditLog.objects.values('department').annotate(count=Count('id'))
    dept_chart_labels = []
    dept_chart_data = []
    dept_dict = dict(AuditLog.DEPARTMENT_CHOICES)
    for dc in dept_counts:
        dept_chart_labels.append(dept_dict.get(dc['department'], dc['department']).title())
        dept_chart_data.append(dc['count'])
        
    action_counts = AuditLog.objects.values('action').annotate(count=Count('id'))
    action_chart_labels = []
    action_chart_data = []
    action_dict = dict(AuditLog.ACTION_CHOICES)
    for ac in action_counts:
        action_chart_labels.append(action_dict.get(ac['action'], ac['action']).title())
        action_chart_data.append(ac['count'])
        
    context = {
        'active_sessions': active_sessions,
        'logs': sliced_logs,
        'active_ops_count': active_ops_count,
        'total_active_devices': total_active_devices,
        'alerts_today': alerts_today,
        'query': query,
        'dept_filter': dept_filter,
        'action_filter': action_filter,
        'departments': AuditLog.DEPARTMENT_CHOICES,
        'actions': AuditLog.ACTION_CHOICES,
        
        # Chart Data
        'dept_chart_labels': dept_chart_labels,
        'dept_chart_data': dept_chart_data,
        'action_chart_labels': action_chart_labels,
        'action_chart_data': action_chart_data,
    }
    
    return render(request, 'monitoring/dashboard.html', context)


@require_role('System Admin')
def export_audit_logs(request):
    """
    Exports the filtered audit logs directly as a downloadable CSV.
    Uses streaming to support massive security dumps without memory leaks.
    """
    query = request.GET.get('q', '').strip()
    dept_filter = request.GET.get('dept', '').strip()
    action_filter = request.GET.get('action', '').strip()
    
    logs = AuditLog.objects.all().select_related('user')
    
    if query:
        logs = logs.filter(
            Q(user__username__icontains=query) |
            Q(details__icontains=query) |
            Q(object_repr__icontains=query)
        )
        
    if dept_filter:
        logs = logs.filter(department=dept_filter)
        
    if action_filter:
        logs = logs.filter(action=action_filter)
        
    # Setup streaming CSV writer
    pseudo_buffer = Echo()
    writer = csv.writer(pseudo_buffer)

    def log_iterator():
        # Header row
        yield writer.writerow(['Timestamp', 'Operator', 'IP Address', 'Department', 'Action', 'Target Object', 'Details'])
        
        # Streaming records
        for log in logs.iterator():
            username = log.user.username if log.user else "System"
            yield writer.writerow([
                log.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                username,
                log.ip_address or 'N/A',
                log.get_department_display(),
                log.get_action_display(),
                log.object_repr or '',
                log.details or ''
            ])

    response = StreamingHttpResponse(log_iterator(), content_type="text/csv")
    response['Content-Disposition'] = f'attachment; filename="audit_logs_{timezone.now().strftime("%Y%m%d_%H%M%S")}.csv"'
    return response


@require_role('System Admin')
def terminate_session(request, session_id):
    """
    Forcefully terminates an active user session.
    Revokes the active flag and purges from Django's backend session storage.
    """
    if request.method == 'POST':
        user_session = get_object_or_404(UserSession, id=session_id)
        
        # Don't let admins kill their own active session
        admin_session_key = request.session.session_key
        if user_session.session_key == admin_session_key:
            messages.error(request, "Security Safeguard: You cannot terminate your own active session.")
            return redirect('monitoring_dashboard')
            
        # 1. Mark session inactive in custom DB log
        user_session.is_active = False
        user_session.save()
        
        # 2. Delete the session from Django session backend
        try:
            session_obj = Session.objects.get(session_key=user_session.session_key)
            session_obj.delete()
        except Session.DoesNotExist:
            pass
            
        # 3. Log security alert audit entry
        AuditLog.objects.create(
            user=request.user,
            ip_address=request.META.get('REMOTE_ADDR'),
            department='security',
            action='TERMINATE',
            object_repr=f"Session: {user_session.user.username}",
            details=f"Admin {request.user.username} force terminated active session of {user_session.user.username} (IP: {user_session.ip_address})."
        )
        
        messages.success(request, f"Successfully terminated active session for user: {user_session.user.username}.")
        
    return redirect('monitoring_dashboard')

