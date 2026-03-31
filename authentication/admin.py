"""
Django Admin configuration for SSO models
"""

from django.contrib import admin
from schools.models import School, Student, UsageLog
from .models import User, PasswordResetToken, EmailVerificationToken, Plan, PlanFeature, Subscription, CreditTop, PasswordResetCode


# ============================================================================
# SCHOOLS
# ============================================================================

@admin.register(School)
class SchoolAdmin(admin.ModelAdmin):
    list_display = ('name', 'school_email', 'student_count', 'is_active', 'created_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('name', 'school_email')
    readonly_fields = ('id', 'created_at', 'updated_at', 'student_count')
    fieldsets = (
        ('Basic Info', {
            'fields': ('id', 'name', 'school_email')
        }),
        ('Limits', {
            'fields': ('max_students',)
        }),
        ('Status', {
            'fields': ('is_active',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def get_plan_display(self, obj):
        return obj.subscription_plan.get_name_display()
    get_plan_display.short_description = 'Plan'


# ============================================================================
# STUDENTS
# ============================================================================

@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ('get_full_name', 'school_email', 'school', 'student_code', 'is_active', 'last_login_at')
    list_filter = ('school', 'is_active', 'created_at')
    search_fields = ('first_name', 'last_name', 'school_email', 'student_code')
    readonly_fields = ('id', 'created_at', 'updated_at', 'last_login_at')
    fieldsets = (
        ('Personal Info', {
            'fields': ('id', 'first_name', 'last_name', 'school_email')
        }),
        ('School & Identity', {
            'fields': ('school', 'student_code')
        }),
        ('Status', {
            'fields': ('is_active',)
        }),
        ('Activity', {
            'fields': ('last_login_at', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def get_full_name(self, obj):
        return obj.get_full_name()
    get_full_name.short_description = 'Name'


# ============================================================================
# USAGE LOGS
# ============================================================================

@admin.register(UsageLog)
class UsageLogAdmin(admin.ModelAdmin):
    list_display = ('student', 'school', 'tool', 'request_count', 'created_at')
    list_filter = ('school', 'tool', 'created_at')
    search_fields = ('student__first_name', 'student__last_name', 'school__name', 'tool')
    readonly_fields = ('id', 'created_at')
    fieldsets = (
        ('Request Info', {
            'fields': ('id', 'student', 'school', 'tool', 'request_count')
        }),
        ('Timestamp', {
            'fields': ('created_at',)
        }),
    )
    
    def has_add_permission(self, request):
        # UsageLog should only be created programmatically
        return False
    
    def has_delete_permission(self, request, obj=None):
        # Prevent deletion of usage logs
        return False


# ============================================================================
# LEGACY USER MODELS
# ============================================================================

@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ('username', 'email', 'user_type', 'organisation', 'role', 'subscription_plan', 'is_active', 'is_verified', 'trial', 'created_at')
    list_filter = ('user_type', 'organisation', 'role', 'is_active', 'is_verified', 'trial', 'subscription_plan')
    search_fields = ('username', 'email', 'first_name', 'last_name')
    fieldsets = (
        ('Account Info', {
            'fields': ('username', 'email', 'password')
        }),
        ('Personal Info', {
            'fields': ('first_name', 'last_name', 'phone_number', 'date_of_birth')
        }),
        ('User Type & Organisation', {
            'fields': ('user_type', 'organisation')
        }),
        ('Subscription', {
            'fields': ('subscription_plan', 'trial')
        }),
        ('Role & Status', {
            'fields': ('role', 'is_active', 'is_verified')
        }),
        ('Profile', {
            'fields': ('bio', 'profile_picture', 'class_level', 'school', 'subject_specialization', 'years_of_experience')
        }),
        ('Activity', {
            'fields': ('created_at', 'updated_at', 'last_login_at'),
            'classes': ('collapse',)
        }),
    )
    readonly_fields = ('created_at', 'updated_at', 'last_login_at')


@admin.register(PasswordResetToken)
class PasswordResetTokenAdmin(admin.ModelAdmin):
    list_display = ('user', 'created_at', 'expires_at', 'used')
    list_filter = ('used', 'created_at')
    search_fields = ('user__username', 'user__email')
    readonly_fields = ('token', 'created_at')


@admin.register(PasswordResetCode)
class PasswordResetCodeAdmin(admin.ModelAdmin):
    list_display = ('user', 'code', 'created_at', 'expires_at', 'used')
    list_filter = ('used', 'created_at')
    search_fields = ('user__username', 'user__email', 'code')
    readonly_fields = ('created_at',)


@admin.register(EmailVerificationToken)
class EmailVerificationTokenAdmin(admin.ModelAdmin):
    list_display = ('user', 'created_at', 'expires_at', 'used')
    list_filter = ('used', 'created_at')
    search_fields = ('user__username', 'user__email')
    readonly_fields = ('token', 'created_at')


# ============================================================================
# PLANS
# ============================================================================

class PlanFeatureInline(admin.TabularInline):
    """Inline admin for plan features"""
    model = PlanFeature
    extra = 1
    fields = ('text', 'included', 'highlight', 'order')
    ordering = ('order',)


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ('name', 'plan_id', 'use_type', 'monthly_price', 'annual_price', 'is_popular', 'is_active', 'created_at')
    list_filter = ('use_type', 'is_popular', 'is_active', 'created_at')
    search_fields = ('name', 'plan_id', 'description')
    readonly_fields = ('created_at', 'updated_at')
    inlines = [PlanFeatureInline]
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('plan_id', 'name', 'description', 'use_type')
        }),
        ('Pricing', {
            'fields': ('monthly_price', 'annual_price', 'annual_billed', 'total_credits', 'max_users')
        }),
        ('Display Options', {
            'fields': ('theme', 'badge', 'cta', 'is_popular', 'is_active')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(PlanFeature)
class PlanFeatureAdmin(admin.ModelAdmin):
    list_display = ('plan', 'text', 'included', 'highlight', 'order')
    list_filter = ('plan', 'included', 'highlight')
    search_fields = ('plan__name', 'text')
    ordering = ('plan', 'order')


# ============================================================================
# SUBSCRIPTIONS
# ============================================================================

@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ('get_owner', 'plan', 'status', 'billing_start_date', 'billing_end_date', 'remaining_credits')
    list_filter = ('status', 'plan', 'billing_start_date')
    search_fields = ('user__username', 'user__email', 'organisation__name')
    readonly_fields = ('id', 'created_at', 'updated_at')

    def get_owner(self, obj):
        return obj.user.username if obj.user else obj.organisation.name
    get_owner.short_description = 'Owner'


# ============================================================================
# CREDIT TOPS
# ============================================================================

@admin.register(CreditTop)
class CreditTopAdmin(admin.ModelAdmin):
    list_display = ('organisation', 'subscription', 'credit_add', 'purchase_date', 'expiry_date')
    list_filter = ('purchase_date', 'expiry_date')
    search_fields = ('organisation__name', 'subscription__plan__name')
    readonly_fields = ('created_at', 'updated_at')
