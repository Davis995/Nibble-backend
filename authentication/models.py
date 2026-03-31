from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.utils import timezone
import uuid

# Removed import to avoid circular import - use string reference


class Plan(models.Model):
    """
    Subscription plans for users and organizations with pricing tiers and features
    """
    USE_TYPE_CHOICES = [
        ('individual', 'Individual'),
        ('enterprise', 'Enterprise'),
    ]
    
    THEME_CHOICES = [
        ('cream', 'Cream'),
        ('dark', 'Dark'),
        ('light', 'Light'),
    ]

    # Basic info
    plan_id = models.CharField(max_length=50, unique=True, null=True, blank=True, help_text="Unique identifier like 'free', 'plus'")
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, help_text="Plan description for marketing")
    use_type = models.CharField(max_length=20, choices=USE_TYPE_CHOICES)
    theme = models.CharField(max_length=20, choices=THEME_CHOICES, default='cream')
    currency = models.CharField(max_length=10, default='UGX', help_text="Currency for this plan, e.g. 'UGX', 'KES', 'USD'")
    allowed_modals = models.JSONField(default=list, blank=True, help_text="List of allowed AI modals for this plan, e.g. ['gpt-4', 'gpt-3.5', 'deepseek-chat']")
    
    # Pricing
    total_credits = models.IntegerField(default=0, help_text="Total credits for this plan")
    max_users = models.IntegerField(null=True, blank=True)
    monthly_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    annual_price = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text="Monthly cost if paid annually")
    annual_billed = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text="Total annual billing amount")
    
    # Display options
    badge = models.CharField(max_length=100, blank=True, help_text="Badge text like 'Save 27%'")
    cta = models.CharField(max_length=100, default="Select Plan", help_text="Call-to-action button text")
    is_popular = models.BooleanField(default=False, help_text="Mark as popular/featured plan")
    is_active = models.BooleanField(default=True, help_text="Whether this plan is available")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'plans'
        verbose_name = 'Plan'
        verbose_name_plural = 'Plans'
        constraints = [
            models.CheckConstraint(check=models.Q(use_type__in=['individual', 'enterprise']), name='plan_use_type_valid'),
            models.CheckConstraint(check=models.Q(monthly_price__gte=0), name='monthly_price_non_negative'),
            models.CheckConstraint(check=models.Q(annual_price__gte=0), name='annual_price_non_negative'),
        ]
        indexes = [
            models.Index(fields=['name']),
            models.Index(fields=['plan_id']),
            models.Index(fields=['use_type']),
            models.Index(fields=['is_active']),
            models.Index(fields=['is_popular']),
        ]

    def __str__(self):
        return f"{self.name} ({self.get_use_type_display()})"


class PlanFeature(models.Model):
    """
    Features associated with a subscription plan
    """
    plan = models.ForeignKey(Plan, on_delete=models.CASCADE, related_name='features')
    text = models.CharField(max_length=255, help_text="Feature description")
    included = models.BooleanField(default=False, help_text="Whether this feature is included in this plan")
    highlight = models.BooleanField(default=False, help_text="Highlight this feature (for Plus plans, etc.)")
    order = models.IntegerField(default=0, help_text="Display order of features")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'plan_features'
        verbose_name = 'Plan Feature'
        verbose_name_plural = 'Plan Features'
        ordering = ['order', 'id']
        indexes = [
            models.Index(fields=['plan']),
            models.Index(fields=['included']),
        ]

    def __str__(self):
        return f"{self.plan.name} - {self.text}"


