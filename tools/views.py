from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from django.db.models import Sum, Count, Avg, F, Max
from django.db.models.functions import TruncDate
from django.utils import timezone
from datetime import datetime, timedelta
from decimal import Decimal
from openai import OpenAI
import time
import os
from django.conf import settings
from django.shortcuts import get_object_or_404
from authentication.permissions import *
from .models import (
    AILog, AITool, UserAIUsage, ToolCategory, ToolInput, ToolFavorite,
    ChatSession, ChatMessage
)
from schools.service import (
    check_long_request_limit,
    ensure_credits_and_deduct,
)
from .serializers import *
from .serializers import ChatSessionSerializer, ChatMessageSerializer
from .service import  DynamicPromptBuilder, AIProviderRouter, get_provider_router, estimate_tokens


# ================== TOOL CATEGORY ENDPOINTS ==================

class ToolCategoryListView(APIView):
    """
    Get all tool categories
    GET /api/v1/tools/categories/
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        categories = ToolCategory.objects.all()
        serializer = ToolCategorySerializer(categories, many=True)
        return Response(serializer.data)


class ToolCategoryDetailView(APIView):
    """
    Get single tool category
    GET /api/v1/tools/categories/{id}/
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request, category_id):
        category = get_object_or_404(ToolCategory, id=category_id)
        serializer = ToolCategorySerializer(category)
        return Response(serializer.data)


# ================== TOOL ENDPOINTS ==================

class ToolListView(APIView):
    """
    List all tools with filters
    GET /api/v1/tools/
    Query params: category, type (student/teacher), recommended
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        queryset = AITool.objects.filter(is_active=True).prefetch_related(
            'inputs', 'categories'
        )
        
        # Filter by category
        category_id = request.query_params.get('category')
        if category_id:
            queryset = queryset.filter(categories__id=category_id)
        
        # Filter by type (student/teacher)
        tool_type = request.query_params.get('type')
        if tool_type:
            queryset = queryset.filter(categories__type=tool_type)
        
        # Filter recommended
        if request.query_params.get('recommended') == 'true':
            queryset = queryset.filter(is_recommended=True)
        
        serializer = ToolListSerializer(queryset, many=True, context={'request': request})
        return Response({
            'count': queryset.count(),
            'results': serializer.data
        })


class ToolDetailView(APIView):
    """
    Get tool details with inputs
    GET /api/v1/tools/{slug}/
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request, tool_slug):
        tool = get_object_or_404(AITool, slug=tool_slug, is_active=True)
        serializer = ToolDetailSerializer(tool, context={'request': request})
        return Response(serializer.data)


class ToolRecommendedView(APIView):
    """
    Get recommended tools
    GET /api/v1/tools/recommended/
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        tools = AITool.objects.filter(is_recommended=True, is_active=True)[:5]
        serializer = ToolListSerializer(tools, many=True, context={'request': request})
        return Response({
            'count': len(serializer.data),
            'results': serializer.data
        })


class ToolFavoritesListView(APIView):
    """
    Get user's favorite tools
    GET /api/v1/tools/my-favorites/
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        favorites = ToolFavorite.objects.filter(user=request.user).select_related('tool')
        serializer = ToolFavoriteSerializer(favorites, many=True, context={'request': request})
        return Response({
            'count': len(serializer.data),
            'results': serializer.data
        })


