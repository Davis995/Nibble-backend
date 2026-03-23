from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, IsAdminUser


# from tools.models import AITool
# tool = AITool.objects.get(slug="Scaffold")
# tool.icon="FileText"
# tool.save()






# Modal token/credit weights mapping
# Each modal: input_token_weight, output_token_weight, min_charge, credit_multiplier, enterprise_discount
MODAL_CREDIT_RULES = {
    'deepseek-chat': {
        'input_token_weight': 1,
        'output_token_weight': 2,
        'min_charge': 50,
        'credit_multiplier': 1,  # 1 credit per input token, 2 per output
        'enterprise_discount': 0.2,  # 20% discount
    },
    'gpt-4o-mini': {
        'input_token_weight': 1,
        'output_token_weight': 1.5,
        'min_charge': 50,
        'credit_multiplier': 1,
        'enterprise_discount': 0.2,
    },
    'gpt-4': {
        'input_token_weight': 6,
        'output_token_weight': 6,
        'min_charge': 50,
        'credit_multiplier': 1,
        'enterprise_discount': 0.2,
    },
    'gpt-4.1': {
        'input_token_weight': 2,
        'output_token_weight': 4,
        'min_charge': 50,
        'credit_multiplier': 1,
        'enterprise_discount': 0.2,
    },
    'gpt-3.5': {
        'input_token_weight': 1,
        'output_token_weight': 1,
        'min_charge': 50,
        'credit_multiplier': 1,
        'enterprise_discount': 0.2,
    },
}
from django.db.models import Sum, Count, Avg, F, Max, Q
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
from authentication.models import Subscription
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

        # Search tools by name/description/student_friendly_name
        search = request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) |
                Q(description__icontains=search) |
                Q(student_friendly_name__icontains=search)
            )
        
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


