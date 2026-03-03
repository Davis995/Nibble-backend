from rest_framework import serializers
from .models import Payment, Invoice, Audit


class PaymentSerializer(serializers.ModelSerializer):
    """Serializer for Payment model"""
    user_name = serializers.CharField(source='user.get_full_name', read_only=True)
    organisation_name = serializers.CharField(source='organisation.name', read_only=True)
    plan_name = serializers.CharField(source='plan.name', read_only=True)
    subscription_plan_name = serializers.CharField(source='subscription.plan.name', read_only=True)

    class Meta:
        model = Payment
        fields = [
            'id', 'payment_type', 'merchant_reference', 'order_tracking_id', 'redirect_url',
            'user', 'user_name', 'organisation', 'organisation_name', 'subscription',
            'subscription_plan_name', 'amount', 'currency', 'plan', 'plan_name', 'status',
            'paymethod', 'payment_method', 'transaction_date', 'payer_name', 'payer_email',
            'payer_phone', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'merchant_reference', 'order_tracking_id', 'redirect_url',
                          'created_at', 'updated_at']


class InvoiceSerializer(serializers.ModelSerializer):
    """Serializer for Invoice model"""
    user_name = serializers.CharField(source='user.get_full_name', read_only=True)
    organisation_name = serializers.CharField(source='organisation.name', read_only=True)
    payment_details = PaymentSerializer(source='payment', read_only=True)

    class Meta:
        model = Invoice
        fields = [
            'id', 'invoice_number', 'payment', 'payment_details', 'user', 'user_name',
            'organisation', 'organisation_name', 'amount', 'currency', 'status',
            'due_date', 'paid_at', 'billing_address', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'invoice_number', 'created_at', 'updated_at']


class AuditSerializer(serializers.ModelSerializer):
    """Serializer for Audit model"""
    payment_merchant_reference = serializers.CharField(source='payment.merchant_reference', read_only=True)
    subscription_plan_name = serializers.CharField(source='subscription.plan.name', read_only=True)

    class Meta:
        model = Audit
        fields = [
            'id', 'payload', 'status', 'payment', 'payment_merchant_reference',
            'subscription', 'subscription_plan_name', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']


class PaymentInitiateSerializer(serializers.Serializer):
    """Serializer for payment initiation request"""
    payment_type = serializers.ChoiceField(choices=['subscription', 'topup'])
    user_id = serializers.IntegerField(required=False)
    organisation_id = serializers.IntegerField(required=False)
    amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    plan_id = serializers.IntegerField(required=False)
    subscription_id = serializers.IntegerField(required=False)  # For top-ups

    # Billing address fields
    email_address = serializers.EmailField(required=False)
    phone_number = serializers.CharField(max_length=20, required=False)
    country_code = serializers.CharField(max_length=3, required=False)
    first_name = serializers.CharField(max_length=50, required=False)
    middle_name = serializers.CharField(max_length=50, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=50, required=False)
    line_1 = serializers.CharField(max_length=100, required=False)
    line_2 = serializers.CharField(max_length=100, required=False, allow_blank=True)
    city = serializers.CharField(max_length=50, required=False)
    state = serializers.CharField(max_length=50, required=False)
    postal_code = serializers.CharField(max_length=20, required=False)
    zip_code = serializers.CharField(max_length=20, required=False)

    def validate(self, data):
        """Validate payment initiation data"""
        payment_type = data.get('payment_type')

        # Check that either user_id or organisation_id is provided, but not both
        user_id = data.get('user_id')
        organisation_id = data.get('organisation_id')

        if not user_id and not organisation_id:
            raise serializers.ValidationError("Either user_id or organisation_id must be provided")
        if user_id and organisation_id:
            raise serializers.ValidationError("Cannot provide both user_id and organisation_id")

        # Validate based on payment type
        if payment_type == 'subscription':
            if not data.get('plan_id'):
                raise serializers.ValidationError("plan_id is required for subscription payments")
        elif payment_type == 'topup':
            if not data.get('subscription_id'):
                raise serializers.ValidationError("subscription_id is required for top-up payments")

        return data