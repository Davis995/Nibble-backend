"""
SSO Authentication Serializers
"""
from rest_framework import serializers
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.utils import timezone
from .models import User, Plan, PlanFeature
from schools.serializers import StudentSerializer, SchoolSerializer

from schools.models import *
# ============================================================================
# SSO LOGIN SERIALIZER
# ============================================================================

class StudentSSOLoginSerializer(serializers.Serializer):
    """
    Serializer for student SSO login
    Validates school_email and student_code
    Returns JWT token
    """
    school_email = serializers.EmailField()
    student_code = serializers.CharField(max_length=10, min_length=3)
    
    def validate_school_email(self, value):
        """Validate that school exists with this email"""
        if not School.objects.filter(school_email=value.lower(), is_active=True).exists():
            raise serializers.ValidationError("School not found or inactive.")
        return value.lower()
    
    def validate(self, attrs):
        """
        Validate the complete login request
        """
        school_email = attrs.get('school_email')
        student_code = attrs.get('student_code')
        
        # Get school
        try:
            school = School.objects.get(school_email=school_email, is_active=True)
        except School.DoesNotExist:
            raise serializers.ValidationError("School not found or inactive.")
        
        # Check if school subscription is active
        if not school.is_subscription_active():
            # Debug: Check subscription status
            from authentication.models import Subscription
            subs = Subscription.objects.filter(organisation=school)
            sub_details = ', '.join([f"status={s.status}" for s in subs])
            error_msg = "School subscription is not active."
            if subs.exists():
                error_msg += f" (Found subscriptions: {sub_details})"
            else:
                error_msg += " (No subscriptions found)"
            raise serializers.ValidationError(error_msg)
        
        # Get student in that school
        try:
            student = Student.objects.get(
                school=school,
                student_code=student_code,
                is_active=True
            )
        except Student.DoesNotExist:
            raise serializers.ValidationError("Invalid student code or student is inactive.")
        
        # Store for use in create method
        attrs['school'] = school
        attrs['student'] = student
        
        return attrs


class SSOTokenResponseSerializer(serializers.Serializer):
    """
    Serializer for SSO login response
    """
    token = serializers.CharField()
    student = StudentSerializer()
    school = SchoolSerializer()
    plan_name = serializers.CharField()


# ============================================================================
# LEGACY USER SERIALIZERS (Kept for backward compatibility)
# ============================================================================

class UserRegistrationSerializer(serializers.ModelSerializer):
    """
    Serializer for user registration
    """
    password = serializers.CharField(
        write_only=True, 
        required=True, 
        validators=[validate_password],
        style={'input_type': 'password'}
    )
    password_confirm = serializers.CharField(
        write_only=True, 
        required=True,
        style={'input_type': 'password'}
    )
    
    class Meta:
        model = User
        fields = [
            'email', 'password', 'password_confirm',
            'first_name', 'last_name', 'role', 'phone_number'
        ]
        extra_kwargs = {
            'first_name': {'required': True},
            'last_name': {'required': True},
            'email': {'required': True},
        }
    
    def validate(self, attrs):
        """Validate that passwords match"""
        if attrs['password'] != attrs['password_confirm']:
            raise serializers.ValidationError({
                "password": "Password fields didn't match."
            })
        return attrs
    
    def validate_email(self, value):
        """Check if email is already in use"""
        if User.objects.filter(email=value.lower()).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value.lower()
    
    def validate_role(self, value):
        """Validate role selection"""
        # Only allow student and teacher registration via API
        # Admin should be created via Django admin or management command
        if value not in ['student', 'teacher']:
            raise serializers.ValidationError("Invalid role. Only 'student' and 'teacher' are allowed.")
        return value
    
    def create(self, validated_data):
        """Create new user with hashed password"""
        # Remove password_confirm from validated data
        validated_data.pop('password_confirm')
        
        # Extract password
        password = validated_data.pop('password')
        
        # Set username to email since USERNAME_FIELD is email
        validated_data['username'] = validated_data['email']
        
        # Create user
        user = User.objects.create(**validated_data)
        user.set_password(password)
        user.save()
        
        return user


