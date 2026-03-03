from django.db import models
import uuid


class Lead(models.Model):
    """
    Lead for potential customers
    """
    CATEGORY_CHOICES = [
        ('education', 'Education'),
        ('corporate', 'Corporate'),
        ('government', 'Government'),
        ('other', 'Other'),
    ]

    PREFERENCE_CHOICES = [
        ('social_media', 'Social Media'),
        ('email', 'Email'),
        ('website', 'Website'),
        ('referral', 'Referral'),
        ('other', 'Other'),
    ]

    STATUS_CHOICES = [
        ('new', 'New'),
        ('contacted', 'Contacted'),
        ('demo_scheduled', 'Demo Scheduled'),
        ('negotiated', 'Negotiated'),
        ('converted', 'Converted'),
        ('lost', 'Lost'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    firstname = models.CharField(max_length=100)
    secondname = models.CharField(max_length=100)
    phonenumber = models.CharField(max_length=20)
    workemail = models.EmailField()
    jobtitle = models.CharField(max_length=100)
    institution = models.CharField(max_length=100)
    categories = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    institution_name = models.CharField(max_length=255)
    size_of_institution = models.CharField(max_length=50)
    country = models.CharField(max_length=100)
    city = models.CharField(max_length=100)
    question_on_preference = models.CharField(max_length=20, choices=PREFERENCE_CHOICES)
    assigned_staff = models.ForeignKey('authentication.User', on_delete=models.SET_NULL, null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='new')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'leads'
        verbose_name = 'Lead'
        verbose_name_plural = 'Leads'
        indexes = [
            models.Index(fields=['workemail']),
            models.Index(fields=['status']),
            models.Index(fields=['assigned_staff']),
            models.Index(fields=['categories']),
            models.Index(fields=['country']),
        ]

    def __str__(self):
        return f"{self.firstname} {self.secondname} - {self.institution_name}"


class Notification(models.Model):
    """
    Notifications for users
    """
    NOTIFICATION_TYPES = [
        ('new_lead', 'New Lead'),
        ('demo_reminder', 'Demo Reminder'),
        ('lead_assigned', 'Lead Assigned'),
        ('status_changed', 'Status Changed'),
        ('demo_completed', 'Demo Completed'),
        ('onboarding_update', 'Onboarding Update'),
    ]
    
    user = models.ForeignKey('authentication.User', on_delete=models.CASCADE)
    notification_type = models.CharField(max_length=50, choices=NOTIFICATION_TYPES, default='new_lead')
    title = models.CharField(max_length=255)
    body = models.TextField()
    is_read = models.BooleanField(default=False)
    priority = models.CharField(max_length=20, choices=[('low', 'Low'), ('medium', 'Medium'), ('high', 'High')], default='medium')

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'notifications'
        verbose_name = 'Notification'
        verbose_name_plural = 'Notifications'
        indexes = [
            models.Index(fields=['user']),
            models.Index(fields=['is_read']),
        ]

    def __str__(self):
        return f"{self.user.username} - {self.title}"


class DemoSchedule(models.Model):
    """
    Demo schedules for leads
    """
    STATUS_CHOICES = [
        ('physical', 'Physical'),
        ('online', 'Online'),
    ]

    lead = models.ForeignKey(Lead, on_delete=models.CASCADE)
    assigned_staff = models.ForeignKey('authentication.User', on_delete=models.SET_NULL, null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    meeting_link = models.URLField(null=True, blank=True)
    place = models.CharField(max_length=255, null=True, blank=True)
    notes = models.TextField(null=True, blank=True)
    # demo_type: online/physical/hybrid (kept for clarity)
    demo_type = models.CharField(max_length=20, choices=[('online','Online'),('physical','Physical'),('hybrid','Hybrid')], default='online')
    # demo_status: scheduled/completed/missed/cancelled
    demo_status = models.CharField(max_length=20, choices=[('scheduled','Scheduled'),('completed','Completed'),('missed','Missed'),('cancelled','Cancelled')], default='scheduled')
    date = models.DateField()
    time = models.TimeField()

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'demo_schedules'
        verbose_name = 'Demo Schedule'
        verbose_name_plural = 'Demo Schedules'
        indexes = [
            models.Index(fields=['lead']),
            models.Index(fields=['assigned_staff']),
            models.Index(fields=['date']),
        ]

    def __str__(self):
        return f"Demo for {self.lead} on {self.date}"


class Onboarding(models.Model):
    """
    Onboarding process for schools
    """
    STATUS_CHOICES = [
        ('inprogress', 'In Progress'),
        ('completed', 'Completed'),
        ('onhold', 'On Hold'),
    ]

    ONBOARDING_TYPE_CHOICES = [
        ('online', 'Online'),
        ('physical', 'Physical'),
        ('hybrid', 'Hybrid'),
    ]

    school = models.OneToOneField('schools.School', on_delete=models.CASCADE)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='inprogress')
    onboarding_manager = models.ForeignKey('authentication.User', on_delete=models.SET_NULL, null=True, blank=True)
    startdate = models.DateField()
    expected_go_live_date = models.DateField()
    actual_go_live_date = models.DateField(null=True, blank=True)
    onboarding_type = models.CharField(max_length=20, choices=ONBOARDING_TYPE_CHOICES)
    percentage = models.IntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'onboardings'
        verbose_name = 'Onboarding'
        verbose_name_plural = 'Onboardings'
        indexes = [
            models.Index(fields=['school']),
            models.Index(fields=['status']),
            models.Index(fields=['onboarding_manager']),
        ]

    def __str__(self):
        return f"Onboarding for {self.school.name} - {self.status}"


class Logs(models.Model):
    """
    Logs for lead activities
    """
    LOG_TYPE_CHOICES = [
        ('lead_created', 'Lead Created'),
        ('lead_assigned', 'Lead Assigned'),
        ('demo_scheduled', 'Demo Scheduled'),
        ('lead_converted', 'Lead Converted'),
        ('onboarding_started', 'Onboarding Started'),
        ('onboarding_completed', 'Onboarding Completed'),
        ('school_live', 'School Live'),
    ]

    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, null=True, blank=True, related_name='logs')
    user = models.ForeignKey('authentication.User', on_delete=models.CASCADE, null=True, blank=True)
    log_type = models.CharField(max_length=20, choices=LOG_TYPE_CHOICES)
    description = models.TextField()
    metadata = models.JSONField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'logs'
        verbose_name = 'Log'
        verbose_name_plural = 'Logs'
        indexes = [
            models.Index(fields=['lead']),
            models.Index(fields=['user']),
            models.Index(fields=['log_type']),
        ]

    def __str__(self):
        return f"{self.log_type} - {self.description[:50]}"
