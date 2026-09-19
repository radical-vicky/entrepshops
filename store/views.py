from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_GET, require_POST

from .cart import Cart
from .models import (
    Category, DeliveryAddress, Department, Product, ProductVariant, Promotion,
)


def _safe_next(request, fallback):
    """Validate ?next= so we never redirect off-site."""
    nxt = request.POST.get('next') or request.GET.get('next')
    if nxt and url_has_allowed_host_and_scheme(
        nxt, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return nxt
    return fallback


def _parse_quantity(request, default=1, minimum=1, maximum=999):
    try:
        q = int(request.POST.get('quantity', default))
    except (TypeError, ValueError):
        q = default
    return max(minimum, min(maximum, q))


@require_GET
def home(request):
    department_slug = request.GET.get('department')
    category_slug = request.GET.get('category')
    search_query = request.GET.get('q', '').strip()

    departments = Department.objects.filter(is_active=True)
    categories = Category.objects.all()
    products = Product.objects.visible().select_related(
        'category', 'category__department', 'department'
    ).prefetch_related('variants', 'images')

    selected_department = None
    selected_category = None

    if department_slug:
        selected_department = get_object_or_404(
            Department, slug=department_slug, is_active=True
        )
        categories = categories.filter(department=selected_department)
        products = products.filter(department=selected_department)

    if category_slug:
        selected_category = get_object_or_404(Category, slug=category_slug)
        if selected_department and selected_category.department_id != selected_department.id:
            raise Http404(
                f'Category "{selected_category.name}" is not in the '
                f'"{selected_department.name}" department.'
            )
        if not selected_department and selected_category.department_id:
            selected_department = selected_category.department
        products = products.filter(category=selected_category)

    # Sticky department theme.
    if selected_department:
        request.session['current_department_id'] = selected_department.id
    elif not department_slug and not category_slug:
        request.session.pop('current_department_id', None)

    if search_query:
        from django.db.models import Q
        products = products.filter(
            Q(name__icontains=search_query) | Q(description__icontains=search_query)
        )

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        grid_html = render_to_string(
            'store/_product_grid.html',
            {'products': products, 'selected_department': selected_department},
            request=request,
        )
        if search_query:
            heading = f'Results for "{search_query}"'
        elif selected_category:
            heading = selected_category.name
        elif selected_department:
            heading = selected_department.name
        else:
            heading = 'All departments'
        return JsonResponse({
            'grid_html': grid_html,
            'heading': heading,
            'dept_theme': selected_department.theme if selected_department else '',
        })

    hero_products = list(
        Product.objects.visible().filter(is_featured=True)
        .select_related('category', 'department')
        .prefetch_related('variants', 'images')[:5]
    )
    if not hero_products:
        hero_products = list(
            Product.objects.visible().filter(stock__gt=0)
            .exclude(image='').exclude(image__isnull=True)
            .order_by('-created_at')[:3]
        ) or list(Product.objects.visible()[:3])

    themes = ['green', 'orange', 'gold']
    hero_slides = []
    for i, product in enumerate(hero_products):
        lo, _hi = product.price_range
        hero_slides.append({
            'product': product,
            'theme': themes[i % len(themes)],
            'badge': product.hero_tagline or 'Featured',
            'headline': product.hero_headline or product.name,
            'description': (
                product.hero_description
                or product.description
                or f'KES {lo} — order now for delivery to your door.'
            ),
        })

    promotions = Promotion.objects.filter(is_active=True)[:5]

    return render(request, 'store/home.html', {
        'categories': categories,
        'selected_category': selected_category,
        'products': products,
        'hero_slides': hero_slides,
        'promotions': promotions,
        'search_query': search_query,
        'departments': departments,
        'selected_department': selected_department,
    })


@require_GET
def product_detail(request, slug):
    product = get_object_or_404(
        Product.objects.visible()
        .select_related('category', 'category__department', 'department')
        .prefetch_related('variants', 'images', 'offers'),
        slug=slug,
    )
    return render(request, 'store/product_detail.html', {'product': product})


@require_POST
def cart_add(request, product_id):
    cart = Cart(request)
    product = get_object_or_404(Product.objects.visible(), id=product_id)
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    if not product.is_deliverable:
        message = (
            f'{product.name} cannot be added — online sale/delivery of this '
            'item is currently restricted.'
        )
        if is_ajax:
            return JsonResponse({'ok': False, 'message': message}, status=400)
        messages.error(request, message)
        return redirect(_safe_next(request, 'store:home'))

    if not product.is_available:
        message = f'{product.name} is not available right now.'
        if is_ajax:
            return JsonResponse({'ok': False, 'message': message}, status=400)
        messages.error(request, message)
        return redirect(_safe_next(request, product.get_absolute_url()))

    # Resolve the variant the customer picked (or the default one).
    variant = None
    variant_id = request.POST.get('variant_id')
    if variant_id:
        variant = product.variants.filter(id=variant_id, is_active=True).first()
    if not variant and product.has_variants:
        variant = product.available_variants.first()

    quantity = _parse_quantity(request)

    # Stock check — against the variant if there is one, else the product.
    available_stock = variant.stock if variant else product.stock
    if quantity > available_stock:
        message = f'Only {available_stock} left in stock.'
        if is_ajax:
            return JsonResponse({'ok': False, 'message': message}, status=400)
        messages.error(request, message)
        return redirect(_safe_next(request, product.get_absolute_url()))

    cart.add(product=product, variant=variant, quantity=quantity)

    label = f'{product.name} ({variant.size_label})' if variant else product.name

    if is_ajax:
        return JsonResponse({
            'ok': True,
            'message': f'Added {label} to your cart.',
            'cart_count': len(cart),
        })

    messages.success(request, f'Added {label} to your cart.')
    return redirect(_safe_next(request, 'store:cart_detail'))


@require_POST
def cart_remove(request, product_id):
    cart = Cart(request)
    product = get_object_or_404(Product, id=product_id)
    variant_id = request.POST.get('variant_id')
    variant = None
    if variant_id:
        variant = ProductVariant.objects.filter(id=variant_id, product=product).first()
    cart.remove(product, variant=variant)
    label = f'{product.name} ({variant.size_label})' if variant else product.name
    messages.info(request, f'Removed {label} from your cart.')
    return redirect('store:cart_detail')


@require_POST
def cart_update(request, product_id):
    cart = Cart(request)
    product = get_object_or_404(Product, id=product_id)
    variant_id = request.POST.get('variant_id')
    variant = None
    if variant_id:
        variant = ProductVariant.objects.filter(id=variant_id, product=product).first()
    quantity = _parse_quantity(request)
    cart.add(product=product, variant=variant, quantity=quantity, replace=True)
    return redirect('store:cart_detail')


@require_GET
def cart_detail(request):
    cart = Cart(request)
    return render(request, 'store/cart.html', {'cart': cart})


@login_required
@require_GET
def address_list(request):
    addresses = request.user.addresses.all()
    return render(request, 'store/address_list.html', {'addresses': addresses})


@login_required
def address_add(request):
    if request.method == 'POST':
        from django.db import transaction
        required = ('full_name', 'phone_number', 'building_name', 'street', 'area')
        missing = [f for f in required if not (request.POST.get(f) or '').strip()]
        if missing:
            messages.error(request, f'Please fill in: {", ".join(missing)}.')
            return render(request, 'store/address_form.html', status=400)

        is_default = request.POST.get('is_default') == 'on'

        try:
            with transaction.atomic():
                if is_default:
                    DeliveryAddress.objects.filter(
                        user=request.user, is_default=True
                    ).update(is_default=False)
                DeliveryAddress.objects.create(
                    user=request.user,
                    label=request.POST.get('label') or 'Home',
                    full_name=request.POST['full_name'].strip(),
                    phone_number=request.POST['phone_number'].strip(),
                    building_name=request.POST['building_name'].strip(),
                    apartment_number=request.POST.get('apartment_number', '').strip(),
                    floor=request.POST.get('floor', '').strip(),
                    street=request.POST['street'].strip(),
                    area=request.POST['area'].strip(),
                    city=request.POST.get('city') or 'Nairobi',
                    delivery_notes=request.POST.get('delivery_notes', '').strip(),
                    latitude=request.POST.get('latitude') or None,
                    longitude=request.POST.get('longitude') or None,
                    is_default=is_default,
                )
        except Exception as exc:
            messages.error(request, f'Could not save address: {exc}')
            return render(request, 'store/address_form.html', status=400)

        messages.success(request, 'Delivery address saved.')
        return redirect('store:address_list')
    return render(request, 'store/address_form.html')