from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .cart import Cart
from .models import Category, DeliveryAddress, Department, Product, Promotion


def home(request):
    department_slug = request.GET.get('department')
    category_slug = request.GET.get('category')
    search_query = request.GET.get('q', '').strip()
    departments = Department.objects.filter(is_active=True)
    categories = Category.objects.all()
    products = Product.objects.visible().select_related('category', 'category__department')

    selected_department = None
    selected_category = None

    if category_slug:
        selected_category = get_object_or_404(Category, slug=category_slug)
        products = products.filter(category=selected_category)
        selected_department = selected_category.department

    if department_slug:
        selected_department = get_object_or_404(Department, slug=department_slug, is_active=True)
        categories = categories.filter(department=selected_department)
        products = products.filter(category__department=selected_department)

    # Remember the department the customer is currently browsing so the
    # theme sticks across other pages (cart, checkout, etc) until they
    # switch departments again — not just on this one page.
    if selected_department:
        request.session['current_department_id'] = selected_department.id
    elif department_slug == '':
        # Explicit "All departments" click clears any sticky theme.
        request.session.pop('current_department_id', None)

    if search_query:
        from django.db.models import Q
        products = products.filter(
            Q(name__icontains=search_query) | Q(description__icontains=search_query)
        )

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        from django.http import JsonResponse
        from django.template.loader import render_to_string
        grid_html = render_to_string('store/_product_grid.html', {'products': products}, request=request)
        if search_query:
            heading = f'Results for "{search_query}"'
        elif selected_category:
            heading = selected_category.name
        elif selected_department:
            heading = selected_department.name
        else:
            heading = 'All departments'
        return JsonResponse({'grid_html': grid_html, 'heading': heading, 'dept_theme': selected_department.theme if selected_department else ''})

    hero_products = list(
        Product.objects.visible().filter(is_featured=True)
        .select_related('category')[:5]
    )
    if not hero_products:
        # Nothing marked as featured yet — fall back to a few in-stock
        # products (preferring ones with a real photo) so the hero never
        # renders empty on a fresh install.
        hero_products = list(
            Product.objects.visible().filter(stock__gt=0)
            .exclude(image='').order_by('-created_at')[:3]
        ) or list(Product.objects.visible()[:3])

    themes = ['green', 'orange', 'gold']
    hero_slides = []
    for i, product in enumerate(hero_products):
        hero_slides.append({
            'product': product,
            'theme': themes[i % len(themes)],
            'badge': product.hero_tagline or 'Featured',
            'headline': product.hero_headline or product.name,
            'description': product.hero_description or product.description or f'KES {product.price} — order now for delivery to your door.',
        })

    promotions = Promotion.objects.filter(is_active=True)

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


def product_detail(request, slug):
    product = get_object_or_404(Product.objects.visible(), slug=slug)
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
            from django.http import JsonResponse
            return JsonResponse({'ok': False, 'message': message}, status=400)
        messages.error(request, message)
        return redirect(request.POST.get('next') or 'store:home')

    quantity = int(request.POST.get('quantity', 1))
    cart.add(product=product, quantity=quantity)

    if is_ajax:
        from django.http import JsonResponse
        return JsonResponse({
            'ok': True,
            'message': f'Added {product.name} to your cart.',
            'cart_count': len(cart),
        })

    messages.success(request, f'Added {product.name} to your cart.')
    return redirect(request.POST.get('next') or 'store:cart_detail')


@require_POST
def cart_remove(request, product_id):
    cart = Cart(request)
    product = get_object_or_404(Product, id=product_id)
    cart.remove(product)
    messages.info(request, f'Removed {product.name} from your cart.')
    return redirect('store:cart_detail')


@require_POST
def cart_update(request, product_id):
    cart = Cart(request)
    product = get_object_or_404(Product, id=product_id)
    quantity = max(1, int(request.POST.get('quantity', 1)))
    cart.add(product=product, quantity=quantity, replace=True)
    return redirect('store:cart_detail')


def cart_detail(request):
    cart = Cart(request)
    return render(request, 'store/cart.html', {'cart': cart})


@login_required
def address_list(request):
    addresses = request.user.addresses.all()
    return render(request, 'store/address_list.html', {'addresses': addresses})


@login_required
def address_add(request):
    if request.method == 'POST':
        latitude = request.POST.get('latitude') or None
        longitude = request.POST.get('longitude') or None
        DeliveryAddress.objects.create(
            user=request.user,
            label=request.POST.get('label') or 'Home',
            full_name=request.POST.get('full_name'),
            phone_number=request.POST.get('phone_number'),
            building_name=request.POST.get('building_name'),
            apartment_number=request.POST.get('apartment_number', ''),
            floor=request.POST.get('floor', ''),
            street=request.POST.get('street'),
            area=request.POST.get('area'),
            city=request.POST.get('city') or 'Nairobi',
            delivery_notes=request.POST.get('delivery_notes', ''),
            latitude=latitude,
            longitude=longitude,
            is_default=bool(request.POST.get('is_default')),
        )
        messages.success(request, 'Delivery address saved.')
        return redirect('store:address_list')
    return render(request, 'store/address_form.html')
