"""AI tool prompt builders and router moved out of views for separation of concerns.

Provides:
- `DynamicPromptBuilder` class that builds prompts based on tool configuration
- `AIProviderRouter` class to handle multiple AI providers (OpenAI, DeepSeek) with switching
- `estimate_tokens(prompt)` utility to estimate token usage conservatively
"""
from typing import Dict, Optional
import os
from django.conf import settings


class DynamicPromptBuilder:
    """Build prompts dynamically based on tool configuration from database."""

    def build_from_tool_config(self, tool_obj, user_inputs: Dict) -> tuple:
        """
        Build system and user prompts separately based on tool configuration.
        
        Args:
            tool_obj: AITool instance with system_prompt and input fields
            user_inputs: Dictionary of user-provided input values
        
        Returns:
            Tuple of (system_prompt, user_prompt)
        """
        # Get system prompt from AITool
        if tool_obj.system_prompt:
            system_prompt = tool_obj.system_prompt
        else:
            # Build from tool name/description as fallback
            system_prompt = f"You are an AI assistant helping with: {tool_obj.description}"
        
        # Build user prompt from input values based on tool's input configuration
        user_prompt_parts = []
        input_fields = tool_obj.inputs.all().order_by('order')
        for field in input_fields:
            if field.label in user_inputs:
                value = user_inputs[field.label]
                user_prompt_parts.append(f"{field.label}: {value}")
        
        user_prompt = "\n".join(user_prompt_parts) if user_prompt_parts else ""
        
        # Combine: system prompt + user inputs
        full_prompt = system_prompt + "\n\n" + user_prompt if user_prompt else system_prompt
        
        return system_prompt, user_prompt, full_prompt

   


