from django.db import models

from django.utils import timezone
from django.utils.text import slugify
from decimal import Decimal
from django.conf import settings
import uuid


class ToolCategory(models.Model):
    """Tool categories for organizing AI tools"""
    
    CATEGORY_TYPES = [
        ('teacher', 'Teacher'),
        ('student', 'Student'),
    ]
    
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField()
    type = models.CharField(max_length=10, choices=CATEGORY_TYPES)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'tool_categories'
        verbose_name = 'Tool Category'
        verbose_name_plural = 'Tool Categories'
    
    def __str__(self):
        return self.name


class AITool(models.Model):
    """Available AI tools in the system"""
    
    slug = models.SlugField(max_length=255, unique=True, blank=True,
                            help_text="URL-friendly identifier generated from the name")
    name = models.CharField(max_length=255, unique=True)
    description = models.TextField()
    student_friendly_name = models.CharField(max_length=255)
    categories = models.ForeignKey(ToolCategory, on_delete=models.SET_NULL, null=True, blank=True, related_name='tools')
    icon = models.FileField(upload_to='tool_icons/', null=True, blank=True)
    color = models.CharField(max_length=7, default='#000000', help_text="Hex color code")
    system_prompt = models.TextField(blank=True, null=True)
    is_premium = models.BooleanField(default=False)
    is_recommended = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'ai_tools'
        verbose_name = 'AI Tool'
        verbose_name_plural = 'AI Tools'
    
    def __str__(self):
        return self.student_friendly_name

    def save(self, *args, **kwargs):
        # automatically fill slug from name if not provided
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)
    
    def get_inputs(self):
        """Get all input fields for this tool"""
        return self.inputs.all()
    
    def is_favorited_by(self, user):
        """Check if tool is favorited by user"""
        return self.favorites.filter(user=user).exists()
    
    def get_favorites_count(self):
        """Get total number of favorites"""
        return self.favorites.count()


class AILog(models.Model):
    """Log every AI request for analytics and cost tracking"""
    
    PROVIDER_CHOICES = [
        ('openai', 'OpenAI'),
        ('deepseek', 'DeepSeek'),
    ]
    
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='ai_logs')
    tool = models.CharField(max_length=50)
    topic = models.CharField(max_length=255, blank=True, null=True)
    class_level = models.CharField(max_length=50, blank=True, null=True)
    difficulty = models.CharField(max_length=50, blank=True, null=True)
    
    # Token tracking
    prompt_tokens = models.IntegerField(default=0)
    completion_tokens = models.IntegerField(default=0)
    total_tokens = models.IntegerField(default=0)
    
    # Cost tracking
    cost = models.DecimalField(max_digits=10, decimal_places=6, default=0)
    
    # Request/Response data
    prompt = models.TextField()
    response = models.TextField()
    
    # Provider tracking
    provider = models.CharField(max_length=20, choices=PROVIDER_CHOICES, default='openai')
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    response_time = models.FloatField(help_text="Response time in seconds", null=True, blank=True)
    
    class Meta:
        db_table = 'ai_logs'
        verbose_name = 'AI Log'
        verbose_name_plural = 'AI Logs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['-created_at']),
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['tool', '-created_at']),
            models.Index(fields=['provider', '-created_at']),
        ]
    
    def __str__(self):
        return f"{self.user.username} - {self.tool} - {self.provider} - {self.created_at.strftime('%Y-%m-%d %H:%M')}"
    
    def save(self, *args, **kwargs):
        # Calculate total tokens
        self.total_tokens = self.prompt_tokens + self.completion_tokens
        
        # Calculate cost
        # Input: $0.15 per 1M tokens, Output: $0.60 per 1M tokens
        input_cost = Decimal(self.prompt_tokens) / Decimal(1000000) * Decimal('0.15')
        output_cost = Decimal(self.completion_tokens) / Decimal(1000000) * Decimal('0.60')
        self.cost = input_cost + output_cost
        
        super().save(*args, **kwargs)


class UserAIUsage(models.Model):
    """Track cumulative AI usage per user for quick lookups"""
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='ai_usage')
    total_requests = models.IntegerField(default=0)
    total_tokens = models.BigIntegerField(default=0)
    total_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    last_request_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'user_ai_usage'
        verbose_name = 'User AI Usage'
        verbose_name_plural = 'User AI Usage'
    
    def __str__(self):
        return f"{self.user.username} - {self.total_requests} requests"


class ToolInput(models.Model):
    """Define input fields for AI tools"""
    
    INPUT_CHOICES = [
        ('text', 'Text'),
        ('number', 'Number'),
        ('dropdown', 'Dropdown'),
        ('textarea', 'Textarea'),
        ('email', 'Email'),
    ]
    
    tool = models.ForeignKey(AITool, on_delete=models.CASCADE, related_name='inputs')
    type = models.CharField(max_length=20, choices=INPUT_CHOICES)
    label = models.CharField(max_length=255)
    placeholder = models.CharField(max_length=255, blank=True, null=True)
    default_value = models.CharField(max_length=1000, blank=True, null=True)
    options = models.JSONField(null=True, blank=True, help_text="For dropdown: list of options")
    required = models.BooleanField(default=False)
    minlength = models.IntegerField(null=True, blank=True)
    maxlength = models.IntegerField(null=True, blank=True)
    order = models.IntegerField(default=0, help_text="Display order of inputs")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'tool_inputs'
        verbose_name = 'Tool Input'
        verbose_name_plural = 'Tool Inputs'
        ordering = ['order']
    
    def __str__(self):
        return f"{self.tool.name} - {self.label}"


class ToolFavorite(models.Model):
    """Track user favorite tools"""
    
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='favorite_tools')
    tool = models.ForeignKey(AITool, on_delete=models.CASCADE, related_name='favorites')
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'tool_favorites'
        verbose_name = 'Tool Favorite'
        verbose_name_plural = 'Tool Favorites'
        unique_together = ('user', 'tool')
    
    def __str__(self):
        return f"{self.user.username} - {self.tool.name}"


# ---------------------- Chat models ----------------------
class ChatSession(models.Model):
    """A chat session between a user and the AI assistant."""

    session_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='chat_sessions')
    title = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'chat_sessions'
        ordering = ['-updated_at']

    def __str__(self):
        return f"ChatSession {self.session_id} - {self.user or 'anonymous'}"


class ChatMessage(models.Model):
    """Individual messages stored for a chat session."""

    ROLE_USER = 'user'
    ROLE_ASSISTANT = 'assistant'
    ROLE_SYSTEM = 'system'

    ROLE_CHOICES = [
        (ROLE_USER, 'User'),
        (ROLE_ASSISTANT, 'Assistant'),
        (ROLE_SYSTEM, 'System'),
    ]

    session = models.ForeignKey(ChatSession, on_delete=models.CASCADE, related_name='messages')
    role = models.CharField(max_length=16, choices=ROLE_CHOICES)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'chat_messages'
        # Ensure deterministic ordering for rendering: created_at then PK
        ordering = ['created_at', 'id']

    def __str__(self):
        return f"{self.role}: {self.content[:50]}... ({self.created_at})"
