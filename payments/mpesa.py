"""
Thin wrapper around Safaricom's Daraja API for M-Pesa STK Push (Lipa Na
M-Pesa Online). Docs: https://developer.safaricom.co.ke/APIs/MpesaExpressSimulate

Requires these settings (see drinkshop/settings.py):
MPESA_CONSUMER_KEY, MPESA_CONSUMER_SECRET, MPESA_SHORTCODE, MPESA_PASSKEY,
MPESA_CALLBACK_URL, MPESA_AUTH_URL, MPESA_STK_PUSH_URL, MPESA_STK_QUERY_URL
"""
import base64
from datetime import datetime

import requests
from django.conf import settings


class MpesaError(Exception):
    pass


def get_access_token():
    response = requests.get(
        settings.MPESA_AUTH_URL,
        auth=(settings.MPESA_CONSUMER_KEY, settings.MPESA_CONSUMER_SECRET),
        timeout=15,
    )
    if response.status_code != 200:
        raise MpesaError(f'Failed to get access token: {response.text}')
    return response.json()['access_token']


def _password_and_timestamp():
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    raw = f'{settings.MPESA_SHORTCODE}{settings.MPESA_PASSKEY}{timestamp}'
    password = base64.b64encode(raw.encode()).decode()
    return password, timestamp


def normalize_phone(phone_number):
    """Convert 07XXXXXXXX / +2547XXXXXXXX / 2547XXXXXXXX to 2547XXXXXXXX."""
    phone = phone_number.strip().replace(' ', '').replace('+', '')
    if phone.startswith('0'):
        phone = '254' + phone[1:]
    return phone


def stk_push(*, phone_number, amount, account_reference, transaction_desc):
    """Trigger an STK push (M-Pesa payment prompt) on the customer's phone.

    Returns the parsed JSON response from Safaricom, which includes
    MerchantRequestID and CheckoutRequestID used to reconcile the callback.
    """
    token = get_access_token()
    password, timestamp = _password_and_timestamp()
    phone = normalize_phone(phone_number)

    payload = {
        'BusinessShortCode': settings.MPESA_SHORTCODE,
        'Password': password,
        'Timestamp': timestamp,
        'TransactionType': 'CustomerPayBillOnline',
        'Amount': int(amount),
        'PartyA': phone,
        'PartyB': settings.MPESA_SHORTCODE,
        'PhoneNumber': phone,
        'CallBackURL': settings.MPESA_CALLBACK_URL,
        'AccountReference': account_reference,
        'TransactionDesc': transaction_desc,
    }
    response = requests.post(
        settings.MPESA_STK_PUSH_URL,
        json=payload,
        headers={'Authorization': f'Bearer {token}'},
        timeout=15,
    )
    if response.status_code != 200:
        raise MpesaError(f'STK push failed: {response.text}')
    return response.json()


def stk_query(checkout_request_id):
    """Poll Safaricom for the outcome of a previously initiated STK push."""
    token = get_access_token()
    password, timestamp = _password_and_timestamp()

    payload = {
        'BusinessShortCode': settings.MPESA_SHORTCODE,
        'Password': password,
        'Timestamp': timestamp,
        'CheckoutRequestID': checkout_request_id,
    }
    response = requests.post(
        settings.MPESA_STK_QUERY_URL,
        json=payload,
        headers={'Authorization': f'Bearer {token}'},
        timeout=15,
    )
    if response.status_code != 200:
        raise MpesaError(f'STK query failed: {response.text}')
    return response.json()


def generate_security_credential(initiator_password=None, cert_path=None):
    """Encrypt the B2C initiator password with Safaricom's public certificate,
    as required by the B2C API. Get the certificate from the Daraja portal:
    sandbox and production use DIFFERENT certs — download the right one for
    your MPESA_ENV and point MPESA_B2C_CERT_PATH at it.
    """
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.hazmat.primitives.serialization import load_pem_public_key
    from cryptography.x509 import load_pem_x509_certificate

    initiator_password = initiator_password or settings.MPESA_INITIATOR_PASSWORD
    cert_path = cert_path or settings.MPESA_B2C_CERT_PATH
    if not initiator_password or not cert_path:
        raise MpesaError(
            'B2C is not configured: set MPESA_INITIATOR_PASSWORD and '
            'MPESA_B2C_CERT_PATH (see README "Wallet withdrawals").'
        )

    with open(cert_path, 'rb') as f:
        cert_data = f.read()
    try:
        cert = load_pem_x509_certificate(cert_data)
        public_key = cert.public_key()
    except ValueError:
        public_key = load_pem_public_key(cert_data)

    encrypted = public_key.encrypt(initiator_password.encode(), padding.PKCS1v15())
    return base64.b64encode(encrypted).decode()


def b2c_payment(*, phone_number, amount, remarks, occasion='Withdrawal'):
    """Send money OUT to a customer's M-Pesa (wallet withdrawal). This is a
    different, more sensitive Daraja product than STK push — it requires
    Safaricom to have approved your account for B2C and given you an
    initiator name + password, and a security-credential certificate.
    See README "Wallet withdrawals" for the full setup.
    """
    token = get_access_token()
    security_credential = generate_security_credential()
    phone = normalize_phone(phone_number)

    payload = {
        'InitiatorName': settings.MPESA_INITIATOR_NAME,
        'SecurityCredential': security_credential,
        'CommandID': 'BusinessPayment',
        'Amount': int(amount),
        'PartyA': settings.MPESA_B2C_SHORTCODE,
        'PartyB': phone,
        'Remarks': remarks[:100],
        'QueueTimeOutURL': settings.MPESA_B2C_TIMEOUT_URL,
        'ResultURL': settings.MPESA_B2C_RESULT_URL,
        'Occasion': occasion[:100],
    }
    response = requests.post(
        settings.MPESA_B2C_URL,
        json=payload,
        headers={'Authorization': f'Bearer {token}'},
        timeout=15,
    )
    if response.status_code != 200:
        raise MpesaError(f'B2C payment request failed: {response.text}')
    return response.json()
