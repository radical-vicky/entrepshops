from django import forms

from store.models import Category, Product, ProductVariant


class VendorProductForm(forms.ModelForm):
    """A vendor's product creation/edit form. Lighter than the admin
    version — no vendor field, no approval flag. Those are set by the view."""

    class Meta:
        model = Product
        fields = (
            'category', 'name', 'description', 'image',
            'price', 'compare_at_price', 'stock', 'volume_ml',
        )
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4}),
        }

    def __init__(self, *args, vendor=None, **kwargs):
        super().__init__(*args, **kwargs)
        # Vendors can only attach to categories that exist. Prevent them
        # from creating new departments.
        self.fields['category'].queryset = Category.objects.select_related(
            'department'
        ).order_by('department__name', 'name')
        self.fields['category'].empty_label = 'Choose a category…'

    def clean_price(self):
        price = self.cleaned_data.get('price')
        if price is not None and price <= 0:
            raise forms.ValidationError('Price must be greater than zero.')
        return price

    def clean_image(self):
        image = self.cleaned_data.get('image')
        if image and image.size > 5 * 1024 * 1024:
            raise forms.ValidationError('Image must be under 5 MB.')
        return image


class VendorProfileForm(forms.Form):
    business_name = forms.CharField(max_length=150)
    phone_number = forms.CharField(max_length=20, required=False)
    description = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 3}), required=False,
    )
