from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.mail import send_mail
from django.conf import settings
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.text import slugify
from django.views.decorators.http import require_GET, require_POST

from store.models import Product

from .forms import VendorProductForm, VendorProfileForm
from .models import Vendor

TRIAL_DAYS = 30


# ======================================================================
# Start / manage vendor
# ======================================================================
@login_required
@require_GET
def become_vendor(request):
    """Landing page. If the user already has a vendor profile, redirect
    to their dashboard."""
    if hasattr(request.user, 'vendor_profile'):
        return redirect('vendors:dashboard')

    return render(request, 'vendors/become_vendor.html', {
        'trial_days': TRIAL_DAYS,
    })


@login_required
@require_POST
def start_trial(request):
    """Create the vendor row and start the 30-day trial."""
    if hasattr(request.user, 'vendor_profile'):
        messages.info(request, 'You already have a vendor account.')
        return redirect('vendors:dashboard')

    business_name = (request.POST.get('business_name') or '').strip()
    if not business_name:
        messages.error(request, 'Please enter your business name.')
        return redirect('vendors:become_vendor')

    phone_number = (request.POST.get('phone_number') or '').strip()

    now = timezone.now()
    vendor = Vendor.objects.create(
        user=request.user,
        business_name=business_name[:150],
        phone_number=phone_number[:20],
        trial_started_at=now,
        trial_ends_at=now + timedelta(days=TRIAL_DAYS),
    )

    try:
        send_welcome_email(vendor)
    except Exception:
        pass

    messages.success(
        request,
        f'Your 30-day free trial has started. '
        f'You can list products until {vendor.trial_ends_at:%d %b %Y}.'
    )
    return redirect('vendors:dashboard')


def send_welcome_email(vendor):
    user = vendor.user
    if not user.email:
        return
    subject = 'Welcome to Entrep Shop — your 30-day free trial has started'
    body = render_to_string('vendors/emails/welcome.txt', {
        'user': user,
        'vendor': vendor,
        'trial_days': TRIAL_DAYS,
        'site_name': 'Entrep - Shop',
    })
    send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [user.email], fail_silently=False)


# ======================================================================
# Dashboard
# ======================================================================
@login_required
@require_GET
def dashboard(request):
    vendor = get_object_or_404(Vendor, user=request.user)
    products = vendor.products.select_related('category').order_by('-created_at')

    return render(request, 'vendors/dashboard.html', {
        'vendor': vendor,
        'products': products,
    })


@login_required
def edit_profile(request):
    vendor = get_object_or_404(Vendor, user=request.user)

    if request.method == 'POST':
        form = VendorProfileForm(request.POST)
        if form.is_valid():
            vendor.business_name = form.cleaned_data['business_name'][:150]
            vendor.phone_number = form.cleaned_data['phone_number'][:20]
            vendor.description = form.cleaned_data['description']
            vendor.save(update_fields=['business_name', 'phone_number', 'description'])
            messages.success(request, 'Profile updated.')
            return redirect('vendors:dashboard')
    else:
        form = VendorProfileForm(initial={
            'business_name': vendor.business_name,
            'phone_number': vendor.phone_number,
            'description': vendor.description,
        })

    return render(request, 'vendors/edit_profile.html', {
        'vendor': vendor,
        'form': form,
    })


# ======================================================================
# Product upload
# ======================================================================
@login_required
@require_GET
def product_list(request):
    vendor = get_object_or_404(Vendor, user=request.user)
    products = vendor.products.select_related('category').order_by('-created_at')
    return render(request, 'vendors/product_list.html', {
        'vendor': vendor,
        'products': products,
    })


@login_required
def product_create(request):
    vendor = get_object_or_404(Vendor, user=request.user)

    if not vendor.can_list_products:
        messages.error(
            request,
            'Your free trial has ended. Subscribe to add new products. '
            'Your existing products stay live.'
        )
        return redirect('vendors:dashboard')

    if request.method == 'POST':
        form = VendorProductForm(request.POST, request.FILES, vendor=vendor)
        if form.is_valid():
            product = form.save(commit=False)
            product.vendor = vendor

            # Auto-fill department from category (Product.save handles this
            # too, but we do it here so the form doesn't need to expose it).
            if product.category_id and product.category.department_id:
                product.department = product.category.department

            # First 3 products need admin approval. After that they
            # auto-approve if the vendor is trusted.
            product.is_approved = not vendor.requires_review
            product.is_active = True

            # Slug must be unique. Build from name and de-dupe.
            base_slug = slugify(product.name)[:150] or 'product'
            slug = base_slug
            n = 1
            while Product.objects.filter(slug=slug).exists():
                n += 1
                slug = f'{base_slug}-{n}'[:160]
            product.slug = slug

            product.save()

            if product.is_approved:
                messages.success(request, f'"{product.name}" is now live in your shop.')
            else:
                messages.success(
                    request,
                    f'"{product.name}" has been submitted. Our team reviews the '
                    f'first 3 products — you\'ll get an email when it\'s approved.'
                )
            return redirect('vendors:product_list')
    else:
        form = VendorProductForm(vendor=vendor)

    return render(request, 'vendors/product_form.html', {
        'vendor': vendor,
        'form': form,
        'mode': 'create',
    })


@login_required
def product_edit(request, product_id):
    vendor = get_object_or_404(Vendor, user=request.user)
    product = get_object_or_404(Product, id=product_id, vendor=vendor)

    if request.method == 'POST':
        form = VendorProductForm(request.POST, request.FILES, vendor=vendor, instance=product)
        if form.is_valid():
            form.save()
            messages.success(request, 'Product updated.')
            return redirect('vendors:product_list')
    else:
        form = VendorProductForm(vendor=vendor, instance=product)

    return render(request, 'vendors/product_form.html', {
        'vendor': vendor,
        'form': form,
        'product': product,
        'mode': 'edit',
    })


@login_required
@require_POST
def product_delete(request, product_id):
    vendor = get_object_or_404(Vendor, user=request.user)
    product = get_object_or_404(Product, id=product_id, vendor=vendor)
    product.delete()
    messages.success(request, 'Product removed.')
    return redirect('vendors:product_list')
