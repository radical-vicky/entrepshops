"""
Order lifecycle emails.

On localhost these get printed to the console (see EMAIL_BACKEND in
settings.py — real SMTP only switches on once DJANGO_DEBUG=False and
EMAIL_HOST is set, i.e. once you've deployed). fail_silently=True is used
throughout so a broken email configuration never breaks the M-Pesa
callback or checkout flow itself — a failed notification email is a
lesser problem than a failed payment webhook.
"""
from django.conf import settings
from django.core.mail import EmailMessage, send_mail


def _send(subject, message, to_email):
    if not to_email:
        return
    send_mail(
        subject=subject,
        message=message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[to_email],
        fail_silently=True,
    )


def _send_with_attachment(subject, message, to_email, filename, content, mimetype):
    if not to_email:
        return
    email = EmailMessage(
        subject=subject, body=message, from_email=settings.DEFAULT_FROM_EMAIL,
        to=[to_email],
    )
    email.attach(filename, content, mimetype)
    email.send(fail_silently=True)


def send_payment_confirmation_email(order):
    """Sent the moment M-Pesa confirms payment succeeded — includes the PDF receipt."""
    lines = [
        f'Hi {order.user.username},',
        '',
        f"We've received your payment of KES {order.total} for order #{order.id}. Thank you for shopping with DrinkShop!",
        '',
        'Order summary:',
    ]
    for item in order.items.all():
        lines.append(f'  - {item.quantity} x {item.product.name} — KES {item.subtotal}')
    lines += [
        '',
        f'Subtotal: KES {order.subtotal}',
        f'Delivery fee: KES {order.delivery_fee}',
        f'Total: KES {order.total}',
        '',
        'Your receipt is attached to this email — also downloadable/printable anytime from your order page.',
        '',
        "We'll email you again shortly to confirm your order is being prepared for delivery.",
        '',
        'DrinkShop',
    ]
    try:
        from .receipts import generate_receipt_pdf
        pdf_bytes = generate_receipt_pdf(order)
        _send_with_attachment(
            f'Payment received — Order #{order.id}', '\n'.join(lines), order.user.email,
            f'drinkshop-receipt-order-{order.id}.pdf', pdf_bytes, 'application/pdf',
        )
    except Exception:
        # Never let a receipt-generation hiccup block the payment
        # confirmation email itself — fall back to the plain version.
        _send(f'Payment received — Order #{order.id}', '\n'.join(lines), order.user.email)


def send_order_received_email(order):
    """Sent right after payment confirmation — order accepted, with an ETA."""
    eta = order.estimated_minutes or settings.DEFAULT_DELIVERY_ETA_MINUTES
    lines = [
        f'Hi {order.user.username},',
        '',
        f'Your order #{order.id} has been received and is being prepared for delivery.',
        '',
        f'Estimated delivery time: about {eta} minutes (always within 24 hours).',
        f'Delivering to: {order.delivery_address.as_text()}',
        '',
        "We'll let you know as soon as it's out for delivery.",
        '',
        'DrinkShop',
    ]
    _send(f'Order #{order.id} received — on its way', '\n'.join(lines), order.user.email)


def send_out_for_delivery_email(order):
    """Optional: call this if/when you mark an order OUT_FOR_DELIVERY in admin."""
    lines = [
        f'Hi {order.user.username},',
        '',
        f'Order #{order.id} is out for delivery now.',
        f'Delivering to: {order.delivery_address.as_text()}',
        '',
        'Once it arrives, you can rate your items and tip your rider from your order page.',
        '',
        'DrinkShop',
    ]
    _send(f'Order #{order.id} is out for delivery', '\n'.join(lines), order.user.email)


def send_delivered_email(order):
    """Optional: call this if/when you mark an order DELIVERED in admin."""
    hosts = [h for h in settings.ALLOWED_HOSTS if h != '*']
    site_host = hosts[0] if hosts else 'your-site'
    lines = [
        f'Hi {order.user.username},',
        '',
        f'Order #{order.id} has been delivered — enjoy!',
        '',
        'Got a minute? Rate your items and tip your rider from your order page:',
        f'http://{site_host}/orders/{order.id}/',
        '',
        'DrinkShop',
    ]
    _send(f'Order #{order.id} delivered — rate & tip', '\n'.join(lines), order.user.email)
