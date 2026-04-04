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
from rest_framework import status, viewsets, filters
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import api_view, permission_classes
from django_filters.rest_framework import DjangoFilterBackend
from authentication.permissions import IsAdmin

from .models import Payment, Invoice, Audit
from .serializers import PaymentSerializer, InvoiceSerializer, AuditSerializer, PaymentInitiateSerializer
from schools.models import School
from .services import (
    initiate_payment, 
    handle_webhook, 
    get_pesapal_transaction_status,
    process_subscription_payment,
    process_topup_payment
)


# ============================================================================
# PAYMENT CRUD VIEWS
# ============================================================================

# LEGACY PAYMENT VIEWS - REPLACED BY VIEWSETS
# class PaymentListView(APIView): ...
# class PaymentDetailView(APIView): ...
# class InvoiceListView(APIView): ...
# class InvoiceDetailView(APIView): ...
# class AuditListView(APIView): ...


# ============================================================================
# ADMIN VIEWSETS
# ============================================================================

class AdminPaymentViewSet(viewsets.ModelViewSet):
    """
    Administrative ViewSet for managing payment records.
    """
    queryset = Payment.objects.all().select_related('user', 'organisation', 'subscription').order_by('-created_at')
    serializer_class = PaymentSerializer
    permission_classes = [IsAuthenticated, IsAdmin]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    
    # Filterable fields
    filterset_fields = ['status', 'payment_type', 'currency', 'paymethod']
    
    # Searchable fields
    search_fields = [
        'merchant_reference', 'order_tracking_id', 
        'payer_name', 'payer_email', 'payer_phone',
        'user__email', 'organisation__name'
    ]
    
    # Sortable fields
    ordering_fields = ['created_at', 'amount', 'transaction_date']


class AdminInvoiceViewSet(viewsets.ModelViewSet):
    """
    Administrative ViewSet for managing invoices.
    """
    queryset = Invoice.objects.all().select_related('user', 'organisation', 'payment').order_by('-created_at')
    serializer_class = InvoiceSerializer
    permission_classes = [IsAuthenticated, IsAdmin]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    
    # Filterable fields
    filterset_fields = ['status', 'currency']
    
    # Searchable fields
    search_fields = [
        'invoice_number', 'user__email', 'organisation__name',
        'payment__merchant_reference'
    ]
    
    # Sortable fields
    ordering_fields = ['created_at', 'amount', 'due_date', 'paid_at']


class AdminAuditViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Administrative ViewSet for viewing payment audit logs.
    """
    queryset = Audit.objects.all().select_related('payment', 'subscription').order_by('-created_at')
    serializer_class = AuditSerializer
    permission_classes = [IsAuthenticated, IsAdmin]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    
    # Filterable fields
    filterset_fields = ['status', 'payment', 'subscription']
    
    # Searchable fields
    search_fields = [
        'payment__merchant_reference',
        'subscription__id'
    ]
    
    # Sortable fields
    ordering_fields = ['created_at']


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
            result = initiate_payment(data, request.user)
            
            if 'error' in result:
                return Response(result, status=status.HTTP_400_BAD_REQUEST)

            return Response({
                'payment': PaymentSerializer(result['payment']).data,
                'invoice': InvoiceSerializer(result['invoice']).data,
                'redirect_url': result['redirect_url'],
                'order_tracking_id': result['order_tracking_id']
            })

        except Exception as e:
            return Response({
                'error': 'Payment initiation failed',
                'details': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


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
        result = handle_webhook(request.data)
        
        if 'error' in result:
            return Response({'error': result['error']}, status=result.get('status', 400))
            
        return Response({'message': result['message']})

    except Exception as e:
        # Log error
        print(f"Webhook processing error: {str(e)}")
        return Response({'error': 'Internal server error'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
