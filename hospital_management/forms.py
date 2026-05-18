from django import forms


class HospitalForm(forms.Form):
    name = forms.CharField(
        max_length=255,
        widget=forms.TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'Name'}),
    )
    address = forms.CharField(
        max_length=500,
        widget=forms.TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'Address'}),
    )
    phone = forms.CharField(
        max_length=50,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'Phone (optional)'}),
    )
