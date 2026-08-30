import uuid
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import Max
from django.utils import timezone
from apps.master_data.models import LegalEntity

class CustomUser(AbstractUser):
    """
    Extends the default User model to support role-based access and multi-company scoping.
    """
    ROLE_CHOICES = [
        ('ADMIN', 'System Admin / Owner'),
        ('CASTING_MGR', 'Foundry Casting Manager'),
        ('MACHINING_MGR', 'Machining & Polishing Supervisor'),
        ('PACKAGING_MGR', 'Packaging & Warehouse Manager'),
        ('SALES_ADMIN', 'Sales & Customer PO Admin'),
        ('ACCOUNTANT', 'Accounts & Payroll Manager'),
        ('AUDITOR', 'Auditor (Read-Only)'),
        ('CUSTOM', 'Custom Role Matrix'),
    ]

    role = models.CharField(max_length=30, choices=ROLE_CHOICES, default='CUSTOM')
    company = models.ForeignKey(
        LegalEntity, 
        on_delete=models.SET_NULL, 
        blank=True, 
        null=True, 
        related_name="users",
        help_text="The active legal company this user belongs to. Leave empty for system-wide access."
    )
    can_view_financials = models.BooleanField(default=True, help_text="Can view rates, costs, wages, and monetary figures")
    permissions = models.JSONField(default=dict, blank=True, help_text="Hierarchical Permission Tree Matrix (JSON)")
    allowed_companies = models.ManyToManyField(
        LegalEntity,
        blank=True,
        related_name="allowed_users",
        help_text="Explicit legal companies this user is allowed to access and switch between."
    )
    is_global_access = models.BooleanField(
        default=False, 
        help_text="True if granted Global / All Access (Owner Portal)."
    )

    class Meta:
        verbose_name = "User Account"
        verbose_name_plural = "User Accounts"

    @property
    def permissions_json(self):
        import json
        if isinstance(self.permissions, dict):
            return json.dumps(self.permissions)
        return json.dumps({})

    def get_allowed_companies(self):
        """
        Returns a QuerySet of LegalEntity instances the user is authorized to access.
        """
        if self.is_superuser or self.role == 'ADMIN' or self.is_global_access:
            return LegalEntity.objects.all()
        allowed = self.allowed_companies.all()
        if allowed.exists():
            return allowed
        if self.company:
            return LegalEntity.objects.filter(id=self.company.id)
        return LegalEntity.objects.all()

    def can_access_company(self, company_obj_or_id):
        """
        Returns True if the user can access the specified company ID or 'global'.
        """
        if self.is_superuser or self.role == 'ADMIN' or self.is_global_access:
            return True
        if str(company_obj_or_id) == 'global':
            return False
        allowed_ids = list(self.get_allowed_companies().values_list('id', flat=True))
        try:
            cid = company_obj_or_id.id if hasattr(company_obj_or_id, 'id') else int(company_obj_or_id)
            return cid in allowed_ids
        except (ValueError, TypeError):
            return False

    def has_perm_node(self, path):
        """
        Checks dot-notation permission path, e.g. 'machining.stock.adjust_inventory' or 'casting'
        Superusers or ADMIN role users always return True.
        """
        if self.is_superuser or self.role == 'ADMIN':
            return True
        if not path:
            return True
        if not isinstance(self.permissions, dict) or not self.permissions:
            # Default fallback: staff users have access unless explicitly configured
            return self.is_staff or self.is_superuser
        
        parts = path.split('.')
        curr = self.permissions
        for p in parts:
            if not isinstance(curr, dict):
                return bool(curr)
            if p not in curr:
                return False
            curr = curr[p]
        return bool(curr)

    def has_module_access(self, module_name):
        """
        Checks top-level module access, e.g. 'casting', 'machining', 'labor_ledger'
        """
        if self.is_superuser or self.role == 'ADMIN':
            return True
        if not isinstance(self.permissions, dict) or not self.permissions:
            return True
        mod_node = self.permissions.get(module_name)
        if mod_node is None:
            return True
        if isinstance(mod_node, bool):
            return mod_node
        if isinstance(mod_node, dict):
            return mod_node.get('enabled', True)
        return True

    def __str__(self):
        company_scope = self.company.name if self.company else "Global/All"
        return f"{self.username} ({self.get_role_display()} - {company_scope})"