class AIProviderRouter:
    """Manages multiple AI providers (OpenAI, DeepSeek) with automatic switching."""
    
    PROVIDER_OPENAI = 'openai'
    PROVIDER_DEEPSEEK = 'deepseek'
    
    def __init__(self, default_provider: Optional[str] = None):
        """
        Initialize provider router.
        
        Args:
            default_provider: 'openai' or 'deepseek', defaults to OpenAI if not set
        """
        self.default_provider = default_provider or self.PROVIDER_OPENAI
        self._init_clients()
    
    def _init_clients(self):
        """Initialize clients for both providers."""
        from openai import OpenAI
        
        openai_key = getattr(settings, 'OPENAI_API_KEY', os.getenv('OPENAI_API_KEY', None))
        self.openai_client = OpenAI(api_key=openai_key) if openai_key else None
        
        deepseek_key = getattr(settings, 'DEEPSEEK_API_KEY', os.getenv('DEEPSEEK_API_KEY', None))
        # DeepSeek uses the same OpenAI SDK but with different base URL
        self.deepseek_client = OpenAI(
            api_key=deepseek_key,
            base_url="https://api.deepseek.com"
        ) if deepseek_key else None
    
    def get_provider(self, provider: Optional[str] = None) -> str:
        """
        Get provider, with fallback logic.
        
        Args:
            provider: Preferred provider ('openai', 'deepseek', or None for default)
        
        Returns:
            Actual provider to use based on availability
        """
        if provider is None:
            provider = self.default_provider
        
        # Check if requested provider is available
        if provider == self.PROVIDER_DEEPSEEK and self.deepseek_client:
            return self.PROVIDER_DEEPSEEK
        elif provider == self.PROVIDER_OPENAI and self.openai_client:
            return self.PROVIDER_OPENAI
        
        # Fallback: use first available provider
        if self.deepseek_client:
            return self.PROVIDER_DEEPSEEK
        if self.openai_client:
            return self.PROVIDER_OPENAI
        
        raise ValueError("No AI providers configured. Set OPENAI_API_KEY or DEEPSEEK_API_KEY in settings.")
    
    def call_ai(self, prompt: str = None, system_prompt: str = None, user_prompt: str = None, provider: Optional[str] = None, **kwargs) -> Dict:
        """
        Call AI with automatic provider selection and fallback.
        
        Args:
            prompt: Full prompt text (for backward compatibility)
            system_prompt: System/instruction prompt (separate)
            user_prompt: User-provided prompt (separate)
            provider: Preferred provider (will auto-fallback if unavailable)
            **kwargs: Additional parameters (temperature, max_tokens, model, etc.)
        
        Returns:
            Dictionary with 'provider', 'response', 'usage', and other completion details
        """
        # Handle both new (separate) and legacy (combined) prompt formats
        if system_prompt is None and user_prompt is None:
            # Legacy: use combined prompt
            system_prompt = "You are a helpful educational assistant."
            user_prompt = prompt
        
        selected_provider = self.get_provider(provider)
        
        try:
            if selected_provider == self.PROVIDER_DEEPSEEK:
                return self._call_deepseek(system_prompt, user_prompt, **kwargs)
            else:
                return self._call_openai(system_prompt, user_prompt, **kwargs)
        except Exception as e:
            # Auto-switch to fallback provider on error
            if selected_provider == self.PROVIDER_OPENAI and self.deepseek_client:
                print(f"OpenAI call failed: {e}. Switching to DeepSeek...")
                return self._call_deepseek(system_prompt, user_prompt, **kwargs)
            elif selected_provider == self.PROVIDER_DEEPSEEK and self.openai_client:
                print(f"DeepSeek call failed: {e}. Switching to OpenAI...")
                return self._call_openai(system_prompt, user_prompt, **kwargs)
            raise
    
    def _call_openai(self, system_prompt: str, user_prompt: str, **kwargs) -> Dict:
        """Call OpenAI API with separate system and user prompts."""
        if not self.openai_client:
            raise ValueError("OpenAI client not initialized")
        
        completion = self.openai_client.chat.completions.create(
            model=kwargs.get('model', 'gpt-4o-mini'),
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=kwargs.get('temperature', 0.5),
            max_tokens=kwargs.get('max_tokens', 400)
        )
        
        return {
            'provider': self.PROVIDER_OPENAI,
            'response': completion.choices[0].message.content,
            'usage': {
                'prompt_tokens': completion.usage.prompt_tokens,
                'completion_tokens': completion.usage.completion_tokens,
                'total_tokens': completion.usage.total_tokens,
            },
            'model': completion.model,
            'finish_reason': completion.choices[0].finish_reason,
        }
    
    def _call_deepseek(self, system_prompt: str, user_prompt: str, **kwargs) -> Dict:
        """Call DeepSeek API (compatible with OpenAI SDK) with separate system and user prompts."""
        if not self.deepseek_client:
            raise ValueError("DeepSeek client not initialized")
        
        completion = self.deepseek_client.chat.completions.create(
            model=kwargs.get('model', 'deepseek-chat'),
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=kwargs.get('temperature', 0.5),
            max_tokens=kwargs.get('max_tokens', 400)
        )
        
        return {
            'provider': self.PROVIDER_DEEPSEEK,
            'response': completion.choices[0].message.content,
            'usage': {
                'prompt_tokens': completion.usage.prompt_tokens,
                'completion_tokens': completion.usage.completion_tokens,
                'total_tokens': completion.usage.total_tokens,
            },
            'model': completion.model,
            'finish_reason': completion.choices[0].finish_reason,
        }



def estimate_tokens(prompt: str) -> int:
    """Conservative estimate of tokens for billing pre-checks.

    Uses a simple heuristic: 1 token ~ 4 chars. Adds fixed headroom.
    """
    return 500 + max(0, len(prompt) // 4)


def get_provider_router(default_provider: Optional[str] = None) -> AIProviderRouter:
    """
    Factory function to get a provider router instance.
    
    Args:
        default_provider: 'openai' or 'deepseek' (defaults to PREFERRED_AI_PROVIDER setting)
    
    Returns:
        AIProviderRouter instance
    """
    if default_provider is None:
        default_provider = getattr(settings, 'PREFERRED_AI_PROVIDER', 'openai')
    
    return AIProviderRouter(default_provider=default_provider)