class ToolFavoriteToggleView(APIView):
    """
    Add/Remove tool from favorites
    POST /api/v1/tools/{slug}/favorite/  - Add to favorites
    DELETE /api/v1/tools/{slug}/favorite/ - Remove from favorites
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request, tool_slug):
        tool = get_object_or_404(AITool, slug=tool_slug)
        favorite, created = ToolFavorite.objects.get_or_create(user=request.user, tool=tool)
        
        return Response(
            {
                'detail': 'Added to favorites',
                'is_favorited': True,
                'favorites_count': tool.get_favorites_count()
            },
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK
        )
    
    def delete(self, request, tool_slug):
        tool = get_object_or_404(AITool, slug=tool_slug)
        ToolFavorite.objects.filter(user=request.user, tool=tool).delete()
        
        return Response(
            {
                'detail': 'Removed from favorites',
                'is_favorited': False,
                'favorites_count': tool.get_favorites_count()
            },
            status=status.HTTP_200_OK
        )


# ================== MAIN AI REQUEST VIEW ==================

class AIRequestView(APIView):
    """
    Main view to handle all AI requests with dynamic tool configuration
    and automatic AI provider switching (OpenAI/DeepSeek)
    
    POST: Send AI request and get response
    Accepts:
      - tool_id: (int) ID of the AITool to use (NEW - overrides 'tool' field)
      - tool_slug: (str) slug of the AITool to use (NEW - alternative to ID)
      - tool: (str) Tool name string (LEGACY - for backward compatibility)
      - inputs: (dict) Dynamic input fields based on tool configuration
      - provider: (str) Preferred provider: 'openai', 'deepseek' (optional, auto-switches on failure)
      - Additional fields for backward compatibility (topic, class_level, etc.)
    """
    permission_classes = [IsAuthenticated]
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.prompt_builder = DynamicPromptBuilder()
        self.provider_router = get_provider_router()
    
    def post(self, request):
        """Handle AI request with dynamic tool configuration and provider switching"""
        
        # Validate request data
        serializer = AIRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                'success': False,
                'message': 'Invalid request data',
                'errors': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        validated_data = serializer.validated_data
        
        try:
            # Ensure user is authenticated
            if not (hasattr(request, 'user') and request.user and request.user.is_authenticated):
                return Response({'success': False, 'message': 'Authentication required'}, status=status.HTTP_401_UNAUTHORIZED)

            user = request.user
            
            # Step 1: Determine tool and build prompt
            tool_id = request.data.get('tool_id')
            tool_slug = validated_data.get('tool_slug')
            tool_name = validated_data.get('tool')
            provider = request.data.get('provider')  # Preferred provider (optional)
            
            if tool_id or tool_slug:
                # NEW: Dynamic tool configuration based on identifier
                try:
                    if tool_id:
                        tool_obj = AITool.objects.get(id=tool_id, is_active=True)
                    else:
                        tool_obj = AITool.objects.get(slug=tool_slug, is_active=True)
                except AITool.DoesNotExist:
                    missing = tool_id if tool_id else tool_slug
                    return Response({
                        'success': False,
                        'message': f'Tool with identifier {missing} not found'
                    }, status=status.HTTP_404_NOT_FOUND)
                
                # Build prompt dynamically from tool configuration
                user_inputs = request.data.get('inputs', {})
                system_prompt, user_prompt, full_prompt = self.prompt_builder.build_from_tool_config(tool_obj, user_inputs)
                prompt = full_prompt
                tool_for_logging = tool_obj.name
            else:
                # LEGACY: Use tool name string
                if not tool_name:
                    return Response({
                        'success': False,
                        'message': 'Either tool_id or tool must be provided'
                    }, status=status.HTTP_400_BAD_REQUEST)
                
                # Build prompt from legacy fields (topic, class_level, difficulty, content, etc.)
                prompt_parts = []
                if validated_data.get('topic'):
                    prompt_parts.append(f"Topic: {validated_data['topic']}")
                if validated_data.get('class_level'):
                    prompt_parts.append(f"Class Level: {validated_data['class_level']}")
                if validated_data.get('difficulty'):
                    prompt_parts.append(f"Difficulty: {validated_data['difficulty']}")
                if validated_data.get('content'):
                    prompt_parts.append(f"Content: {validated_data['content']}")
                if validated_data.get('num_questions'):
                    prompt_parts.append(f"Number of Questions: {validated_data['num_questions']}")
                if validated_data.get('question_type'):
                    prompt_parts.append(f"Question Type: {validated_data['question_type']}")
                
                prompt = "\n".join(prompt_parts) if prompt_parts else "Please process the request"
                tool_for_logging = tool_name
            
            # Estimate token usage
            estimated_tokens = estimate_tokens(prompt)
            
            # Pre-check subscription / per-request limits
            try:
                check_long_request_limit(user, estimated_tokens)
            except Exception as e:
                return Response({'success': False, 'message': str(e)}, status=status.HTTP_403_FORBIDDEN)
            
            # Step 2: Call AI provider (with automatic switching)
            start_time = time.time()
            if tool_id and 'system_prompt' in locals():
                # Use separated prompts for tool_id requests
                result = self.provider_router.call_ai(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    provider=provider,
                    temperature=getattr(settings, 'OPENAI_TEMPERATURE', float(os.getenv('OPENAI_TEMPERATURE', 0.5))),
                    max_tokens=getattr(settings, 'OPENAI_MAX_TOKENS', int(os.getenv('OPENAI_MAX_TOKENS', 400)))
                )
            else:
                # Use combined prompt for legacy tool name requests
                result = self.provider_router.call_ai(
                    prompt=prompt,
                    provider=provider,
                    temperature=getattr(settings, 'OPENAI_TEMPERATURE', float(os.getenv('OPENAI_TEMPERATURE', 0.5))),
                    max_tokens=getattr(settings, 'OPENAI_MAX_TOKENS', int(os.getenv('OPENAI_MAX_TOKENS', 400)))
                )
            response_time = time.time() - start_time
            
            # Extract response data
            ai_response = result['response']
            prompt_tokens = result['usage']['prompt_tokens']
            completion_tokens = result['usage']['completion_tokens']
            total_tokens = result['usage']['total_tokens']
            ai_provider = result['provider']
            
            # Deduct credits from subscription
            try:
                ensure_credits_and_deduct(user, total_tokens)
            except Exception as e:
                return Response({'success': False, 'message': f'Billing failed: {str(e)}'}, status=status.HTTP_402_PAYMENT_REQUIRED)
            
            # Step 3: Log the request
            log = self._create_log(
                user=user,
                tool=tool_for_logging,
                topic=validated_data.get('topic', ''),
                class_level=validated_data.get('class_level', ''),
                difficulty=validated_data.get('difficulty', ''),
                prompt=prompt,
                response=ai_response,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                response_time=response_time,
                provider=ai_provider
            )
            
            # Step 4: Update user usage
            self._update_user_usage(user, log)
            
            # Step 5: Return response
            response_data = {
                'success': True,
                'data': ai_response,
                'tokens_used': total_tokens,
                'provider': ai_provider,
                'model': result.get('model'),
                'message': 'AI request completed successfully'
            }
            
            if log:
                response_data.update({
                    'log_id': log.id,
                    'cost': float(log.cost),
                })
            
            return Response(response_data, status=status.HTTP_200_OK)
        
        except Exception as e:
            return Response({
                'success': False,
                'message': f'Error processing AI request: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def _call_openai(self, prompt):
        """Call OpenAI API (LEGACY - use provider_router instead)"""
        completion = self.provider_router.openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a helpful educational assistant."},
                {"role": "user", "content": prompt}
            ],
            temperature=getattr(settings, 'OPENAI_TEMPERATURE', float(os.getenv('OPENAI_TEMPERATURE', 0.5))),
            max_tokens=getattr(settings, 'OPENAI_MAX_TOKENS', int(os.getenv('OPENAI_MAX_TOKENS', 400)))
        )
        return completion
    
    def _create_log(self, user, tool, topic, class_level, difficulty, 
                    prompt, response, prompt_tokens, completion_tokens, response_time, provider='openai'):
        """Create AI log entry with provider information"""
        log = AILog.objects.create(
            user=user,
            tool=tool,
            topic=topic,
            class_level=class_level,
            difficulty=difficulty,
            prompt=prompt,
            response=response,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            response_time=response_time,
            provider=provider
        )
        return log
    
    def _update_user_usage(self, user, log):
        """Update or create user AI usage record"""
        usage, created = UserAIUsage.objects.get_or_create(user=user)
        usage.total_requests += 1
        usage.total_tokens += log.total_tokens
        usage.total_cost += log.cost
        usage.last_request_at = timezone.now()
        usage.save()


# ================== AI LOGS VIEW ==================

class AILogListView(APIView):
    """
    GET: List all AI logs for the authenticated user
    """
    authentication_classes = []
    permission_classes = []
    
    def get(self, request):
        
        """Get user's AI logs"""
        # Check authentication
        user = request.user if hasattr(request, 'user') and request.user and request.user.is_authenticated else None
        
        
        logs = AILog.objects.filter(user=user)
        
        # Filter by tool if provided
        tool = request.query_params.get('tool')
        if tool:
            logs = logs.filter(tool=tool)
        
        # Filter by date range if provided
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        if start_date:
            logs = logs.filter(created_at__gte=start_date)
        if end_date:
            logs = logs.filter(created_at__lte=end_date)
        
        # Pagination
        page = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('page_size', 20))
        start = (page - 1) * page_size
        end = start + page_size
        
        total_count = logs.count()
        logs = logs[start:end]
        
        serializer = AILogListSerializer(logs, many=True)
        
        return Response({
            'success': True,
            'count': total_count,
            'page': page,
            'page_size': page_size,
            'results': serializer.data
        }, status=status.HTTP_200_OK)


