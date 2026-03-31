"""
School and Student Serializers
"""
from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.conf import settings

from .models import School, Student, Staff, Activity
from authentication.models import Subscription

User = get_user_model()


class InvitationSerializer(serializers.Serializer):
    """Serializer used by school admins to create an invitation."""
    email = serializers.EmailField()
    role = serializers.ChoiceField(choices=[('teacher', 'Teacher'), ('school_admin', 'School Admin')], default='teacher')


class AcceptInvitationSerializer(serializers.Serializer):
    """Serializer for accepting an invitation link from email.

    Frontend will supply `code` (from the URL), then the user fills password
    and name fields. Optionally frontend can send `school_id` and `role` in
    a second step which will be validated against the invitation.
    """
    code = serializers.CharField()
    password = serializers.CharField(write_only=True)
    confirm_password = serializers.CharField(write_only=True)
    first_name = serializers.CharField(required=False, allow_blank=True)
    last_name = serializers.CharField(required=False, allow_blank=True)
    school_id = serializers.UUIDField(required=False)
    role = serializers.ChoiceField(choices=[('teacher', 'Teacher'), ('school_admin', 'School Admin')], required=False)

    def validate(self, data):
        if data.get('password') != data.get('confirm_password'):
            raise serializers.ValidationError({'password': 'Passwords do not match'})
        return data


# ============================================================================
# SUBSCRIPTION SERIALIZER
# ============================================================================

class SubscriptionSerializer(serializers.ModelSerializer):
    """
    Serialize subscription information for schools
    """
    plan_name = serializers.CharField(source='plan.name', read_only=True)
    plan_description = serializers.CharField(source='plan.description', read_only=True)
    is_active = serializers.SerializerMethodField()

    class Meta:
        model = Subscription
        fields = [
            'id', 'plan_name', 'plan_description', 'status', 'is_active',
            'max_users', 'start_credits', 'remaining_credits',
            'billing_start_date', 'billing_end_date',
            'created_at', 'updated_at'
        ]
        read_only_fields = fields

    def get_is_active(self, obj):
        return obj.status == 'active'


# ============================================================================
# SCHOOL SERIALIZERS
# ============================================================================

class SchoolSerializer(serializers.ModelSerializer):
    """
    Serialize school information with subscription details
    """
    student_count = serializers.SerializerMethodField()
    subscription_info = serializers.SerializerMethodField()
    is_subscription_active = serializers.SerializerMethodField()
    plan_name = serializers.SerializerMethodField()
    plan_type = serializers.SerializerMethodField()

    # Admin user fields for creation
    admin_username = serializers.CharField(write_only=True, required=True)
    admin_email = serializers.EmailField(write_only=True, required=True)
    admin_password = serializers.CharField(write_only=True, required=True)
    admin_first_name = serializers.CharField(write_only=True, required=False, default='')
    admin_last_name = serializers.CharField(write_only=True, required=False, default='')

    class Meta:
        model = School
        fields = [
            'id', 'name', 'school_email',
            'max_students', 'student_count', 'teacher_count', 'is_active',
            'subscription_info', 'is_subscription_active', 'plan_name', 'plan_type',
            'assigned_staff', 'assigned_staff_name', 'contact_phone',
            'created_at', 'updated_at',
            'admin_username', 'admin_email', 'admin_password', 'admin_first_name', 'admin_last_name'
        ]
        read_only_fields = [
            'id', 'created_at', 'updated_at', 'subscription_info', 'is_subscription_active', 'plan_name', 'plan_type'
        ]

    assigned_staff_name = serializers.CharField(source='assigned_staff.get_full_name', read_only=True)

    def get_student_count(self, obj):
        return obj.student_count()

    def get_is_subscription_active(self, obj):
        """Return if school has an active subscription"""
        return obj.is_subscription_active()

    def get_plan_name(self, obj):
        """Return the plan name from subscription"""
        if obj.subscription and obj.subscription.plan:
            return obj.subscription.plan.name
        return None

    def get_plan_type(self, obj):
        """Return the plan use_type from subscription"""
        if obj.subscription and obj.subscription.plan:
            return obj.subscription.plan.use_type
        return None

    def get_subscription_info(self, obj):
        """Return subscription details for the school"""
        from authentication.models import Subscription
        # Try OneToOne field first
        if obj.subscription:
            return SubscriptionSerializer(obj.subscription).data
        # Try reverse relationship
        sub = Subscription.objects.filter(organisation=obj, status='active').first()
        if sub:
            return SubscriptionSerializer(sub).data
        return None

    def create(self, validated_data):
        # Extract admin data
        admin_username = validated_data.pop('admin_username')
        admin_email = validated_data.pop('admin_email')
        admin_password = validated_data.pop('admin_password')
        admin_first_name = validated_data.pop('admin_first_name', '')
        admin_last_name = validated_data.pop('admin_last_name', '')

        # Create the school first
        school = super().create(validated_data)

        # Create the admin user
        admin_user = User.objects.create_user(
            username=admin_username,
            email=admin_email,
            password=admin_password,
            first_name=admin_first_name,
            last_name=admin_last_name,
            user_type='enterprise',
            organisation=school,
            role='school_admin'
        )

        # Link the admin to the school
        school.admin_user = admin_user
        school.save()

        # Send notification email to school email
        subject = f"School Created: {school.name}"
        message = f"""
        Dear {school.name} Team,

        Your school account has been successfully created on our platform.

        School Details:
        - Name: {school.name}
        - Email: {school.school_email}
        - Admin: {admin_user.get_full_name()} ({admin_user.email})
        - Max Students: {school.max_students}

        You can now start inviting teachers and students to your school.

        Best regards,
        NibbleAI Team
        """
        try:
            send_mail(
                subject,
                message,
                settings.DEFAULT_FROM_EMAIL,
                [school.school_email],
                fail_silently=False,
            )
        except Exception as e:
            # Log the error but don't fail the creation
            print(f"Failed to send school creation email: {e}")

        return school