class UserManager(BaseUserManager):
    """
    Custom manager for User model that uses email as username
    """
    
    def _create_user(self, email, password, **extra_fields):
        """
        Create and save a user with the given email and password.
        """
        if not email:
            raise ValueError('The Email must be set')
        email = self.normalize_email(email)
        # Set username to email since USERNAME_FIELD = 'email'
        extra_fields.setdefault('username', email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        """
        Create and save a regular user with the given email and password.
        """
        extra_fields.setdefault('is_staff', False)
        extra_fields.setdefault('is_superuser', False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password, **extra_fields):
        """
        Create and save a superuser with the given email and password.
        """
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self._create_user(email, password, **extra_fields)


class User(AbstractUser):
    """
    Custom User model extending Django's AbstractUser
    Kept for backward compatibility and admin purposes
    """
    objects = UserManager()
    
    USER_TYPE_CHOICES = [
        ('individual', 'Individual'),
        ('enterprise', 'Enterprise'),
        ('nibble',"Nibble")
    ]
    
    email = models.EmailField(unique=True, verbose_name='Email Address')
    user_type = models.CharField(max_length=20, choices=USER_TYPE_CHOICES, default='individual')
    organisation = models.ForeignKey('schools.School', on_delete=models.SET_NULL, null=True, blank=True, related_name='users')
    phone_number = models.CharField(max_length=15, blank=True, null=True)
    date_of_birth = models.DateField(blank=True, null=True)
    
    # Profile fields
    bio = models.TextField(max_length=500, blank=True)
    profile_picture = models.ImageField(upload_to='profile_pics/', blank=True, null=True)
    
    # User roles
    ROLE_CHOICES = [
        # Normal users
        ('student', 'Student'),
        ('teacher', 'Teacher'),
        # School/organisation level
        ('school_admin', 'School Admin'),
        # Owner level
        ('operator', 'Operator'),
        ('sale_manager', 'Sale Manager'),
        ('sales_assistant', 'Sales Assistant')
        
    ]
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='student')
    
    # Subscription plan (for legacy users)
    subscription_plan = models.ForeignKey(
        Plan, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='users',
        help_text="Subscription plan for this user (legacy auth)"
    )
    
    # Account status
    is_verified = models.BooleanField(default=False)
    is_onboarded = models.BooleanField(default=False, help_text="Whether the user has completed onboarding")
    trial = models.BooleanField(default=False)
    start_trial = models.DateField(blank=True, null=True)
    end_trial = models.DateField(blank=True, null=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_login_at = models.DateTimeField(blank=True, null=True)
    
    # Make email required
    REQUIRED_FIELDS = []
    
    USERNAME_FIELD = 'email'
    
    class Meta:
        db_table = 'users'
        verbose_name = 'User'
        verbose_name_plural = 'Users'
        ordering = ['-created_at']
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(user_type='individual') | 
                    (models.Q(user_type='enterprise') & models.Q(organisation__isnull=False))
                ),
                name='enterprise_user_must_have_organisation'
            ),
        ]
        indexes = [
            models.Index(fields=['email']),
            models.Index(fields=['user_type']),
            models.Index(fields=['organisation']),
            models.Index(fields=['role']),
        ]
    
    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"
    
    def is_trial_active(self):
        """Check if user has active trial"""
        if not self.trial:
            return False
        if self.end_trial and self.end_trial < timezone.now().date():
            return False
        return True
    
    def is_student(self):
        """Check if user is a student"""
        return self.role == 'student'
    
    def is_teacher(self):
        """Check if user is a teacher"""
        return self.role == 'teacher'
    
    def is_school_admin(self):
        """Check if user is a school admin"""
        return self.role == 'school_admin'
    
    def is_operator(self):
        """Check if user is an operator"""
        return self.role == 'operator'
    
    def is_admin_user(self):
        """Check if user is an admin (school admin, operator, or Django superuser)"""
        return self.role in ['school_admin', 'operator'] or self.is_superuser
    
    def is_owner_level(self):
        """Check if user is at owner level (operator or superuser)"""
        return self.role == 'operator' or self.is_superuser
    
    def get_full_name(self):
        """Return the first_name plus the last_name, with a space in between."""
        full_name = f"{self.first_name} {self.last_name}"
        return full_name.strip() or self.username




