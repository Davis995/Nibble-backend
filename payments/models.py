from django.db import models
from django.core.validators import MinValueValidator
import uuid


class Payment(models.Model):
    """
    Payment records for subscriptions and top-ups
    """
    PAYMENT_TYPE_CHOICES = [
        ('subscription', 'Subscription'),
        ('topup', 'Top-up'),
    ]

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('complete', 'Complete'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
        ('partially_paid', 'Partially Paid'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    payment_type = models.CharField(max_length=20, choices=PAYMENT_TYPE_CHOICES)
    merchant_reference = models.CharField(max_length=100, unique=True)
    order_tracking_id = models.CharField(max_length=100, blank=True, null=True)
    redirect_url = models.URLField(blank=True, null=True)
    user = models.ForeignKey('authentication.User', on_delete=models.SET_NULL, null=True, blank=True)
    organisation = models.ForeignKey('schools.School', on_delete=models.SET_NULL, null=True, blank=True)
    subscription = models.ForeignKey('authentication.Subscription', on_delete=models.SET_NULL, null=True, blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0.01)])
    currency = models.CharField(max_length=3, default='KES')
    plan = models.ForeignKey('authentication.Plan', on_delete=models.SET_NULL, null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    paymethod = models.CharField(max_length=50, blank=True, null=True)
    payment_method = models.CharField(max_length=50, blank=True, null=True)  # From webhook
    transaction_date = models.DateTimeField(blank=True, null=True)  # From webhook
    payer_name = models.CharField(max_length=100, blank=True, null=True)  # From webhook
    payer_email = models.EmailField(blank=True, null=True)  # From webhook
    payer_phone = models.CharField(max_length=20, blank=True, null=True)  # From webhook

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'payments'
        verbose_name = 'Payment'
        verbose_name_plural = 'Payments'
        constraints = [
            models.CheckConstraint(
                check=(
                    (models.Q(user__isnull=False) & models.Q(organisation__isnull=True)) |
                    (models.Q(user__isnull=True) & models.Q(organisation__isnull=False))
                ),
                name='payment_belongs_to_user_or_organisation'
            ),
            models.CheckConstraint(check=models.Q(payment_type__in=['subscription', 'topup']), name='payment_type_valid'),
            models.CheckConstraint(check=models.Q(status__in=['pending', 'complete', 'failed', 'cancelled', 'partially_paid']), name='payment_status_valid'),
        ]
        indexes = [
            models.Index(fields=['merchant_reference']),
            models.Index(fields=['order_tracking_id']),
            models.Index(fields=['status']),
            models.Index(fields=['user']),
            models.Index(fields=['organisation']),
            models.Index(fields=['subscription']),
        ]

    def __str__(self):
        owner = self.user.username if self.user else self.organisation.name
        return f"{owner} - {self.payment_type} - {self.amount} ({self.status})"


class Invoice(models.Model):
    """
    Invoice records for payments
    """
    STATUS_CHOICES = [
        ('unpaid', 'Unpaid'),
        ('paid', 'Paid'),
        ('overdue', 'Overdue'),
        ('cancelled', 'Cancelled'),
        ('partially_paid', 'Partially Paid'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    invoice_number = models.CharField(max_length=50, unique=True)
    payment = models.OneToOneField(Payment, on_delete=models.CASCADE, related_name='invoice')
    user = models.ForeignKey('authentication.User', on_delete=models.SET_NULL, null=True, blank=True)
    organisation = models.ForeignKey('schools.School', on_delete=models.SET_NULL, null=True, blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0.01)])
    currency = models.CharField(max_length=3, default='KES')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='unpaid')
    due_date = models.DateField(blank=True, null=True)
    paid_at = models.DateTimeField(blank=True, null=True)

    # Billing address from payment request
    billing_address = models.JSONField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'invoices'
        verbose_name = 'Invoice'
        verbose_name_plural = 'Invoices'
        constraints = [
            models.CheckConstraint(
                check=(
                    (models.Q(user__isnull=False) & models.Q(organisation__isnull=True)) |
                    (models.Q(user__isnull=True) & models.Q(organisation__isnull=False))
                ),
                name='invoice_belongs_to_user_or_organisation'
            ),
            models.CheckConstraint(check=models.Q(status__in=['unpaid', 'paid', 'overdue', 'cancelled', 'partially_paid']), name='invoice_status_valid'),
        ]
        indexes = [
            models.Index(fields=['invoice_number']),
            models.Index(fields=['status']),
            models.Index(fields=['user']),
            models.Index(fields=['organisation']),
            models.Index(fields=['due_date']),
        ]

    def __str__(self):
        owner = self.user.username if self.user else self.organisation.name
        return f"Invoice {self.invoice_number} - {owner} - {self.amount} ({self.status})"


class Audit(models.Model):
    """
    Audit logs for payments and subscriptions
    """
    STATUS_CHOICES = [
        ('success', 'Success'),
        ('failure', 'Failure'),
        ('pending', 'Pending'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    payload = models.JSONField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    payment = models.ForeignKey(Payment, on_delete=models.CASCADE, related_name='audits')
    subscription = models.ForeignKey('authentication.Subscription', on_delete=models.CASCADE, related_name='audits')

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'audits'
        verbose_name = 'Audit'
        verbose_name_plural = 'Audits'
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['payment']),
            models.Index(fields=['subscription']),
        ]

    def __str__(self):
        return f"Audit {self.id} - {self.status}"
