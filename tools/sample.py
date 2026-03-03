from tools.models import (
    ToolCategory,
    AITool,
    ToolInput,
    ToolFavorite,
    AILog,
    UserAIUsage,
)
from authentication.models import User
from django.utils.text import slugify
from datetime import datetime


def run():
    print("Clearing existing tools data...")
    UserAIUsage.objects.all().delete()
    AILog.objects.all().delete()
    ToolFavorite.objects.all().delete()
    ToolInput.objects.all().delete()
    AITool.objects.all().delete()
    ToolCategory.objects.all().delete()

    print("Creating sample category...")
    cat = ToolCategory.objects.create(
        name="Sample Category",
        description="A category for testing",
        type="teacher",
    )

    print("Creating sample tool entries with slug...")
    tools_info = [
        ("summarizer", "Summarizes text", "Text Summarizer", "#ff0000", False, True),
        ("essay-analyzer", "Analyzes student essays", "My Essay Checker", "#FF6B6B", False, True),
    ]
    created_tools = []
    for slug_val, desc, friendly, color, premium, recommended in tools_info:
        tool = AITool.objects.create(
            slug=slug_val,
            name=slug_val.replace("-", " ").title(),
            description=desc,
            student_friendly_name=friendly,
            categories=cat,
            color=color,
            system_prompt="",
            is_premium=premium,
            is_recommended=recommended,
        )
        created_tools.append(tool)

    print("Adding input fields to first tool...")
    if created_tools:
        tool = created_tools[0]
        ToolInput.objects.create(
            tool=tool,
            type="textarea",
            label="Text",
            placeholder="Enter text here",
            required=True,
            order=1,
        )

    print("Creating sample user for favorites and logs...")
    user, _ = User.objects.get_or_create(
        email="tooluser@example.com",
        defaults={"first_name":"Tool","last_name":"User","user_type":"individual","password":"pass1234"},
    )

    if created_tools:
        ToolFavorite.objects.create(user=user, tool=created_tools[0])

        log = AILog.objects.create(
            user=user,
            tool=created_tools[0].name,
            topic="testing",
            class_level="N/A",
            difficulty="medium",
            prompt_tokens=10,
            completion_tokens=20,
            prompt="Sample prompt",
            response="Sample response",
            provider="openai",
            response_time=0.5,
        )

        UserAIUsage.objects.create(
            user=user,
            total_requests=1,
            total_tokens=log.total_tokens,
            total_cost=log.cost,
            last_request_at=datetime.now(),
        )

    print("✅ Sample data for tools created successfully!")


if __name__ == "__main__":
    run()
