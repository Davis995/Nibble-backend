from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from .views import *

app_name = 'authentication'

urlpatterns = [
    # ==================== AUTHENTICATION ENDPOINTS ====================

    # User Registration
    path('register/', UserRegistrationView.as_view(), name='register'),

    # User Login (returns JWT tokens)
    path('login/', UserLoginView.as_view(), name='login'),

    # School-based Student Login (school email + student code)
    path('school-login/', StudentSchoolLoginView.as_view(), name='school_login'),

    # Google OAuth2 login
    path('google-login/', GoogleLoginView.as_view(), name='google-login'),

    # JWT Token Refresh
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    # Logout
    path('logout/', UserLogoutView.as_view(), name='logout'),

    # Get current user (me endpoint)
    path('me/', CurrentUserView.as_view(), name='current-user'),

    # Get Credits Usage
    path('credits/usage/', CreditsUsageView.as_view(), name='credits-usage'),

    # ==================== USER PROFILE ENDPOINTS ====================

    # Get Profile
    path('profile/', UserProfileView.as_view(), name='profile'),

    # Update Profile
    path('profile/update/', UserProfileUpdateView.as_view(), name='profile-update'),

    # Change Password
    path('password/change/', ChangePasswordView.as_view(), name='password-change'),

    # ==================== SETTINGS ENDPOINTS ====================

    # Get/Update Settings Profile
    path('settings/profile/', SettingsProfileView.as_view(), name='settings-profile'),

    # Change Password via Settings
    path('settings/change-password/', SettingsChangePasswordView.as_view(), name='settings-change-password'),

    # ==================== PASSWORD RESET ENDPOINTS ====================

    # Request Password Reset
    path('password/reset/request/', PasswordResetRequestView.as_view(), name='password-reset-request'),

    # Confirm Password Reset
    path('password/reset/confirm/', PasswordResetConfirmView.as_view(), name='password-reset-confirm'),

    # ==================== EMAIL VERIFICATION ENDPOINTS ====================

    # Verify Email
    path('email/verify/', EmailVerificationView.as_view(), name='email-verify'),

    # Resend Verification Email
    path('email/verify/resend/', ResendVerificationEmailView.as_view(), name='email-verify-resend'),

    # ==================== ADMIN USER MANAGEMENT ENDPOINTS ====================

    # List All Users (Admin only)
    path('admin/users/', UserListView.as_view(), name='admin-users-list'),

    # User Detail (Admin only)
    path('admin/users/<int:user_id>/', UserDetailView.as_view(), name='admin-user-detail'),

    # ==================== ROLE-SPECIFIC DASHBOARD ENDPOINTS ====================

    # Student Dashboard
    path('dashboard/student/', StudentDashboardView.as_view(), name='student-dashboard'),

    # Teacher Dashboard
    path('dashboard/teacher/', TeacherDashboardView.as_view(), name='teacher-dashboard'),

    # Admin Dashboard
    path('dashboard/admin/', AdminDashboardView.as_view(), name='admin-dashboard'),

    # ==================== PLAN ENDPOINTS ====================
    
    # Plan List & Create
    path('plans/', PlanListCreateView.as_view(), name='plan-list-create'),
    
    # Plan Detail (Retrieve, Update, Partial Update, Delete)
    path('plans/<int:pk>/', PlanDetailView.as_view(), name='plan-detail'),
    
    # Additional plan endpoints
    path('plans/active/', ActivePlansView.as_view(), name='active-plans'),
    path('plans/by-type/', PlansByTypeView.as_view(), name='plans-by-type'),
    # Invitation endpoints
    path('invite/create/', InvitationCreateView.as_view(), name='invite-create'),
    path('invite/accept/', InvitationAcceptView.as_view(), name='invite-accept'),
]