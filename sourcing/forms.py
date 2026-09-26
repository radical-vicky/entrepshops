from django import forms

from .models import ImportRequest


class ImportRequestForm(forms.ModelForm):
    class Meta:
        model = ImportRequest
        fields = (
            'title', 'description', 'reference_url', 'reference_image',
            'quantity', 'business_name', 'phone_number', 'delivery_location',
        )
        widgets = {
            'description': forms.Textarea(attrs={'rows': 5}),
            'title': forms.TextInput(attrs={'placeholder': 'e.g. Solar panel, 400W, mono'}),
            'reference_url': forms.URLInput(attrs={'placeholder': 'https://www.alibaba.com/product-detail/...'}),
            'phone_number': forms.TextInput(attrs={'placeholder': '254712345678'}),
            'delivery_location': forms.TextInput(attrs={'placeholder': 'e.g. Nairobi CBD, Industrial Area'}),
        }
        help_texts = {
            'reference_url': 'If you found the exact item somewhere, paste the link.',
            'reference_image': 'Optional — a photo or screenshot helps us quote faster.',
        }

    def clean_phone_number(self):
        phone = (self.cleaned_data.get('phone_number') or '').strip()
        # normalize to 2547XXXXXXXX
        cleaned = phone.replace(' ', '').replace('+', '')
        if cleaned.startswith('0'):
            cleaned = '254' + cleaned[1:]
        if cleaned.startswith('7'):
            cleaned = '254' + cleaned
        if not (cleaned.startswith('254') and len(cleaned) == 12 and cleaned[3] == '7'):
            raise forms.ValidationError(
                'Enter a Safaricom number, e.g. 254712345678.'
            )
        return cleaned

    def clean_quantity(self):
        qty = self.cleaned_data.get('quantity') or 1
        if qty < 1:
            raise forms.ValidationError('Quantity must be at least 1.')
        return qty

    def clean_reference_image(self):
        img = self.cleaned_data.get('reference_image')
        if img and img.size > 5 * 1024 * 1024:
            raise forms.ValidationError('Image must be under 5 MB.')
        return img