class UserLoginSerializer(serializers.Serializer):
    """
    Serializer for user login with email and password
    """
    email = serializers.EmailField(required=True)
    password = serializers.CharField(
        required=True,
        write_only=True,
        style={'input_type': 'password'}
    )
    
    def validate(self, attrs):
        email = attrs.get('email')
        password = attrs.get('password')
        
        if email and password:
            user = authenticate(
                request=self.context.get('request'),
                username=email,  # Since USERNAME_FIELD is email
                password=password
            )
            
            if not user:
                raise serializers.ValidationError(
                    'Unable to log in with provided credentials.',
                    code='authorization'
                )
            
            if not user.is_active:
                raise serializers.ValidationError(
                    'User account is disabled.',
                    code='authorization'
                )
            
            attrs['user'] = user
            return attrs
        else:
            raise serializers.ValidationError(
                'Must include "username" and "password".',
                code='authorization'
            )




class ChangePasswordSerializer(serializers.Serializer):
    """
    Serializer for password change
    """
    old_password = serializers.CharField(required=True, write_only=True)
    new_password = serializers.CharField(required=True, write_only=True, validators=[validate_password])
    new_password_confirm = serializers.CharField(required=True, write_only=True)
    
    def validate(self, attrs):
        if attrs['new_password'] != attrs['new_password_confirm']:
            raise serializers.ValidationError({
                "new_password": "Password fields didn't match."
            })
        return attrs
    
    def validate_old_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError("Old password is incorrect.")
        return value


class StudentSchoolLoginSerializer(serializers.Serializer):
    """
    Serializer for student login using school's email address and student code
    """
    school_email = serializers.EmailField(
        required=True,
        help_text="School's email address"
    )
    student_code = serializers.CharField(
        required=True,
        min_length=3,
        max_length=10,
        help_text="Student code (3-10 characters)"
    )

    def validate(self, attrs):
        school_email = attrs.get('school_email')
        student_code = attrs.get('student_code')

        if school_email and student_code:
            try:
                # First find the school by its email
                school = School.objects.get(
                    school_email=school_email.lower(),
                    is_active=True
                )
                
                # Then find the student within that school by student code
                student = Student.objects.select_related('school').get(
                    school=school,
                    student_code=student_code.upper(),  # Codes are stored uppercase
                    is_active=True
                )

                # Check if school subscription is active
                if not school.is_subscription_active():
                    raise serializers.ValidationError("School subscription is not active.")

                attrs['student'] = student
                attrs['school'] = school
                return attrs

            except School.DoesNotExist:
                raise serializers.ValidationError("School not found or inactive.")
            except Student.DoesNotExist:
                raise serializers.ValidationError("Invalid student code for this school.")
        else:
            raise serializers.ValidationError("Must include school_email and student_code.")


