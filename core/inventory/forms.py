from django import forms

from .models import StockTransaction


class CastingEntryForm(forms.ModelForm):

    class Meta:

        model = StockTransaction

        fields = [

            'heat_no',
            'client',
            'item',
            'quantity',
            'weight',
            'notes',

        ]

        widgets = {

            'heat_no': forms.TextInput(

                attrs={
                    'class': 'form-control',
                    'placeholder': 'Heat Number',
                    'id': 'id_heat_no'
                }

            ),

            'client': forms.Select(

                attrs={
                    'class': 'form-control',
                    'id': 'id_client'
                }

            ),

            'item': forms.Select(

                attrs={
                    'class': 'form-control',
                    'id': 'id_item'
                }

            ),

            'quantity': forms.NumberInput(

                attrs={
                    'class': 'form-control',
                    'id': 'id_quantity'
                }

            ),

            'weight': forms.NumberInput(

                attrs={
                    'class': 'form-control',
                    'step': '0.001',
                    'id': 'id_weight'
                }

            ),

            'notes': forms.Textarea(

                attrs={
                    'class': 'form-control',
                    'rows': 3
                }

            ),

        }