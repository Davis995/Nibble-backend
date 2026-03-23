"""
Test cases for Nibble AI System
Run with: pytest
"""

import pytest
from django.contrib.auth.models import User
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from decimal import Decimal
from unittest.mock import patch, MagicMock

from .models import AILog, AITool, UserAIUsage


@pytest.fixture
def api_client():
    """Create an API client"""
    return APIClient()


@pytest.fixture
def user(db):
    """Create a test user"""
    return User.objects.create_user(
        username='testuser',
        email='test@example.com',
        password='testpass123'
    )


@pytest.fixture
def admin_user(db):
    """Create an admin user"""
    return User.objects.create_superuser(
        username='admin',
        email='admin@example.com',
        password='adminpass123'
    )


@pytest.fixture
def ai_tool(db):
    """Create an AI tool"""
    return AITool.objects.create(
            slug='topic-explainer',
            name='topic_explainer',
            student_friendly_name='Topic Explainer',

@pytest.fixture
def ai_log(db, user):
    """Create an AI log"""
    return AILog.objects.create(
        user=user,
        tool='topic_explainer',
        topic='Photosynthesis',
        class_level='Primary 6',
        prompt='Test prompt',
        response='Test response',
        prompt_tokens=100,
        completion_tokens=200
    )


@pytest.mark.django_db
class TestAIRequestView:
    """Tests for AI Request View"""
    
    def test_request_without_auth(self, api_client):
        """Test that unauthenticated requests are rejected"""
        url = reverse('nibble_ai:ai-request')
        data = {
            'tool': 'topic_explainer',
            'topic': 'Photosynthesis',
            'class_level': 'Primary 6'
        }
        response = api_client.post(url, data, format='json')
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
    
    def test_request_with_auth_invalid_data(self, api_client, user):
        """Test request with invalid data"""
        api_client.force_authenticate(user=user)
        url = reverse('nibble_ai:ai-request')
        data = {
            'tool': 'topic_explainer',
            # Missing required 'topic' field
            'class_level': 'Primary 6'
        }
        response = api_client.post(url, data, format='json')
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'errors' in response.data
    
    @patch('openai.ChatCompletion.create')
    def test_request_with_valid_data(self, mock_openai, api_client, user):
        """Test successful AI request"""
        # Mock OpenAI response
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Photosynthesis is..."
        mock_response.usage.prompt_tokens = 100
        mock_response.usage.completion_tokens = 200
        mock_response.usage.total_tokens = 300
        mock_openai.return_value = mock_response
        
        api_client.force_authenticate(user=user)
        url = reverse('nibble_ai:ai-request')
        data = {
            'tool': 'topic_explainer',
            'topic': 'Photosynthesis',
            'class_level': 'Primary 6',
            'difficulty': 'medium'
        }
        
        response = api_client.post(url, data, format='json')
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['success'] is True
        assert 'data' in response.data
        assert 'log_id' in response.data
        assert 'tokens_used' in response.data
        assert 'cost' in response.data
        
        # Verify log was created
        assert AILog.objects.filter(user=user).count() == 1
        log = AILog.objects.first()
        assert log.tool == 'topic_explainer'
        assert log.topic == 'Photosynthesis'
        assert log.total_tokens == 300
    
    @patch('openai.ChatCompletion.create')
    def test_summarizer_tool(self, mock_openai, api_client, user):
        """Test summarizer tool"""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Summary text..."
        mock_response.usage.prompt_tokens = 150
        mock_response.usage.completion_tokens = 100
        mock_response.usage.total_tokens = 250
        mock_openai.return_value = mock_response
        
        api_client.force_authenticate(user=user)
        url = reverse('nibble_ai:ai-request')
        data = {
            'tool': 'summarizer',
            'content': 'Long text to summarize...',
            'class_level': 'Primary 5'
        }
        
        response = api_client.post(url, data, format='json')
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['success'] is True


@pytest.mark.django_db
class TestAILogViews:
    """Tests for AI Log Views"""
    
    def test_list_logs_without_auth(self, api_client):
        """Test that unauthenticated requests are rejected"""
        url = reverse('nibble_ai:ai-logs-list')
        response = api_client.get(url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
    
    def test_list_logs_with_auth(self, api_client, user, ai_log):
        """Test listing logs for authenticated user"""
        api_client.force_authenticate(user=user)
        url = reverse('nibble_ai:ai-logs-list')
        response = api_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['success'] is True
        assert response.data['count'] == 1
        assert len(response.data['results']) == 1
    
    def test_list_logs_filter_by_tool(self, api_client, user, ai_log):
        """Test filtering logs by tool"""
        # Create another log with different tool
        AILog.objects.create(
            user=user,
            tool='summarizer',
            topic='Test',
            class_level='Primary 6',
            prompt='Test',
            response='Test',
            prompt_tokens=50,
            completion_tokens=100
        )
        
        api_client.force_authenticate(user=user)
        url = reverse('nibble_ai:ai-logs-list')
        response = api_client.get(url, {'tool': 'topic_explainer'})
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['count'] == 1
        assert response.data['results'][0]['tool'] == 'topic_explainer'
    
    def test_get_log_detail(self, api_client, user, ai_log):
        """Test getting specific log detail"""
        api_client.force_authenticate(user=user)
        url = reverse('nibble_ai:ai-log-detail', args=[ai_log.id])
        response = api_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['success'] is True
        assert response.data['data']['id'] == ai_log.id
    
    def test_get_other_user_log(self, api_client, user, ai_log):
        """Test that users can't access other users' logs"""
        other_user = User.objects.create_user(
            username='other',
            email='other@example.com',
            password='pass123'
        )
        
        api_client.force_authenticate(user=other_user)
        url = reverse('nibble_ai:ai-log-detail', args=[ai_log.id])
        response = api_client.get(url)
        
        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
class TestAdminViews:
    """Tests for Admin Analytics Views"""
    
    def test_admin_dashboard_without_admin(self, api_client, user):
        """Test that non-admin users can't access admin dashboard"""
        api_client.force_authenticate(user=user)
        url = reverse('nibble_ai:admin-dashboard')
        response = api_client.get(url)
        assert response.status_code == status.HTTP_403_FORBIDDEN
    
    def test_admin_dashboard_with_admin(self, api_client, admin_user, ai_log):
        """Test admin dashboard access"""
        api_client.force_authenticate(user=admin_user)
        url = reverse('nibble_ai:admin-dashboard')
        response = api_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['success'] is True
        assert 'overall' in response.data
        assert 'cost_per_tool' in response.data
        assert 'top_users' in response.data
        assert 'daily_breakdown' in response.data
    
    def test_admin_dashboard_period_filter(self, api_client, admin_user, ai_log):
        """Test admin dashboard with period filter"""
        api_client.force_authenticate(user=admin_user)
        url = reverse('nibble_ai:admin-dashboard')
        response = api_client.get(url, {'period': '7days'})
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['period'] == '7days'
    
    def test_tool_analytics(self, api_client, admin_user, ai_log):
        """Test tool analytics endpoint"""
        api_client.force_authenticate(user=admin_user)
        url = reverse('nibble_ai:tool-analytics')
        response = api_client.get(url, {'tool': 'topic_explainer'})
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['success'] is True
        assert 'stats' in response.data
    
    def test_user_analytics(self, api_client, admin_user, user, ai_log):
        """Test user analytics endpoint"""
        api_client.force_authenticate(user=admin_user)
        url = reverse('nibble_ai:user-analytics')
        response = api_client.get(url, {'user_id': user.id})
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['success'] is True
        assert 'user_stats' in response.data
        assert 'tool_breakdown' in response.data


@pytest.mark.django_db
class TestModels:
    """Tests for Models"""
    
    def test_ailog_cost_calculation(self, user):
        """Test that cost is calculated correctly on save"""
        log = AILog.objects.create(
            user=user,
            tool='topic_explainer',
            topic='Test',
            class_level='Primary 6',
            prompt='Test prompt',
            response='Test response',
            prompt_tokens=1000,
            completion_tokens=2000
        )
        
        # Cost = (1000/1000000 * 0.15) + (2000/1000000 * 0.60)
        # Cost = 0.00015 + 0.0012 = 0.00135
        expected_cost = Decimal('0.001350')
        assert log.cost == expected_cost
        assert log.total_tokens == 3000
    
    def test_user_ai_usage_creation(self, user):
        """Test UserAIUsage creation"""
        usage, created = UserAIUsage.objects.get_or_create(user=user)
        assert created is True
        assert usage.total_requests == 0
        assert usage.total_tokens == 0
        assert usage.total_cost == 0
    
    def test_aitool_string_representation(self, ai_tool):
        """Test AITool string representation"""
        assert str(ai_tool) == 'Topic Explainer'

    def test_tool_list_view_search(self, api_client, user):
        """Test tool list search filtering works"""
        AITool.objects.create(
            slug='math-explainer',
            name='math_explainer',
            student_friendly_name='Math Explainer',
            description='Explain math concepts',
            is_active=True
        )
        AITool.objects.create(
            slug='science-helper',
            name='science_helper',
            student_friendly_name='Science Helper',
            description='Assist with science',
            is_active=True
        )

        api_client.force_authenticate(user=user)
        url = reverse('nibble_ai:tool-list')
        response = api_client.get(url, {'search': 'math'})

        assert response.status_code == status.HTTP_200_OK
        assert response.data['count'] == 1
        assert response.data['results'][0]['name'] == 'math_explainer'


@pytest.mark.django_db
class TestPromptBuilder:
    """Tests for Prompt Builder"""
    
    def test_topic_explainer_prompt(self):
        """Test topic explainer prompt generation"""
        from ..backend.tools.views import PromptBuilder
        builder = PromptBuilder()
        
        prompt = builder.topic_explainer(
            topic='Photosynthesis',
            class_level='Primary 6',
            difficulty='medium'
        )
        
        assert 'Photosynthesis' in prompt
        assert 'Primary 6' in prompt
        assert 'medium' in prompt
    
    def test_summarizer_prompt(self):
        """Test summarizer prompt generation"""
        from views import PromptBuilder
        builder = PromptBuilder()
        
        prompt = builder.summarizer(
            content='Long text here...',
            class_level='Primary 5'
        )
        
        assert 'summarize' in prompt.lower()
        assert 'Primary 5' in prompt
        assert 'Long text here...' in prompt
    
    def test_question_generator_prompt(self):
        """Test question generator prompt generation"""
        from views import PromptBuilder
        builder = PromptBuilder()
        
        prompt = builder.question_generator(
            topic='Science',
            class_level='Secondary 2',
            num_questions=10,
            question_type='multiple_choice'
        )
        
        assert 'Science' in prompt
        assert 'Secondary 2' in prompt
        assert '10' in prompt
        assert 'multiple_choice' in prompt