class Subscription(models.Model):
    """
    Subscription for users or organizations
    """
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('expired', 'Expired'),
        ('suspended', 'Suspended'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    max_users = models.IntegerField()
    plan = models.ForeignKey(Plan, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    organisation = models.ForeignKey('schools.School', on_delete=models.CASCADE, null=True, blank=True, related_name='subscriptions')
    start_credits = models.IntegerField()
    remaining_credits = models.IntegerField()
    billing_start_date = models.DateField()
    billing_end_date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'subscriptions'
        verbose_name = 'Subscription'
        verbose_name_plural = 'Subscriptions'
        constraints = [
            models.CheckConstraint(
                check=(
                    (models.Q(user__isnull=False) & models.Q(organisation__isnull=True)) |
                    (models.Q(user__isnull=True) & models.Q(organisation__isnull=False))
                ),
                name='subscription_belongs_to_user_or_organisation'
            ),
        ]
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['plan']),
            models.Index(fields=['user']),
            models.Index(fields=['organisation']),
        ]

    def __str__(self):
        owner = self.user.username if self.user else self.organisation.name
        return f"{owner} - {self.plan.name} ({self.get_status_display()})"


class CreditTop(models.Model):
    """
    Credit top-ups for organisations
    """
    subscription = models.ForeignKey(Subscription, on_delete=models.CASCADE, related_name='credit_tops')
    organisation = models.ForeignKey('schools.School', on_delete=models.CASCADE, related_name='credit_tops')
    credit_add = models.IntegerField()
    purchase_date = models.DateField()
    expiry_date = models.DateField()

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'credit_tops'
        verbose_name = 'Credit Top'
        verbose_name_plural = 'Credit Tops'
        constraints = [
            models.CheckConstraint(check=models.Q(credit_add__gt=0), name='credit_add_positive'),
        ]
        indexes = [
            models.Index(fields=['subscription']),
        ]

    def __str__(self):
        return f"{self.organisation.name} - {self.credit_add} credits on {self.purchase_date}"


class PasswordResetToken(models.Model):
    """
    Token for password reset functionality
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='password_reset_tokens')
    token = models.CharField(max_length=100, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used = models.BooleanField(default=False)
    
    class Meta:
        db_table = 'password_reset_tokens'
        verbose_name = 'Password Reset Token'
        verbose_name_plural = 'Password Reset Tokens'
    
    def __str__(self):
        return f"Reset token for {self.user.username}"
    
    def is_valid(self):
        """Check if token is still valid"""
        return not self.used and timezone.now() < self.expires_at


class EmailVerificationToken(models.Model):
    """
    Token for email verification
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='email_verification_tokens')
    token = models.CharField(max_length=100, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used = models.BooleanField(default=False)
    
    class Meta:
        db_table = 'email_verification_tokens'
        verbose_name = 'Email Verification Token'
        verbose_name_plural = 'Email Verification Tokens'
    
    def __str__(self):
        return f"Verification token for {self.user.username}"
    
    def is_valid(self):
        """Check if token is still valid"""
        return not self.used and timezone.now() < self.expires_at


class Invitation(models.Model):
    """
    Invitation token for creating 'nibble' users by admin/superadmin
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(max_length=254, help_text="Invitee email")
    role = models.CharField(max_length=50, help_text="Role to assign to invited user")
    token = models.CharField(max_length=128, unique=True)
    invited_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        # use a distinct related_name so it doesn't clash with the
        # Invitation model defined in the schools app
        related_name='auth_sent_invitations',
    )
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='accepted_invitations')
    used = models.BooleanField(default=False)
    expires_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        # keep the table separate from the schools.Invitation model
        db_table = 'auth_invitations'
        verbose_name = 'Invitation'
        verbose_name_plural = 'Invitations'
        indexes = [
            models.Index(fields=['email']),
            models.Index(fields=['token']),
            models.Index(fields=['used']),
        ]

    def __str__(self):
        return f"Invitation {self.email} -> {self.role} ({'used' if self.used else 'pending'})"

    def is_valid(self):
        if self.used:
            return False
        if self.expires_at and timezone.now() > self.expires_at:
            return False
        return True


class PasswordResetCode(models.Model):
    """
    6-digit code for password reset functionality
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='password_reset_codes')
    code = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used = models.BooleanField(default=False)

    class Meta:
        db_table = 'password_reset_codes'
        verbose_name = 'Password Reset Code'
        verbose_name_plural = 'Password Reset Codes'

    def __str__(self):
        return f"Reset code for {self.user.username}"

    def is_valid(self):
        """Check if code is still valid"""
        return not self.used and timezone.now() < self.expires_at
