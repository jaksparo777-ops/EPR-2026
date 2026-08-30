from django import forms
from apps.master_data.models import Item, Client
from apps.authentication.models import Worker, WorkerType
from .models import StockTransaction


class CastingEntryForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['client'].queryset = Client.objects.filter(company_id=1)
        self.fields['item'].queryset = Item.objects.filter(client__company_id=1)

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
            'casting_required', 'machining_required', 'polishing_required', 'packing_required', 'notes',
            'min_casting_stock', 'min_machining_stock', 'min_polishing_stock', 'min_ready_stock',
            'is_raw_material', 'raw_material', 'yield_pcs_per_unit', 'uom'
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.master_data.models import Category, Material, Item
        
        self.fields['raw_material'] = forms.ModelChoiceField(
            queryset=Item.objects.filter(is_raw_material=True).order_by('code'),
            required=False,
            empty_label="-- No Raw Material Conversion --",
            widget=forms.Select(attrs={'class': 'form-control'})
        )
        
        cats = Category.objects.all().order_by('name')
        self.fields['category'] = forms.ChoiceField(
            choices=[(c.name, c.name) for c in cats],
            widget=forms.Select(attrs={'class': 'form-control'})
        )
        
        mats = Material.objects.all().order_by('name')
        self.fields['material'] = forms.ChoiceField(
            choices=[(m.name, m.name) for m in mats],
            widget=forms.Select(attrs={'class': 'form-control'})
        )

class ClientForm(forms.ModelForm):
    class Meta:
        model = Client
        fields = ['name', 'phone', 'email', 'city', 'address', 'gst_number', 'company', 'packing_preference']

class WorkerForm(forms.ModelForm):
    class Meta:
        model = Worker
        fields = [
            'name', 'process', 'daily_rate', 'phone', 'employee_id', 
            'designation', 'joining_date', 'standard_shift_hours', 
            'identity_number', 'emergency_contact_name', 'emergency_contact_phone', 
            'blood_group', 'casting_rate_per_kg', 'salary_model', 'monthly_fixed_salary', 'fixed_salary_calc_mode', 'monthly_allowance', 'allowance_calc_mode', 'overtime_rate', 'company', 'active'
        ]

class JobWorkerForm(forms.ModelForm):
    class Meta:
        model = Worker
        fields = ['name', 'process', 'phone', 'email', 'address', 'gst_number', 'jw_code', 'casting_rate_per_kg', 'company', 'active']

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.worker_type = 'JOB_WORKER'
        if commit:
            instance.save()
        return instance