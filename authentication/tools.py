
from authentication.models import (
    User,
    Plan,
    Subscription,
    CreditTop,
    EmailVerificationToken,
    PasswordResetToken,
    Invitation,
)
from django.utils import timezone
from schools.models import School

from tools.models import *
from payments.models import *
from leads.models import *
print("Creating sample AI Tools...")
teacher_category, _ = ToolCategory.objects.get_or_create(name="Teacher Tools")
student_category, _ = ToolCategory.objects.get_or_create(name="Student Tools")
# Create AI Tools with preferred_modal

tool1 = AITool.objects.create(
    slug="Scaffold",
    name="Scaffold",
    description="Analyzes student essays and provides detailed feedback on structure, grammar, and content",
    student_friendly_name="My Essay Checker",
    categories=teacher_category,
    color="#FF6B6B",
    system_prompt="Explain [topic below] to me as if I were a beginner, then gradually increase the complexity. Start with the basics, and add real-world examples as we progress.if class provided answer in curriculum used in Uganda",
    is_premium=False,
    is_recommended=True,
    is_active=True,
    preferred_modal="gpt-4o-mini"
)


print("Creating sample Tool Inputs...")

# Create Tool Inputs for each tool
# Essay Analyzer
ToolInput.objects.create(
    tool=tool1,
    type="text",
    label="Topic",
    placeholder="Enter your topic",
    required=True,
    minlength=100,
    order=1
)
ToolInput.objects.create(
    tool=tool1,
    type="dropdown",
    label="Grade Level",
    options=["S1", "S2", "S3", "S4"],
    required=False,
    order=2
)

