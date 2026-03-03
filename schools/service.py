from django.utils import timezone
from django.db import transaction
from rest_framework.exceptions import PermissionDenied, ValidationError, APIException
from authentication.models import Subscription
from django.contrib.auth import get_user_model

User = get_user_model()


def get_org_subscription(school):
    """Return active subscription object for a school (organisation)."""
    try:
        sub = Subscription.objects.filter(organisation=school, status='active').first()
        return sub
    except Exception:
        return None


def is_subscription_active_for_user_or_org(user):
    """Return True if the user or their organisation has an active subscription or an active trial."""
    # Individual user subscription
    try:
        user_sub = Subscription.objects.filter(user=user, status='active').first()
    except Exception:
        user_sub = None

    if user_sub:
        return True

    # Enterprise users rely on organisation subscription
    if user.user_type == 'enterprise' and user.organisation:
        org_sub = get_org_subscription(user.organisation)
        if org_sub:
            return True

    # Allow if user has an active trial flag
    if hasattr(user, 'is_trial_active') and user.is_trial_active():
        return True

    return False


def get_current_user_count_for_school(school):
    """Count current users linked to a school (organisation).

    This uses the `User.organisation` relation which is used when creating
    user accounts for students and staff.
    """
    return User.objects.filter(organisation=school).count()


def ensure_user_slots_available(school, required_slots=1):
    """Ensure the school's subscription allows creating `required_slots` more users.

    Raises `PermissionDenied` if creating users would exceed limits.
    """
    sub = get_org_subscription(school)
    if not sub:
        # If there is no organisation subscription, allow only if school's admin_user or trial allows
        # But for safety, deny by default
        raise PermissionDenied('Organisation does not have an active subscription')

    max_users = sub.max_users
    if max_users is None:
        return True

    current = get_current_user_count_for_school(school)
    if current + required_slots > max_users:
        raise PermissionDenied('User limit exceeded for this organisation subscription')

    return True


def ensure_credits_and_deduct(user, token_cost):
    """Ensure the appropriate subscription has enough remaining credits and deduct them atomically.

    token_cost: integer number of token units to charge.
    Raises PermissionDenied if insufficient credits or subscription inactive.
    Returns remaining_credits after deduction.
    """
    # Determine subscription to charge
    sub = None
    if user.user_type == 'enterprise' and user.organisation:
        sub = get_org_subscription(user.organisation)
    else:
        sub = Subscription.objects.filter(user=user, status='active').first()

    if not sub and not (hasattr(user, 'is_trial_active') and user.is_trial_active()):
        raise PermissionDenied('No active subscription found for billing tokens')

    if sub is None:
        # In trial mode: allow but do not deduct
        return None

    # Check remaining credits
    if sub.remaining_credits is None:
        raise PermissionDenied('Subscription has no remaining credit information')

    if sub.remaining_credits < token_cost:
        raise PermissionDenied('Insufficient subscription credits for this request')

    # Deduct atomically
    with transaction.atomic():
        sub = Subscription.objects.select_for_update().get(id=sub.id)
        if sub.remaining_credits < token_cost:
            raise PermissionDenied('Insufficient subscription credits for this request')
        sub.remaining_credits = sub.remaining_credits - token_cost
        sub.save(update_fields=['remaining_credits'])

    return sub.remaining_credits


def check_long_request_limit(user, estimated_tokens, max_per_request=None):
    """Check that an estimated token usage for a single request is allowed.

    max_per_request: optional override limit; if None, uses remaining credits.
    Raises PermissionDenied if request is too large.
    """
    if not is_subscription_active_for_user_or_org(user):
        raise PermissionDenied('Subscription inactive or expired')

    # If explicit max per request specified, enforce it
    if max_per_request is not None and estimated_tokens > max_per_request:
        raise PermissionDenied('Request exceeds maximum allowed tokens per request')

    # Otherwise ensure remaining credits cover the estimated tokens
    sub = None
    if user.user_type == 'enterprise' and user.organisation:
        sub = get_org_subscription(user.organisation)
    else:
        sub = Subscription.objects.filter(user=user, status='active').first()

    # If no subscription (trial), allow
    if not sub:
        return True

    if sub.remaining_credits < estimated_tokens:
        raise PermissionDenied('Not enough credits for this request')

    return True


def ensure_org_credits_and_deduct(school, token_cost):
    """Ensure organisation subscription has enough credits and deduct them atomically.

    Raises PermissionDenied if insufficient credits or no active organisation subscription.
    Returns remaining_credits after deduction.
    """
    sub = get_org_subscription(school)
    if not sub:
        raise PermissionDenied('Organisation does not have an active subscription')

    if sub.remaining_credits is None:
        raise PermissionDenied('Organisation subscription has no remaining credit information')

    if sub.remaining_credits < token_cost:
        raise PermissionDenied('Insufficient organisation credits for this request')

    with transaction.atomic():
        sub = Subscription.objects.select_for_update().get(id=sub.id)
        if sub.remaining_credits < token_cost:
            raise PermissionDenied('Insufficient organisation credits for this request')
        sub.remaining_credits = sub.remaining_credits - token_cost
        sub.save(update_fields=['remaining_credits'])

    return sub.remaining_credits
