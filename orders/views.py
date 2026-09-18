from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from functools import wraps

from payments.mpesa import MpesaError, stk_push
from payments.models import MpesaTransaction
from store.cart import Cart
from store.delivery import get_delivery_fee
from store.models import DeliveryAddress

from .models import Order, OrderItem, Review, Rider, RiderTip
from .receipts import generate_receipt_pdf


@login_required
def checkout(request):
    cart = Cart(request)
    if len(cart) == 0:
        messages.warning(request, 'Your cart is empty.')
        return redirect('store:home')

    if cart.has_undeliverable_items():
        messages.error(
            request,
            'Your cart contains an item that cannot currently be delivered. '
            'Please remove it to continue.'
        )
        return redirect('store:cart_detail')

    addresses = request.user.addresses.all()
    # Precompute each address's delivery fee/zone so the radio list can show it.
    address_options = []
    for addr in addresses:
        fee, zone, deliverable = get_delivery_fee(addr, cart.subtotal)
        address_options.append({
            'address': addr,
            'fee': fee,
            'zone': zone,
            'deliverable': deliverable,
            'total': (cart.subtotal + fee) if deliverable else None,
        })

    if request.method == 'POST':
        address_id = request.POST.get('address_id')
        phone_number = request.POST.get('phone_number', '').strip()
        address = get_object_or_404(DeliveryAddress, id=address_id, user=request.user)

        fee, zone, deliverable = get_delivery_fee(address, cart.subtotal)
        if not deliverable:
            messages.error(
                request,
                f'Sorry, we are not currently delivering to {address.area}. '
                'Please choose a different address.'
            )
            return redirect('orders:checkout')

        if not phone_number:
            phone_number = address.phone_number

        order = Order.objects.create(
            user=request.user,
            delivery_address=address,
            subtotal=cart.subtotal,
            delivery_fee=fee,
            total=cart.subtotal + fee,
            phone_number=phone_number,
            estimated_minutes=zone.estimated_minutes if zone else None,
        )
        for line in cart:
            OrderItem.objects.create(
                order=order,
                product=line['product'],
                unit_price=line['unit_price'],
                quantity=line['quantity'],
            )

        try:
            response = stk_push(
                phone_number=phone_number,
                amount=order.total,
                account_reference=f'Order{order.id}',
                transaction_desc=f'Payment for order #{order.id}',
            )
            MpesaTransaction.objects.create(
                order=order,
                phone_number=phone_number,
                amount=order.total,
                merchant_request_id=response.get('MerchantRequestID', ''),
                checkout_request_id=response.get('CheckoutRequestID', ''),
            )
        except MpesaError as exc:
            messages.error(
                request,
                'We could not reach M-Pesa to request payment. '
                f'Please try again. ({exc})'
            )
            return redirect('orders:checkout')

        cart.clear()
        messages.success(
            request,
            'Check your phone and enter your M-Pesa PIN to complete payment.'
        )
        return redirect('orders:payment_waiting', order_id=order.id)

    return render(request, 'orders/checkout.html', {
        'cart': cart,
        'address_options': address_options,
        'free_delivery_small': settings.FREE_DELIVERY_MAX_SMALL_ORDER,
        'free_delivery_wholesale': settings.FREE_DELIVERY_MIN_WHOLESALE_ORDER,
    })


@login_required
def payment_waiting(request, order_id):
    order = get_object_or_404(Order, id=order_id, user=request.user)
    return render(request, 'orders/payment_waiting.html', {'order': order})


@login_required
@require_POST
def retry_payment(request, order_id):
    """Re-sends the M-Pesa prompt for an order whose payment failed or was
    cancelled — re-uses the same order (and cart is long since cleared by
    this point) rather than sending the customer back to an empty cart."""
    order = get_object_or_404(Order, id=order_id, user=request.user)
    if order.status not in (Order.Status.PENDING_PAYMENT, Order.Status.CANCELLED):
        messages.info(request, 'This order has already been paid.')
        return redirect('orders:order_detail', order_id=order.id)

    try:
        response = stk_push(
            phone_number=order.phone_number,
            amount=order.total,
            account_reference=f'Order{order.id}',
            transaction_desc=f'Payment for order #{order.id}',
        )
        MpesaTransaction.objects.create(
            order=order,
            phone_number=order.phone_number,
            amount=order.total,
            merchant_request_id=response.get('MerchantRequestID', ''),
            checkout_request_id=response.get('CheckoutRequestID', ''),
        )
        order.status = Order.Status.PENDING_PAYMENT
        order.cancellation_reason = ''
        order.save(update_fields=['status', 'cancellation_reason', 'updated_at'])
        messages.success(request, 'Check your phone and enter your M-Pesa PIN to complete payment.')
    except MpesaError as exc:
        messages.error(request, f'We could not reach M-Pesa to request payment. Please try again. ({exc})')

    return redirect('orders:payment_waiting', order_id=order.id)