class TeacherDashboardView(APIView):
    """Teacher dashboard data for frontend widgets"""
    permission_classes = [IsAuthenticated]

    def _serialize_tool_entry(self, tool):
        return {
            'id': tool.slug or str(tool.id),
            'name': tool.student_friendly_name or tool.name,
            'icon': tool.icon or 'FileText',
            'color': tool.color or 'bg-blue-500',
            'time': self._relative_time(tool.updated_at),
            'desc': tool.description or ''
        }

    def _relative_time(self, dt):
        if not dt:
            return 'Unknown'
        now = timezone.now()
        delta = now - dt
        if delta.days >= 1:
            return f"{delta.days} days ago"
        hours = delta.seconds // 3600
        if hours >= 1:
            return f"{hours} hours ago"
        minutes = delta.seconds // 60
        return f"{minutes} minutes ago" if minutes > 0 else 'just now'

    def get(self, request):
        # recent tools: based on the current authenticated user's recent AI usage
        recent_tools_qs = (
            AILog.objects.filter(user=request.user)
            .values('tool')
            .annotate(last_used=Max('created_at'))
            .order_by('-last_used')[:4]
        )
        recent_tool_names = [item['tool'] for item in recent_tools_qs]

        recent_tools = []
        if recent_tool_names:
            recent_qs = AITool.objects.filter(name__in=recent_tool_names, is_active=True)
            # preserve chronological order by names from logs
            name_to_obj = {tool.name: tool for tool in recent_qs}
            recent_tools = [self._serialize_tool_entry(name_to_obj[name]) for name in recent_tool_names if name in name_to_obj]

        # popular tools: recommended tools preferring top by updated_at, fallback to active
        popular_qs = AITool.objects.filter(is_active=True, is_recommended=True).order_by('-updated_at')[:6]
        if not popular_qs.exists():
            popular_qs = AITool.objects.filter(is_active=True).order_by('-updated_at')[:6]
        popular_tools = [self._serialize_tool_entry(tool) for tool in popular_qs]

        # categories: teacher-only categories
        categories_qs = ToolCategory.objects.filter(type='teacher').annotate(count=Count('tools'))
        categories = [
            {
                'name': cat.name,
                'count': cat.count,
                'icon': cat.icon or 'FileText',
                'color': 'from-blue-500 to-cyan-500'
            }
            for cat in categories_qs
        ]

        search_tools = [
            {'id': 'real-world-connections', 'name': 'Real World Connections', 'icon': 'Link', 'input_placeholder': 'Topic or concept', 'color': 'bg-emerald-500'},
            {'id': 'research-assistant', 'name': 'Research Assistant', 'icon': 'Search', 'input_placeholder': 'Research topic or question', 'color': 'bg-indigo-500'},
            {'id': 'rewrite-it', 'name': 'Rewrite It!', 'icon': 'Edit3', 'input_placeholder': 'Text to rewrite', 'color': 'bg-pink-500'},
            {'id': 'song-generator', 'name': 'Song Generator', 'icon': 'Music', 'input_placeholder': 'Song theme or topic', 'color': 'bg-amber-400'},
            {'id': 'translate-it', 'name': 'Translate It!', 'icon': 'Globe', 'input_placeholder': 'Text to translate', 'color': 'bg-sky-500'},
            {'id': 'summarize-it', 'name': 'Summarize It!', 'icon': 'FileText', 'input_placeholder': 'Text to summarize', 'color': 'bg-cyan-500'},
            {'id': '5-questions', 'name': '5 Questions', 'icon': 'QuestionMarkCircle', 'input_placeholder': 'Topic for questions', 'color': 'bg-teal-500'},
            {'id': 'book-suggestions', 'name': 'Book Suggestions', 'icon': 'BookOpen', 'input_placeholder': 'Genre or interest', 'color': 'bg-lime-500'},
            {'id': 'conceptual-understanding', 'name': 'Conceptual Understanding', 'icon': 'Lightbulb', 'input_placeholder': 'Concept area', 'color': 'bg-blue-500'},
            {'id': 'expand-on-idea', 'name': 'Expand on My Idea', 'icon': 'LayoutGrid', 'input_placeholder': 'Idea description', 'color': 'bg-orange-500'},
            {'id': 'idea-generator', 'name': 'Idea Generator', 'icon': 'Sparkles', 'input_placeholder': 'Topic or prompt', 'color': 'bg-violet-500'},
            {'id': 'informational-texts', 'name': 'Informational Texts', 'icon': 'AlignJustify', 'input_placeholder': 'Subject text', 'color': 'bg-fuchsia-500'},
            {'id': 'joke-creator', 'name': 'Joke Creator', 'icon': 'Smile', 'input_placeholder': 'Topic or keyword', 'color': 'bg-rose-500'},
            {'id': 'make-it-relevant', 'name': 'Make it Relevant!', 'icon': 'Heart', 'input_placeholder': 'Learning topic', 'color': 'bg-amber-500'},
            {'id': 'multiple-explanations', 'name': 'Multiple Explanations', 'icon': 'BookOpen', 'input_placeholder': 'Concept to explain', 'color': 'bg-sky-500'},
            {'id': 'quiz-me', 'name': 'Quiz Me!', 'icon': 'ClipboardCheck', 'input_placeholder': 'Topic to quiz', 'color': 'bg-lime-500'},
        ]

        student_qs = AITool.objects.filter(categories__type='student', is_active=True).order_by('-updated_at')[:40]
        student_tools = [
            {
                'id': tool.slug or str(tool.id),
                'name': tool.student_friendly_name or tool.name,
                'icon': tool.icon or 'BookOpen',
                'color': tool.color or 'bg-blue-100 text-blue-600',
                'desc': tool.description or '',
            }
            for tool in student_qs
        ]

        return Response({
            'success': True,
            'recent_tools': recent_tools,
            'popular_tools': popular_tools,
            'categories': categories,
            'search_tools': search_tools,
            'student_tools': student_tools,
        }, status=status.HTTP_200_OK)


class StudentDashboardView(APIView):
    """Student dashboard data for frontend widgets"""
    permission_classes = [IsAuthenticated]

    def _relative_time(self, dt):
        if not dt:
            return 'Unknown'
        now = timezone.now()
        delta = now - dt
        if delta.days >= 1:
            if delta.days == 1:
                return 'Yesterday'
            return f"{delta.days} days ago"
        hours = delta.seconds // 3600
        if hours >= 1:
            return f"{hours} hours ago"
        minutes = delta.seconds // 60
        return f"{minutes} minutes ago" if minutes > 0 else 'just now'

    def get(self, request):
        # 1. recommendedTools (about 9 items)
        recommended_qs = AITool.objects.filter(categories__type='student', is_active=True).order_by('-is_recommended', '-updated_at')[:9]
        
        recommendedTools = []
        for tool in recommended_qs:
            recommendedTools.append({
                'id': tool.slug or str(tool.id),
                'name': tool.student_friendly_name or tool.name,
                'icon': tool.icon or 'BookOpen',
                'color': tool.color or 'bg-blue-500',
                'desc': tool.description or ''
            })

        # 2. studentHistoryItems
        logs = AILog.objects.filter(user=request.user).order_by('-created_at')[:20]
        
        tool_names = [log.tool for log in logs]
        tools = AITool.objects.filter(name__in=tool_names).select_related('categories')
        tool_map = {t.name: t for t in tools}
        
        studentHistoryItems = []
        for log in logs:
            tool_obj = tool_map.get(log.tool)
            tool_slug = tool_obj.slug if tool_obj and tool_obj.slug else log.tool.lower().replace(' ', '-')
            tool_type = tool_obj.categories.name if tool_obj and getattr(tool_obj, 'categories', None) else 'General'
            
            formData = log.inputs or {}
            
            if not formData:
                if log.topic:
                    formData['topic'] = log.topic
                if log.class_level:
                    formData['grade'] = log.class_level
                if log.difficulty:
                    formData['difficulty'] = log.difficulty

            studentHistoryItems.append({
                'id': log.id,
                'toolId': tool_slug,
                'userId': f"student_{log.user.id}",
                'title': log.topic or f"{log.tool} Session",
                'type': tool_type,
                'date': self._relative_time(log.created_at),
                'toolName': log.tool,
                'formData': formData,
                'output': log.response
            })

        return Response({
            'success': True,
            'recommendedTools': recommendedTools,
            'studentHistoryItems': studentHistoryItems,
        }, status=status.HTTP_200_OK)


