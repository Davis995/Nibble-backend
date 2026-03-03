from django.db import models
from django.utils import timezone
from django.core.validators import MinLengthValidator
import uuid

# Removed import to avoid circular import - use string reference


class School(models.Model):
    """
    Organization account representing a school
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    school_email = models.EmailField(unique=True)

    # Limits
    max_students = models.IntegerField()

    # Subscription
    subscription = models.OneToOneField(
        'authentication.Subscription',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='school'
    )

    # Admin user (created automatically on school registration)
    admin_user = models.OneToOneField(
        'authentication.User', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='managed_school',
        help_text="School admin user linked to this school"
    )

    # Assigned sales staff (who manages this account)
    assigned_staff = models.ForeignKey('authentication.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_schools')

    # Contact fields
    contact_phone = models.CharField(max_length=30, null=True, blank=True)

    # Teacher count (optional metadata)
    teacher_count = models.IntegerField(default=0)

    # Status
    is_active = models.BooleanField(default=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'schools'
        verbose_name = 'School'
        verbose_name_plural = 'Schools'
        ordering = ['name']

    def __str__(self):
        return self.name

    def student_count(self):
        """Get current number of active students"""
        return self.students.filter(is_active=True).count()

    def is_subscription_active(self):
        """Check if the school has an active subscription"""
        # First try the direct OneToOne relationship
        if self.subscription and self.subscription.status == 'active':
            return True
        
        # Also check via the reverse relationship (subscriptions)
        from authentication.models import Subscription
        active_sub = Subscription.objects.filter(
            organisation=self,
            status='active'
        ).exists()
        return active_sub


class Student(models.Model):
    """
    Student identity tied to a school
    Unique constraint: student_code is unique per school
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='students')

    # Identity
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    school_email = models.EmailField()
    student_code = models.CharField(
        max_length=10,
        validators=[MinLengthValidator(3)],
        help_text="Unique code per school (3-10 characters)"
    )

    # Academic info

    # Status
    is_active = models.BooleanField(default=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_login_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = 'students'
        verbose_name = 'Student'
        verbose_name_plural = 'Students'
        # Unique constraint: student_code is unique per school
        constraints = [
            models.UniqueConstraint(fields=['school', 'student_code'], name='unique_student_code_per_school'),
            models.UniqueConstraint(fields=['school', 'school_email'], name='unique_email_per_school'),
        ]
        # Index for fast lookup
        indexes = [
            models.Index(fields=['school', 'student_code']),
            models.Index(fields=['school', 'school_email']),
            models.Index(fields=['is_active']),
        ]
        ordering = ['school', 'last_name', 'first_name']

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.school_email})"

    def get_full_name(self):
        return f"{self.first_name} {self.last_name}".strip()


class Staff(models.Model):
    """
    Staff member (teacher/admin) tied to a school
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='staff')

    # Identity
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    school_email = models.EmailField()

    # Role
    ROLE_CHOICES = [
        ('teacher', 'Teacher'),
        ('school_admin', 'School Admin'),
    ]
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='teacher')


    # Status
    is_active = models.BooleanField(default=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_login_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = 'staff'
        verbose_name = 'Staff'
        verbose_name_plural = 'Staff'
        constraints = [
            models.UniqueConstraint(fields=['school', 'school_email'], name='unique_staff_email_per_school'),
        ]
        indexes = [
            models.Index(fields=['school', 'school_email']),
            models.Index(fields=['is_active']),
        ]
        ordering = ['school', 'last_name', 'first_name']

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.get_role_display()})"

    def get_full_name(self):
        return f"{self.first_name} {self.last_name}".strip()


class UsageLog(models.Model):
    """
    Track AI tool usage per student for rate limiting
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='usage_logs')
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='usage_logs')

    tool = models.CharField(max_length=100)
    request_count = models.IntegerField(default=1)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'usage_logs'
        verbose_name = 'Usage Log'
        verbose_name_plural = 'Usage Logs'
        indexes = [
            models.Index(fields=['student', 'created_at']),
            models.Index(fields=['school', 'created_at']),
        ]

    def __str__(self):
        return f"{self.student.get_full_name()} - {self.tool} on {self.created_at.date()}"


class Invitation(models.Model):
    """
    Invitation record for staff invited by email to join a school.
    The invitation contains a short code sent in the email link.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField()
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='invitations')
    ROLE_CHOICES = [
        ('teacher', 'Teacher'),
        ('school_admin', 'School Admin'),
    ]
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='teacher')
    code = models.CharField(max_length=64, unique=True)
    invited_by = models.ForeignKey(
        'authentication.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        # this name must differ from the one used in authentication.models.Invitation
        related_name='school_sent_invitations',
    )
    expires_at = models.DateTimeField(null=True, blank=True)
    used = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        # keep the two Invitation models in separate tables
        db_table = 'school_invitations'
        verbose_name = 'Invitation'
        verbose_name_plural = 'Invitations'

    def __str__(self):
        return f"Invite {self.email} -> {self.school.name} ({self.role})"

    def is_valid(self):
        """Return True if the invitation is not used and not expired."""
        from django.utils import timezone

        if self.used:
            return False
        if self.expires_at and timezone.now() > self.expires_at:
            return False
        return True
