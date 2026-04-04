from django.utils import timezone
from datetime import timedelta
from .models import Subscription, Plan

def create_subscription(user, plan, organisation=None):
    """
    Create or update a subscription for a user or organisation.
    """
    billing_start_date = timezone.now().date()
    billing_end_date = billing_start_date + timedelta(days=30)
    
    subscription, created = Subscription.objects.update_or_create(
        user=user,
        organisation=organisation,
        defaults={
            'plan': plan,
            'status': 'active',
            'max_users': plan.max_users if plan.max_users is not None else 1,
            'start_credits': plan.total_credits,
            'remaining_credits': plan.total_credits,
            'billing_start_date': billing_start_date,
            'billing_end_date': billing_end_date,
        }
    )
    
    return subscription, created
