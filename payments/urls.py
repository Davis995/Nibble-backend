from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'admin/payments', views.AdminPaymentViewSet, basename='admin-payments')
router.register(r'admin/invoices', views.AdminInvoiceViewSet, basename='admin-invoices')
router.register(r'admin/audits', views.AdminAuditViewSet, basename='admin-audits')

app_name = 'payments'

urlpatterns = [
    # Admin ViewSets
    path('', include(router.urls)),

    # Payment Processing
    path('initiate/', views.PaymentInitiateView.as_view(), name='payment-initiate'),
    path('ipn/', views.payment_webhook, name='payment-webhook'),
]