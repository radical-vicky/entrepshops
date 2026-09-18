import json
from datetime import timedelta

from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from orders.models import Order, RiderTip

from .mpesa import MpesaError, stk_query
from .models import MpesaTransaction


@csrf_exempt
@require_POST
def mpesa_callback(request):
    """Safaricom posts the result of an STK push here.

    This endpoint must be publicly reachable (set MPESA_CALLBACK_URL to its
    real, HTTPS URL) and is exempt from CSRF since Safaricom, not a browser,
    calls it. It handles order payments (MpesaTransaction), rider tips
    (RiderTip), and vendor subscription payments — all share this one
    callback URL, so we look the checkout_request_id up in whichever table
    matches.
    """
    try:
        data = json.loads(request.body)
    except (ValueError, TypeError):
        return JsonResponse({'ResultCode': 1, 'ResultDesc': 'Invalid payload'})

    stk_callback = data.get('Body', {}).get('stkCallback', {})
    checkout_request_id = stk_callback.get('CheckoutRequestID')
    result_code = stk_callback.get('ResultCode')
    result_desc = stk_callback.get('ResultDesc', '')

    txn = MpesaTransaction.objects.filter(checkout_request_id=checkout_request_id).first()
    if txn:
        return _handle_order_payment_callback(txn, result_code, result_desc, stk_callback)

    tip = RiderTip.objects.filter(checkout_request_id=checkout_request_id).first()
    if tip:
        return _handle_tip_callback(tip, result_code)

    from vendors.models import VendorSubscriptionPayment
    subscription_payment = VendorSubscriptionPayment.objects.filter(checkout_request_id=checkout_request_id).first()
    if subscription_payment:
        return _handle_vendor_subscription_callback(subscription_payment, result_code, stk_callback)

    return JsonResponse({'ResultCode': 0, 'ResultDesc': 'Accepted (no matching txn)'})


def _handle_vendor_subscription_callback(payment, result_code, stk_callback):
    if result_code == 0:
        items = stk_callback.get('CallbackMetadata', {}).get('Item', [])
        metadata = {item.get('Name'): item.get('Value') for item in items}
        payment.mark_success(receipt_number=str(metadata.get('MpesaReceiptNumber', '')))
    else:
        from vendors.models import VendorSubscriptionPayment
        payment.status = (
            VendorSubscriptionPayment.Status.CANCELLED if result_code == 1032
            else VendorSubscriptionPayment.Status.FAILED
        )
        payment.save(update_fields=['status'])
    return JsonResponse({'ResultCode': 0, 'ResultDesc': 'Accepted'})


def _customer_facing_reason(result_code, result_desc):
    """Translate an M-Pesa result code into something a customer can
    actually understand, instead of a raw Safaricom error string."""
    mapping = {
        1032: 'You cancelled the M-Pesa payment prompt.',
        1: 'Payment failed — insufficient M-Pesa balance.',
        1037: 'You didn\'t respond to the M-Pesa prompt in time.',
        1025: 'M-Pesa couldn\'t reach your line — please try again.',
        2001: 'The M-Pesa PIN entered was incorrect.',
    }
    try:
        code_int = int(result_code)
    except (TypeError, ValueError):
        code_int = None
    return mapping.get(code_int, result_desc or 'Payment could not be completed.')


def _handle_order_payment_callback(txn, result_code, result_desc, stk_callback):
    txn.result_description = result_desc

    if result_code == 0:
        # Successful payment — pull the M-Pesa receipt number out of the
        # CallbackMetadata items array.
        items = stk_callback.get('CallbackMetadata', {}).get('Item', [])
        metadata = {item.get('Name'): item.get('Value') for item in items}
        txn.mpesa_receipt_number = metadata.get('MpesaReceiptNumber', '')
        txn.status = MpesaTransaction.Status.SUCCESS
        txn.save()

        order = txn.order
        order.mark_paid()
    else:
        txn.status = MpesaTransaction.Status.CANCELLED if result_code == 1032 else MpesaTransaction.Status.FAILED
        txn.save()
        txn.order.mark_cancelled(_customer_facing_reason(result_code, result_desc))

    return JsonResponse({'ResultCode': 0, 'ResultDesc': 'Accepted'})


def _handle_tip_callback(tip, result_code):
    if result_code == 0:
        tip.status = RiderTip.Status.SUCCESS
    else:
        tip.status = RiderTip.Status.CANCELLED if result_code == 1032 else RiderTip.Status.FAILED
    tip.save(update_fields=['status'])
    return JsonResponse({'ResultCode': 0, 'ResultDesc': 'Accepted'})


