from django.urls import path
from . import views

app_name = 'payments'

# Mapping common ViewSet actions for manual standard path registration
list_create = {'get': 'list', 'post': 'create'}
retrieve_update_destroy = {
    'get': 'retrieve', 
    'put': 'update', 
    'patch': 'partial_update', 
    'delete': 'destroy'
}
list_retrieve = {'get': 'list'}
retrieve_only = {'get': 'retrieve'}

urlpatterns = [
    # ==================== ADMIN PAYMENT ENDPOINTS ====================
    # List and Create Payments
    path('admin/payments/', views.AdminPaymentViewSet.as_view(list_create), name='admin-payments-list'),
    
    # Detail, Update, and Delete Payments
    path('admin/payments/<uuid:pk>/', views.AdminPaymentViewSet.as_view(retrieve_update_destroy), name='admin-payments-detail'),

    # ==================== ADMIN INVOICE ENDPOINTS ====================
    # List and Create Invoices
    path('admin/invoices/', views.AdminInvoiceViewSet.as_view(list_create), name='admin-invoices-list'),
    
    # Detail, Update, and Delete Invoices
    path('admin/invoices/<uuid:pk>/', views.AdminInvoiceViewSet.as_view(retrieve_update_destroy), name='admin-invoices-detail'),

    # ==================== ADMIN AUDIT ENDPOINTS ====================
    # List Audits
    path('admin/audits/', views.AdminAuditViewSet.as_view(list_retrieve), name='admin-audits-list'),
    
    # Detail Audits
    path('admin/audits/<uuid:pk>/', views.AdminAuditViewSet.as_view(retrieve_only), name='admin-audits-detail'),

    # ==================== PAYMENT PROCESSING ====================
    # Initiate a payment request
    path('initiate/', views.PaymentInitiateView.as_view(), name='payment-initiate'),
    
    # Pesapal IPN Webhook
    path('ipn/', views.payment_webhook, name='payment-webhook'),
]