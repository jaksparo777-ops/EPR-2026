from django.db import models
from django.contrib.auth.models import User

class UserSession(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='active_sessions')
    session_key = models.CharField(max_length=40, unique=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(null=True, blank=True)
    device_type = models.CharField(max_length=20, default='Desktop') # Desktop, Mobile, Tablet, Bot
    browser = models.CharField(max_length=50, null=True, blank=True)
    os = models.CharField(max_length=50, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_activity = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['-last_activity']
        verbose_name = 'User Session'
        verbose_name_plural = 'User Sessions'

    def __str__(self):
        return f"{self.user.username} - {self.device_type} ({self.ip_address})"


class AuditLog(models.Model):
    DEPARTMENT_CHOICES = [
        ('production', 'Production'),
        ('logistics', 'Logistics'),
        ('workforce', 'Workforce'),
        ('ledger_pay', 'Ledger & Pay'),
        ('products', 'Products & Master'),
        ('security', 'Security & Access'),
    ]

    ACTION_CHOICES = [
        ('CREATE', 'Create'),
        ('UPDATE', 'Update'),
        ('DELETE', 'Delete'),
        ('LOGIN', 'Login'),
        ('LOGOUT', 'Logout'),
        ('TERMINATE', 'Force Session Termination'),
    ]

    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='audit_logs')
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    department = models.CharField(max_length=50, choices=DEPARTMENT_CHOICES)
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    object_repr = models.CharField(max_length=255, null=True, blank=True)
    details = models.TextField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']
        verbose_name = 'Audit Log'
        verbose_name_plural = 'Audit Logs'

    def __str__(self):
        user_str = self.user.username if self.user else "System"
        return f"[{self.get_action_display()}] {user_str} - {self.object_repr} at {self.timestamp}"