class ProcessType(models.TextChoices):
    CASTING = "casting", "Casting"
    MACHINING = "machining", "Machining"
    POLISHING = "polishing", "Polishing"
    PACKAGING = "packaging", "Packaging"


class SalaryModel(models.TextChoices):
    DAILY = "DAILY", "Daily Wage"
    FIXED = "FIXED", "Monthly Fixed"
    HOURLY = "HOURLY", "Hourly/Time Based"


class FixedSalaryCalcMode(models.TextChoices):
    PRO_RATA = "PRO_RATA", "Pro-Rata (Divided by Net Working Days)"
    FIXED_FULL = "FIXED_FULL", "Full Fixed Monthly (No Absent Cut)"
    CALENDAR_30 = "CALENDAR_30", "30-Day Fixed Rate (Salary / 30)"


class AllowanceCalcMode(models.TextChoices):
    FIXED = "FIXED", "Full Fixed Monthly Allowance"
    PRO_RATA = "PRO_RATA", "Pro-Rata Attendance Based (Working Days)"


class WorkerType(models.TextChoices):
    IN_HOUSE = "IN_HOUSE", "In-House Worker"
    JOB_WORKER = "JOB_WORKER", "External Job Worker"


class Worker(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, null=True, blank=True)

    worker_type = models.CharField(max_length=20, choices=WorkerType.choices, default=WorkerType.IN_HOUSE)
    user = models.OneToOneField(
        CustomUser,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="worker_profile",
        help_text="Optional portal login account associated with this worker or job worker."
    )
    name = models.CharField(max_length=100)
    company = models.ForeignKey(LegalEntity, on_delete=models.PROTECT, related_name="workers")
    salary_model = models.CharField(max_length=20, choices=SalaryModel.choices, default=SalaryModel.DAILY)
    daily_rate = models.FloatField(default=0)
    monthly_fixed_salary = models.FloatField(default=0)
    fixed_salary_calc_mode = models.CharField(
        max_length=20,
        choices=FixedSalaryCalcMode.choices,
        default=FixedSalaryCalcMode.PRO_RATA,
        help_text="Pro-rata absent cut vs full fixed salary vs 30-day rate"
    )
    overtime_rate = models.FloatField(default=0)
    monthly_allowance = models.FloatField(default=0)
    allowance_calc_mode = models.CharField(
        max_length=20,
        choices=AllowanceCalcMode.choices,
        default=AllowanceCalcMode.FIXED,
        help_text="Full fixed allowance vs pro-rata attendance divided by net working days"
    )
    process = models.CharField(max_length=50, choices=ProcessType.choices, default="machining")
    phone = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    gst_number = models.CharField(max_length=15, blank=True, null=True)
    employee_id = models.CharField(max_length=50, blank=True, null=True, unique=True)
    jw_code = models.CharField(max_length=50, blank=True, null=True, unique=True)
    designation = models.CharField(max_length=100, blank=True, null=True)
    joining_date = models.DateField(blank=True, null=True)
    standard_shift_hours = models.FloatField(default=8)
    identity_number = models.CharField(max_length=100, blank=True, null=True, help_text="Aadhar / Govt ID")
    emergency_contact_name = models.CharField(max_length=100, blank=True, null=True)
    emergency_contact_phone = models.CharField(max_length=20, blank=True, null=True)
    blood_group = models.CharField(max_length=10, blank=True, null=True)
    casting_rate_per_kg = models.FloatField(default=0.0)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if self.worker_type == WorkerType.IN_HOUSE and (not self.employee_id or not str(self.employee_id).strip()):
            max_id = Worker.objects.filter(employee_id__startswith='EMP-').aggregate(Max('id'))['id__max'] or 1000
            self.employee_id = f"EMP-{max_id + 1}"
        elif self.worker_type == WorkerType.JOB_WORKER and (not self.jw_code or not str(self.jw_code).strip()):
            max_id = Worker.objects.filter(jw_code__startswith='JW-').aggregate(Max('id'))['id__max'] or 1000
            self.jw_code = f"JW-{max_id + 1}"
            
        if self.overtime_rate == 0 and self.salary_model == "DAILY" and self.standard_shift_hours > 0:
            self.overtime_rate = round(self.daily_rate / self.standard_shift_hours, 2)
        super().save(*args, **kwargs)

    def __str__(self):
        code = self.employee_id or self.jw_code or '---'
        return f"{code} - {self.name} ({self.company.name})"




