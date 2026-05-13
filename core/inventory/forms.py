from django import forms

from .models import StockTransaction, Item, Client, Worker


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
            'code', 'name', 'client', 'category', 'material', 'variant',
            'weight_per_piece', 'lot_size', 'lot_with_box',
            'machining_required', 'polishing_required', 'packing_required', 'notes'
        ]

class ClientForm(forms.ModelForm):
    class Meta:
        model = Client
        fields = ['name', 'phone', 'city']

class WorkerForm(forms.ModelForm):
    class Meta:
        model = Worker
        fields = ['name', 'process', 'phone']