class AdminUserSerializer(serializers.ModelSerializer):
    """
    Serializer for admin user management (create/update users)
    """
    password = serializers.CharField(write_only=True, required=False, validators=[validate_password])
    full_name = serializers.CharField(source='get_full_name', read_only=True)
    effective_role = serializers.SerializerMethodField()
    
    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name', 'full_name',
            'user_type', 'organisation', 'role', 'effective_role', 'phone_number', 'date_of_birth', 'bio', 'profile_picture',
            'password', 'is_verified', 'trial', 
            'is_active', 'is_staff', 'is_superuser',
            'created_at', 'last_login_at'
        ]
        read_only_fields = ['id', 'created_at', 'last_login_at', 'effective_role']
        extra_kwargs = {
            'password': {'write_only': True}
        }
    
    def get_effective_role(self, obj):
        """Get the effective role, considering superuser status"""
        return 'superuser' if obj.is_superuser else obj.role
    
    def create(self, validated_data):
        """Create user with password hashing"""
        password = validated_data.pop('password', None)
        user = User(**validated_data)
        if password:
            user.set_password(password)
        user.save()
        return user
    
    def update(self, instance, validated_data):
        """Update user with password handling"""
        password = validated_data.pop('password', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if password:
            instance.set_password(password)
        instance.save()
        return instance


class InvitationCreateSerializer(serializers.Serializer):
    """Serializer for creating an invitation"""
    email = serializers.EmailField(required=True)
    role = serializers.ChoiceField(choices=[('sale_manager','sale_manager'),('sales_assistant','sales_assistant'),('school_admin','school_admin'),('operator','operator')], required=True)

    def validate_email(self, value):
        if User.objects.filter(email=value.lower()).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value.lower()


class InvitationAcceptSerializer(serializers.Serializer):
    """Serializer for accepting an invitation and creating the user"""
    token = serializers.CharField(required=True)
    password = serializers.CharField(write_only=True, required=True, validators=[validate_password])
    password_confirm = serializers.CharField(write_only=True, required=True)
    first_name = serializers.CharField(required=False, allow_blank=True)
    last_name = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        if attrs.get('password') != attrs.get('password_confirm'):
            raise serializers.ValidationError({"password": "Password fields didn't match."})
        return attrs


class UserProfileSerializer(serializers.ModelSerializer):
    """
    Serializer for user profile
    """
    full_name = serializers.CharField(source='get_full_name', read_only=True)
    effective_role = serializers.SerializerMethodField()
    
    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name', 'full_name',
            'user_type', 'organisation', 'role', 'effective_role', 'phone_number', 'date_of_birth', 'bio', 'profile_picture',
            'password', 'is_verified', 'trial', 
            'is_active', 'is_staff', 'is_superuser',
            'created_at', 'last_login_at'
        ]
        read_only_fields = ['id', 'created_at', 'last_login_at', 'effective_role']
        extra_kwargs = {
            'password': {'write_only': True}
        }
    
    def get_effective_role(self, obj):
        """Get the effective role, considering superuser status"""
        return 'superuser' if obj.is_superuser else obj.role


class UserProfileUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer for updating user profile
    """
    onboarding = serializers.BooleanField(source='is_onboarded', required=False)
    
    class Meta:
        model = User
        fields = [
            'first_name', 'last_name', 'phone_number', 'date_of_birth', 'bio', 'profile_picture', 'onboarding'
        ]


# ============================================================================
# ADMIN PLAN AND PLAN FEATURE SERIALIZERS
# ============================================================================

class PlanFeatureAdminSerializer(serializers.ModelSerializer):
    """
    Detailed admin serializer for plan features
    """
    class Meta:
        model = PlanFeature
        fields = ['id', 'text', 'included', 'highlight', 'order']

class PlanAdminSerializer(serializers.ModelSerializer):
    """
    Comprehensive admin serializer for plans
    Handles all administrative fields and nested feature management
    """
    features = PlanFeatureAdminSerializer(many=True, required=False)

    class Meta:
        model = Plan
        fields = [
            'id', 'plan_id', 'name', 'description', 'use_type', 'theme', 
            'currency', 'allowed_modals', 'total_credits', 'max_users', 
            'monthly_price', 'annual_price', 'annual_billed', 'badge', 
            'cta', 'is_popular', 'is_active', 'display_order', 'features', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def create(self, validated_data):
        features_data = validated_data.pop('features', [])
        plan = Plan.objects.create(**validated_data)
        
        for feature_data in features_data:
            PlanFeature.objects.create(plan=plan, **feature_data)
        
        return plan

    def update(self, instance, validated_data):
        features_data = validated_data.pop('features', None)
        
        # Update main plan fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        
        # If features provided, replace old ones (standard pattern for this UI)
        if features_data is not None:
            instance.features.all().delete()
            for feature_data in features_data:
                PlanFeature.objects.create(plan=instance, **feature_data)
        
        return instance


# ============================================================================
# PLAN AND PLAN FEATURE SERIALIZERS
# ============================================================================

class PlanFeatureSerializer(serializers.ModelSerializer):
    """
    Serializer for plan features
    """
    class Meta:
        model = PlanFeature
        fields = [
            'id', 'text', 'included', 'highlight', 'order', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']


class PlanListSerializer(serializers.ModelSerializer):
    """
    Serializer for listing plans with features
    """
    features = PlanFeatureSerializer(many=True, read_only=True)

    class Meta:
        model = Plan
        fields = [
            'id', 'plan_id', 'name', 'description', 'use_type', 'theme',
            'total_credits', 'max_users', 'monthly_price', 'annual_price',
            'annual_billed', 'badge', 'cta', 'is_popular', 'is_active', 'display_order', 'features'
        ]


class PlanDetailSerializer(serializers.ModelSerializer):
    """
    Serializer for plan details with all fields
    """
    features = PlanFeatureSerializer(many=True, read_only=True)

    class Meta:
        model = Plan
        fields = [
            'id', 'plan_id', 'name', 'description', 'use_type', 'theme',
            'total_credits', 'max_users', 'monthly_price', 'annual_price',
            'annual_billed', 'badge', 'cta', 'is_popular', 'is_active', 'display_order', 'features',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']


class PlanCreateUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating and updating plans
    Handles nested features creation/update
    """
    features = PlanFeatureSerializer(many=True, required=False)

    class Meta:
        model = Plan
        fields = [
            'plan_id', 'name', 'description', 'use_type', 'theme',
            'total_credits', 'max_users', 'monthly_price', 'annual_price',
            'annual_billed', 'badge', 'cta', 'is_popular', 'is_active', 'display_order', 'features'
        ]

    def create(self, validated_data):
        """Create a new plan with features"""
        features_data = validated_data.pop('features', [])
        plan = Plan.objects.create(**validated_data)
        
        # Create features for this plan
        for index, feature_data in enumerate(features_data):
            feature_data['order'] = index
            PlanFeature.objects.create(plan=plan, **feature_data)
        
        return plan

    def update(self, instance, validated_data):
        """Update an existing plan with features"""
        features_data = validated_data.pop('features', None)
        
        # Update plan fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        
        # Update features if provided
        if features_data is not None:
            instance.features.all().delete()
            for index, feature_data in enumerate(features_data):
                feature_data['order'] = index
                PlanFeature.objects.create(plan=instance, **feature_data)
        
        return instance