@login_required
def order_history(request):
    orders = request.user.orders.exclude(status=Order.Status.CANCELLED)
    cancelled_orders = request.user.orders.filter(status=Order.Status.CANCELLED)
    return render(request, 'orders/order_history.html', {
        'orders': orders,
        'cancelled_orders': cancelled_orders,
    })


@login_required
def order_detail(request, order_id):
    order = get_object_or_404(Order, id=order_id, user=request.user)
    reviewable_items = None
    if order.is_delivered:
        reviewable_items = order.items.select_related('product').all()
    latest_tip = order.tips.order_by('-created_at').first()
    return render(request, 'orders/order_detail.html', {
        'order': order,
        'reviewable_items': reviewable_items,
        'latest_tip': latest_tip,
    })


@login_required
@require_POST
def submit_review(request, item_id):
    item = get_object_or_404(OrderItem, id=item_id, order__user=request.user)
    if not item.order.is_delivered:
        messages.error(request, 'You can only review items from a delivered order.')
        return redirect('orders:order_detail', order_id=item.order_id)

    rating = int(request.POST.get('rating', 0))
    comment = request.POST.get('comment', '').strip()
    if rating < 1 or rating > 5:
        messages.error(request, 'Please choose a rating between 1 and 5.')
        return redirect('orders:order_detail', order_id=item.order_id)

    Review.objects.update_or_create(
        order_item=item,
        defaults={'user': request.user, 'product': item.product, 'rating': rating, 'comment': comment},
    )
    messages.success(request, f'Thanks for rating {item.product.name}!')
    return redirect('orders:order_detail', order_id=item.order_id)


@login_required
@require_POST
def send_tip(request, order_id):
    order = get_object_or_404(Order, id=order_id, user=request.user)
    if not order.is_delivered or not order.rider:
        messages.error(request, 'Tips can only be sent for delivered orders with a rider assigned.')
        return redirect('orders:order_detail', order_id=order.id)

    try:
        amount = int(request.POST.get('amount', 0))
    except ValueError:
        amount = 0
    if amount < 10:
        messages.error(request, 'Please enter a tip amount of at least KES 10.')
        return redirect('orders:order_detail', order_id=order.id)

    phone_number = request.POST.get('phone_number', '').strip() or order.phone_number

    try:
        response = stk_push(
            phone_number=phone_number,
            amount=amount,
            account_reference=f'Tip{order.id}',
            transaction_desc=f'Tip for rider on order #{order.id}',
        )
        RiderTip.objects.create(
            order=order,
            amount=amount,
            phone_number=phone_number,
            checkout_request_id=response.get('CheckoutRequestID', ''),
        )
        messages.success(request, 'Check your phone to confirm the tip via M-Pesa.')
    except MpesaError as exc:
        messages.error(request, f'Could not send the tip request. ({exc})')

    return redirect('orders:order_detail', order_id=order.id)


@login_required
def download_receipt(request, order_id):
    order = get_object_or_404(Order, id=order_id, user=request.user)
    if order.status not in (Order.Status.PAID, Order.Status.PREPARING, Order.Status.OUT_FOR_DELIVERY, Order.Status.DELIVERED):
        messages.error(request, 'A receipt is only available once an order is paid.')
        return redirect('orders:order_detail', order_id=order.id)

    pdf_bytes = generate_receipt_pdf(order)
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    # inline (not attachment) so it opens in the browser's PDF viewer,
    # where the person can read it or hit print — same file either way.
    response['Content-Disposition'] = f'inline; filename="drinkshop-receipt-order-{order.id}.pdf"'
    return response


def rider_required(view_func):
    @login_required
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        rider = getattr(request.user, 'rider_profile', None)
        if not rider or not rider.is_active:
            messages.error(request, "You don't have an active rider account.")
            return redirect('store:home')
        return view_func(request, rider, *args, **kwargs)
    return wrapper


@rider_required
def rider_dashboard(request, rider):
    active_orders = rider.orders.exclude(
        status__in=[Order.Status.DELIVERED, Order.Status.CANCELLED]
    ).select_related('delivery_address', 'user')
    completed_orders = rider.orders.filter(
        status=Order.Status.DELIVERED
    ).select_related('delivery_address', 'user').order_by('-delivered_at')[:20]
    return render(request, 'orders/rider_dashboard.html', {
        'rider': rider,
        'active_orders': active_orders,
        'completed_orders': completed_orders,
    })


@rider_required
@require_POST
def rider_mark_out_for_delivery(request, rider, order_id):
    order = get_object_or_404(Order, id=order_id, rider=rider)
    order.mark_out_for_delivery()
    messages.success(request, f'Order #{order.id} marked out for delivery.')
    return redirect('orders:rider_dashboard')


@rider_required
@require_POST
def rider_mark_delivered(request, rider, order_id):
    order = get_object_or_404(Order, id=order_id, rider=rider)
    order.mark_delivered()
    messages.success(request, f'Order #{order.id} marked delivered.')
    return redirect('orders:rider_dashboard')