def _reconcile_stuck_transaction(txn):
    """Safety net for a lost/delayed M-Pesa callback: if a payment has sat
    in 'initiated' for more than 15 seconds, actively ask Safaricom what
    actually happened rather than leaving the customer staring at a
    spinner forever. Called from the polling endpoint, so it runs at most
    every few seconds per open payment-waiting page — cheap and safe."""
    if txn.status != MpesaTransaction.Status.INITIATED:
        return
    if not txn.checkout_request_id:
        return
    if timezone.now() - txn.created_at < timedelta(seconds=15):
        return  # give the real callback a fair chance first

    try:
        result = stk_query(txn.checkout_request_id)
    except MpesaError:
        return  # still pending, or Safaricom unreachable right now — try again next poll

    result_code = str(result.get('ResultCode', ''))
    if result_code == '0':
        txn.status = MpesaTransaction.Status.SUCCESS
        txn.result_description = result.get('ResultDesc', '')
        txn.save(update_fields=['status', 'result_description'])
        txn.order.mark_paid()
    elif result_code == '1032':
        txn.status = MpesaTransaction.Status.CANCELLED
        txn.result_description = result.get('ResultDesc', '')
        txn.save(update_fields=['status', 'result_description'])
        txn.order.mark_cancelled(_customer_facing_reason(1032, result.get('ResultDesc', '')))
    elif result_code:
        txn.status = MpesaTransaction.Status.FAILED
        txn.result_description = result.get('ResultDesc', '')
        txn.save(update_fields=['status', 'result_description'])
        txn.order.mark_cancelled(_customer_facing_reason(result_code, result.get('ResultDesc', '')))
    # else: Safaricom says it's still processing — leave as initiated, poll again shortly.


def _reconcile_stuck_tip(tip):
    if tip.status != RiderTip.Status.INITIATED:
        return
    if not tip.checkout_request_id:
        return
    if timezone.now() - tip.created_at < timedelta(seconds=15):
        return

    try:
        result = stk_query(tip.checkout_request_id)
    except MpesaError:
        return

    result_code = str(result.get('ResultCode', ''))
    if result_code == '0':
        tip.status = RiderTip.Status.SUCCESS
        tip.save(update_fields=['status'])
    elif result_code == '1032':
        tip.status = RiderTip.Status.CANCELLED
        tip.save(update_fields=['status'])
    elif result_code:
        tip.status = RiderTip.Status.FAILED
        tip.save(update_fields=['status'])


@require_GET
def payment_status(request, order_id):
    """Polled by the checkout-waiting page's JS to see if payment landed."""
    order = Order.objects.filter(id=order_id, user=request.user).first()
    if not order:
        return JsonResponse({'status': 'unknown'}, status=404)

    latest_txn = order.mpesa_transactions.order_by('-created_at').first()
    if latest_txn:
        _reconcile_stuck_transaction(latest_txn)
        latest_txn.refresh_from_db()
    order.refresh_from_db()
    return JsonResponse({
        'order_status': order.status,
        'txn_status': latest_txn.status if latest_txn else None,
        'txn_message': order.cancellation_reason or (latest_txn.result_description if latest_txn else ''),
    })


@require_GET
def tip_status(request, tip_id):
    """Polled by the order page's JS to see if a rider tip landed."""
    tip = RiderTip.objects.filter(id=tip_id, order__user=request.user).first()
    if not tip:
        return JsonResponse({'status': 'unknown'}, status=404)
    _reconcile_stuck_tip(tip)
    tip.refresh_from_db()
    return JsonResponse({'tip_status': tip.status})


@csrf_exempt
@require_POST
def b2c_result(request):
    """Safaricom posts the outcome of a wallet withdrawal here once B2C is
    approved and configured. Exempt from CSRF since Safaricom, not a
    browser, calls it — same pattern as the STK callback.
    """
    from accounts.models import WithdrawalRequest

    try:
        data = json.loads(request.body)
    except (ValueError, TypeError):
        return JsonResponse({'ResultCode': 1, 'ResultDesc': 'Invalid payload'})

    result = data.get('Result', {})
    conversation_id = result.get('ConversationID')
    result_code = result.get('ResultCode')
    result_desc = result.get('ResultDesc', '')

    withdrawal = WithdrawalRequest.objects.filter(mpesa_conversation_id=conversation_id).first()
    if not withdrawal:
        return JsonResponse({'ResultCode': 0, 'ResultDesc': 'Accepted (no matching withdrawal)'})

    if result_code == 0:
        params = {
            p.get('Key'): p.get('Value')
            for p in result.get('ResultParameters', {}).get('ResultParameter', [])
        }
        withdrawal.mark_success(receipt_number=str(params.get('TransactionReceipt', '')))
    else:
        withdrawal.mark_failed(result_desc)

    return JsonResponse({'ResultCode': 0, 'ResultDesc': 'Accepted'})


@csrf_exempt
@require_POST
def b2c_timeout(request):
    """Safaricom posts here if the B2C request itself times out in their
    queue (distinct from a normal success/fail result). Treat it as a
    failure so the customer's wallet gets refunded rather than left in
    limbo indefinitely."""
    from accounts.models import WithdrawalRequest

    try:
        data = json.loads(request.body)
    except (ValueError, TypeError):
        return JsonResponse({'ResultCode': 1, 'ResultDesc': 'Invalid payload'})

    conversation_id = data.get('Result', {}).get('ConversationID')
    withdrawal = WithdrawalRequest.objects.filter(mpesa_conversation_id=conversation_id).first()
    if withdrawal and withdrawal.status == withdrawal.Status.PROCESSING:
        withdrawal.mark_failed('Timed out waiting for Safaricom to process the payout.')

    return JsonResponse({'ResultCode': 0, 'ResultDesc': 'Accepted'})
