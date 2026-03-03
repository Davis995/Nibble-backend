from django.contrib import admin
from .models import Payment, Invoice, Audit

# Register your models here.

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('merchant_reference', 'payment_type', 'get_owner', 'amount', 'status', 'created_at')
    list_filter = ('payment_type', 'status', 'created_at')
    search_fields = ('merchant_reference', 'user__username', 'organisation__name', 'order_tracking_id')
    readonly_fields = ('id', 'created_at', 'updated_at')

    def get_owner(self, obj):
        return obj.user.username if obj.user else obj.organisation.name
    get_owner.short_description = 'Owner'


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ('invoice_number', 'get_owner', 'amount', 'status', 'due_date', 'paid_at', 'created_at')
    list_filter = ('status', 'due_date', 'created_at')
    search_fields = ('invoice_number', 'user__username', 'organisation__name')
    readonly_fields = ('id', 'created_at', 'updated_at')

    def get_owner(self, obj):
        return obj.user.username if obj.user else obj.organisation.name
    get_owner.short_description = 'Owner'


@admin.register(Audit)
class AuditAdmin(admin.ModelAdmin):
    list_display = ('id', 'status', 'get_payment_reference', 'get_subscription_plan', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('payment__merchant_reference', 'subscription__plan__name')
    readonly_fields = ('id', 'created_at', 'payload')

    def get_payment_reference(self, obj):
        return obj.payment.merchant_reference if obj.payment else 'N/A'
    get_payment_reference.short_description = 'Payment Reference'

    def get_subscription_plan(self, obj):
        return obj.subscription.plan.name if obj.subscription and obj.subscription.plan else 'N/A'
    get_subscription_plan.short_description = 'Subscription Plan'
