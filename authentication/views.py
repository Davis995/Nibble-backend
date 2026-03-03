"""
Legacy Authentication Views
Kept for backward compatibility with existing User model
For new SSO functionality, see sso_views.py
"""
from django.core.mail import send_mail
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import logout
from django.utils import timezone
from django.db import models
from datetime import date, timedelta
from .permissions import IsAdmin
from .models import User, Subscription, Plan, PlanFeature
from .serializers import *;
from .serializers import InvitationCreateSerializer, InvitationAcceptSerializer
from .models import Invitation
import secrets, urllib.parse
from django.conf import settings


class CustomTokenObtainPairView(TokenObtainPairView):
    """Custom JWT token view for legacy User model"""
    pass


class UserRegistrationView(APIView):
    """POST: Register a new user (legacy, non-SSO)"""
    permission_classes = [AllowAny]
    authentication_classes = []  # No authentication required for registration
    
    def post(self, request, *args, **kwargs):
        serializer = UserRegistrationSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            
            # Generate JWT tokens for auto-login after registration
            refresh = RefreshToken.for_user(user)
            access_token = str(refresh.access_token)
            refresh_token = str(refresh)
            
            return Response(
                {
                    'message': 'User registered successfully',
                    'user_id': user.id,
                    'email': user.email,
                    'tokens': {
                        'access': access_token,
                        'refresh': refresh_token
                    }
                },
                status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class UserLoginView(APIView):
    """POST: Login with email and password, returns JWT tokens"""
    permission_classes = [AllowAny]
    authentication_classes = []  # No authentication required for login
    
    def post(self, request, *args, **kwargs):
        serializer = UserLoginSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            user = serializer.validated_data['user']
            user.last_login_at = timezone.now()
            user.save(update_fields=['last_login_at'])
            
            # Generate JWT tokens
            refresh = RefreshToken.for_user(user)
            access_token = str(refresh.access_token)
            refresh_token = str(refresh)
            
            # Get subscription details
            subscription_info = self._get_subscription_info(user)
            
            return Response(
                {
                    'message': 'Login successful',
                    'user': {
                        'id': user.id,
                        'username': user.username,
                        'email': user.email,
                        'role': 'superuser' if user.is_superuser else user.role,
                        'first_name': user.first_name,
                        'last_name': user.last_name,
                        'is_superuser': user.is_superuser,
                        'is_staff': user.is_staff,
                        'user_type': user.user_type,
                        'organisation': user.organisation.name if user.organisation else None,
                        'organisation_id': str(user.organisation.id) if getattr(user, 'organisation', None) else None,
                        'is_trial_active': user.is_trial_active(),
                        'trial_remaining_days': self._get_trial_remaining_days(user),
                        'subscription': subscription_info
                    },
                    'tokens': {
                        'access': access_token,
                        'refresh': refresh_token
                    }
                },
                status=status.HTTP_200_OK
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def _get_subscription_info(self, user):
        """Get subscription information for the user"""
        subscription = None
        
        if user.user_type == 'enterprise' and user.organisation:
            # For enterprise users, get organisation's active subscription
            subscription = user.organisation.subscriptions.filter(status='active').first()
            if subscription:
                remaining_days = (subscription.billing_end_date - date.today()).days
                return {
                    'plan_name': subscription.plan.name,
                    'status': subscription.status,
                    'remaining_credits': subscription.remaining_credits,
                    'billing_end_date': subscription.billing_end_date,
                    'remaining_days': remaining_days
                }
        elif user.subscription_plan:
            # For individual users, get user's subscription plan
            plan = user.subscription_plan
            return {
                'plan_name': plan.name,
                'status': 'active',  # Assuming active if assigned
                'remaining_credits': plan.total_credits,  # Or some logic
                'billing_end_date': None,
                'remaining_days': None
            }
        return None

    def _get_trial_remaining_days(self, user):
        """Get remaining trial days for the user"""
        if user.is_trial_active() and user.end_trial:
            return (user.end_trial - date.today()).days
        return 0


class UserLogoutView(APIView):
    """POST: Logout user (JWT is stateless, client should discard tokens)"""
    permission_classes = [IsAuthenticated]
    
    def post(self, request, *args, **kwargs):
        # JWT is stateless, no server-side logout needed
        # Client should discard the tokens
        return Response({'success': True, 'message': 'Logout successful'}, status=status.HTTP_200_OK)


class CurrentUserView(APIView):
    """GET: Get current authenticated user (me endpoint)"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request, *args, **kwargs):
        user = request.user
        return Response({
            'success': True,
            'data': {
                'id': str(user.id),
                'name': user.get_full_name() or user.username,
                'email': user.email,
                'role': 'superuser' if user.is_superuser else user.role,
                'avatar': None
            }
        }, status=status.HTTP_200_OK)


class UserProfileView(APIView):
    """GET: Get current user profile"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request, *args, **kwargs):
        serializer = UserProfileSerializer(request.user)
        return Response(serializer.data, status=status.HTTP_200_OK)


class UserProfileUpdateView(APIView):
    """PUT: Update user profile"""
    permission_classes = [IsAuthenticated]
    
    def put(self, request, *args, **kwargs):
        serializer = UserProfileUpdateSerializer(request.user, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(
                {'message': 'Profile updated successfully', 'data': serializer.data},
                status=status.HTTP_200_OK
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ChangePasswordView(APIView):
    """POST: Change user password"""
    permission_classes = [IsAuthenticated]
    
    def post(self, request, *args, **kwargs):
        serializer = ChangePasswordSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            user = request.user
            user.set_password(serializer.validated_data['new_password'])
            user.save()
            return Response({'message': 'Password changed successfully'}, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class PasswordResetRequestView(APIView):
    """POST: Request password reset"""
    permission_classes = [AllowAny]
    authentication_classes = []  # No authentication required for password reset request
    
    def post(self, request, *args, **kwargs):
        return Response({'message': 'Password reset email would be sent'}, status=status.HTTP_200_OK)


class PasswordResetConfirmView(APIView):
    """POST: Confirm password reset with token"""
    permission_classes = [AllowAny]
    authentication_classes = []  # No authentication required for password reset confirm
    
    def post(self, request, *args, **kwargs):
        return Response({'message': 'Password reset confirmed'}, status=status.HTTP_200_OK)


class EmailVerificationView(APIView):
    """POST: Verify email with token"""
    permission_classes = [AllowAny]
    authentication_classes = []  # No authentication required for email verification
    
    def post(self, request, *args, **kwargs):
        return Response({'message': 'Email verified'}, status=status.HTTP_200_OK)


class ResendVerificationEmailView(APIView):
    """POST: Resend verification email"""
    permission_classes = [IsAuthenticated]
    
    def post(self, request, *args, **kwargs):
        return Response({'message': 'Verification email resent'}, status=status.HTTP_200_OK)


class UserListView(APIView):
    """GET: List all users (admin only), POST: Create new user (admin only)"""
    permission_classes = [IsAdmin]
    
    def get(self, request, *args, **kwargs):
        # Get query parameters for filtering/pagination
        role = request.query_params.get('role')
        is_active = request.query_params.get('is_active')
        search = request.query_params.get('search')
        page = int(request.query_params.get('page', 1))
        limit = int(request.query_params.get('limit', 20))
        
        # Base queryset
        users = User.objects.all()
        
        # Apply filters
        if role:
            users = users.filter(role=role)
        if is_active is not None:
            users = users.filter(is_active=is_active.lower() == 'true')
        if search:
            users = users.filter(
                models.Q(username__icontains=search) |
                models.Q(email__icontains=search) |
                models.Q(first_name__icontains=search) |
                models.Q(last_name__icontains=search)
            )
        
        # Pagination
        total = users.count()
        start = (page - 1) * limit
        end = start + limit
        users_page = users[start:end]
        
        serializer = AdminUserSerializer(users_page, many=True)
        return Response({
            'users': serializer.data,
            'pagination': {
                'page': page,
                'limit': limit,
                'total': total,
                'pages': (total + limit - 1) // limit
            }
        }, status=status.HTTP_200_OK)
    
    def post(self, request, *args, **kwargs):
        serializer = AdminUserSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            return Response({
                'message': 'User created successfully',
                'user': AdminUserSerializer(user).data
            }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class UserDetailView(APIView):
    """GET: Get user details, PUT/PATCH: Update user, DELETE: Delete user (admin only)"""
    permission_classes = [IsAdmin]
    
    def get(self, request, user_id, *args, **kwargs):
        try:
            user = User.objects.get(id=user_id)
            serializer = AdminUserSerializer(user)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
    
    def put(self, request, user_id, *args, **kwargs):
        try:
            user = User.objects.get(id=user_id)
            serializer = AdminUserSerializer(user, data=request.data, partial=False)
            if serializer.is_valid():
                updated_user = serializer.save()
                return Response({
                    'message': 'User updated successfully',
                    'user': AdminUserSerializer(updated_user).data
                }, status=status.HTTP_200_OK)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
    
    def patch(self, request, user_id, *args, **kwargs):
        try:
            user = User.objects.get(id=user_id)
            serializer = AdminUserSerializer(user, data=request.data, partial=True)
            if serializer.is_valid():
                updated_user = serializer.save()
                return Response({
                    'message': 'User updated successfully',
                    'user': AdminUserSerializer(updated_user).data
                }, status=status.HTTP_200_OK)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
    
    def delete(self, request, user_id, *args, **kwargs):
        try:
            user = User.objects.get(id=user_id)
            # Prevent deleting superusers or operators by other operators
            if user.is_superuser and not request.user.is_superuser:
                return Response({'error': 'Cannot delete superuser'}, status=status.HTTP_403_FORBIDDEN)
            if user.role == 'operator' and not request.user.is_superuser:
                return Response({'error': 'Cannot delete operator'}, status=status.HTTP_403_FORBIDDEN)
            
            user.delete()
            return Response({'message': 'User deleted successfully'}, status=status.HTTP_204_NO_CONTENT)
        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)


class StudentDashboardView(APIView):
    """GET: Student dashboard"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request, *args, **kwargs):
        if request.user.role != 'student':
            return Response({'error': 'Only students'}, status=status.HTTP_403_FORBIDDEN)
        return Response({'message': 'Student dashboard', 'user': {'username': request.user.username}}, status=status.HTTP_200_OK)


class TeacherDashboardView(APIView):
    """GET: Teacher dashboard"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request, *args, **kwargs):
        if request.user.role != 'teacher':
            return Response({'error': 'Only teachers'}, status=status.HTTP_403_FORBIDDEN)
        return Response({'message': 'Teacher dashboard', 'user': {'username': request.user.username}}, status=status.HTTP_200_OK)


class AdminDashboardView(APIView):
    """GET: Admin dashboard"""
    permission_classes = [IsAdmin]
    
    def get(self, request, *args, **kwargs):
        return Response({'message': 'Admin dashboard', 'user': {'username': request.user.username}}, status=status.HTTP_200_OK)


class SettingsProfileView(APIView):
    """GET: Get user settings/profile, PUT: Update user settings"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request, *args, **kwargs):
        user = request.user
        return Response({
            'success': True,
            'data': {
                'id': str(user.id),
                'name': user.get_full_name() or user.username,
                'email': user.email,
                'role': 'superuser' if user.is_superuser else user.role,
                'avatar': None,
                'timezone': getattr(user, 'timezone', 'UTC'),
                'emailNotifications': getattr(user, 'email_notifications', True),
                'twoFactorEnabled': False
            }
        }, status=status.HTTP_200_OK)
    
    def put(self, request, *args, **kwargs):
        user = request.user
        name = request.data.get('name')
        timezone_str = request.data.get('timezone')
        email_notifications = request.data.get('emailNotifications')
        
        if name:
            parts = name.split(' ', 1)
            user.first_name = parts[0]
            user.last_name = parts[1] if len(parts) > 1 else ''
        if timezone_str:
            user.timezone = timezone_str
        if email_notifications is not None:
            user.email_notifications = email_notifications
        
        user.save()
        
        return Response({
            'success': True,
            'data': {
                'id': str(user.id),
                'name': user.get_full_name() or user.username,
                'email': user.email,
                'timezone': getattr(user, 'timezone', 'UTC'),
                'emailNotifications': getattr(user, 'email_notifications', True)
            }
        }, status=status.HTTP_200_OK)



class InvitationCreateView(APIView):
    """POST: Create an invitation for a nibble user (admin only)"""
    permission_classes = [IsAuthenticated, IsAdmin]

    def post(self, request, *args, **kwargs):
        serializer = InvitationCreateSerializer(data=request.data, context={'request': request})
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        email = serializer.validated_data['email']
        role = serializer.validated_data['role']

        # generate secure token
        token = secrets.token_urlsafe(32)
        expires_at = timezone.now() + timezone.timedelta(days=7)

        invitation = Invitation.objects.create(
            email=email,
            role=role,
            token=token,
            invited_by=request.user,
            expires_at=expires_at
        )

        # build frontend invite link
        frontend_base = getattr(settings, 'FRONTEND_URL', 'http://localhost:3000').rstrip('/')
        invite_link = f"{frontend_base}/invite/accept/?code={urllib.parse.quote(invitation.token)}"

        # send email
        subject = f"You're invited to join"
        plain = f"You have been invited to join. Click the link to accept and set your password: {invite_link}"
        html = f"<p>You have been invited to join. Click the link to accept and set your password:</p><p><a href='{invite_link}'>{invite_link}</a></p>"

        send_mail(subject, plain, getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@example.com'), [email], html_message=html, fail_silently=True)

        return Response({'success': True, 'email': invitation.email, 'expires_at': invitation.expires_at}, status=status.HTTP_201_CREATED)


class InvitationAcceptView(APIView):
    """POST: Accept an invitation token and create the user"""
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = InvitationAcceptSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        token = serializer.validated_data.get('token')
        password = serializer.validated_data.get('password')
        first_name = serializer.validated_data.get('first_name', '')
        last_name = serializer.validated_data.get('last_name', '')

        try:
            invite = Invitation.objects.get(token=token)
        except Invitation.DoesNotExist:
            return Response({'error': 'Invalid invitation token'}, status=status.HTTP_400_BAD_REQUEST)

        if not invite.is_valid():
            return Response({'error': 'Invitation is invalid or expired'}, status=status.HTTP_400_BAD_REQUEST)

        # Ensure no existing user with email
        if User.objects.filter(email__iexact=invite.email).exists():
            return Response({'error': 'User with this email already exists'}, status=status.HTTP_400_BAD_REQUEST)

        # create user
        user = User.objects.create(
            username=invite.email,
            email=invite.email,
            first_name=first_name or '',
            last_name=last_name or '',
            role=invite.role,
            user_type='nibble',
            is_active=True
        )
        user.set_password(password)
        user.save()

        invite.used = True
        invite.user = user
        invite.save()

        return Response({'success': True, 'message': 'Account created successfully'}, status=status.HTTP_201_CREATED)

class SettingsChangePasswordView(APIView):
    """POST: Change user password"""
    permission_classes = [IsAuthenticated]
    
    def post(self, request, *args, **kwargs):
        user = request.user
        current_password = request.data.get('currentPassword')
        new_password = request.data.get('newPassword')
        confirm_password = request.data.get('confirmPassword')
        
        if not current_password or not new_password or not confirm_password:
            return Response({
                'success': False,
                'error': 'currentPassword, newPassword, and confirmPassword are required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if not user.check_password(current_password):
            return Response({
                'success': False,
                'error': 'Current password is incorrect'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if new_password != confirm_password:
            return Response({
                'success': False,
                'error': 'New password and confirmation password do not match'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if len(new_password) < 8:
            return Response({
                'success': False,
                'error': 'New password must be at least 8 characters long'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        user.set_password(new_password)
        user.save()
        
        return Response({
            'success': True,
            'message': 'Password changed successfully'
        }, status=status.HTTP_200_OK)

# ============================================================================
# PLAN VIEWS FOR CRUD OPERATIONS
# ============================================================================

class PlanListCreateView(APIView):
    """
    View for listing plans and creating new plans.
    
    GET /api/v1/auth/plans/ - List all plans
    POST /api/v1/auth/plans/ - Create new plan
    
    Query Parameters:
    - active=true - Filter active plans
    - popular=true - Filter popular plans
    - use_type=individual|enterprise - Filter by type
    """
    permission_classes = [AllowAny]
    
    def get_queryset(self):
        """Filter queryset based on query parameters"""
        queryset = Plan.objects.all().prefetch_related('features')
        
        # Filter by active status
        if self.request.query_params.get('active') == 'true':
            queryset = queryset.filter(is_active=True)
        
        # Filter by use type
        use_type = self.request.query_params.get('use_type')
        if use_type:
            queryset = queryset.filter(use_type=use_type)
        
        # Filter by popular
        if self.request.query_params.get('popular') == 'true':
            queryset = queryset.filter(is_popular=True)
        
        # Order by popular first, then by creation date
        queryset = queryset.order_by('-is_popular', '-created_at')
        
        return queryset
    
    def get(self, request, *args, **kwargs):
        """List all plans with filtering"""
        queryset = self.get_queryset()
        serializer = PlanListSerializer(queryset, many=True)
        return Response({
            'count': len(serializer.data),
            'results': serializer.data
        }, status=status.HTTP_200_OK)
    
    def post(self, request, *args, **kwargs):
        """Create a new plan with features"""
        serializer = PlanCreateUpdateSerializer(data=request.data)
        if serializer.is_valid():
            plan = serializer.save()
            # Return detail serializer for response
            return Response(
                PlanDetailSerializer(plan).data,
                status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class PlanDetailView(APIView):
    """
    View for retrieving, updating, and deleting plans.
    
    GET /api/v1/auth/plans/{id}/ - Get plan details
    PUT /api/v1/auth/plans/{id}/ - Full update
    PATCH /api/v1/auth/plans/{id}/ - Partial update
    DELETE /api/v1/auth/plans/{id}/ - Delete plan
    """
    permission_classes = [AllowAny]
    
    def get_object(self, pk):
        """Get plan object by pk"""
        try:
            return Plan.objects.prefetch_related('features').get(pk=pk)
        except Plan.DoesNotExist:
            return None
    
    def get(self, request, pk, *args, **kwargs):
        """Retrieve a plan"""
        plan = self.get_object(pk)
        if not plan:
            return Response(
                {'error': 'Plan not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        serializer = PlanDetailSerializer(plan)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    def put(self, request, pk, *args, **kwargs):
        """Full update of a plan"""
        plan = self.get_object(pk)
        if not plan:
            return Response(
                {'error': 'Plan not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        serializer = PlanCreateUpdateSerializer(plan, data=request.data, partial=False)
        if serializer.is_valid():
            updated_plan = serializer.save()
            # Return detail serializer for response
            return Response(
                PlanDetailSerializer(updated_plan).data,
                status=status.HTTP_200_OK
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def patch(self, request, pk, *args, **kwargs):
        """Partial update of a plan"""
        plan = self.get_object(pk)
        if not plan:
            return Response(
                {'error': 'Plan not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        serializer = PlanCreateUpdateSerializer(plan, data=request.data, partial=True)
        if serializer.is_valid():
            updated_plan = serializer.save()
            # Return detail serializer for response
            return Response(
                PlanDetailSerializer(updated_plan).data,
                status=status.HTTP_200_OK
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def delete(self, request, pk, *args, **kwargs):
        """Delete a plan"""
        plan = self.get_object(pk)
        if not plan:
            return Response(
                {'error': 'Plan not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        plan.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ActivePlansView(APIView):
    """
    Get all active plans
    GET /api/plans/active/
    """
    permission_classes = [AllowAny]
    
    def get(self, request):
        """Get all active plans with features"""
        plans = Plan.objects.filter(is_active=True).prefetch_related('features').order_by('-is_popular', '-created_at')
        serializer = PlanListSerializer(plans, many=True)
        return Response({
            'count': plans.count(),
            'plans': serializer.data
        })


class PlansByTypeView(APIView):
    """
    Get plans by type (individual/enterprise)
    GET /api/plans/by-type/?use_type=individual
    """
    permission_classes = [AllowAny]
    
    def get(self, request):
        """Get plans filtered by type"""
        use_type = request.query_params.get('use_type')
        if not use_type or use_type not in ['individual', 'enterprise']:
            return Response(
                {'error': 'use_type parameter must be "individual" or "enterprise"'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        plans = Plan.objects.filter(
            use_type=use_type,
            is_active=True
        ).prefetch_related('features').order_by('-is_popular', '-created_at')
        
        serializer = PlanListSerializer(plans, many=True)
        return Response({
            'use_type': use_type,
            'count': plans.count(),
            'plans': serializer.data
        })
    
class StudentSchoolLoginView(APIView):


        permission_classes = [AllowAny]
        authentication_classes = []

        def post(self, request, *args, **kwargs):

            serializer = StudentSchoolLoginSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)

        # Get validated student
            student = serializer.validated_data['student']
            school = student.school

        # Check if school subscription is active
            if not school.is_subscription_active():
                return Response(
                    {'error': 'School subscription is not active'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Check if student is active
            if not student.is_active:
                return Response(
                {'error': 'Student account is inactive'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Get or create user account for this student
            try:
                user = self._get_user_for_student(student)
            except ValueError as e:
                return Response(
                {'error': str(e)},
                status=status.HTTP_404_NOT_FOUND
            )

            if not user.is_active:
                return Response(
                {'error': 'User account is disabled'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Update student's last login
            student.last_login_at = timezone.now()
            student.save(update_fields=['last_login_at'])

        # Update user's last login
            user.last_login_at = timezone.now()
            user.save(update_fields=['last_login_at'])

        # Generate JWT tokens
            refresh = RefreshToken.for_user(user)
            access_token = str(refresh.access_token)
            refresh_token = str(refresh)

        # Prepare user data similar to regular login
            # reuse UserLoginView helper for subscription info
            subscription_info = None
            try:
                from .views import UserLoginView
                subscription_info = UserLoginView()._get_subscription_info(user)
            except Exception:
                subscription_info = None

            response_data = {
                'message': 'Login successful',
                'user': {
                    'id': user.id,
                    'username': user.username,
                    'email': user.email,
                    'role': 'superuser' if user.is_superuser else user.role,
                    'first_name': user.first_name,
                    'last_name': user.last_name,
                    'is_superuser': user.is_superuser,
                    'is_staff': user.is_staff,
                    'user_type': user.user_type,
                    'organisation': user.organisation.name if user.organisation else None,
                    'organisation_id': str(user.organisation.id) if getattr(user, 'organisation', None) else None,
                    'is_trial_active': user.is_trial_active(),
                    'trial_remaining_days': self._get_trial_remaining_days(user),
                    'subscription': subscription_info
                },
                'tokens': {
                    'access': access_token,
                    'refresh': refresh_token
                },
                'student': StudentSerializer(student).data,
                'school': SchoolSerializer(school).data,
            }

            return Response(response_data, status=status.HTTP_200_OK)

        def _get_user_for_student(self, student):
        
            try:
            # Try to find existing user with this email
                user = User.objects.get(email=student.school_email)
            # Ensure user_type is enterprise
                if user.user_type != 'enterprise':
                    user.user_type = 'enterprise'
                    user.save(update_fields=['user_type'])
                return user
            except User.DoesNotExist:
            # Do not create user, return error
                raise ValueError("User account not found for this student. Please contact administrator.")

        def _get_trial_remaining_days(self, user):
            """Return remaining trial days for a user (copied from UserLoginView)"""
            if user.is_trial_active() and user.end_trial:
                return (user.end_trial - date.today()).days
            return 0


class CreditsUsageView(APIView):
    """
    GET: Get credit usage information for authenticated user
    Returns percentage used, remaining credits, and days until reset
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request, *args, **kwargs):
        user = request.user
        
        try:
            subscription = self._get_user_subscription(user)
            
            if not subscription:
                return Response({
                    'success': False,
                    'message': 'No active subscription found'
                }, status=status.HTTP_404_NOT_FOUND)
            
            # Calculate usage metrics
            used_credits = subscription.start_credits - subscription.remaining_credits
            total_credits = subscription.start_credits
            usage_percentage = (used_credits / total_credits * 100) if total_credits > 0 else 0
            
            # Calculate days until reset
            billing_end_date = subscription.billing_end_date
            today = timezone.now().date()
            days_until_reset = (billing_end_date - today).days
            
            return Response({
                'success': True,
                'data': {
                    'subscription_id': str(subscription.id),
                    'plan_name': subscription.plan.name,
                    'subscription_status': subscription.status,
                    'credits': {
                        'total': total_credits,
                        'used': used_credits,
                        'remaining': subscription.remaining_credits,
                        'usage_percentage': round(usage_percentage, 2)
                    },
                    'billing': {
                        'billing_start_date': subscription.billing_start_date,
                        'billing_end_date': billing_end_date,
                        'days_until_reset': max(days_until_reset, 0),
                        'is_reset_soon': days_until_reset <= 7
                    },
                    'user': {
                        'id': str(user.id),
                        'email': user.email,
                        'name': user.get_full_name() or user.username,
                        'user_type': user.user_type,
                        'role': user.role
                    }
                }
            }, status=status.HTTP_200_OK)
        
        except Exception as e:
            return Response({
                'success': False,
                'message': f'Error retrieving credit usage: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def _get_user_subscription(self, user):
        """Get active subscription for user (individual or enterprise)"""
        
        # If enterprise user, get organisation's subscription
        if user.user_type == 'enterprise' and user.organisation:
            subscription = user.organisation.subscriptions.filter(
                status='active'
            ).order_by('-created_at').first()
            return subscription
        
        # If individual user, get their own subscription
        if user.user_type == 'individual':
            subscription = Subscription.objects.filter(
                user=user,
                status='active'
            ).order_by('-created_at').first()
            return subscription
        
        # Fallback to any active subscription
        subscription = Subscription.objects.filter(
            status='active'
        ).filter(
            models.Q(user=user) | models.Q(organisation=user.organisation)
        ).order_by('-created_at').first()
        
        return subscription