from django.db import models
from apps.monitoring.soft_delete import SoftDeleteModel
from django.utils import timezone
from apps.products.models import ProcessType

class SalaryModel(models.TextChoices):
    DAILY = "DAILY", "Daily Wage"
    FIXED = "FIXED", "Monthly Fixed"
    HOURLY = "HOURLY", "Hourly/Time Based"


class Worker(SoftDeleteModel):
    name = models.CharField(max_length=100)
    salary_model = models.CharField(
        max_length=20,
        choices=SalaryModel.choices,
        default=SalaryModel.DAILY
    )
    daily_rate = models.FloatField(
        default=0,
        help_text="Rate per day for Daily Wage workers"
    )
    monthly_fixed_salary = models.FloatField(
        default=0,
        help_text="Fixed monthly salary for Fixed model"
    )
    overtime_rate = models.FloatField(
        default=0,
        help_text="Rate per hour of overtime"
    )
    monthly_allowance = models.FloatField(
        default=0,
        help_text="Automated monthly allowance added to salary"
    )
    process = models.CharField(
        max_length=50,
        choices=ProcessType.choices,
        default="machining"
    )
    phone = models.CharField(max_length=20, blank=True, null=True)

    # Professional HR Fields
    employee_id = models.CharField(max_length=50, blank=True, null=True, unique=True)
    designation = models.CharField(max_length=100, blank=True, null=True)
    joining_date = models.DateField(blank=True, null=True)
    standard_shift_hours = models.FloatField(default=8, help_text="Standard working hours per day")
    
    # Personal Info & Compliance
    identity_number = models.CharField(max_length=100, blank=True, null=True, help_text="Aadhar / Govt ID")
    emergency_contact_name = models.CharField(max_length=100, blank=True, null=True)
    emergency_contact_phone = models.CharField(max_length=20, blank=True, null=True)
    blood_group = models.CharField(max_length=10, blank=True, null=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.employee_id or not str(self.employee_id).strip():
            if self.id:
                self.employee_id = f"EMP-{1000 + self.id}"
            else:
                last_w = Worker.objects.order_by("-id").first()
                base_id = (last_w.id + 1) if last_w else 1
                while True:
                    code = f"EMP-{1000 + base_id}"
                    if not Worker.objects.filter(employee_id=code).exists():
                        self.employee_id = code
                        break
                    base_id += 1
        
        if self.overtime_rate == 0 and self.salary_model == "DAILY" and self.standard_shift_hours > 0:
            self.overtime_rate = round(self.daily_rate / self.standard_shift_hours, 2)
            
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.employee_id or '---'} - {self.name}"


class JobWorker(SoftDeleteModel):
    name = models.CharField(max_length=100)
    process = models.CharField(
        max_length=50,
        choices=ProcessType.choices
    )
    phone = models.CharField(max_length=20, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    gst_number = models.CharField(max_length=15, blank=True, null=True)
    active = models.BooleanField(default=True)
    jw_code = models.CharField(max_length=50, blank=True, null=True, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.jw_code or not str(self.jw_code).strip():
            last_jw = JobWorker.all_objects.order_by("-id").first()
            base_id = (last_jw.id + 1) if last_jw else 1
            while True:
                code = f"JW-{1000 + base_id}"
                if not JobWorker.all_objects.filter(jw_code=code).exists():
                    self.jw_code = code
                    break
                base_id += 1
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.jw_code or '---'} - {self.name}"


class AttendanceStatus(models.TextChoices):
    PRESENT = "PRESENT", "Present"
    ABSENT = "ABSENT", "Absent"
    HALF_DAY = "HALF_DAY", "Half Day"


class Attendance(models.Model):
    worker = models.ForeignKey(Worker, on_delete=models.CASCADE, related_name='attendance_records')
    date = models.DateField(default=timezone.now)
    status = models.CharField(max_length=20, choices=AttendanceStatus.choices, default=AttendanceStatus.PRESENT)
    overtime_hours = models.FloatField(default=0)
    notes = models.TextField(blank=True, null=True)

    class Meta:
        unique_together = ('worker', 'date')
        verbose_name_plural = "Attendance"
