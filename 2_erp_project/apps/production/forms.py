from django import forms
from .models import StockTransaction

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
