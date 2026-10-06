from datetime import timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.mail import send_mail
from django.conf import settings
from django.db import models, transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.text import slugify
from django.views.decorators.http import require_GET, require_POST

from marketing.models import WithdrawalRequest
from store.models import Category, Department, Product

from . import ai
from .forms import VendorProductForm, VendorProfileForm, VendorWithdrawalForm
from .models import Vendor

TRIAL_DAYS = 30


# ======================================================================
# Start / manage vendor
# ======================================================================
@login_required
@require_GET
def become_vendor(request):
    if hasattr(request.user, 'vendor_profile'):
        return redirect('vendors:dashboard')

    return render(request, 'vendors/become_vendor.html', {
        'trial_days': TRIAL_DAYS,
    })


@login_required
@require_POST
def start_trial(request):
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
# Withdrawals
# ======================================================================
@login_required
def withdraw(request):
    vendor = get_object_or_404(Vendor, user=request.user)

    available = vendor.balance
    pending_total = (
        WithdrawalRequest.objects
        .filter(
            vendor=vendor,
            status__in=[
                WithdrawalRequest.Status.PENDING,
                WithdrawalRequest.Status.APPROVED,
            ],
        )
        .aggregate(s=models.Sum('amount'))['s']
        or Decimal('0.00')
    )

    if available <= Decimal('0.00'):
        messages.info(request, 'You have no balance available to withdraw yet.')
        return redirect('vendors:dashboard')

    initial = {
        'phone_number': vendor.phone_number,
        'amount': available,
    }

    if request.method == 'POST':
        form = VendorWithdrawalForm(request.POST, max_amount=available)
        if form.is_valid():
            amount = form.cleaned_data['amount']
            phone = form.cleaned_data['phone_number']

            with transaction.atomic():
                locked = Vendor.objects.select_for_update().get(pk=vendor.pk)
                if amount > locked.balance:
                    messages.error(
                        request,
                        f'Your withdrawable balance is KES {locked.balance:.2f}.'
                    )
                    return render(request, 'vendors/withdraw.html', {
                        'vendor': vendor,
                        'form': form,
                        'available': locked.balance,
                        'pending_total': pending_total,
                    })

                locked.balance = locked.balance - amount
                locked.save(update_fields=['balance'])

                wr = WithdrawalRequest.objects.create(
                    user=request.user,
                    vendor=vendor,
                    phone_number=phone,
                    amount=amount,
                )

            try:
                from marketing.views import send_withdrawal_requested_email
                send_withdrawal_requested_email(wr)
            except Exception:
                pass

            messages.success(
                request,
                f'Withdrawal of KES {amount} is now in progress. '
                f'We will send it to {phone} within 24 hours.'
            )
            return redirect('vendors:withdrawal_history')
    else:
        form = VendorWithdrawalForm(max_amount=available, initial=initial)

    return render(request, 'vendors/withdraw.html', {
        'vendor': vendor,
        'form': form,
        'available': available,
        'pending_total': pending_total,
    })


@login_required
@require_GET
def withdrawal_history(request):
    vendor = get_object_or_404(Vendor, user=request.user)
    withdrawals = (
        WithdrawalRequest.objects
        .filter(vendor=vendor)
        .order_by('-requested_at')
    )
    return render(request, 'vendors/withdrawal_history.html', {
        'vendor': vendor,
        'withdrawals': withdrawals,
        'available': vendor.balance,
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

            if not product.department_id and product.category_id:
                product.department = product.category.department

            product.is_approved = not vendor.requires_review

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

    all_categories = Category.objects.select_related('department').order_by('name')

    return render(request, 'vendors/product_form.html', {
        'vendor': vendor,
        'form': form,
        'all_categories': all_categories,
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

    all_categories = Category.objects.select_related('department').order_by('name')

    return render(request, 'vendors/product_form.html', {
        'vendor': vendor,
        'form': form,
        'product': product,
        'all_categories': all_categories,
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


# ======================================================================
# AI suggest
# ======================================================================
@login_required
@require_POST
def ai_suggest(request):
    if not hasattr(request.user, 'vendor_profile'):
        return JsonResponse({'ok': False, 'error': 'Not a vendor.'}, status=403)

    text = (request.POST.get('text') or '').strip()
    image = request.FILES.get('image')

    if not text and not image:
        return JsonResponse(
            {'ok': False, 'error': 'Type something or upload an image first.'},
            status=400,
        )

    result = ai.suggest_product(text=text, image_file=image)
    if not result:
        return JsonResponse(
            {
                'ok': False,
                'error': 'The AI could not generate a suggestion right now. '
                         'Please fill in the fields manually.',
            },
            status=502,
        )

    dept_name = result['department'][:100]
    department = Department.objects.filter(name__iexact=dept_name).first()
    if not department:
        department = Department.objects.create(
            name=dept_name,
            slug=slugify(dept_name)[:110] or 'general',
            theme='amber',
            unit_kind='none',
            icon_kind='star',
            is_active=True,
        )

    cat_name = result['category'][:100]
    category = Category.objects.filter(
        name__iexact=cat_name, department=department,
    ).first()
    if not category:
        category = Category.objects.filter(name__iexact=cat_name).first()
        if not category:
            base_slug = slugify(cat_name)[:110] or 'general'
            slug = base_slug
            n = 1
            while Category.objects.filter(slug=slug).exists():
                n += 1
                slug = f'{base_slug}-{n}'[:110]
            category = Category.objects.create(
                name=cat_name,
                slug=slug,
                department=department,
            )

    return JsonResponse({
        'ok': True,
        'title': result['title'],
        'description': result['description'],
        'department_id': department.id,
        'department_name': department.name,
        'category_id': category.id,
        'category_name': category.name,
        'price_low': result.get('price_low'),
        'price_high': result.get('price_high'),
        'price_notes': result.get('price_notes', ''),
    })