class PlanFeaturePublicSerializer(serializers.ModelSerializer):
    """
    Simple serializer for plan features (text, included, highlight)
    """
    class Meta:
        model = PlanFeature
        fields = ['text', 'included', 'highlight']

class PlanPublicSerializer(serializers.ModelSerializer):
    """
    Public serializer for plans with camelCase fields as requested
    """
    id = serializers.CharField(source='plan_id')
    useType = serializers.CharField(source='use_type')
    totalCredits = serializers.IntegerField(source='total_credits')
    maxUsers = serializers.IntegerField(source='max_users')
    monthlyPrice = serializers.FloatField(source='monthly_price')
    annualPrice = serializers.FloatField(source='annual_price')
    annualBilled = serializers.FloatField(source='annual_billed')
    popular = serializers.BooleanField(source='is_popular')
    displayOrder = serializers.IntegerField(source='display_order')
    features = PlanFeaturePublicSerializer(many=True, read_only=True)

    class Meta:
        model = Plan
        fields = [
            'id', 'name', 'description', 'useType', 'currency', 'totalCredits',
            'maxUsers', 'monthlyPrice', 'annualPrice', 'annualBilled', 'badge',
            'popular', 'theme', 'cta', 'displayOrder', 'features'
        ]

class CreditsUsageSerializer(serializers.Serializer):
    """
    Serializer for user credit usage information
    """
    subscription_id = serializers.CharField()
    plan_name = serializers.CharField()
    subscription_status = serializers.CharField()
    
    credits = serializers.DictField()
    billing = serializers.DictField()
    user = serializers.DictField()
    
    class Meta:
        fields = ['subscription_id', 'plan_name', 'subscription_status', 'credits', 'billing', 'user']

class PasswordResetRequestSerializer(serializers.Serializer):
    """
    Serializer for password reset request
    """
    email = serializers.EmailField(required=True)

class PasswordResetConfirmSerializer(serializers.Serializer):
    """
    Serializer for password reset confirmation
    """
    token = serializers.CharField(required=True)
    new_password = serializers.CharField(write_only=True, required=True, validators=[validate_password])
    new_password_confirm = serializers.CharField(write_only=True, required=True)

    def validate(self, attrs):
        if attrs.get('new_password') != attrs.get('new_password_confirm'):
            raise serializers.ValidationError({"new_password": "Password fields didn't match."})
        return attrs