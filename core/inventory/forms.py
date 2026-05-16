from django import forms

from .models import StockTransaction, Item, Client, Worker, JobWorker


class CastingEntryForm(forms.ModelForm):

    class Meta:
        model = StockTransaction
        fields = ['heat_no', 'client', 'item', 'quantity', 'weight', 'notes']
        widgets = {
            'heat_no': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Heat Number'}),
            'client': forms.Select(attrs={'class': 'form-control'}),
            'item': forms.Select(attrs={'class': 'form-control'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control'}),
            'weight': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.001'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

class ItemForm(forms.ModelForm):
    class Meta:
        model = Item
        fields = [
            'code', 'name', 'client', 'category', 'sub_category', 'material', 'variant', 'item_type',
            'casting_weight', 'machining_weight',
            'lot_size', 'lot_with_box',
            'casting_required', 'machining_required', 'polishing_required', 'packing_required', 'notes'
        ]

class ClientForm(forms.ModelForm):
    class Meta:
        model = Client
        fields = ['name', 'phone', 'email', 'city', 'address', 'gst_number']

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
        fields = ['name', 'process', 'phone', 'email', 'address', 'gst_number']