from django import forms
from .models import Item, Client, Category, Material

class ItemForm(forms.ModelForm):
    class Meta:
        model = Item
        fields = [
            'code', 'name', 'client', 'category', 'sub_category', 'material', 'variant', 'item_type',
            'casting_weight', 'machining_weight',
            'lot_size', 'lot_with_box',
            'casting_required', 'machining_required', 'polishing_required', 'packing_required', 'notes'
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        cats = Category.objects.all().order_by('name')
        cat_choices = [(c.name, c.name) for c in cats]
        if not any(c[0].upper() == 'OTHER' for c in cat_choices):
            cat_choices.append(('Other', 'Other'))
        self.fields['category'] = forms.ChoiceField(
            choices=cat_choices,
            widget=forms.Select(attrs={'class': 'form-control'})
        )
        
        mats = Material.objects.all().order_by('name')
        mat_choices = [(m.name, m.name) for m in mats]
        if not any(m[0].upper() == 'OTHER' for m in mat_choices):
            mat_choices.append(('Other', 'Other'))
        self.fields['material'] = forms.ChoiceField(
            choices=mat_choices,
            widget=forms.Select(attrs={'class': 'form-control'})
        )


class ClientForm(forms.ModelForm):
    class Meta:
        model = Client
        fields = ['name', 'phone', 'email', 'city', 'address', 'gst_number']
