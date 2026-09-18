from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.text import slugify
from django.views.decorators.http import require_POST

from payments.mpesa import MpesaError, stk_push
from store.models import Category, Department, Product

from .models import Vendor, VendorSubscriptionPayment


@login_required
def become_vendor(request):
    existing = Vendor.objects.filter(user=request.user).first()
    if existing:
        return redirect('vendors:dashboard')

    if request.method == 'POST':
        business_name = request.POST.get('business_name', '').strip()
        phone_number = request.POST.get('phone_number', '').strip()
        if not (business_name and phone_number):
            messages.error(request, 'Please fill in your business name and phone number.')
            return render(request, 'vendors/become_vendor.html')

        vendor = Vendor.objects.create(user=request.user, business_name=business_name, phone_number=phone_number)
        messages.success(request, 'Account created — pay your first month to start listing products.')
        return redirect('vendors:subscribe')

    return render(request, 'vendors/become_vendor.html', {
        'fee': settings.VENDOR_SUBSCRIPTION_FEE_KES,
        'days': settings.VENDOR_SUBSCRIPTION_DAYS,
    })


@login_required
def subscribe(request):
    vendor = get_object_or_404(Vendor, user=request.user)
    fee = settings.VENDOR_SUBSCRIPTION_FEE_KES
    days = settings.VENDOR_SUBSCRIPTION_DAYS

    if request.method == 'POST':
        phone_number = request.POST.get('phone_number', '').strip() or vendor.phone_number
        try:
            response = stk_push(
                phone_number=phone_number, amount=fee,
                account_reference=f'VendorSub{vendor.id}',
                transaction_desc=f'{days}-day platform subscription',
            )
            VendorSubscriptionPayment.objects.create(
                vendor=vendor, amount=fee, phone_number=phone_number, days=days,
                checkout_request_id=response.get('CheckoutRequestID', ''),
            )
            messages.success(request, 'Check your phone to complete the subscription payment via M-Pesa.')
            return redirect('vendors:dashboard')
        except MpesaError as exc:
            messages.error(request, f'Could not start the payment. ({exc})')

    return render(request, 'vendors/subscribe.html', {'vendor': vendor, 'fee': fee, 'days': days})


@login_required
def dashboard(request):
    vendor = get_object_or_404(Vendor, user=request.user)
    products = vendor.products.all().select_related('category')
    recent_payments = vendor.subscription_payments.all()[:10]
    return render(request, 'vendors/dashboard.html', {
        'vendor': vendor,
        'products': products,
        'recent_payments': recent_payments,
        'fee': settings.VENDOR_SUBSCRIPTION_FEE_KES,
    })


@login_required
def product_form(request, product_id=None):
    vendor = get_object_or_404(Vendor, user=request.user)
    if not vendor.can_sell:
        messages.error(
            request,
            'Your subscription needs to be active (and approved) before you can list products.'
            if not vendor.is_approved else
            'Your subscription has expired — renew to add or edit products.'
        )
        return redirect('vendors:dashboard')

    product = None
    if product_id:
        product = get_object_or_404(Product, id=product_id, vendor=vendor)

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        category_id = request.POST.get('category')
        price = request.POST.get('price', '').strip()
        stock = request.POST.get('stock', '0').strip()
        description = request.POST.get('description', '').strip()

        if not (name and category_id and price):
            messages.error(request, 'Please fill in the product name, category, and price.')
        else:
            category = get_object_or_404(Category, id=category_id)
            if product is None:
                slug = slugify(name)
                base_slug = slug
                i = 1
                while Product.objects.filter(slug=slug).exists():
                    i += 1
                    slug = f'{base_slug}-{i}'
                product = Product(vendor=vendor, slug=slug)
            product.category = category
            product.name = name
            product.price = price
            product.stock = stock or 0
            product.description = description
            if request.FILES.get('image'):
                product.image = request.FILES['image']
            product.is_active = True
            product.save()
            messages.success(
                request,
                'Product saved — it will appear once an admin approves it.' if not product.is_approved
                else 'Product saved.'
            )
            return redirect('vendors:dashboard')

    return render(request, 'vendors/product_form.html', {
        'vendor': vendor,
        'product': product,
        'departments': Department.objects.filter(is_active=True).prefetch_related('categories'),
    })


@login_required
@require_POST
def product_delete(request, product_id):
    vendor = get_object_or_404(Vendor, user=request.user)
    product = get_object_or_404(Product, id=product_id, vendor=vendor)
    product.delete()
    messages.success(request, 'Product removed.')
    return redirect('vendors:dashboard')
