from django.urls import path
from .views import (
    AIRequestView,
    AILogListView,
    AILogDetailView,
    AdminDashboardView,
    ToolAnalyticsView,
    UserAnalyticsView,
    AvailableToolsView,
    ToolListView,
    ToolDetailView,
    ToolCategoryListView,
    ToolCategoryDetailView,
    ToolRecommendedView,
    ToolFavoritesListView,
    ToolFavoriteToggleView
    , ChatAPIView, ChatDetailAPIView, ChatMessagesAPIView, ChatReplyAPIView
)

app_name = 'nibble_ai'

urlpatterns = [
    # Tool Categories
    path('categories/', ToolCategoryListView.as_view(), name='category-list'),
    path('categories/<int:category_id>/', ToolCategoryDetailView.as_view(), name='category-detail'),
    
    # Tools
    path('', ToolListView.as_view(), name='tool-list'),
    path('<slug:tool_slug>/', ToolDetailView.as_view(), name='tool-detail'),
    path('recommended/', ToolRecommendedView.as_view(), name='tool-recommended'),
    path('my-favorites/', ToolFavoritesListView.as_view(), name='tool-favorites'),
    path('<slug:tool_slug>/favorite/', ToolFavoriteToggleView.as_view(), name='tool-favorite-toggle'),
    
    # Main AI Request endpoint
    path('request/', AIRequestView.as_view(), name='ai-request'),
    
    # User AI Logs
    path('logs/', AILogListView.as_view(), name='ai-logs-list'),
    path('logs/<int:log_id>/', AILogDetailView.as_view(), name='ai-log-detail'),
    
    # Available Tools
    path('available-tools/', AvailableToolsView.as_view(), name='available-tools'),
    # Chat API for AI-powered teaching assistant
    path('chats/', ChatAPIView.as_view(), name='chat-api'),
    path('chats/<uuid:session_id>/', ChatDetailAPIView.as_view(), name='chat-detail'),
    path('chats/<uuid:session_id>/messages/', ChatMessagesAPIView.as_view(), name='chat-messages'),
    path('chats/<uuid:session_id>/reply/', ChatReplyAPIView.as_view(), name='chat-reply'),
    
    # Admin Analytics
    path('admin/dashboard/', AdminDashboardView.as_view(), name='admin-dashboard'),
    path('admin/tools/', ToolAnalyticsView.as_view(), name='tool-analytics'),
    path('admin/users/', UserAnalyticsView.as_view(), name='user-analytics'),
]
