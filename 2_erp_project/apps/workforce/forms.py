from django import forms
from .models import Worker, JobWorker

class WorkerForm(forms.ModelForm):
    class Meta:
        model = Worker
        fields = [
            'name', 'process', 'daily_rate', 'phone', 'employee_id', 
            'designation', 'joining_date', 'standard_shift_hours', 
            'identity_number', 'emergency_contact_name', 'emergency_contact_phone', 
            'blood_group', 'salary_model', 'monthly_fixed_salary', 'monthly_allowance', 'overtime_rate'
        ]


class JobWorkerForm(forms.ModelForm):
    class Meta:
        model = JobWorker
        fields = ['name', 'process', 'phone', 'email', 'address', 'gst_number', 'jw_code']
