import requests
import time
import json
from decimal import Decimal
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from .models import Payment, Invoice, Audit
from authentication.models import User, Plan, Subscription, CreditTop

def get_pesapal_token():
    """Get Pesapal access token from API"""
    url = f"{settings.PESAPAL_BASE_URL}/Auth/RequestToken"
    payload = {
        "consumer_key": settings.PESAPAL_CONSUMER_KEY,
        "consumer_secret": settings.PESAPAL_CONSUMER_SECRET
    }
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        response.raise_for_status()
        response_data = response.json()
        token = response_data.get("token")
        if not token:
            raise ValueError(f"No token in response: {response_data}")
        return token
    except requests.RequestException as e:
        raise Exception(f"Failed to get Pesapal token: {str(e)}")

def get_pesapal_transaction_status(order_tracking_id):
    """Get transaction status from Pesapal API"""
    token = get_pesapal_token()
    url = f"{settings.PESAPAL_BASE_URL}/Transactions/GetTransactionStatus?orderTrackingId={order_tracking_id}"
    
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {token}"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        raise Exception(f"Failed to get transaction status: {str(e)}")

def initiate_payment(data, user):
    """
    Core logic for initiating a payment through Pesapal.
    """
    with transaction.atomic():
        # 1. Create payment record
        payment = _create_payment_record(data, user)

        # 2. Create invoice
        invoice = _create_invoice_record(payment, data)

        # 3. Initiate Pesapal payment
        pesapal_response = _request_pesapal_order(payment, data)

        if pesapal_response.get('error'):
            payment.status = 'failed'
            payment.save()
            return {'error': 'Payment initiation failed', 'details': pesapal_response['error']}

        # 4. Update payment with Pesapal response
        payment.order_tracking_id = pesapal_response['order_tracking_id']
        payment.redirect_url = pesapal_response['redirect_url']
        payment.save()

        # 5. Create audit log
        Audit.objects.create(
            payload={
                'action': 'payment_initiated',
                'payment_id': str(payment.id),
                'merchant_reference': payment.merchant_reference,
                'pesapal_response': pesapal_response
            },
            status='success',
            payment=payment,
            subscription=payment.subscription
        )

        return {
            'payment': payment,
            'invoice': invoice,
            'redirect_url': payment.redirect_url,
            'order_tracking_id': payment.order_tracking_id
        }

def _create_payment_record(data, user):
    """Helper: Create payment record"""
    timestamp = int(time.time())
    payment_type = data['payment_type']
    entity_id = data.get('user_id') or data.get('organisation_id') or user.id
    merchant_reference = f"INV-{entity_id}-{timestamp}"

    payment = Payment(
        payment_type=payment_type,
        merchant_reference=merchant_reference,
        amount=data['amount'],
        currency=data.get('currency', 'UGX'),
        status='pending'
    )

    if data.get('user_id'):
        payment.user_id = data['user_id']
    elif data.get('organisation_id'):
        payment.organisation_id = data['organisation_id']
    else:
        payment.user = user

    if payment_type == 'subscription':
        payment.plan_id = data['plan_id']
    elif payment_type == 'topup':
        payment.subscription_id = data['subscription_id']
        payment.subscription = Subscription.objects.get(id=data['subscription_id'])

    payment.save()
    return payment

def _create_invoice_record(payment, data):
    """Helper: Create invoice for payment"""
    timestamp = int(time.time())
    invoice_number = f"INV-{payment.id.hex[:8].upper()}-{timestamp}"

    invoice = Invoice.objects.create(
        invoice_number=invoice_number,
        payment=payment,
        amount=payment.amount,
        currency=payment.currency,
        user=payment.user,
        organisation=payment.organisation,
        billing_address=_extract_billing_address(data)
    )

    return invoice

def _extract_billing_address(data):
    """Helper: Extract billing address from request data"""
    address_fields = [
        'email_address', 'phone_number', 'country_code', 'first_name',
        'middle_name', 'last_name', 'line_1', 'line_2', 'city', 'state',
        'postal_code', 'zip_code'
    ]

    billing_address = {}
    for field in address_fields:
        if data.get(field):
            billing_address[field] = data[field]

    return billing_address if billing_address else None

def _request_pesapal_order(payment, data):
    """Helper: Initiate payment with Pesapal API"""
    description = _get_payment_description(payment)
    payload = {
        "merchant_reference": payment.merchant_reference,
        "amount": float(payment.amount),
        "currency": payment.currency,
        "description": description,
        "notification_id": settings.PESAPAL_NOTIFICATION_ID,
        "callback_url": settings.PESAPAL_CALLBACK_URL,
        "redirect_mode": "",
        "branch": "E-Learning Platform - HQ",
        "billing_address": _extract_billing_address(data)
    }

    if not payload['billing_address']:
        del payload['billing_address']

    try:
        url = f"{settings.PESAPAL_BASE_URL}/Transactions/SubmitOrderRequest"
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {get_pesapal_token()}'
        }

        response = requests.post(url, json=payload, headers=headers, timeout=30)
        try:
            response_data = response.json()
        except json.JSONDecodeError:
            return {'error': f'Request failed: {response.text or "Empty response"}', 'status_code': response.status_code}

        if response.status_code == 200 and not response_data.get('error'):
            return response_data
        else:
            return {
                'error': response_data.get('error', 'Unknown error'),
                'status_code': response.status_code
            }
    except requests.RequestException as e:
        return {'error': f'Request failed: {str(e)}'}

