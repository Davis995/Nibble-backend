from rest_framework import serializers
from django.contrib.auth import get_user_model
User = get_user_model()
from .models import AILog, AITool, UserAIUsage, ToolCategory, ToolInput, ToolFavorite
from datetime import datetime, timedelta
from django.db.models import Sum, Count
from decimal import Decimal


class ToolCategorySerializer(serializers.ModelSerializer):
    description = serializers.CharField(allow_blank=True, required=False)
    
    class Meta:
        model = ToolCategory
        fields = ['id', 'name', 'description', 'icon', 'type', 'created_at', 'updated_at']


class ToolInputSerializer(serializers.ModelSerializer):
    class Meta:
        model = ToolInput
        fields = [
            'id', 'type', 'label', 'placeholder', 'default_value',
            'options', 'required', 'minlength', 'maxlength', 'order'
        ]


class ToolDetailSerializer(serializers.ModelSerializer):
    """Detailed tool serializer with inputs and category info"""
    category = ToolCategorySerializer(source='categories', read_only=True)
    inputs = ToolInputSerializer(many=True, read_only=True)
    is_favorited = serializers.SerializerMethodField()
    favorites_count = serializers.SerializerMethodField()
    
    class Meta:
        model = AITool
        fields = [
            'id', 'slug', 'name', 'student_friendly_name', 'description',
            'category', 'icon', 'color', 'system_prompt',
            'is_premium', 'is_recommended', 'is_active',
            'inputs', 'is_favorited', 'favorites_count',
            'created_at', 'updated_at'
        ]
    
    def get_is_favorited(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.is_favorited_by(request.user)
        return False
    
    def get_favorites_count(self, obj):
        return obj.get_favorites_count()


class ToolListSerializer(serializers.ModelSerializer):
    """Simplified tool serializer for list view"""
    category = ToolCategorySerializer(source='categories', read_only=True)
    is_favorited = serializers.SerializerMethodField()
    favorites_count = serializers.SerializerMethodField()
    
    class Meta:
        model = AITool
        fields = [
            'id', 'slug', 'name', 'student_friendly_name', 'description',
            'category', 'icon', 'color', 'system_prompt', 'preferred_modal',
            'is_premium', 'is_recommended', 'is_active', 'is_favorited',
            'favorites_count', 'created_at'
        ]
    
    def get_is_favorited(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.is_favorited_by(request.user)
        return False
    
    def get_favorites_count(self, obj):
        return obj.get_favorites_count()


class ToolFavoriteSerializer(serializers.ModelSerializer):
    tool = ToolListSerializer(read_only=True)
    
    class Meta:
        model = ToolFavorite
        fields = ['id', 'tool', 'created_at']


class AIRequestSerializer(serializers.Serializer):
    """Serializer for incoming AI requests (supports both legacy tool name and new tool_id)"""
    # Legacy tool name field (for backward compatibility) - dynamically validated
    tool = serializers.CharField(max_length=255, required=False, allow_blank=True)
    
    # New tool_id field (recommended)
    tool_id = serializers.IntegerField(required=False)
    
    # New slug field (recommended alternate identifier)
    tool_slug = serializers.SlugField(required=False)
    
    # Dynamic inputs for tool_id-based requests
    inputs = serializers.JSONField(required=False, default=dict)
    
    # Provider selection (optional, defaults to PREFERRED_AI_PROVIDER) - dynamically validated
    provider = serializers.CharField(max_length=50, required=False, allow_blank=True)
    
    # Optional task/log title
    title = serializers.CharField(max_length=255, required=False, allow_blank=True)
    
    # Legacy fields for backward compatibility
    topic = serializers.CharField(max_length=255, required=False, allow_blank=True)
    class_level = serializers.CharField(max_length=50, required=False, allow_blank=True)
    difficulty = serializers.CharField(max_length=50, required=False, allow_blank=True)
    content = serializers.CharField(required=False, allow_blank=True)
    num_questions = serializers.IntegerField(required=False, default=5, min_value=1, max_value=20)
    question_type = serializers.CharField(required=False, default='multiple_choice')
    
    def validate(self, data):
        """Custom validation - support both tool_id (new) and tool name (legacy), and enforce required tool inputs."""
        tool_id = data.get('tool_id')
        tool = data.get('tool')
        tool_slug = data.get('tool_slug')
        provider = data.get('provider')
        inputs = data.get('inputs', {})

        # Either tool_id, tool_slug, or tool name must be provided
        if not tool_id and not tool and not tool_slug:
            raise serializers.ValidationError(
                'Either tool_id, tool_slug or tool must be provided.'
            )

        # Dynamically validate provider if provided
        if provider:
            valid_providers = ['openai', 'deepseek']
            if provider not in valid_providers:
                raise serializers.ValidationError({
                    'provider': f'Provider must be one of: {", ".join(valid_providers)}'
                })

        # Enforce required tool inputs if tool_id or tool_slug is provided
        from tools.models import AITool, ToolInput
        tool_obj = None
        if tool_id:
            try:
                tool_obj = AITool.objects.get(id=tool_id)
            except AITool.DoesNotExist:
                raise serializers.ValidationError({'tool_id': 'Invalid tool_id'})
        elif tool_slug:
            try:
                tool_obj = AITool.objects.get(slug=tool_slug)
            except AITool.DoesNotExist:
                raise serializers.ValidationError({'tool_slug': 'Invalid tool_slug'})
        # (Legacy) If only tool name is provided, skip required input enforcement
        if tool_obj:
            required_inputs = ToolInput.objects.filter(tool=tool_obj, required=True)
            missing = []
            for inp in required_inputs:
                if inp.label not in inputs or inputs.get(inp.label) in [None, '']:
                    missing.append(inp.label)
            if missing:
                raise serializers.ValidationError({
                    'inputs': f'Missing required input fields: {", ".join(missing)}'
                })

        return data


class AIResponseSerializer(serializers.Serializer):
    """Serializer for AI responses"""
    success = serializers.BooleanField()
    data = serializers.CharField(allow_blank=True)
    message = serializers.CharField(required=False)
    log_id = serializers.IntegerField(required=False)
    tokens_used = serializers.IntegerField(required=False)
    cost = serializers.DecimalField(max_digits=10, decimal_places=6, required=False)


class AILogSerializer(serializers.ModelSerializer):
    """Serializer for AILog model with provider tracking"""
    username = serializers.CharField(source='user.username', read_only=True)
    cost_display = serializers.SerializerMethodField()
    
    class Meta:
        model = AILog
        fields = [
            'id', 'username', 'user', 'tool', 'title', 'topic', 'class_level',
            'difficulty', 'inputs', 'prompt_tokens', 'completion_tokens', 
            'total_tokens', 'credits', 'cost', 'cost_display', 'response',
            'provider', 'created_at', 'response_time'
        ]
        read_only_fields = ['id', 'created_at', 'cost', 'provider']
    
    def get_cost_display(self, obj):
        return f"${obj.cost:.6f}"


class UserLogMemberSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'email', 'username']

class AILogListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for listing AI logs with provider info"""
    user = UserLogMemberSerializer(read_only=True)
    username = serializers.CharField(source='user.username', read_only=True)
    response_time_ms = serializers.SerializerMethodField()
    
    class Meta:
        model = AILog
        fields = [
            'id', 'user', 'username', 'tool', 'title', 'topic', 'total_tokens',
            'credits', 'cost', 'provider', 'created_at', 'response_time_ms'
        ]

    def get_response_time_ms(self, obj):
        if obj.response_time:
            return round(obj.response_time * 1000)
        return None


class AIToolOldSerializer(serializers.ModelSerializer):
    """Serializer for AI tools"""
    class Meta:
        model = AITool
        fields = ['id', 'name', 'student_friendly_name', 'description', 'is_active', 'created_at']


class UserAIUsageSerializer(serializers.ModelSerializer):
    """Serializer for user AI usage statistics"""
    username = serializers.CharField(source='user.username', read_only=True)
    email = serializers.EmailField(source='user.email', read_only=True)
    cost_display = serializers.SerializerMethodField()
    
    class Meta:
        model = UserAIUsage
        fields = [
            'username', 'email', 'total_requests', 'total_tokens',
            'total_credits', 'total_cost', 'cost_display', 'last_request_at'
        ]
    
    def get_cost_display(self, obj):
        return f"${obj.total_cost:.2f}"


class AdminAnalyticsSerializer(serializers.Serializer):
    """Serializer for admin dashboard analytics"""
    period = serializers.CharField(read_only=True)
    
    # Overall metrics
    total_requests = serializers.IntegerField(read_only=True)
    total_tokens = serializers.IntegerField(read_only=True)
    total_cost = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    
    # Per tool breakdown
    cost_per_tool = serializers.ListField(read_only=True)
    
    # Per user breakdown
    top_users = serializers.ListField(read_only=True)
    
    # Daily breakdown
    daily_breakdown = serializers.ListField(read_only=True)


class ToolAnalyticsSerializer(serializers.Serializer):
    """Serializer for per-tool analytics"""
    tool = serializers.CharField()
    total_requests = serializers.IntegerField()
    total_tokens = serializers.IntegerField()
    total_cost = serializers.DecimalField(max_digits=10, decimal_places=2)
    avg_tokens = serializers.FloatField()
    cost_display = serializers.SerializerMethodField()
    
    def get_cost_display(self, obj):
        return f"${obj['total_cost']:.2f}"


class UserAnalyticsSerializer(serializers.Serializer):
    """Serializer for per-user analytics"""
    username = serializers.CharField()
    email = serializers.EmailField()
    total_requests = serializers.IntegerField()
    total_tokens = serializers.IntegerField()
    total_cost = serializers.DecimalField(max_digits=10, decimal_places=2)
    last_request = serializers.DateTimeField()
    cost_display = serializers.SerializerMethodField()
    
    def get_cost_display(self, obj):
        return f"${obj['total_cost']:.2f}"


class DailyAnalyticsSerializer(serializers.Serializer):
    """Serializer for daily analytics breakdown"""
    date = serializers.DateField()
    requests = serializers.IntegerField()
    tokens = serializers.IntegerField()
    cost = serializers.DecimalField(max_digits=10, decimal_places=2)
    cost_display = serializers.SerializerMethodField()
    
    def get_cost_display(self, obj):
        return f"${obj['cost']:.2f}"


# ---------------------- Chat Serializers ----------------------
from .models import ChatSession, ChatMessage


class ChatMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChatMessage
        fields = ['id', 'role', 'content', 'created_at']
        read_only_fields = ['id', 'created_at']


class ChatSessionSerializer(serializers.ModelSerializer):
    messages = ChatMessageSerializer(many=True, read_only=True)
    session_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = ChatSession
        fields = ['id', 'session_id', 'user', 'title', 'created_at', 'updated_at', 'messages']
        read_only_fields = ['id', 'session_id', 'created_at', 'updated_at', 'messages']

class ToolInputCreateUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ToolInput
        fields = [
            'id', 'tool', 'type', 'label', 'placeholder', 'default_value',
            'options', 'required', 'minlength', 'maxlength', 'order'
        ]


class ToolCreateUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = AITool
        fields = [
            'id', 'slug', 'name', 'student_friendly_name', 'description',
            'categories', 'icon', 'color', 'system_prompt',
            'is_premium', 'is_recommended', 'is_active', 'preferred_modal'
        ]
