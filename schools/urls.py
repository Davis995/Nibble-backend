from django.urls import path
from .views import (
    # School CRUD
    SchoolListCreateView,
    SchoolDetailView,
    SchoolOnboardingUpdateView,
    SchoolUpgradeView,
    SchoolSupportHistoryView,
    SchoolCancelSubscriptionView,

    # Student CRUD
    StudentListCreateView,
    StudentDetailView,
    StudentBulkCreateView,
    StudentCodesView,

    # Activation/Deactivation
    SchoolToggleActiveView,
    StudentToggleActiveView,
    StudentBulkToggleActiveView,

    # School Admin User CRUD
    SchoolAdminUserListCreateView,
    SchoolAdminUserDetailView,
    StaffListCreateView,
    StaffDetailView,
    ActivityListCreateView,
    ActivityDetailView,
    InviteStaffView,
    AcceptInvitationView,

    # Admin Dashboard
    AdminDashboardView,
    SchoolAdminDashboardView,
    SchoolDetailsView,
    SchoolMonitoringView,
    GlobalAlertsView,
    SchoolNotificationsView,
    SchoolBillingView,
    SchoolBillingTopUpView,
    SchoolOrientationOnboardView,
    SchoolResetDataView
)

app_name = 'schools'
urlpatterns = [
    # ==================== SCHOOL CRUD ENDPOINTS ====================

    # List/Create Schools
    path('', SchoolListCreateView.as_view(), name='school_list_create'),

    # School Detail (Update/Delete)
    path('<uuid:school_id>/', SchoolDetailView.as_view(), name='school_detail'),
    path('<uuid:school_id>/details/', SchoolDetailsView.as_view(), name='school_details'),
    path('<uuid:school_id>/onboarding/', SchoolOnboardingUpdateView.as_view(), name='school_onboarding_update'),
    path('<uuid:school_id>/upgrade/', SchoolUpgradeView.as_view(), name='school_upgrade'),
    path('<uuid:school_id>/support/', SchoolSupportHistoryView.as_view(), name='school_support'),
    path('<uuid:school_id>/cancel/', SchoolCancelSubscriptionView.as_view(), name='school_cancel'),

    # ==================== STUDENT CRUD ENDPOINTS ====================

    # List/Create Students for a School
    path('<uuid:school_id>/students/', StudentListCreateView.as_view(), name='student_list_create'),

    # Student Detail (Update/Delete)
    path('<uuid:school_id>/students/<uuid:student_id>/', StudentDetailView.as_view(), name='student_detail'),

    # Bulk Create Students from Excel
    path('<uuid:school_id>/students/bulk/', StudentBulkCreateView.as_view(), name='student_bulk_create'),

    # Display Students and Codes
    path('<uuid:school_id>/students/codes/', StudentCodesView.as_view(), name='student_codes'),

    # ==================== ACTIVATION/DEACTIVATION ENDPOINTS ====================

    # Toggle School Active Status
    path('<uuid:school_id>/toggle-active/', SchoolToggleActiveView.as_view(), name='school_toggle_active'),

    # Toggle Student Active Status
    path('<uuid:school_id>/students/<uuid:student_id>/toggle-active/', StudentToggleActiveView.as_view(), name='student_toggle_active'),

    # Bulk Toggle Students Active Status
    path('<uuid:school_id>/students/bulk/toggle-active/', StudentBulkToggleActiveView.as_view(), name='student_bulk_toggle_active'),

    # ==================== SCHOOL ADMIN USER CRUD ENDPOINTS ====================

    # List/Create School Admin Users
    path('admin-users/', SchoolAdminUserListCreateView.as_view(), name='school_admin_user_list_create'),

    # School Admin User Detail (Update/Delete)
    path('admin-users/<int:user_id>/', SchoolAdminUserDetailView.as_view(), name='school_admin_user_detail'),

    # Staff CRUD endpoints
    path('<uuid:school_id>/staff/', StaffListCreateView.as_view(), name='staff_list_create'),
    path('<uuid:school_id>/staff/<uuid:staff_id>/', StaffDetailView.as_view(), name='staff_detail'),

    # Activity CRUD endpoints
    path('<uuid:school_id>/activities/', ActivityListCreateView.as_view(), name='activity_list_create'),
    path('<uuid:school_id>/activities/<int:activity_id>/', ActivityDetailView.as_view(), name='activity_detail'),

    # Invite staff (creates an invitation code)
    path('<uuid:school_id>/staff/invite/', InviteStaffView.as_view(), name='invite_staff'),

    # Accept invitation (public endpoint)
    path('invitations/accept/', AcceptInvitationView.as_view(), name='accept_invitation'),

    # ==================== ADMIN DASHBOARD ENDPOINTS ====================

    # Admin Dashboard Data
    path('admin/dashboard/', AdminDashboardView.as_view(), name='admin_dashboard'),
    # School-admin scoped dashboard (school admin uses their managed_school)
    path('dashboard/', SchoolAdminDashboardView.as_view(), name='school_admin_dashboard_me'),
    # Operators can fetch dashboard for any school by id
    path('<uuid:school_id>/dashboard/', SchoolAdminDashboardView.as_view(), name='school_admin_dashboard'),

    # ==================== MONITORING & ALERTS ENDPOINTS ====================
    path('alerts/', GlobalAlertsView.as_view(), name='global_alerts'),
    path('<uuid:school_id>/monitoring/', SchoolMonitoringView.as_view(), name='school_monitoring'),
    path('<uuid:school_id>/notifications/', SchoolNotificationsView.as_view(), name='school_notifications'),
    path('<uuid:school_id>/billing/', SchoolBillingView.as_view(), name='school_billing'),
    path('<uuid:school_id>/billing/topup/', SchoolBillingTopUpView.as_view(), name='school_billing_topup'),
    path('<uuid:school_id>/onboard-orientation/', SchoolOrientationOnboardView.as_view(), name='school_onboard_orientation'),
    path('<uuid:school_id>/reset-data/', SchoolResetDataView.as_view(), name='school_reset_data'),
]