def _get_payment_description(payment):
    """Helper: Generate payment description"""
    if payment.payment_type == 'subscription':
        plan_name = payment.plan.name if payment.plan else 'Plan'
        entity = payment.user.username if payment.user else payment.organisation.name
        return f"{plan_name} subscription for {entity}"
    else:  # topup
        entity = payment.user.username if payment.user else payment.organisation.name
        return f"Credit top-up for {entity}"

def process_subscription_payment(payment):
    """Post-payment: Activate subscription logic"""
    from authentication.services import create_subscription
    plan = payment.plan
    if not plan:
        raise ValueError("No plan associated with subscription payment")

    subscription, created = create_subscription(
        user=payment.user,
        plan=plan,
        organisation=payment.organisation
    )

    payment.subscription = subscription
    payment.save()
    return subscription

def process_topup_payment(payment):
    """Post-payment: Activate top-up logic"""
    try:
        subscription = payment.subscription
        if not subscription:
            raise ValueError("No subscription associated with top-up payment")

        # Simplified calculation: 1 UGX = 1 credit (Adjust per plan)
        credits_to_add = int(payment.amount) 

        subscription.remaining_credits += credits_to_add
        subscription.save()

        CreditTop.objects.create(
            subscription=subscription,
            organisation=subscription.organisation,
            user=subscription.user,
            credit_add=credits_to_add,
            purchase_date=timezone.now().date(),
            expiry_date=subscription.billing_end_date,
        )
    except Exception as e:
        print(f"Error processing top-up payment: {str(e)}")
        raise

def handle_webhook(webhook_data):
    """
    Process verified Pesapal webhook data.
    """
    merchant_reference = webhook_data.get('merchant_reference')
    order_tracking_id = webhook_data.get('order_tracking_id')
    
    if not all([merchant_reference, order_tracking_id]):
        return {'error': 'Missing required fields', 'status': 400}

    try:
        payment = Payment.objects.get(merchant_reference=merchant_reference)
    except Payment.DoesNotExist:
        return {'error': 'Payment not found', 'status': 404}

    # GET VERIFIED STATUS
    try:
        pesapal_status = get_pesapal_transaction_status(order_tracking_id)
        api_status = pesapal_status.get('status_description')
        api_amount = Decimal(str(pesapal_status.get('amount', 0)))
        api_merchant_ref = pesapal_status.get('merchant_reference')
    except Exception as e:
        return {'error': f'Verification failed: {str(e)}', 'status': 500}

    # SECURITY CHECKS
    if api_merchant_ref != merchant_reference:
        return {'error': 'Merchant reference mismatch', 'status': 400}

    is_partial = False
    if api_amount < payment.amount:
        is_partial = True
        Audit.objects.create(
            payload={'action': 'partial_payment_received', 'expected': float(payment.amount), 'actual': float(api_amount), 'order_tracking_id': order_tracking_id},
            status='pending', payment=payment
        )
    elif api_amount > payment.amount:
        Audit.objects.create(
            payload={'action': 'overpayment_received', 'expected': float(payment.amount), 'actual': float(api_amount), 'order_tracking_id': order_tracking_id},
            status='success', payment=payment
        )

    # Update payment
    with transaction.atomic():
        old_status = payment.status
        if api_status == 'COMPLETED':
            payment.status = 'partially_paid' if is_partial else 'complete'
            payment.payment_method = pesapal_status.get('payment_method')
            payment.transaction_date = pesapal_status.get('created_date')
            payment.payer_name = f"{pesapal_status.get('payment_account', '')}"
            
            if not payment.order_tracking_id:
                payment.order_tracking_id = order_tracking_id

            if hasattr(payment, 'invoice'):
                payment.invoice.status = 'partially_paid' if is_partial else 'paid'
                payment.invoice.paid_at = timezone.now()
                payment.invoice.save()

            if not is_partial:
                if payment.payment_type == 'subscription':
                    process_subscription_payment(payment)
                elif payment.payment_type == 'topup':
                    process_topup_payment(payment)
        elif api_status == 'FAILED':
            payment.status = 'failed'

        payment.save()

        Audit.objects.create(
            payload={'action': 'webhook_verified', 'pesapal_status': pesapal_status, 'old_status': old_status, 'new_status': payment.status},
            status='success' if api_status == 'COMPLETED' else 'failure',
            payment=payment, subscription=payment.subscription
        )

    return {'message': 'Webhook processed successfully', 'status': 200}
