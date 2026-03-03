import requests
import time
import json
from decimal import Decimal
from django.shortcuts import render
from django.conf import settings
from django.db import transaction, models
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import api_view, permission_classes

from .models import Payment, Invoice, Audit
from .serializers import PaymentSerializer, InvoiceSerializer, AuditSerializer, PaymentInitiateSerializer
from authentication.models import User, Plan, Subscription, CreditTop
from schools.models import School


# ============================================================================
# PAYMENT CRUD VIEWS
# ============================================================================

class PaymentListView(APIView):
    """
    GET: List payments (filtered by user/organisation)
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """List payments"""
        user = request.user

        if user.is_superuser:
            payments = Payment.objects.all()
        elif user.role in ['operator', 'sale_manager']:
            payments = Payment.objects.all()  # Staff can see all payments
        else:
            # Regular users see only their payments
            payments = Payment.objects.filter(
                models.Q(user=user) | models.Q(organisation__admin_user=user)
            )

        payments = payments.order_by('-created_at')
        serializer = PaymentSerializer(payments, many=True)
        return Response(serializer.data)


class PaymentDetailView(APIView):
    """
    GET: Get payment details
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, payment_id):
        """Get payment details"""
        try:
            payment = Payment.objects.get(id=payment_id)

            # Check permissions
            if not self._can_access_payment(request.user, payment):
                return Response({'error': 'Access denied'}, status=status.HTTP_403_FORBIDDEN)

            serializer = PaymentSerializer(payment)
            return Response(serializer.data)
        except Payment.DoesNotExist:
            return Response({'error': 'Payment not found'}, status=status.HTTP_404_NOT_FOUND)

    def _can_access_payment(self, user, payment):
        """Check if user can access this payment"""
        if user.is_superuser or user.role in ['operator', 'sale_manager']:
            return True
        return (payment.user == user or
                (payment.organisation and payment.organisation.admin_user == user))


# ============================================================================
# INVOICE CRUD VIEWS
# ============================================================================

class InvoiceListView(APIView):
    """
    GET: List invoices (filtered by user/organisation)
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """List invoices"""
        user = request.user

        if user.is_superuser:
            invoices = Invoice.objects.all()
        elif user.role in ['operator', 'sale_manager']:
            invoices = Invoice.objects.all()  # Staff can see all invoices
        else:
            # Regular users see only their invoices
            invoices = Invoice.objects.filter(
                models.Q(user=user) | models.Q(organisation__admin_user=user)
            )

        invoices = invoices.order_by('-created_at')
        serializer = InvoiceSerializer(invoices, many=True)
        return Response(serializer.data)


class InvoiceDetailView(APIView):
    """
    GET: Get invoice details
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, invoice_id):
        """Get invoice details"""
        try:
            invoice = Invoice.objects.get(id=invoice_id)

            # Check permissions
            if not self._can_access_invoice(request.user, invoice):
                return Response({'error': 'Access denied'}, status=status.HTTP_403_FORBIDDEN)

            serializer = InvoiceSerializer(invoice)
            return Response(serializer.data)
        except Invoice.DoesNotExist:
            return Response({'error': 'Invoice not found'}, status=status.HTTP_404_NOT_FOUND)

    def _can_access_invoice(self, user, invoice):
        """Check if user can access this invoice"""
        if user.is_superuser or user.role in ['operator', 'sale_manager']:
            return True
        return (invoice.user == user or
                (invoice.organisation and invoice.organisation.admin_user == user))


# ============================================================================
# AUDIT CRUD VIEWS
# ============================================================================

