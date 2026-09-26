from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.mail import send_mail
from django.conf import settings
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from .forms import ImportRequestForm
from .models import ImportRequest


@login_required
@require_GET
def request_list(request):
    """A customer's own import requests."""
    requests_qs = (
        ImportRequest.objects
        .filter(user=request.user)
        .prefetch_related('quotes', 'payments')
    )
    return render(request, 'sourcing/request_list.html', {
        'requests': requests_qs,
    })


@login_required
def request_create(request):
    if request.method == 'POST':
        form = ImportRequestForm(request.POST, request.FILES)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.user = request.user
            obj.save()

            try:
                send_request_received_email(obj)
            except Exception:
                pass

            messages.success(
                request,
                f'Request {obj.reference} received. '
                f'We\'ll research and send you a quote within 24–48 hours.'
            )
            return redirect('sourcing:request_detail', reference=obj.reference)
    else:
        initial = {}
        if hasattr(request.user, 'addresses') and request.user.addresses.exists():
            addr = request.user.addresses.first()
            initial['phone_number'] = addr.phone_number
        form = ImportRequestForm(initial=initial)

    return render(request, 'sourcing/request_form.html', {'form': form})


@login_required
@require_GET
def request_detail(request, reference):
    obj = get_object_or_404(
        ImportRequest.objects.prefetch_related('quotes', 'payments'),
        reference=reference, user=request.user,
    )
    quote = obj.active_quote
    return render(request, 'sourcing/request_detail.html', {
        'req': obj,
        'quote': quote,
    })


@login_required
@require_POST
def request_cancel(request, reference):
    obj = get_object_or_404(
        ImportRequest, reference=reference, user=request.user,
    )
    if not obj.is_active:
        messages.error(request, 'This request is already closed.')
        return redirect('sourcing:request_detail', reference=obj.reference)

    if obj.paid_amount > 0:
        messages.error(
            request,
            'You\'ve already paid a deposit. Contact us directly to cancel.'
        )
        return redirect('sourcing:request_detail', reference=obj.reference)

    obj.status = ImportRequest.Status.CANCELLED
    obj.save(update_fields=['status'])
    messages.info(request, 'Request cancelled.')
    return redirect('sourcing:request_list')


# ======================================================================
# Payment: kick off the deposit via STK push
# ======================================================================
@login_required
@require_POST
def pay_deposit(request, reference):
    """Initiate the M-Pesa STK push for the deposit amount."""
    obj = get_object_or_404(
        ImportRequest, reference=reference, user=request.user,
    )
    quote = obj.active_quote
    if not quote:
        messages.error(request, 'No quote on this request yet.')
        return redirect('sourcing:request_detail', reference=obj.reference)

    if obj.status not in (
        ImportRequest.Status.QUOTED,
        ImportRequest.Status.AWAITING_DEPOSIT,
    ):
        messages.error(request, 'This request can\'t be paid right now.')
        return redirect('sourcing:request_detail', reference=obj.reference)

    amount = quote.deposit_amount
    phone = request.POST.get('phone_number') or obj.phone_number

    # Reuse the existing M-Pesa helper in the payments app.
    try:
        from payments.mpesa import initiate_stk_push
        from .models import ImportPayment

        payment = ImportPayment.objects.create(
            request=obj,
            kind=ImportPayment.Kind.DEPOSIT,
            amount=amount,
            phone_number=phone,
        )
        result = initiate_stk_push(
            phone=phone,
            amount=amount,
            account_reference=obj.reference,
            description=f'Deposit for {obj.reference}',
            callback_url=settings.MPESA_CALLBACK_URL,
        )
        payment.merchant_request_id = result.get('MerchantRequestID', '')
        payment.checkout_request_id = result.get('CheckoutRequestID', '')
        payment.result_code = str(result.get('ResponseCode', ''))
        payment.result_description = result.get('ResponseDescription', '')
        payment.save(update_fields=[
            'merchant_request_id', 'checkout_request_id',
            'result_code', 'result_description',
        ])

        obj.status = ImportRequest.Status.AWAITING_DEPOSIT
        obj.save(update_fields=['status'])

        messages.success(
            request,
            'A payment request has been sent to your phone. '
            'Enter your M-Pesa PIN to confirm.'
        )
    except Exception as exc:
        messages.error(request, f'Could not start payment: {exc}')

    return redirect('sourcing:request_detail', reference=obj.reference)


# ======================================================================
# Emails
# ======================================================================
def send_request_received_email(obj):
    user = obj.user
    if not user.email:
        return
    subject = f'Import request received — {obj.reference}'
    body = render_to_string('sourcing/emails/request_received.txt', {
        'user': user,
        'req': obj,
        'site_name': 'Entrep - Shop',
    })
    send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [user.email], fail_silently=False)