class AuthorizedDevice(models.Model):
    """
    Device Authorization Whitelist model.
    Stores device fingerprint UUIDs, 3-state authorization status (Pending, Approved, Rejected),
    and hardware/user-agent metadata.
    """
    STATUS_CHOICES = (
        ('PENDING', 'Pending Approval'),
        ('APPROVED', 'Approved'),
        ('REJECTED', 'Rejected / Blocked'),
    )

    device_id = models.CharField(max_length=100, unique=True, db_index=True, help_text="Unique UUID device fingerprint string")
    name = models.CharField(max_length=150, blank=True, help_text="Device label (e.g. Casting Floor Tablet #1)")
    assigned_user = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name="authorized_devices")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING', db_index=True)
    rejection_reason = models.TextField(blank=True, null=True, help_text="Reason why device was rejected/blocked by Admin")
    device_type = models.CharField(max_length=20, default='MOBILE', help_text="MOBILE, TABLET, DESKTOP")
    brand_model = models.CharField(max_length=120, blank=True, null=True, help_text="e.g. Apple iPhone, Samsung Galaxy Tab")
    os_info = models.CharField(max_length=100, blank=True, null=True, help_text="e.g. iOS 17.5, Android 14, Windows 11")
    browser_info = models.CharField(max_length=100, blank=True, null=True, help_text="e.g. Safari, Chrome")
    hardware_fingerprint = models.CharField(max_length=255, blank=True, null=True)
    user_agent = models.TextField(blank=True, null=True)
    is_approved = models.BooleanField(default=False, help_text="True if approved by Admin")
    approved_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name="approved_devices")
    approved_at = models.DateTimeField(null=True, blank=True)
    last_ip = models.CharField(max_length=50, blank=True, null=True)
    last_used_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Authorized Device"
        verbose_name_plural = "Authorized Devices"
        ordering = ['-created_at']

    @property
    def is_rejected(self):
        return self.status == 'REJECTED'

    @property
    def is_online(self):
        if not self.last_used_at or self.status != 'APPROVED':
            return False
        from django.utils import timezone
        from datetime import timedelta
        return (timezone.now() - self.last_used_at) <= timedelta(minutes=3)

    def get_device_icon(self):
        dt = (self.device_type or '').upper()
        if dt == 'DESKTOP':
            return '💻'
        elif dt == 'TABLET':
            return '📱'
        return '📱'

    def __str__(self):
        label = self.name or self.device_id[:12]
        return f"{label} ({self.get_status_display()})"


class WorkerRateHistory(models.Model):
    worker = models.ForeignKey(Worker, on_delete=models.CASCADE, related_name="rate_history")
    daily_rate = models.FloatField(default=0.0)
    monthly_fixed_salary = models.FloatField(default=0.0)
    overtime_rate = models.FloatField(default=0.0)
    monthly_allowance = models.FloatField(default=0.0)
    effective_from = models.DateField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-effective_from', '-created_at']

    def __str__(self):
        return f"{self.worker.name} @ Eff: {self.effective_from} (Daily: ₹{self.daily_rate}, Fixed: ₹{self.monthly_fixed_salary})"