class AuditListView(APIView):
    """
    GET: List audit logs
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """List audit logs"""
        if not (request.user.is_superuser or request.user.role in ['operator', 'sale_manager']):
            return Response({'error': 'Access denied'}, status=status.HTTP_403_FORBIDDEN)

        audits = Audit.objects.all().order_by('-created_at')
        serializer = AuditSerializer(audits, many=True)
        return Response(serializer.data)


# ============================================================================
# PAYMENT INITIATION AND PROCESSING
# ============================================================================

class PaymentInitiateView(APIView):
    """
    POST: Initiate a payment with Pesapal
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        """Initiate payment"""
        serializer = PaymentInitiateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data

        try:
            with transaction.atomic():
                # Create payment record
                payment = self._create_payment(data, request.user)

                # Create invoice
                invoice = self._create_invoice(payment, data)

                # Initiate Pesapal payment
                pesapal_response = self._initiate_pesapal_payment(payment, data)

                if pesapal_response.get('error'):
                    payment.status = 'failed'
                    payment.save()
                    return Response({
                        'error': 'Payment initiation failed',
                        'details': pesapal_response['error']
                    }, status=status.HTTP_400_BAD_REQUEST)

                # Update payment with Pesapal response
                payment.order_tracking_id = pesapal_response['order_tracking_id']
                payment.redirect_url = pesapal_response['redirect_url']
                payment.save()

                # Create audit log
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

                return Response({
                    'payment': PaymentSerializer(payment).data,
                    'invoice': InvoiceSerializer(invoice).data,
                    'redirect_url': payment.redirect_url,
                    'order_tracking_id': payment.order_tracking_id
                })

        except Exception as e:
            return Response({
                'error': 'Payment initiation failed',
                'details': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def _create_payment(self, data, user):
        """Create payment record"""
        # Generate merchant reference
        timestamp = int(time.time())
        payment_type = data['payment_type']
        entity_id = data.get('user_id') or data.get('organisation_id')
        merchant_reference = f"INV-{entity_id}-{timestamp}"

        payment = Payment(
            payment_type=payment_type,
            merchant_reference=merchant_reference,
            amount=data['amount'],
            currency='KES',  # Default to KES
            status='pending'
        )

        # Set user or organisation
        if data.get('user_id'):
            payment.user_id = data['user_id']
        elif data.get('organisation_id'):
            payment.organisation_id = data['organisation_id']

        # Set plan and subscription based on payment type
        if payment_type == 'subscription':
            payment.plan_id = data['plan_id']
        elif payment_type == 'topup':
            payment.subscription_id = data['subscription_id']
            payment.subscription = Subscription.objects.get(id=data['subscription_id'])

        payment.save()
        return payment

    def _create_invoice(self, payment, data):
        """Create invoice for payment"""
        # Generate invoice number
        timestamp = int(time.time())
        invoice_number = f"INV-{payment.id.hex[:8].upper()}-{timestamp}"

        invoice = Invoice.objects.create(
            invoice_number=invoice_number,
            payment=payment,
            amount=payment.amount,
            currency=payment.currency,
            user=payment.user,
            organisation=payment.organisation,
            billing_address=self._extract_billing_address(data)
        )

        return invoice

    def _extract_billing_address(self, data):
        """Extract billing address from request data"""
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

    def _initiate_pesapal_payment(self, payment, data):
        """Initiate payment with Pesapal API"""
        # Prepare Pesapal request payload
        payload = {
            "merchant_reference": payment.merchant_reference,
            "amount": float(payment.amount),
            "currency": payment.currency,
            "description": self._get_payment_description(payment),
            "notification_id": settings.PESAPAL_NOTIFICATION_ID,
            "callback_url": settings.PESAPAL_CALLBACK_URL,
            "redirect_mode": "",
            "branch": "E-Learning Platform - HQ",
            "billing_address": self._extract_billing_address(data)
        }

        # Remove empty billing address if no data provided
        if not payload['billing_address']:
            del payload['billing_address']

        try:
            # Make request to Pesapal
            url = f"{settings.PESAPAL_BASE_URL}/Transactions/SubmitOrderRequest"
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {self._get_pesapal_token()}'
            }

            response = requests.post(url, json=payload, headers=headers, timeout=30)
            
            # Try to parse JSON response
            try:
                response_data = response.json()
            except json.JSONDecodeError:
                # If response is not valid JSON, return error with response text
                return {
                    'error': f'Request failed: {response.text or "Empty response"}',
                    'status_code': response.status_code
                }

            if response.status_code == 200 and not response_data.get('error'):
                return response_data
            else:
                return {
                    'error': response_data.get('error', 'Unknown error'),
                    'status_code': response.status_code
                }

        except requests.RequestException as e:
            return {'error': f'Request failed: {str(e)}'}

    def _get_payment_description(self, payment):
        """Generate payment description"""
        if payment.payment_type == 'subscription':
            plan_name = payment.plan.name if payment.plan else 'Plan'
            entity = payment.user.username if payment.user else payment.organisation.name
            return f"{plan_name} subscription for {entity}"
        else:  # topup
            entity = payment.user.username if payment.user else payment.organisation.name
            return f"Credit top-up for {entity}"

    def _get_pesapal_token(self):
        """Get Pesapal access token (simplified - in production, implement proper OAuth)"""
        # This is a simplified version. In production, you should implement proper OAuth flow
        # to get and cache the access token
        return f"{settings.PESAPAL_CONSUMER_KEY}:{settings.PESAPAL_CONSUMER_SECRET}"


# ============================================================================
# PESAPAL WEBHOOK HANDLER
# ============================================================================

@api_view(['POST'])
@permission_classes([])
def payment_webhook(request):
    """
    Handle Pesapal IPN (Instant Payment Notification)
    """
    try:
        webhook_data = request.data

        # Log webhook receipt
        print(f"Webhook received: {json.dumps(webhook_data, indent=2)}")

        # Validate webhook data
        merchant_reference = webhook_data.get('merchant_reference')
        order_tracking_id = webhook_data.get('order_tracking_id')
        payment_status = webhook_data.get('payment_status')

        if not all([merchant_reference, order_tracking_id, payment_status]):
            return Response({'error': 'Missing required fields'}, status=status.HTTP_400_BAD_REQUEST)

        # Find payment by merchant reference
        try:
            payment = Payment.objects.get(merchant_reference=merchant_reference)
        except Payment.DoesNotExist:
            return Response({'error': 'Payment not found'}, status=status.HTTP_404_NOT_FOUND)

        # Update payment based on webhook data
        with transaction.atomic():
            old_status = payment.status

            if payment_status == 'COMPLETED':
                payment.status = 'complete'
                payment.payment_method = webhook_data.get('payment_method')
                payment.transaction_date = webhook_data.get('transaction_date')
                payment.payer_name = webhook_data.get('payer_name')
                payment.payer_email = webhook_data.get('payer_email')
                payment.payer_phone = webhook_data.get('payer_phone')

                # Mark invoice as paid
                if hasattr(payment, 'invoice'):
                    payment.invoice.status = 'paid'
                    payment.invoice.paid_at = timezone.now()
                    payment.invoice.save()

                # Process payment based on type
                if payment.payment_type == 'subscription':
                    _process_subscription_payment(payment)
                elif payment.payment_type == 'topup':
                    _process_topup_payment(payment)

            elif payment_status == 'FAILED':
                payment.status = 'failed'

            payment.save()

            # Create audit log
            Audit.objects.create(
                payload={
                    'action': 'webhook_received',
                    'webhook_data': webhook_data,
                    'old_status': old_status,
                    'new_status': payment.status
                },
                status='success' if payment_status == 'COMPLETED' else 'failure',
                payment=payment,
                subscription=payment.subscription
            )

        return Response({'message': 'Webhook processed successfully'})

    except Exception as e:
        # Log error
        print(f"Webhook processing error: {str(e)}")
        return Response({'error': 'Internal server error'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


def _process_subscription_payment(payment):
    """Process subscription payment"""
    try:
        plan = payment.plan
        if not plan:
            raise ValueError("No plan associated with subscription payment")

        # Create subscription
        subscription = Subscription.objects.create(
            plan=plan,
            user=payment.user,
            organisation=payment.organisation,
            max_users=plan.max_users,
            start_credits=plan.total_credits,
            remaining_credits=plan.total_credits,
            billing_start_date=timezone.now().date(),
            billing_end_date=timezone.now().date() + timezone.timedelta(days=30),
            status='active'
        )

        payment.subscription = subscription
        payment.save()

    except Exception as e:
        print(f"Error processing subscription payment: {str(e)}")
        raise


def _process_topup_payment(payment):
    """Process top-up payment"""
    try:
        subscription = payment.subscription
        if not subscription:
            raise ValueError("No subscription associated with top-up payment")

        # Calculate credits to add based on payment amount
        # This is a simplified calculation - adjust based on your pricing
        credits_to_add = int(payment.amount) * 100  # Example: $1 = 100 credits

        # Add credits to subscription
        subscription.remaining_credits += credits_to_add
        subscription.save()

        # Create credit top-up record
        CreditTop.objects.create(
            subscription=subscription,
            organisation=subscription.organisation,
            user=subscription.user,
            amount=payment.amount,
            credits_added=credits_to_add,
            description=f"Top-up payment: {payment.merchant_reference}"
        )

    except Exception as e:
        print(f"Error processing top-up payment: {str(e)}")
        raise
