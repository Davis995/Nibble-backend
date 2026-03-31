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
from rest_framework import viewsets, filters
from django_filters.rest_framework import DjangoFilterBackend
from .serializers import *;
from .serializers import InvitationCreateSerializer, InvitationAcceptSerializer
from .models import Invitation
import secrets, urllib.parse
from django.conf import settings
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from .models import PasswordResetToken, PasswordResetCode
import random


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
            
            # Auto-create subscription to individual free plan
            try:
                free_plan = Plan.objects.get(name='Free')
                Subscription.objects.create(
                    user=user,
                    plan=free_plan,
                    status='active',
                    max_users=free_plan.max_users if hasattr(free_plan, 'max_users') else 1,
                    start_credits=free_plan.total_credits,
                    remaining_credits=free_plan.total_credits,
                    billing_start_date=timezone.now().date(),
                    billing_end_date=timezone.now().date() + timedelta(days=30)
                )
            except Plan.DoesNotExist:
                # If plan doesn't exist, skip or handle
                pass
            
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
                        'onboarding': user.is_onboarded,
                        'organisation': (user.organisation or getattr(user, 'managed_school', None)).name if (user.organisation or getattr(user, 'managed_school', None)) else None,
                        'organisation_id': str((user.organisation or getattr(user, 'managed_school', None)).id) if (user.organisation or getattr(user, 'managed_school', None)) else None,
                        'org_orientation': (user.organisation or getattr(user, 'managed_school', None)).org_orientation if (user.organisation or getattr(user, 'managed_school', None)) else False,
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
        """Get subscription information for the user.

        Prefer an actual Subscription object (either tied to the user or,
        for enterprise accounts, to the organisation). The legacy
        ``subscription_plan`` field is used only as a fallback when no
        active Subscription record exists.
        """
        # try to find a real subscription record for the user first
        subscription = Subscription.objects.filter(user=user, status='active').order_by('-billing_end_date').first()
        if subscription:
            remaining_days = (subscription.billing_end_date - date.today()).days
            # If expired, override status to 'expired'
            status = 'expired' if remaining_days < 0 else subscription.status
            return {
                'plan_name': subscription.plan.name,
                'status': status,
                'remaining_credits': subscription.remaining_credits,
                'billing_end_date': subscription.billing_end_date,
                'remaining_days': max(0, remaining_days)  # Ensure non-negative
            }

        # enterprise users may have organisation subscription instead
        if user.user_type == 'enterprise' and user.organisation:
            subscription = user.organisation.subscriptions.filter(status='active').order_by('-billing_end_date').first()
            if subscription:
                remaining_days = (subscription.billing_end_date - date.today()).days
                # If expired, override status to 'expired'
                status = 'expired' if remaining_days < 0 else subscription.status
                return {
                    'plan_name': subscription.plan.name,
                    'status': status,
                    'remaining_credits': subscription.remaining_credits,
                    'billing_end_date': subscription.billing_end_date,
                    'remaining_days': max(0, remaining_days)  # Ensure non-negative
                }

        # legacy behavior: fall back to subscription_plan field if set
        if user.subscription_plan:
            plan = user.subscription_plan
            return {
                'plan_name': plan.name,
                'status': 'active',  # assume active when assigned
                'remaining_credits': plan.total_credits,
                'billing_end_date': None,
                'remaining_days': None
            }

        return None

    def _get_trial_remaining_days(self, user):
        """Get remaining trial days for the user"""
        if user.is_trial_active() and user.end_trial:
            return (user.end_trial - date.today()).days
        return 0