class ToolFavoritesListView(APIView):
    """
    Get or add user's favorite tools
    GET  /api/v1/tools/my-favorites/
    POST /api/v1/tools/my-favorites/
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        favorites = ToolFavorite.objects.filter(user=request.user).select_related('tool')
        serializer = ToolFavoriteSerializer(favorites, many=True, context={'request': request})
        return Response({
            'count': len(serializer.data),
            'results': serializer.data
        })
        
    def post(self, request):
        tool_slug = request.data.get('tool_slug') or request.data.get('slug') or request.data.get('toolId')
        if not tool_slug:
            return Response(
                {'detail': 'Tool slug must be provided in request body as tool_slug, slug, or toolId.'},
                status=status.HTTP_400_BAD_REQUEST
            )
            
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
            provider = request.data.get('provider')  # Preferred provider (optional)

            if not (tool_id or tool_slug):
                return Response({
                    'success': False,
                    'message': 'Either tool_id or tool_slug must be provided.'
                }, status=status.HTTP_400_BAD_REQUEST)

            # Dynamic tool configuration based on identifier
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
            try:
                system_prompt, user_prompt, full_prompt = self.prompt_builder.build_from_tool_config(tool_obj, user_inputs)
            except Exception as e:
                return Response({
                    'success': False,
                    'message': f'Error building prompt: {str(e)}'
                }, status=status.HTTP_400_BAD_REQUEST)
            prompt = full_prompt
            tool_for_logging = tool_obj.name

            # Modal selection logic
            plan = None
            subscription = None
            if hasattr(request.user, 'subscription_set'):
                subscription = request.user.subscription_set.filter(status='active').order_by('-created_at').first()
            elif hasattr(request.user, 'subscription'):
                subscription = request.user.subscription
            if subscription:
                plan = subscription.plan
            elif hasattr(request.user, 'subscription_plan') and request.user.subscription_plan:
                plan = request.user.subscription_plan

            allowed_modals = plan.allowed_modals if plan and hasattr(plan, 'allowed_modals') else []
            preferred_modal = tool_obj.preferred_modal or None
            selected_modal = None
            if preferred_modal and preferred_modal in allowed_modals:
                selected_modal = preferred_modal
            elif allowed_modals:
                selected_modal = allowed_modals[0]
            else:
                selected_modal = preferred_modal or 'gpt-3.5'  # fallback default


                # (Removed: credits calculation block is now after token estimation)

            # Map modal to provider
            modal_provider_map = {
                'gpt-4': 'openai',
                'gpt-4o-mini': 'openai',
                'gpt-3.5': 'openai',
                'deepseek-chat': 'deepseek',
            }
            provider = modal_provider_map.get(selected_modal, 'openai')
            model = selected_modal



            # Pre-check subscription / per-request limits (use estimate for pre-check only)
            try:
                token_info = estimate_tokens(prompt)
                # Handle both dict and int return types for estimate_tokens
                if isinstance(token_info, int):
                    est_input_tokens = token_info
                    est_output_tokens = 0
                elif isinstance(token_info, dict):
                    est_input_tokens = token_info.get('input_tokens', 0)
                    est_output_tokens = token_info.get('output_tokens', 0)
                else:
                    est_input_tokens = 0
                    est_output_tokens = 0
                check_long_request_limit(user, est_input_tokens + est_output_tokens)
            except Exception as e:
                return Response({'success': False, 'message': str(e)}, status=status.HTTP_403_FORBIDDEN)


            # Step 2: Call AI provider (with automatic switching)
            start_time = time.time()
            try:
                result = self.provider_router.call_ai(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    provider=provider,  # This is set by modal selection logic above
                    model=model,        # Always pass the selected modal/model
                    temperature=getattr(settings, 'OPENAI_TEMPERATURE', float(os.getenv('OPENAI_TEMPERATURE', 0.5))),
                    max_tokens=getattr(settings, 'OPENAI_MAX_TOKENS', int(os.getenv('OPENAI_MAX_TOKENS', 400)))
                )
            except Exception as e:
                return Response({
                    'success': False,
                    'message': f'Error calling AI provider: {str(e)}'
                }, status=status.HTTP_502_BAD_GATEWAY)
            response_time = time.time() - start_time

            # Extract response data
            try:
                ai_response = result['response']
                prompt_tokens = result['usage']['prompt_tokens']
                completion_tokens = result['usage']['completion_tokens']
                total_tokens = result['usage']['total_tokens']
                ai_provider = result['provider']
            except Exception as e:
                return Response({
                    'success': False,
                    'message': f'Error parsing AI provider response: {str(e)}'
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            # Calculate credits for this modal using actual token usage
            modal_rules = MODAL_CREDIT_RULES.get(model, MODAL_CREDIT_RULES['gpt-3.5'])
            input_weight = modal_rules['input_token_weight']
            output_weight = modal_rules['output_token_weight']
            min_charge = modal_rules['min_charge']
            credit_multiplier = modal_rules['credit_multiplier']
            enterprise_discount = modal_rules['enterprise_discount']

            credits_used = (
                (prompt_tokens * input_weight + completion_tokens * output_weight) * credit_multiplier
            )
            if credits_used < min_charge:
                credits_used = min_charge

            # Apply enterprise discount if user is enterprise
            if hasattr(user, 'user_type') and user.user_type == 'enterprise':
                credits_used = int(credits_used * (1 - enterprise_discount))

            # Deduct calculated credits from subscription
            try:
                ensure_credits_and_deduct(user, credits_used)
            except Exception as e:
                return Response({'success': False, 'message': f'Billing failed: {str(e)}'}, status=status.HTTP_402_PAYMENT_REQUIRED)

            # Step 3: Log the request
            try:
                log = self._create_log(
                    user=user,
                    tool=tool_for_logging,
                    topic=validated_data.get('topic', ''),
                    class_level=validated_data.get('class_level', ''),
                    difficulty=validated_data.get('difficulty', ''),
                    inputs=user_inputs,
                    prompt=prompt,
                    response=ai_response,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    response_time=response_time,
                    provider=ai_provider
                )
            except Exception as e:
                return Response({
                    'success': False,
                    'message': f'Error logging AI request: {str(e)}'
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            # Step 4: Update user usage
            try:
                self._update_user_usage(user, log)
            except Exception as e:
                return Response({
                    'success': False,
                    'message': f'Error updating user usage: {str(e)}'
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            # Step 5: Return response

            response_data = {
                'success': True,
                'data': ai_response,
                'tokens_used': total_tokens,
                'credits_used': credits_used,
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

    
    def _create_log(self, user, tool, topic, class_level, difficulty, 
                    prompt, response, prompt_tokens, completion_tokens, response_time, provider, inputs=None):
        """Create AI log entry with provider information"""
        log = AILog.objects.create(
            user=user,
            tool=tool,
            topic=topic,
            class_level=class_level,
            difficulty=difficulty,
            inputs=inputs,
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


class AILogHistoryModalView(APIView):
    """
    GET: Get AI log history formatted for the frontend modal
    """
    permission_classes = [IsAuthenticated]
    
    def _relative_time(self, dt):
        if not dt:
            return 'Unknown'
        now = timezone.now()
        delta = now - dt
        if delta.days >= 1:
            if delta.days == 1:
                return 'Yesterday'
            return f"{delta.days} days ago"
        hours = delta.seconds // 3600
        if hours >= 1:
            return f"{hours} hours ago"
        minutes = delta.seconds // 60
        return f"{minutes} minutes ago" if minutes > 0 else 'just now'

    def get(self, request):
        logs = AILog.objects.filter(user=request.user).order_by('-created_at')[:50]
        
        tool_names = [log.tool for log in logs]
        tools = AITool.objects.filter(name__in=tool_names).select_related('categories')
        tool_map = {t.name: t for t in tools}
        
        results = []
        for log in logs:
            tool_obj = tool_map.get(log.tool)
            tool_id = tool_obj.slug if tool_obj and tool_obj.slug else log.tool.lower().replace(' ', '-')
            tool_type = tool_obj.categories.name if tool_obj and getattr(tool_obj, 'categories', None) else 'General'
            
            formData = log.inputs or {}
            
            # Fallback for older legacy logs
            if not formData:
                if log.topic:
                    formData['topic'] = log.topic
                if log.class_level:
                    formData['grade'] = log.class_level
                if log.difficulty:
                    formData['difficulty'] = log.difficulty
                
            results.append({
                'id': log.id,
                'toolId': tool_id,
                'tool': log.tool,
                'title': log.topic or log.tool,
                'date': self._relative_time(log.created_at),
                'type': tool_type,
                'formData': formData,
                'output': log.response
            })
            
        return Response(results, status=status.HTTP_200_OK)


class AILogHistoryModalDetailView(APIView):
    """
    GET: Get a specific AI log formatted for the frontend modal
    """
    permission_classes = [IsAuthenticated]
    
    def _relative_time(self, dt):
        if not dt:
            return 'Unknown'
        now = timezone.now()
        delta = now - dt
        if delta.days >= 1:
            if delta.days == 1:
                return 'Yesterday'
            return f"{delta.days} days ago"
        hours = delta.seconds // 3600
        if hours >= 1:
            return f"{hours} hours ago"
        minutes = delta.seconds // 60
        return f"{minutes} minutes ago" if minutes > 0 else 'just now'

    def get(self, request, log_id):
        try:
            log = AILog.objects.get(id=log_id, user=request.user)
        except AILog.DoesNotExist:
            return Response({'success': False, 'message': 'Log not found'}, status=status.HTTP_404_NOT_FOUND)
            
        tool_obj = AITool.objects.filter(name=log.tool).select_related('categories').first()
        
        tool_id = tool_obj.slug if tool_obj and getattr(tool_obj, 'slug', None) else log.tool.lower().replace(' ', '-')
        tool_type = tool_obj.categories.name if tool_obj and getattr(tool_obj, 'categories', None) else 'General'
        
        formData = log.inputs or {}
        if not formData:
            if log.topic:
                formData['topic'] = log.topic
            if log.class_level:
                formData['grade'] = log.class_level
            if log.difficulty:
                formData['difficulty'] = log.difficulty
            
        result = {
            'id': log.id,
            'toolId': tool_id,
            'tool': log.tool,
            'title': log.topic or log.tool,
            'date': self._relative_time(log.created_at),
            'type': tool_type,
            'formData': formData,
            'output': log.response
        }
        
        return Response(result, status=status.HTTP_200_OK)


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


# ================== USAGE ENDPOINTS ==================

class UsageCreditsView(APIView):
    """
    Get credit usage information for authenticated user
    GET /api/v1/tools/usage/credits/
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        user = request.user
        
        try:
            subscription = self._get_user_subscription(user)
            
            if not subscription:
                return Response({
                    "current_usage": 0,
                    "monthly_limit": 0,
                    "usage_percentage": 0,
                    "reset_days": 0,
                    "reset_date": None,
                    "plan_name": "No Plan"
                })
            
            # Calculate usage metrics
            current_usage = subscription.start_credits - subscription.remaining_credits
            monthly_limit = subscription.start_credits
            usage_percentage = round((current_usage / monthly_limit * 100), 2) if monthly_limit > 0 else 0.0
            
            # Calculate days until reset
            billing_end_date = subscription.billing_end_date
            today = timezone.now().date()
            reset_days = max((billing_end_date - today).days, 0)
            
            # Format reset date
            reset_date = billing_end_date.isoformat() + "T00:00:00Z" if billing_end_date else None
            
            return Response({
                "current_usage": current_usage,
                "monthly_limit": monthly_limit,
                "usage_percentage": usage_percentage,
                "reset_days": reset_days,
                "reset_date": reset_date,
                "plan_name": subscription.plan.name
            })
        
        except Exception as e:
            return Response({
                "current_usage": 0,
                "monthly_limit": 0,
                "usage_percentage": 0,
                "reset_days": 0,
                "reset_date": None,
                "plan_name": "Error"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def _get_user_subscription(self, user):
        """Get active subscription for user (individual or enterprise)"""
        
        # If enterprise user, get organisation's subscription
        if user.user_type == 'enterprise' and user.organisation:
            subscription = user.organisation.subscriptions.filter(
                status='active'
            ).order_by('-created_at').first()
        else:
            # Individual user subscription
            subscription = Subscription.objects.filter(
                user=user,
                status='active'
            ).order_by('-created_at').first()
        
        return subscription
