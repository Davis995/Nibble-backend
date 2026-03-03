from django.urls import path
from . import views

app_name = 'payments'

urlpatterns = [
    # Payment CRUD
    path('payments/', views.PaymentListView.as_view(), name='payment-list'),
    path('payments/<uuid:payment_id>/', views.PaymentDetailView.as_view(), name='payment-detail'),

    # Invoice CRUD
    path('invoices/', views.InvoiceListView.as_view(), name='invoice-list'),
    path('invoices/<uuid:invoice_id>/', views.InvoiceDetailView.as_view(), name='invoice-detail'),

    # Audit CRUD
    path('audits/', views.AuditListView.as_view(), name='audit-list'),

    # Payment Processing
    path('initiate/', views.PaymentInitiateView.as_view(), name='payment-initiate'),
    path('ipn/', views.payment_webhook, name='payment-webhook'),
]