class GoogleLoginView(APIView):
    """POST: Google OAuth2 login with id_token"""
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request, *args, **kwargs):
        token = request.data.get('token') or request.data.get('id_token')
        if not token:
            return Response({'error': 'Google token is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            audience = getattr(settings, 'GOOGLE_CLIENT_ID', None)
            if audience:
                id_info = id_token.verify_oauth2_token(token, google_requests.Request(), audience=audience)
            else:
                id_info = id_token.verify_oauth2_token(token, google_requests.Request())
        except ValueError:
            return Response({'error': 'Invalid Google token'}, status=status.HTTP_400_BAD_REQUEST)

        email = id_info.get('email')
        if not email:
            return Response({'error': 'Google token does not contain email'}, status=status.HTTP_400_BAD_REQUEST)

        if not id_info.get('email_verified', False):
            return Response({'error': 'Google email is not verified'}, status=status.HTTP_400_BAD_REQUEST)

        first_name = id_info.get('given_name', '')
        last_name = id_info.get('family_name', '')

        created = False
        user = None
        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            user = User(
                username=email,
                email=email,
                first_name=first_name,
                last_name=last_name,
                role='student',
                user_type='individual',
                is_active=True
            )
            user.set_password(User.objects.make_random_password())
            user.save()
            created = True

            # auto-create subscription to free plan for new users, as in registration workflow
            try:
                free_plan = Plan.objects.get(name='Free')
                Subscription.objects.create(
                    user=user,
                    plan=free_plan,
                    status='active',
                    max_users=free_plan.max_users if hasattr(free_plan, 'max_users') else 1,
                    start_credits=free_plan.total_credits,
                    remaining_credits=free_plan.total_credits,
                    billing_start_date=timezone.now().date(),
                    billing_end_date=timezone.now().date() + timedelta(days=30)
                )
            except Plan.DoesNotExist:
                pass

        if not user.is_active:
            return Response({'error': 'User account is disabled'}, status=status.HTTP_403_FORBIDDEN)

        user.last_login_at = timezone.now()
        user.save(update_fields=['last_login_at'])

        refresh = RefreshToken.for_user(user)
        access_token = str(refresh.access_token)
        refresh_token = str(refresh)

        subscription_info = None
        try:
            subscription_info = UserLoginView()._get_subscription_info(user)
        except Exception:
            subscription_info = None

        response_data = {
            'message': 'Login successful',
            'is_new_user': created,
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
                'onboarding': user.is_onboarded,
                'organisation': user.organisation.name if user.organisation else None,
                'organisation_id': str(user.organisation.id) if getattr(user, 'organisation', None) else None,
                'org_orientation': user.organisation.org_orientation if user.organisation else False,
                'is_trial_active': user.is_trial_active(),
                'trial_remaining_days': self._get_trial_remaining_days(user),
                'subscription': subscription_info
            },
            'tokens': {
                'access': access_token,
                'refresh': refresh_token
            }
        }

        return Response(response_data, status=status.HTTP_200_OK)

    def _get_trial_remaining_days(self, user):
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
                'org_orientation': (user.organisation or getattr(user, 'managed_school', None)).org_orientation if (user.organisation or getattr(user, 'managed_school', None)) else False,
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


class UserOnboardingUpdateView(APIView):
    """PUT: Update user onboarding along with other modal data"""
    permission_classes = [IsAuthenticated]
    
    def put(self, request, *args, **kwargs):
        user = request.user
        data = request.data
        
        # Optional user fields that could be sent from the onboarding modal
        if 'phone_number' in data:
            user.phone_number = data['phone_number']
            
        if 'role' in data and data['role'] in ['student', 'teacher']:
            user.role = data['role']
            
        if 'user_type' in data and data['user_type'] in dict(User.USER_TYPE_CHOICES).keys():
            user.user_type = data['user_type']
            
        if 'first_name' in data:
            user.first_name = data['first_name']
            
        if 'last_name' in data:
            user.last_name = data['last_name']
            
        # specifically handles mapping onboarding to is_onboarded field
        if 'onboarding' in data:
            val = data['onboarding']
            user.is_onboarded = (str(val).lower() == 'true' or val is True)
            
        user.save()
        
        # Can reuse UserProfileSerializer to send the updated user state back
        serializer = UserProfileSerializer(user)
        return Response(
            {'message': 'Onboarding data updated successfully', 'data': serializer.data},
            status=status.HTTP_200_OK
        )


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
        serializer = PasswordResetRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        email = serializer.validated_data['email']
        user = User.objects.filter(email__iexact=email).first()

        if user:
            # Generate secure token
            token = secrets.token_urlsafe(32)
            expires_at = timezone.now() + timezone.timedelta(hours=24)

            PasswordResetToken.objects.create(
                user=user,
                token=token,
                expires_at=expires_at
            )

            # Build frontend reset link
            frontend_base = getattr(settings, 'FRONTEND_URL', 'http://localhost:3000').rstrip('/')
            reset_link = f"{frontend_base}/forgot-password/?token={urllib.parse.quote(token)}"

            # Send email
            subject = "Password Reset Request"
            plain = f"You requested a password reset. Click the following link to set your new password: {reset_link}\n\nIf you did not request this, please ignore this email."
            html = f"<p>You requested a password reset. Click the link below to set your new password:</p><p><a href='{reset_link}'>{reset_link}</a></p><p>If you did not request this, please ignore this email.</p>"

            send_mail(
                subject, 
                plain, 
                getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@example.com'), 
                [email], 
                html_message=html, 
                fail_silently=True
            )

            return Response({'message': 'Password reset email has been sent.'}, status=status.HTTP_200_OK)
        else:
            return Response({'error': 'User with this email does not exist.'}, status=status.HTTP_404_NOT_FOUND)


class PasswordResetConfirmView(APIView):
    """POST: Confirm password reset with token"""
    permission_classes = [AllowAny]
    authentication_classes = []  # No authentication required for password reset confirm
    
    def post(self, request, *args, **kwargs):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        token = serializer.validated_data['token']
        new_password = serializer.validated_data['new_password']

        try:
            reset_token = PasswordResetToken.objects.get(token=token)
        except PasswordResetToken.DoesNotExist:
            return Response({'error': 'Invalid reset token'}, status=status.HTTP_400_BAD_REQUEST)

        if not reset_token.is_valid():
            return Response({'error': 'Reset token is invalid or expired'}, status=status.HTTP_400_BAD_REQUEST)

        user = reset_token.user
        user.set_password(new_password)
        user.save()

        reset_token.used = True
        reset_token.save()

        return Response({'message': 'Password has been reset successfully'}, status=status.HTTP_200_OK)


class AccountResetRequestView(APIView):
    """
    POST: Request account reset (sends 6-digit code)
    Requires authentication as per user request
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        email = request.data.get('email')
        if not email:
            return Response({"success": False, "message": "Email is required"}, status=400)
        
        # Verify email matches current user if needed, 
        # but the request asks to use request.user
        if email.lower() != request.user.email.lower():
            return Response({"success": False, "message": "Email does not match your account"}, status=400)

        # Generate 6-digit code
        code = "".join([str(random.randint(0, 9)) for _ in range(6)])
        
        # Save code to database
        expires_at = timezone.now() + timezone.timedelta(minutes=15)
        PasswordResetCode.objects.update_or_create(
            user=request.user, 
            defaults={'code': code, 'expires_at': expires_at, 'used': False}
        )
        
        # Send Email
        subject = 'Your Account Reset Code'
        message = f'Your verification code is: {code}'
        from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@example.com')
        recipient_list = [email]
        
        try:
            send_mail(subject, message, from_email, recipient_list)
        except Exception as e:
            # Log error but don't fail if mail server is not configured
            print(f"DEBUG: Failed to send email: {e}")
        
        print(f"DEBUG: Account reset code for {email}: {code}")

        return Response({
            "success": True, 
            "message": "A verification code has been sent to your email."
        })


class AccountResetVerifyView(APIView):
    """
    POST: Verify account reset code
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        code = request.data.get('code')
        if not code:
            return Response({"success": False, "message": "Code is required"}, status=400)
            
        reset_code = PasswordResetCode.objects.filter(user=request.user).order_by('-created_at').first()
        
        if reset_code and reset_code.is_valid() and reset_code.code == code:
            return Response({"success": True, "message": "Code verified successfully"})
            
        return Response({"success": False, "message": "Invalid or expired verification code"}, status=400)


class AccountResetConfirmView(APIView):
    """
    POST: Confirm account reset and set new password
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        code = request.data.get('code') # Verify code again for security or assume verified
        new_password = request.data.get('new_password')
        
        if not new_password:
            return Response({"success": False, "message": "New password is required"}, status=400)
            
        # Re-verify code
        reset_code = PasswordResetCode.objects.filter(user=request.user).order_by('-created_at').first()
        if not reset_code or not reset_code.is_valid() or reset_code.code != code:
             return Response({"success": False, "message": "Invalid or expired verification code"}, status=400)

        # Update user password
        request.user.set_password(new_password)
        request.user.save()
        
        # Mark code as used
        reset_code.used = True
        reset_code.save()
        
        return Response({"success": True, "message": "Password updated successfully"})


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


# Legacy User Views - Now handled by AdminUserViewSet
# class UserListView(APIView): ...
# class UserDetailView(APIView): ...


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
                "organisation": user.organisation,
                "phone_number":user.phone_number,
                
                'timezone': getattr(user, 'timezone', 'UTC'),
                'emailNotifications': getattr(user, 'email_notifications', True),
                'twoFactorEnabled': False
            }
        }, status=status.HTTP_200_OK)
    
    def put(self, request, *args, **kwargs):
        user = request.user
        phone_number=request.data.get('phone_number')   
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
        if phone_number:
            user.phone_number = phone_number
        
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


# ============================================================================
# ADMIN VIEWSETS
# ============================================================================

class AdminPlanViewSet(viewsets.ModelViewSet):
    """
    Comprehensive ViewSet for administrative plan management.
    Handles List, Create, Retrieve, Update, and Delete for Plans 
    including their nested features.
    """
    queryset = Plan.objects.all().prefetch_related('features').order_by('-is_popular', '-created_at')
    serializer_class = PlanAdminSerializer
    permission_classes = [IsAuthenticated, IsAdmin]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    
    # Filterable fields
    filterset_fields = ['is_active', 'is_popular', 'use_type', 'theme']
    
    # Searchable fields
    search_fields = ['name', 'description', 'plan_id']
    
    # Sortable fields
    ordering_fields = ['created_at', 'monthly_price', 'total_credits']


class AdminUserViewSet(viewsets.ModelViewSet):
    """
    ViewSet for administrative user management.
    Handles searching, filtering, and deep editing of user accounts.
    """
    queryset = User.objects.all().select_related('organisation', 'subscription_plan').order_by('-created_at')
    serializer_class = AdminUserSerializer
    permission_classes = [IsAuthenticated, IsAdmin]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    
    # Filterable fields
    filterset_fields = ['role', 'user_type', 'is_active', 'is_verified', 'trial', 'organisation']
    
    # Searchable fields
    search_fields = ['email', 'username', 'first_name', 'last_name', 'phone_number']
    
    # Sortable fields
    ordering_fields = ['created_at', 'last_login_at', 'email', 'username']

    def destroy(self, request, *args, **kwargs):
        """Override delete to perform deactivation instead of hard delete for safety"""
        user = self.get_object()
        user.is_active = False
        user.save()
        return Response(
            {'message': 'User deactivated successfully'}, 
            status=status.HTTP_200_OK
        )


class ActivePlansView(APIView):
    """
    Get all active plans
    GET /api/plans/active/
    """
    permission_classes = [AllowAny]
    
    def get(self, request):
        """Get all active plans with features in public camelCase format"""
        plans = Plan.objects.filter(is_active=True).prefetch_related('features').order_by('-is_popular', '-created_at')
        serializer = PlanPublicSerializer(plans, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


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

class SidebarBadgesView(APIView):
    """
    Get dynamic badge counts for sidebar navigation
    GET /api/v1/auth/sidebar-badges/
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from tools.models import AITool, AILog
        from leads.models import Notification
        from django.utils import timezone
        import datetime
        
        user = request.user
        
        # Tools: new tools created in the last 7 days appropriate for user role
        seven_days_ago = timezone.now() - datetime.timedelta(days=7)
        tools_count = AITool.objects.filter(
            created_at__gte=seven_days_ago, 
            categories__type=user.role
        ).count()
        
        # History: user's AI generations today
        today = timezone.now().date()
        history_count = AILog.objects.filter(user=user, created_at__date=today).count()
        
        # Notifications: unread notifications for user
        notifications_count = Notification.objects.filter(user=user, is_read=False).count()
        
        return Response({
            'tools': tools_count,
            'history': history_count,
            'notifications': notifications_count
        }, status=status.HTTP_200_OK)