from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.contrib.auth.signals import user_logged_in, user_logged_out
from apps.monitoring.models import AuditLog, UserSession
from apps.monitoring.middleware import get_current_user, get_current_ip

# Mapping of custom app labels to audit log departments
APP_DEPARTMENTS = {
    'products': 'products',
    'production': 'production',
    'logistics': 'logistics',
    'workforce': 'workforce',
    'ledger_pay': 'ledger_pay',
}

@receiver(post_save)
def audit_post_save(sender, instance, created, **kwargs):
    """Dynamically monitors and audits all database insertions and modifications."""
    app_label = sender._meta.app_label
    if app_label not in APP_DEPARTMENTS:
        return
        
    user = get_current_user()
    ip = get_current_ip()
    action = 'CREATE' if created else 'UPDATE'
    
    model_name = sender._meta.verbose_name.title()
    try:
        object_repr = str(instance)
    except Exception:
        object_repr = f"{model_name} #{instance.pk if hasattr(instance, 'pk') else 'Unknown'}"
        
    details = f"{model_name} '{object_repr}' was {'created' if created else 'updated'}."

    
    # Enrich details based on model attributes if available
    try:
        if sender.__name__ == 'StockTransaction':
            worker_name = instance.worker.name if instance.worker else (instance.job_worker.name if instance.job_worker else 'N/A')
            details += f" | Type: {instance.transaction_type.upper()} | Qty: {instance.quantity} | Item: {instance.item.name} | Worker: {worker_name}"
        elif sender.__name__ == 'LaborPayment':
            worker_name = instance.worker.name if instance.worker else (instance.job_worker.name if instance.job_worker else 'N/A')
            details += f" | Worker: {worker_name} | Amount Paid: ₹{instance.amount} | Date: {instance.date}"
        elif sender.__name__ == 'Attendance':
            details += f" | Worker: {instance.worker.name} | Status: {instance.get_status_display()} | Date: {instance.date}"
        elif sender.__name__ == 'Loan':
            worker_name = instance.worker.name if instance.worker else (instance.job_worker.name if instance.job_worker else 'N/A')
            status_str = "Active" if instance.is_active else "Inactive"
            details += f" | Worker: {worker_name} | Amount: ₹{instance.total_amount} | Status: {status_str}"
        elif sender.__name__ == 'Carton':
            details += f" | Label: {instance.carton_label} | Client: {instance.client.name if instance.client else 'N/A'} | Status: {instance.status}"
    except Exception:
        pass
        
    AuditLog.objects.create(
        user=user,
        ip_address=ip,
        department=APP_DEPARTMENTS[app_label],
        action=action,
        object_repr=f"{model_name}: {object_repr}",
        details=details
    )


@receiver(post_delete)
def audit_post_delete(sender, instance, **kwargs):
    """Dynamically monitors and audits all database deletions."""
    app_label = sender._meta.app_label
    if app_label not in APP_DEPARTMENTS:
        return
        
    user = get_current_user()
    ip = get_current_ip()
    
    model_name = sender._meta.verbose_name.title()
    try:
        object_repr = str(instance)
    except Exception:
        object_repr = f"{model_name} #{instance.pk if hasattr(instance, 'pk') else 'Unknown'}"
        
    details = f"{model_name} '{object_repr}' was deleted."

    
    try:
        AuditLog.objects.create(
            user=user,
            ip_address=ip,
            department=APP_DEPARTMENTS[app_label],
            action='DELETE',
            object_repr=f"{model_name}: {object_repr}",
            details=details
        )
    except Exception:
        pass



@receiver(user_logged_in)
def log_user_login(sender, request, user, **kwargs):
    """Logs security audit entry on operator login."""
    ip = get_current_ip() or request.META.get('REMOTE_ADDR')
    
    AuditLog.objects.create(
        user=user,
        ip_address=ip,
        department='security',
        action='LOGIN',
        object_repr=f"User: {user.username}",
        details=f"User '{user.username}' successfully authenticated and logged in."
    )


@receiver(user_logged_out)
def log_user_logout(sender, request, user, **kwargs):
    """Logs security audit entry and deactivates active session on user logout."""
    if not user:
        return
        
    ip = get_current_ip() or request.META.get('REMOTE_ADDR')
    
    AuditLog.objects.create(
        user=user,
        ip_address=ip,
        department='security',
        action='LOGOUT',
        object_repr=f"User: {user.username}",
        details=f"User '{user.username}' initiated sign out."
    )
    
    # Mark the corresponding UserSession record inactive
    if request and hasattr(request, 'session') and request.session.session_key:
        UserSession.objects.filter(session_key=request.session.session_key).update(is_active=False)
