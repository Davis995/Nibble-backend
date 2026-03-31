from django.urls import path
from . import views

app_name = 'leads'

urlpatterns = [
    # Lead CRUD
    path('', views.LeadListCreateView.as_view(), name='lead-list-create'),
    path('export/csv/', views.LeadExportCSVView.as_view(), name='lead-export-csv'),
    path('<uuid:lead_id>/', views.LeadDetailView.as_view(), name='lead-detail'),
    path('<uuid:lead_id>/assign/', views.LeadAssignView.as_view(), name='lead-assign'),
    path('<uuid:lead_id>/convert/', views.LeadConvertView.as_view(), name='lead-convert'),
    path('<uuid:lead_id>/status/', views.LeadStatusUpdateView.as_view(), name='lead-status-update'),
    path('<uuid:lead_id>/notes/', views.LeadAddNoteView.as_view(), name='lead-add-note'),
    
    # Demo Schedule CRUD
    path('demo-schedules/', views.DemoScheduleListCreateView.as_view(), name='demo-schedule-list-create'),
    path('demo-schedules/<int:schedule_id>/', views.DemoScheduleDetailView.as_view(), name='demo-schedule-detail'),
    # Demos public API (alias paths matching 03_Demos.md)
    path('demos/', views.DemoScheduleListCreateView.as_view(), name='demos-list'),
    path('demos/<int:schedule_id>/', views.DemoScheduleDetailView.as_view(), name='demos-detail'),
    path('demos/<int:schedule_id>/status/', views.DemoStatusUpdateView.as_view(), name='demos-status'),
    path('demos/calendar/', views.DemosCalendarView.as_view(), name='demos-calendar'),
    path('demos/upcoming/', views.DemosUpcomingView.as_view(), name='demos-upcoming'),
    path('demos/<int:schedule_id>/attendees/', views.DemoAttendeesView.as_view(), name='demos-attendees'),
    
    # Notification CRUD
    path('notifications/', views.NotificationListView.as_view(), name='notification-list'),
    path('notifications/unread/', views.UnreadNotificationsView.as_view(), name='unread-notifications'),
    path('notifications/<int:notification_id>/read/', views.NotificationMarkReadView.as_view(), name='notification-mark-read'),
    path('notifications/read-all/', views.NotificationMarkAllReadView.as_view(), name='notification-mark-all-read'),
    
    # Onboarding CRUD
    path('onboardings/', views.OnboardingListView.as_view(), name='onboarding-list'),
    path('onboardings/<int:onboarding_id>/', views.OnboardingDetailView.as_view(), name='onboarding-detail'),
    
    # Logs CRUD
    path('logs/', views.LogsListView.as_view(), name='logs-list'),

    # Dashboard endpoints
    path('dashboard/kpi/', views.DashboardKPIView.as_view(), name='dashboard-kpi'),
    path('dashboard/leads-status/', views.DashboardLeadsStatusView.as_view(), name='dashboard-leads-status'),
    path('dashboard/upcoming-demos/', views.DashboardUpcomingDemosView.as_view(), name='dashboard-upcoming-demos'),
    path('dashboard/activity/', views.DashboardActivityView.as_view(), name='dashboard-activity'),
    
    # Activities & Analytics
    path('activities/', views.ActivityListView.as_view(), name='activities-list'),
    path('users/sales/', views.SalesUsersListView.as_view(), name='users-sales'),
    path('analytics/', views.AnalyticsView.as_view(), name='analytics'),
]