class AILogDetailView(APIView):
    """
    GET: Get detailed view of a specific AI log
    """
    authentication_classes = []
    permission_classes = []
    
    def get(self, request, log_id):
        """Get specific log details"""
        # Check authentication
        user = None
        if hasattr(request, 'user') and request.user and request.user.is_authenticated:
            user = request.user
        elif hasattr(request, 'student') and request.student:
            # SSO students don't have AI logs
            return Response({
                'success': False,
                'message': 'AI logs not available for SSO students'
            }, status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response({
                'success': False,
                'message': 'Authentication required'
            }, status=status.HTTP_401_UNAUTHORIZED)
        
        try:
            log = AILog.objects.get(id=log_id, user=user)
            serializer = AILogSerializer(log)
            return Response({
                'success': True,
                'data': serializer.data
            }, status=status.HTTP_200_OK)
        except AILog.DoesNotExist:
            return Response({
                'success': False,
                'message': 'Log not found'
            }, status=status.HTTP_404_NOT_FOUND)


# ================== ADMIN ANALYTICS VIEWS ==================

class AdminDashboardView(APIView):
    """
    GET: Get comprehensive admin analytics
    """
    
    permission_classes = [IsAdmin]
    
    def get(self, request):
        """Get admin dashboard data"""
        # Get period parameter (default: last 30 days)
        period = request.query_params.get('period', '30days')
        
        # Calculate date range
        if period == '7days':
            start_date = timezone.now() - timedelta(days=7)
        elif period == '30days':
            start_date = timezone.now() - timedelta(days=30)
        elif period == '90days':
            start_date = timezone.now() - timedelta(days=90)
        elif period == 'all':
            start_date = None
        else:
            start_date = timezone.now() - timedelta(days=30)
        
        # Filter logs
        logs = AILog.objects.all()
        if start_date:
            logs = logs.filter(created_at__gte=start_date)
        
        # Overall metrics
        overall_stats = logs.aggregate(
            total_requests=Count('id'),
            total_tokens=Sum('total_tokens'),
            total_cost=Sum('cost')
        )
        
        # Cost per tool
        cost_per_tool = logs.values('tool').annotate(
            total_requests=Count('id'),
            total_tokens_sum=Sum('total_tokens'),
            total_cost=Sum('cost'),
            avg_tokens=Avg('total_tokens')
        ).order_by('-total_cost')
        
        # Top users
        top_users = logs.values(
            'user__username',
            'user__email'
        ).annotate(
            total_requests=Count('id'),
            total_tokens=Sum('total_tokens'),
            total_cost=Sum('cost'),
            last_request=Max('created_at')
        ).order_by('-total_cost')[:10]
        
        # Daily breakdown
        daily_breakdown = logs.annotate(
            date=TruncDate('created_at')
        ).values('date').annotate(
            requests=Count('id'),
            tokens=Sum('total_tokens'),
            cost=Sum('cost')
        ).order_by('-date')[:30]
        
        return Response({
            'success': True,
            'period': period,
            'overall': {
                'total_requests': overall_stats['total_requests'] or 0,
                'total_tokens': overall_stats['total_tokens'] or 0,
                'total_cost': float(overall_stats['total_cost'] or 0),
            },
            'cost_per_tool': [{**item, 'total_tokens': item['total_tokens_sum']} for item in cost_per_tool],
            'top_users': list(top_users),
            'daily_breakdown': list(daily_breakdown)
        }, status=status.HTTP_200_OK)


class ToolAnalyticsView(APIView):
    """
    GET: Get analytics per tool
    """
    permission_classes = [IsAdmin]
    
    def get(self, request):
        """Get tool-specific analytics"""
        tool = request.query_params.get('tool')
        period = request.query_params.get('period', '30days')
        
        # Calculate date range
        if period == '7days':
            start_date = timezone.now() - timedelta(days=7)
        elif period == '30days':
            start_date = timezone.now() - timedelta(days=30)
        elif period == '90days':
            start_date = timezone.now() - timedelta(days=90)
        else:
            start_date = None
        
        logs = AILog.objects.all()
        if start_date:
            logs = logs.filter(created_at__gte=start_date)
        if tool:
            logs = logs.filter(tool=tool)
        
        stats = logs.aggregate(
            total_requests=Count('id'),
            total_tokens_sum=Sum('total_tokens'),
            total_cost=Sum('cost'),
            avg_tokens=Avg('total_tokens'),
            avg_response_time=Avg('response_time'))
        stats['total_tokens'] = stats.pop('total_tokens_sum')
        
        return Response({
            'success': True,
            'tool': tool or 'all',
            'period': period,
            'stats': stats
        }, status=status.HTTP_200_OK)


class UserAnalyticsView(APIView):
    """
    GET: Get analytics per user
    """
    permission_classes = [IsAdmin]
    
    def get(self, request):
        """Get user-specific analytics"""
        user_id = request.query_params.get('user_id')
        period = request.query_params.get('period', '30days')
        
        # Calculate date range
        if period == '7days':
            start_date = timezone.now() - timedelta(days=7)
        elif period == '30days':
            start_date = timezone.now() - timedelta(days=30)
        elif period == '90days':
            start_date = timezone.now() - timedelta(days=90)
        else:
            start_date = None
        
        logs = AILog.objects.all()
        if start_date:
            logs = logs.filter(created_at__gte=start_date)
        if user_id:
            logs = logs.filter(user_id=user_id)
        
        # User stats
        stats = logs.values(
            'user__id',
            'user__username',
            'user__email'
        ).annotate(
            total_requests=Count('id'),
            total_tokens=Sum('total_tokens'),
            total_cost=Sum('cost'),
            last_request=Max('created_at')
        )
        
        # Tool breakdown for user
        tool_breakdown = logs.values('tool').annotate(
            requests=Count('id'),
            tokens=Sum('total_tokens'),
            cost=Sum('cost')
        ).order_by('-requests')
        
        return Response({
            'success': True,
            'period': period,
            'user_stats': list(stats),
            'tool_breakdown': list(tool_breakdown)
        }, status=status.HTTP_200_OK)


# ================== AVAILABLE TOOLS VIEW ==================

class AvailableToolsView(APIView):
    """
    GET: List all available AI tools
    """
    authentication_classes = []
    permission_classes = []
    
    def get(self, request):
        """Get list of available tools"""
        # Check authentication
        if not (hasattr(request, 'user') and request.user) and not (hasattr(request, 'student') and request.student):
            return Response({
                'success': False,
                'message': 'Authentication required'
            }, status=status.HTTP_401_UNAUTHORIZED)
        
        tools = AITool.objects.filter(is_active=True)
        serializer = ToolListSerializer(tools, many=True)
        return Response({
            'success': True,
            'tools': serializer.data
        }, status=status.HTTP_200_OK)



class ChatAPIView(APIView):
    """Handle creating/appending chat messages and listing chat sessions.

    POST /api/v1/tools/chats/ - create or append to a session. Payload:
      - session_id (optional): UUID of existing session
      - message: user message text

    GET /api/v1/tools/chats/ - list all chat sessions with messages
    """
    permission_classes = [IsAuthenticated]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        api_key = getattr(settings, 'OPENAI_API_KEY', os.getenv('OPENAI_API_KEY', None))
        self.client = OpenAI(api_key=api_key)

    def get(self, request):
        sessions = ChatSession.objects.all().select_related('user').prefetch_related('messages')
        serializer = ChatSessionSerializer(sessions, many=True, context={'request': request})
        return Response(serializer.data)

    def post(self, request):
        data = request.data
        user = request.user if hasattr(request, 'user') and request.user.is_authenticated else None

        message_text = data.get('message')
        if not message_text:
            return Response({'detail': 'Field "message" is required.'}, status=status.HTTP_400_BAD_REQUEST)

        session_id = data.get('session_id')

        # Create or fetch session
        if session_id:
            try:
                session = ChatSession.objects.get(session_id=session_id)
            except ChatSession.DoesNotExist:
                return Response({'detail': 'Session not found.'}, status=status.HTTP_404_NOT_FOUND)
        else:
            session = ChatSession.objects.create(user=user)
            # Add an initial system message and assistant greeting
            ChatMessage.objects.create(session=session, role=ChatMessage.ROLE_SYSTEM, content=getattr(settings, 'CHAT_SYSTEM_PROMPT', 'You are a helpful teaching assistant.'))
            ChatMessage.objects.create(session=session, role=ChatMessage.ROLE_ASSISTANT, content=getattr(settings, 'CHAT_ASSISTANT_GREETING', 'Hello — I am your teaching assistant. How can I help you today?'))

        # Append user message
        user_msg = ChatMessage.objects.create(session=session, role=ChatMessage.ROLE_USER, content=message_text)

        # Build messages for OpenAI from full history (ordered)
        history = []
        for msg in session.messages.order_by('created_at', 'id'):
            history.append({'role': msg.role, 'content': msg.content})

        # Call OpenAI chat completion
        try:
            completion = self.client.chat.completions.create(
                model=getattr(settings, 'OPENAI_MODEL', 'gpt-4o-mini'),
                messages=history,
                temperature=getattr(settings, 'OPENAI_TEMPERATURE', float(os.getenv('OPENAI_TEMPERATURE', 0.2))),
                max_tokens=getattr(settings, 'OPENAI_MAX_TOKENS', int(os.getenv('OPENAI_MAX_TOKENS', 512)))
            )

            assistant_content = ''
            # Safely extract assistant content
            if hasattr(completion, 'choices') and len(completion.choices) > 0:
                choice = completion.choices[0]
                # New SDK shape: choice.message.content
                assistant_content = getattr(getattr(choice, 'message', None), 'content', None) or getattr(choice, 'text', '')

            # Store assistant response
            if assistant_content is None:
                assistant_content = ''

            ChatMessage.objects.create(session=session, role=ChatMessage.ROLE_ASSISTANT, content=assistant_content)

        except Exception as e:
            return Response({'detail': f'OpenAI request failed: {str(e)}'}, status=status.HTTP_502_BAD_GATEWAY)

        # Refresh session and return full serialized chat
        session.refresh_from_db()
        serializer = ChatSessionSerializer(session, context={'request': request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class ChatDetailAPIView(APIView):
    """Retrieve, update (title), or delete a chat session."""
    permission_classes = [IsAuthenticated]

    def get_object(self, session_id):
        return get_object_or_404(ChatSession, session_id=session_id)

    def get(self, request, session_id):
        session = self.get_object(session_id)
        serializer = ChatSessionSerializer(session, context={'request': request})
        return Response(serializer.data)

    def patch(self, request, session_id):
        session = self.get_object(session_id)
        # Only owner or staff may update
        if session.user and session.user != request.user and not request.user.is_staff:
            return Response({'detail': 'Permission denied.'}, status=status.HTTP_403_FORBIDDEN)

        title = request.data.get('title')
        if title is not None:
            session.title = title
            session.save()

        serializer = ChatSessionSerializer(session, context={'request': request})
        return Response(serializer.data)

    def delete(self, request, session_id):
        session = self.get_object(session_id)
        if session.user and session.user != request.user and not request.user.is_staff:
            return Response({'detail': 'Permission denied.'}, status=status.HTTP_403_FORBIDDEN)
        session.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ChatMessagesAPIView(APIView):
    """List messages for a chat session (paginated, chronological)."""
    permission_classes = [IsAuthenticated]

    def get(self, request, session_id):
        session = get_object_or_404(ChatSession, session_id=session_id)
        # Ensure requester is owner or staff
        if session.user and session.user != request.user and not request.user.is_staff:
            return Response({'detail': 'Permission denied.'}, status=status.HTTP_403_FORBIDDEN)

        page = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('page_size', 50))
        start = (page - 1) * page_size
        end = start + page_size

        qs = session.messages.order_by('created_at', 'id')
        total = qs.count()
        msgs = qs[start:end]

        serializer = ChatMessageSerializer(msgs, many=True)
        return Response({'count': total, 'page': page, 'page_size': page_size, 'results': serializer.data})


class ChatReplyAPIView(APIView):
    """Append a user message to a session and return the assistant reply."""
    permission_classes = [IsAuthenticated]

    def post(self, request, session_id):
        session = get_object_or_404(ChatSession, session_id=session_id)
        if session.user and session.user != request.user and not request.user.is_staff:
            return Response({'detail': 'Permission denied.'}, status=status.HTTP_403_FORBIDDEN)

        message_text = request.data.get('message')
        if not message_text:
            return Response({'detail': 'Field "message" is required.'}, status=status.HTTP_400_BAD_REQUEST)

        # Append user message
        ChatMessage.objects.create(session=session, role=ChatMessage.ROLE_USER, content=message_text)

        # Build history and call OpenAI
        history = [{'role': msg.role, 'content': msg.content} for msg in session.messages.order_by('created_at', 'id')]

        try:
            completion = self.client.chat.completions.create(
                model=getattr(settings, 'OPENAI_MODEL', 'gpt-4o-mini'),
                messages=history,
                temperature=getattr(settings, 'OPENAI_TEMPERATURE', float(os.getenv('OPENAI_TEMPERATURE', 0.2))),
                max_tokens=getattr(settings, 'OPENAI_MAX_TOKENS', int(os.getenv('OPENAI_MAX_TOKENS', 512)))
            )

            assistant_content = ''
            if hasattr(completion, 'choices') and len(completion.choices) > 0:
                choice = completion.choices[0]
                assistant_content = getattr(getattr(choice, 'message', None), 'content', None) or getattr(choice, 'text', '')

            ChatMessage.objects.create(session=session, role=ChatMessage.ROLE_ASSISTANT, content=assistant_content)

        except Exception as e:
            return Response({'detail': f'OpenAI request failed: {str(e)}'}, status=status.HTTP_502_BAD_GATEWAY)

        session.refresh_from_db()
        serializer = ChatSessionSerializer(session, context={'request': request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)