class SystemAuditLog(models.Model):
    EVENT_TYPE_CHOICES = [
        ('CREATE', '➕ Data Created'),
        ('UPDATE', '✏️ Data Updated'),
        ('DELETE', '🗑 Data Deleted'),
        ('SECURITY_BLOCKED', '🚫 Permission Blocked'),
        ('SECURITY_REJECTED', '🛑 Device Access Rejected'),
        ('AUTH_LOGIN', '🔑 User Login'),
        ('AUTH_FAILED', '⚠️ Login Failed'),
        ('PAGE_VIEW', '👁 Page Navigation'),
    ]

    NETWORK_SCOPE_CHOICES = [
        ('FACTORY_LOCAL', '🏢 Factory Local Wi-Fi'),
        ('EXTERNAL_REMOTE', '🌐 External Remote Network'),
    ]

    timestamp = models.DateTimeField(default=timezone.now, db_index=True)
    user = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='audit_logs')
    device = models.ForeignKey(AuthorizedDevice, on_delete=models.SET_NULL, null=True, blank=True, related_name='audit_logs')
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    network_scope = models.CharField(max_length=20, choices=NETWORK_SCOPE_CHOICES, default='FACTORY_LOCAL')
    event_type = models.CharField(max_length=30, choices=EVENT_TYPE_CHOICES, db_index=True)
    module_name = models.CharField(max_length=60, db_index=True)
    object_id = models.CharField(max_length=60, null=True, blank=True)
    object_repr = models.CharField(max_length=255, null=True, blank=True)
    changes_json = models.JSONField(null=True, blank=True)
    request_path = models.CharField(max_length=255, null=True, blank=True)
    user_agent_summary = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        verbose_name = "System Audit Log"
        verbose_name_plural = "System Audit Logs"
        ordering = ['-timestamp']

    def __str__(self):
        user_str = self.user.username if self.user else "Anonymous/System"
        return f"[{self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}] {self.get_event_type_display()} by {user_str} ({self.module_name})"


class UserLiveActivity(models.Model):
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name='live_activity')
    device = models.ForeignKey(AuthorizedDevice, on_delete=models.SET_NULL, null=True, blank=True)
    current_page = models.CharField(max_length=100, default='Dashboard')
    current_path = models.CharField(max_length=255, default='/')
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    network_scope = models.CharField(max_length=20, default='FACTORY_LOCAL')
    last_heartbeat = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        verbose_name = "User Live Activity"
        verbose_name_plural = "User Live Activities"
        ordering = ['-last_heartbeat']

    @property
    def is_active_now(self):
        if not self.last_heartbeat:
            return False
        return (timezone.now() - self.last_heartbeat).total_seconds() <= 180

    def __str__(self):
        return f"{self.user.username} @ {self.current_page} ({self.last_heartbeat.strftime('%H:%M:%S')})"


class MonthlySettlementLock(models.Model):
    """
    Stores frozen settlement locks per worker and month.
    Prevents routine Master Data edits from altering past fully-paid payroll settlements.
    Can be explicitly unlocked by an Admin for intentional data entry corrections.
    """
    worker = models.ForeignKey(Worker, on_delete=models.CASCADE, related_name="settlement_locks")
    month_str = models.CharField(max_length=7, db_index=True, help_text="YYYY-MM e.g. 2026-07")
    is_locked = models.BooleanField(default=True, help_text="True if settlement is frozen")
    locked_earnings = models.FloatField(default=0.0, help_text="Frozen earned wages at time of settlement")
    locked_paid = models.FloatField(default=0.0, help_text="Frozen total paid at time of settlement")
    locked_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True)
    unlocked_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('worker', 'month_str')
        verbose_name = "Monthly Settlement Lock"
        verbose_name_plural = "Monthly Settlement Locks"

    def __str__(self):
        status = "LOCKED" if self.is_locked else "UNLOCKED"
        return f"{self.worker.name} - {self.month_str} ({status})"

