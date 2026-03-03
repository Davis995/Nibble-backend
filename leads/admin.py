from django.contrib import admin
from .models import Lead, Notification, DemoSchedule, Onboarding, Logs

# Register your models here.

@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = ('firstname', 'secondname', 'workemail', 'institution_name', 'status', 'assigned_staff', 'created_at')
    list_filter = ('status', 'categories', 'country', 'assigned_staff')
    search_fields = ('firstname', 'secondname', 'workemail', 'institution_name')
    readonly_fields = ('id', 'created_at', 'updated_at')


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('user', 'title', 'is_read', 'created_at')
    list_filter = ('is_read', 'created_at')
    search_fields = ('user__username', 'title')
    readonly_fields = ('created_at',)


@admin.register(DemoSchedule)
class DemoScheduleAdmin(admin.ModelAdmin):
    list_display = ('lead', 'assigned_staff', 'status', 'date', 'time')
    list_filter = ('status', 'date')
    search_fields = ('lead__firstname', 'lead__secondname', 'assigned_staff__username')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Onboarding)
class OnboardingAdmin(admin.ModelAdmin):
    list_display = ('school', 'status', 'onboarding_manager', 'startdate', 'expected_go_live_date', 'percentage')
    list_filter = ('status', 'onboarding_type')
    search_fields = ('school__name', 'onboarding_manager__username')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Logs)
class LogsAdmin(admin.ModelAdmin):
    list_display = ('lead', 'user', 'log_type', 'created_at')
    list_filter = ('log_type', 'created_at')
    search_fields = ('lead__firstname', 'user__username', 'description')
    readonly_fields = ('created_at',)