# ============================================================================
# STUDENT SERIALIZERS
# ============================================================================

class StudentSerializer(serializers.ModelSerializer):
    """
    Serialize student information
    """
    full_name = serializers.SerializerMethodField()
    school_name = serializers.CharField(source='school.name', read_only=True)
    school = serializers.PrimaryKeyRelatedField(
        queryset=School.objects.all(),
        required=False,
        allow_null=False
    )

    class Meta:
        model = Student
        fields = [
            'id', 'school', 'school_name', 'first_name', 'last_name',
            'full_name', 'school_email', 'student_code', 'is_active',
            'created_at', 'updated_at', 'last_login_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'last_login_at', 'school_email', 'is_active']

    def get_full_name(self, obj):
        return obj.get_full_name()

    def validate_school(self, value):
        """Ensure school is provided and exists"""
        if not value:
            raise serializers.ValidationError("School is required to create a student.")
        return value

    def create(self, validated_data):
        import uuid
        from django.contrib.auth import get_user_model
        from django.db import IntegrityError
        
        User = get_user_model()
        
        # Get school from validated_data or context
        school_obj = validated_data.get('school')
        if not school_obj:
            # Try context (passed from view)
            school_obj = self.context.get('school') if hasattr(self, 'context') else None
        
        if not school_obj:
            raise serializers.ValidationError({'school': 'School ID is required'})
        
        # Ensure school_obj is a model instance
        from .models import School as SchoolModel
        if not isinstance(school_obj, SchoolModel):
            try:
                school_obj = SchoolModel.objects.get(id=school_obj)
            except SchoolModel.DoesNotExist:
                raise serializers.ValidationError({'school': 'School not found'})
        
        # Set school in validated_data for the parent create()
        validated_data['school'] = school_obj

        # Generate a unique school-scoped email for the student since
        # `school_email` must be unique per school (constraint on students table).
        # Format: firstname.lastname.studentcode@schooldomain
        student_code = validated_data.get('student_code') or uuid.uuid4().hex[:5].upper()
        first_name = (validated_data.get('first_name') or '').strip().lower() or 'student'
        last_name = (validated_data.get('last_name') or '').strip().lower() or 'user'
        domain = school_obj.school_email.split('@')[1] if '@' in school_obj.school_email else 'school.local'

        # sanitize parts to avoid spaces
        local_part = f"{first_name}.{last_name}.{student_code}".replace(' ', '')
        student_email = f"{local_part}@{domain}"

        validated_data['student_code'] = student_code
        validated_data['school_email'] = student_email

        # Create the student first
        student = super().create(validated_data)
        
        # Generate username: first_name + last_name + 3 uuid chars + @ + domain from school_email
        domain = student.school_email.split('@')[1] if '@' in student.school_email else 'school.com'
        uuid_chars = uuid.uuid4().hex[:3].upper()
        username = f"{student.first_name}{student.last_name}{uuid_chars}@{domain}"
        
        # Ensure unique username
        max_attempts = 10
        attempt = 0
        while User.objects.filter(username=username).exists() and attempt < max_attempts:
            uuid_chars = uuid.uuid4().hex[:3].upper()
            username = f"{student.first_name}{student.last_name}{uuid_chars}@{domain}"
            attempt += 1
        
        # Create user account
        try:
            user = User.objects.create_user(
                username=username,
                email=student.school_email,
                password=student.student_code,  # Use student_code as password
                first_name=student.first_name,
                last_name=student.last_name,
                user_type='enterprise',  # Students are individual
                organisation=student.school,
                role='student'
            )
        except IntegrityError as e:
            # If user creation fails, clean up the student record
            student.delete()
            raise serializers.ValidationError(f"Failed to create user account: {str(e)}")
        except Exception as e:
            # If user creation fails, clean up the student record
            student.delete()
            raise serializers.ValidationError(f"An error occurred while creating user account: {str(e)}")
        
        return student


# ============================================================================
# SCHOOL DETAILS RESPONSE SERIALIZERS
# ============================================================================

class SchoolDetailsResponseSerializer(serializers.Serializer):
    """Serializer for GET /api/schools/:id/details response"""
    id = serializers.CharField()
    name = serializers.CharField()
    planType = serializers.CharField()
    subscriptionStatus = serializers.CharField()
    onboardingStatus = serializers.CharField()
    onboardingProgress = serializers.IntegerField()


class OnboardingStepsSerializer(serializers.Serializer):
    """Serializer for onboarding steps"""
    initialSetup = serializers.BooleanField()
    staffTraining = serializers.BooleanField()
    dataMigration = serializers.BooleanField()
    goLive = serializers.BooleanField()


class SchoolStatsSerializer(serializers.Serializer):
    """Serializer for school statistics"""
    totalUsers = serializers.IntegerField()
    activeUsers = serializers.IntegerField()


class SchoolDetailsFullResponseSerializer(serializers.Serializer):
    """Full response serializer for GET /api/schools/:id/details"""
    school = SchoolDetailsResponseSerializer()
    onboardingSteps = OnboardingStepsSerializer()
    stats = SchoolStatsSerializer()


class OnboardingUpdateResponseSerializer(serializers.Serializer):
    """Serializer for PATCH /api/schools/:id/onboarding response"""
    id = serializers.CharField()
    onboardingProgress = serializers.IntegerField()
    completedSteps = OnboardingStepsSerializer()


# ============================================================================
# STAFF CRUD SERIALIZER
# ============================================================================

class StaffCRUDSerializer(serializers.ModelSerializer):
    """
    Serialize staff information matching frontend Teacher shape:
    id, name, email, subject, status
    """
    name = serializers.CharField(required=False)
    email = serializers.EmailField(source='school_email')
    status = serializers.ChoiceField(choices=['Active', 'Inactive'], required=False)

    class Meta:
        model = Staff
        fields = ['id', 'name', 'email', 'subject', 'status', 'role']
        read_only_fields = ['id']

    def to_representation(self, instance):
        return {
            'id': instance.id,
            'name': f"{instance.first_name} {instance.last_name}".strip(),
            'email': instance.school_email,
            'subject': instance.subject,
            'status': 'Active' if instance.is_active else 'Inactive',
            'role': instance.role
        }

    def to_internal_value(self, data):
        ret = {}
        if 'name' in data:
            parts = str(data['name']).split(' ', 1)
            ret['first_name'] = parts[0]
            ret['last_name'] = parts[1] if len(parts) > 1 else ''
        if 'email' in data:
            ret['school_email'] = data['email']
        if 'subject' in data:
            ret['subject'] = data['subject']
        if 'status' in data:
            ret['is_active'] = (str(data['status']).lower() == 'active')
        if 'role' in data:
            ret['role'] = data['role']
        return ret

    def create(self, validated_data):
        from django.db import IntegrityError
        
        school_obj = self.context.get('school')
        if not school_obj:
            raise serializers.ValidationError({'school': 'School is required'})
            
        validated_data['school'] = school_obj
        
        if 'first_name' not in validated_data:
            validated_data['first_name'] = 'Staff'
        if 'last_name' not in validated_data:
            validated_data['last_name'] = 'Member'

        email = validated_data.get('school_email')
        try:
            staff, created = Staff.objects.update_or_create(
                school=school_obj,
                school_email=email,
                defaults=validated_data
            )
            return staff
        except IntegrityError:
            raise serializers.ValidationError({'email': 'Staff with this email already exists in this school.'})


# ============================================================================
# ACTIVITY SERIALIZER
# ============================================================================

class ActivitySerializer(serializers.ModelSerializer):
    """
    Serialize activity information matching frontend shape:
    id, user, role, action, tool, time, date
    """
    user = serializers.CharField(source='user_name')

    class Meta:
        model = Activity
        fields = ['id', 'user', 'role', 'action', 'tool', 'time', 'date']
        
    def create(self, validated_data):
        school_obj = self.context.get('school')
        if not school_obj:
            raise serializers.ValidationError({'school': 'School is required'})
            
        validated_data['school'] = school_obj
        return super().create(validated_data)
