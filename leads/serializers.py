from rest_framework import serializers
from .models import Lead, Notification, DemoSchedule, Onboarding, Logs


class LeadSerializer(serializers.ModelSerializer):
    """Serializer for Lead model"""
    assigned_staff_name = serializers.CharField(source='assigned_staff.get_full_name', read_only=True)
    last_activity = serializers.SerializerMethodField()
    
    class Meta:
        model = Lead
        fields = [
            'id', 'firstname', 'secondname', 'phonenumber', 'workemail', 'jobtitle',
            'institution', 'categories', 'institution_name', 'size_of_institution',
            'country', 'city', 'question_on_preference', 'assigned_staff', 
            'assigned_staff_name', 'status', 'created_at', 'updated_at', 'last_activity'
        ]
        read_only_fields = ['created_at', 'updated_at', 'last_activity']

    def get_last_activity(self, obj):
        # Use latest related log as last activity if present, otherwise use updated_at
        last_log = obj.logs.order_by('-created_at').first()
        if last_log:
            return last_log.created_at
        return obj.updated_at


class NotificationSerializer(serializers.ModelSerializer):
    """Serializer for Notification model"""
    user_name = serializers.CharField(source='user.get_full_name', read_only=True)
    
    class Meta:
        model = Notification
        fields = [
            'id', 'user', 'user_name', 'notification_type', 'title', 'body', 'is_read', 'priority', 'created_at'
        ]
        read_only_fields = ['created_at']


class DemoScheduleSerializer(serializers.ModelSerializer):
    """Serializer for DemoSchedule model"""
    lead_name = serializers.CharField(source='lead.institution_name', read_only=True)
    assigned_staff_name = serializers.CharField(source='assigned_staff.get_full_name', read_only=True)
    scheduledAt = serializers.SerializerMethodField()
    
    class Meta:
        model = DemoSchedule
        fields = [
            'id', 'lead', 'lead_name', 'assigned_staff', 'assigned_staff_name',
            'date', 'time', 'meeting_link', 'place', 'notes', 'demo_type', 'demo_status',
            'created_at', 'updated_at', 'scheduledAt'
        ]
        read_only_fields = ['created_at', 'updated_at', 'scheduledAt']

    def get_scheduledAt(self, obj):
        from django.utils import timezone
        scheduled = timezone.datetime.combine(obj.date, obj.time)
        if timezone.is_naive(scheduled):
            scheduled = timezone.make_aware(scheduled)
        return scheduled.isoformat()


class OnboardingSerializer(serializers.ModelSerializer):
    """Serializer for Onboarding model"""
    school_name = serializers.CharField(source='school.name', read_only=True)
    onboarding_manager_name = serializers.CharField(source='onboarding_manager.get_full_name', read_only=True)
    
    class Meta:
        model = Onboarding
        fields = [
            'id', 'school', 'school_name', 'onboarding_manager', 'onboarding_manager_name',
            'startdate', 'expected_go_live_date', 'actual_go_live_date', 'onboarding_type',
            'percentage', 'status', 'notes', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']


class LogsSerializer(serializers.ModelSerializer):
    """Serializer for Logs model"""
    lead_institution = serializers.CharField(source='lead.institution_name', read_only=True)
    user_name = serializers.CharField(source='user.get_full_name', read_only=True)
    
    class Meta:
        model = Logs
        fields = [
            'id', 'lead', 'lead_institution', 'user', 'user_name', 'log_type',
            'description', 'metadata', 'created_at'
        ]
        read_only_fields = ['created_at']