from decimal import Decimal

from django import forms

from store.models import Category, Department, Product


class VendorProductForm(forms.ModelForm):
    """A vendor's product form, laid out like Shopify's add-product screen."""

    class Meta:
        model = Product
        fields = (
            'name',
            'description',
            'image',
            'price',
            'compare_at_price',
            'stock',
            'department',
            'category',
            'is_active',
        )
        widgets = {
            'name': forms.TextInput(attrs={
                'placeholder': 'Short sleeve t-shirt',
                'autofocus': True,
            }),
            'description': forms.Textarea(attrs={
                'rows': 8,
                'placeholder': 'Describe the item — materials, specs, condition, dimensions. '
                               'Anything a customer would want to know.',
            }),
            'price': forms.NumberInput(attrs={'placeholder': '0.00', 'step': '0.01', 'min': '0'}),
            'compare_at_price': forms.NumberInput(attrs={'placeholder': '0.00', 'step': '0.01', 'min': '0'}),
            'stock': forms.NumberInput(attrs={'placeholder': '0', 'min': '0'}),
        }
        labels = {
            'name': 'Title',
            'description': 'Description',
            'image': 'Product image',
            'price': 'Price (KES)',
            'compare_at_price': 'Compare-at price',
            'stock': 'Quantity available',
            'department': 'Department',
            'category': 'Category',
            'is_active': 'Active',
        }
        help_texts = {
            'compare_at_price': 'Optional. Shows a struck-through "was" price.',
            'stock': 'How many units you currently have ready to ship.',
            'is_active': 'Uncheck to hide from the shop without deleting it.',
        }

    def __init__(self, *args, vendor=None, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['department'].queryset = Department.objects.filter(is_active=True).order_by('name')
        self.fields['department'].empty_label = 'Choose a department…'
        self.fields['department'].required = True

        self.fields['category'].queryset = Category.objects.select_related('department').order_by('name')
        self.fields['category'].empty_label = 'Choose a category…'
        self.fields['category'].required = True

        self.fields['image'].required = False
        self.fields['compare_at_price'].required = False
        self.fields['description'].required = False

        if not self.instance.pk:
            self.fields['stock'].initial = 0
            self.fields['is_active'].initial = True

    def clean_name(self):
        name = (self.cleaned_data.get('name') or '').strip()
        if len(name) < 3:
            raise forms.ValidationError('Title must be at least 3 characters.')
        return name

    def clean_price(self):
        price = self.cleaned_data.get('price')
        if price is None or price <= 0:
            raise forms.ValidationError('Price must be greater than zero.')
        return price

    def clean_compare_at_price(self):
        compare = self.cleaned_data.get('compare_at_price')
        price = self.cleaned_data.get('price')
        if compare and price and compare <= price:
            raise forms.ValidationError(
                'Compare-at price must be higher than the price, or leave it blank.'
            )
        return compare

    def clean_image(self):
        image = self.cleaned_data.get('image')
        if image and image.size > 5 * 1024 * 1024:
            raise forms.ValidationError('Image must be under 5 MB.')
        return image

    def clean(self):
        cleaned = super().clean()
        department = cleaned.get('department')
        category = cleaned.get('category')
        if department and category and category.department_id and category.department_id != department.id:
            self.add_error(
                'category',
                f'"{category.name}" belongs to "{category.department.name}", '
                f'not to "{department.name}". Pick a matching pair.'
            )
        return cleaned


class VendorProfileForm(forms.Form):
    business_name = forms.CharField(max_length=150)
    phone_number = forms.CharField(max_length=20, required=False)
    description = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 3}), required=False,
    )


class VendorWithdrawalForm(forms.Form):
    """Vendors withdraw from Vendor.balance. Minimum KES 500."""

    MIN_AMOUNT = 500

    phone_number = forms.RegexField(
        regex=r'^2547\d{8}$',
        error_messages={
            'invalid': 'Enter a Safaricom number in the format 2547XXXXXXXX '
                       '(e.g. 254712345678).'
        },
        label='M-Pesa phone number',
        widget=forms.TextInput(attrs={'placeholder': '254712345678'}),
    )
    amount = forms.DecimalField(
        min_value=500, max_digits=12, decimal_places=2,
        label='Amount (KES)',
        widget=forms.NumberInput(attrs={'step': '1', 'min': '500'}),
    )

    def __init__(self, *args, max_amount=0, **kwargs):
        super().__init__(*args, **kwargs)
        self.max_amount = Decimal(str(max_amount))
        self.fields['amount'].widget.attrs['max'] = str(self.max_amount)
        self.fields['amount'].help_text = (
            f'Available to withdraw: KES {self.max_amount:.2f}'
        )

    def clean_amount(self):
        amount = self.cleaned_data['amount']
        if amount < Decimal(self.MIN_AMOUNT):
            raise forms.ValidationError(
                f'Minimum withdrawal is KES {self.MIN_AMOUNT}.'
            )
        if amount > self.max_amount:
            raise forms.ValidationError(
                f'Your withdrawable balance is KES {self.max_amount:.2f}.'
            )
        return amount
