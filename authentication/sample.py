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
def run():
    """Seed authentication-related data. This script focuses exclusively on models
    defined in the `authentication` app and creates minimal related objects.
    """
    print("Clearing existing authentication data...")

    # Be careful when deleting; preserve superusers
    Invitation.objects.all().delete()
    PasswordResetToken.objects.all().delete()
    EmailVerificationToken.objects.all().delete()
    CreditTop.objects.all().delete()
    Subscription.objects.all().delete()
    Plan.objects.all().delete()
    User.objects.filter(is_superuser=False).delete()

    print("Creating sample plans...")
    basic_plan = Plan.objects.create(
        name="Basic",
        use_type="individual",
        total_credits=1000,
        max_users=1,
        monthly_price=9.99,
    )

    enterprise_plan = Plan.objects.create(
        name="Enterprise",
        use_type="enterprise",
        total_credits=20000,
        max_users=500,
        monthly_price=499.99,
    )

    print("Creating sample users...")
    alice = User.objects.create_user(
        email="alice@example.com",
        password="Password123",
        first_name="Alice",
        last_name="Anderson",
        user_type="individual",
    )

    bob = User.objects.create_user(
        email="bob@enterprise.com",
        password="Secret456",
        first_name="Bob",
        last_name="Brown",
        user_type="enterprise",
    )

    print("Creating a sample school for Bob's subscription...")
    school = School.objects.create(
        name="Sample Academy",
        school_email="admin@sampleacademy.edu",
        max_students=300,
    )

    bob.organisation = school
    bob.save()

    print("Creating sample subscriptions...")
    Subscription.objects.create(
        max_users=basic_plan.max_users,
        plan=basic_plan,
        user=alice,
        start_credits=basic_plan.total_credits,
        remaining_credits=basic_plan.total_credits,
        billing_start_date=timezone.now().date(),
        billing_end_date=timezone.now().date(),
        status="active",
    )

    Subscription.objects.create(
        max_users=enterprise_plan.max_users,
        plan=enterprise_plan,
        organisation=school,
        start_credits=enterprise_plan.total_credits,
        remaining_credits=enterprise_plan.total_credits,
        billing_start_date=timezone.now().date(),
        billing_end_date=timezone.now().date(),
        status="active",
    )

    print("Adding a credit top-up for Alice...")
    CreditTop.objects.create(
        subscription=Subscription.objects.filter(user=alice).first(),
        amount=500,
    )

    print("Generating sample tokens and invitations...")
    EmailVerificationToken.objects.create(
        user=alice,
        token="verif-token-123",
        expires_at=timezone.now() + timezone.timedelta(days=1),
    )

    PasswordResetToken.objects.create(
        user=bob,
        token="reset-token-456",
        expires_at=timezone.now() + timezone.timedelta(hours=2),
    )

    Invitation.objects.create(
        email="newuser@example.com",
        invited_by=alice,
        token="invite-789",
        expires_at=timezone.now() + timezone.timedelta(days=7),
    )

    print("✅ Authentication sample data created successfully!")


if __name__ == "__main__":
    run()

print("Creating sample Plans...")
# Create Plans
enterprise_plan = Plan.objects.create(
    name="Enterprise Premium",
    use_type="enterprise",
    total_credits=10000,
    max_users=300,
    monthly_price=6000.00
)

individual_plan = Plan.objects.create(
    name="Individual Basic",
    use_type="individual",
    total_credits=1000,
    max_users=1,
    monthly_price=50.00
)

individual_pro_plan = Plan.objects.create(
    name="Individual Pro",
    use_type="individual",
    total_credits=5000,
    max_users=1,
    monthly_price=150.00
)

print("Creating sample Schools and Users...")
# Create Schools with Admin Users
school1 = School.objects.create(
    name="Nairobi International School",
    school_email="admin@nairobi-intl.edu",
    max_students=500
)

school2 = School.objects.create(
    name="Mombasa Academy",
    school_email="admin@mombasa-academy.edu",
    max_students=300
)

school3 = School.objects.create(
    name="Kisumu High School",
    school_email="admin@kisumu-high.edu",
    max_students=200
)

# Create admin users for schools
admin_user1 = User.objects.create_user(
    email="admin1@nairobi-intl.edu",
    password="SecurePass123!",
    first_name="James",
    last_name="Kibaki",
    user_type="enterprise",
    organisation=school1,
    is_staff=True
)

admin_user2 = User.objects.create_user(
    email="admin2@mombasa-academy.edu",
    password="SecurePass123!",
    first_name="Mary",
    last_name="Ochieng",
    user_type="enterprise",
    organisation=school2,
    is_staff=True
)

admin_user3 = User.objects.create_user(
    email="admin3@kisumu-high.edu",
    password="SecurePass123!",
    first_name="David",
    last_name="Kipchoge",
    user_type="enterprise",
    organisation=school3,
    is_staff=True
)

# Link admin users to schools
school1.admin_user = admin_user1
school1.save()
school2.admin_user = admin_user2
school2.save()
school3.admin_user = admin_user3
school3.save()

print("Creating sample Subscriptions...")
# Create Subscriptions
subscription1 = Subscription.objects.create(
    max_users=enterprise_plan.max_users,
    plan=enterprise_plan,
    organisation=school1,
    start_credits=enterprise_plan.total_credits,
    remaining_credits=enterprise_plan.total_credits,
    billing_start_date='2026-02-15',
    billing_end_date='2026-03-15',
    status="active"
)

subscription2 = Subscription.objects.create(
    max_users=enterprise_plan.max_users,
    plan=enterprise_plan,
    organisation=school2,
    start_credits=enterprise_plan.total_credits,
    remaining_credits=8500,
    billing_start_date='2026-02-10',
    billing_end_date='2026-03-10',
    status="active"
)

subscription3 = Subscription.objects.create(
    max_users=enterprise_plan.max_users,
    plan=enterprise_plan,
    organisation=school3,
    start_credits=enterprise_plan.total_credits,
    remaining_credits=5000,
    billing_start_date='2026-01-15',
    billing_end_date='2026-02-15',
    status="active"
)

school1.subscription = subscription1
school1.save()
school2.subscription = subscription2
school2.save()
school3.subscription = subscription3
school3.save()

print("Creating sample individual Users...")
# Create individual users
teacher1 = User.objects.create_user(
    email="teacher1@email.com",
    password="SecurePass123!",
    first_name="Sarah",
    last_name="Mwangi",
    user_type="individual"
)

teacher2 = User.objects.create_user(
    email="teacher2@email.com",
    password="SecurePass123!",
    first_name="Michael",
    last_name="Kipchoge",
    user_type="individual"
)

student1 = User.objects.create_user(
    email="student1@email.com",
    password="SecurePass123!",
    first_name="Emma",
    last_name="Johnson",
    user_type="individual"
)

student2 = User.objects.create_user(
    email="student2@email.com",
    password="SecurePass123!",
    first_name="Liam",
    last_name="Smith",
    user_type="individual"
)

print("Creating sample Leads...")
# Create Leads
lead1 = Lead.objects.create(
    firstname="John",
    secondname="Okonkwo",
    phonenumber="+254712345678",
    workemail="john.okonkwo@example.com",
    jobtitle="Principal",
    institution="school",
    categories="education",
    institution_name="St. Mary's School",
    size_of_institution="500-1000",
    country="Kenya",
    city="Nairobi",
    question_on_preference="email",
    assigned_staff=admin_user1,
    status="demo_scheduled"
)

lead2 = Lead.objects.create(
    firstname="Grace",
    secondname="Kariuki",
    phonenumber="+254723456789",
    workemail="grace.kariuki@example.com",
    jobtitle="ICT Coordinator",
    institution="school",
    categories="education",
    institution_name="Westside Academy",
    size_of_institution="1000+",
    country="Kenya",
    city="Mombasa",
    question_on_preference="website",
    assigned_staff=admin_user2,
    status="contacted"
)

lead3 = Lead.objects.create(
    firstname="Peter",
    secondname="Nyambura",
    phonenumber="+254734567890",
    workemail="peter.nyambura@example.com",
    jobtitle="Education Director",
    institution="corporate",
    categories="corporate",
    institution_name="Tech Training Institute",
    size_of_institution="100-500",
    country="Kenya",
    city="Kisumu",
    question_on_preference="referral",
    assigned_staff=None,
    status="new"
)

lead4 = Lead.objects.create(
    firstname="Alice",
    secondname="Mutua",
    phonenumber="+254745678901",
    workemail="alice.mutua@example.com",
    jobtitle="Superintendent",
    institution="government",
    categories="government",
    institution_name="Ministry of Education",
    size_of_institution="1000+",
    country="Kenya",
    city="Nairobi",
    question_on_preference="email",
    status="negotiated"
)

print("Creating sample Tool Categories...")
# Create Tool Categories
teacher_category = ToolCategory.objects.create(
    name="Teacher Tools",
    description="AI tools designed for teachers to enhance classroom experience",
    type="teacher"
)

student_category = ToolCategory.objects.create(
    name="Student Tools",
    description="AI tools designed for students to improve learning",
    type="student"
)

print("Creating sample AI Tools...")
# Create AI Tools
tool1 = AITool.objects.create(
    slug="essay-analyzer",
    name="Essay Analyzer",
    description="Analyzes student essays and provides detailed feedback on structure, grammar, and content",
    student_friendly_name="My Essay Checker",
    categories=teacher_category,
    color="#FF6B6B",
    system_prompt="You are an expert essay analyzer. Provide constructive feedback on essays focusing on structure, grammar, clarity, and argumentation.",
    is_premium=False,
    is_recommended=True,
    is_active=True
)

tool2 = AITool.objects.create(
    slug="lesson-plan-generator",
    name="Lesson Plan Generator",
    description="Generates comprehensive lesson plans based on curriculum requirements",
    student_friendly_name="Lesson Planner",
    categories=teacher_category,
    color="#4ECDC4",
    system_prompt="You are an experienced curriculum designer. Create detailed, engaging lesson plans that align with educational standards.",
    is_premium=True,
    is_recommended=True,
    is_active=True
)

tool3 = AITool.objects.create(
    slug="math-problem-solver",
    name="Math Problem Solver",
    description="Solves math problems and explains the solution step by step",
    student_friendly_name="Math Tutor",
    categories=student_category,
    color="#95E1D3",
    system_prompt="You are a patient math tutor. Solve problems step-by-step and explain concepts clearly.",
    is_premium=False,
    is_recommended=True,
    is_active=True
)

tool4 = AITool.objects.create(
    slug="science-experiment-designer",
    name="Science Experiment Designer",
    description="Designs interactive science experiments suitable for different grade levels",
    student_friendly_name="Lab Experiment Creator",
    categories=teacher_category,
    color="#F38181",
    system_prompt="You are a science education expert. Design safe, engaging experiments that teach scientific principles.",
    is_premium=True,
    is_recommended=False,
    is_active=True
)

tool5 = AITool.objects.create(
    slug="writing-assistant",
    name="Writing Assistant",
    description="Helps students improve their writing with suggestions for clarity and style",
    student_friendly_name="Smart Writer",
    categories=student_category,
    color="#AA96DA",
    system_prompt="You are a writing coach. Help users improve their writing with constructive suggestions.",
    is_premium=False,
    is_recommended=True,
    is_active=True
)

tool6 = AITool.objects.create(
    slug="quiz-generator",
    name="Quiz Generator",
    description="Creates customized quizzes based on topics and difficulty levels",
    student_friendly_name="Quiz Maker",
    categories=teacher_category,
    color="#FCBAD3",
    system_prompt="You are an assessment expert. Create engaging, fair quizzes that test understanding.",
    is_premium=False,
    is_recommended=False,
    is_active=True
)

print("Creating sample Tool Inputs...")
# Create Tool Inputs for tools
ToolInput.objects.create(
    tool=tool1,
    type="textarea",
    label="Student Essay",
    placeholder="Paste the student's essay here...",
    required=True,
    minlength=100,
    order=1
)

ToolInput.objects.create(
    tool=tool1,
    type="dropdown",
    label="Grade Level",
    options=["Grade 9", "Grade 10", "Grade 11", "Grade 12"],
    required=True,
    order=2
)

ToolInput.objects.create(
    tool=tool3,
    type="textarea",
    label="Math Problem",
    placeholder="Enter the math problem here...",
    required=True,
    order=1
)

ToolInput.objects.create(
    tool=tool3,
    type="dropdown",
    label="Difficulty Level",
    options=["Easy", "Medium", "Hard"],
    required=False,
    order=2
)

ToolInput.objects.create(
    tool=tool5,
    type="textarea",
    label="Your Text",
    placeholder="Paste your text here for improvement suggestions...",
    required=True,
    minlength=50,
    order=1
)

ToolInput.objects.create(
    tool=tool6,
    type="text",
    label="Topic",
    placeholder="Enter the topic for the quiz...",
    required=True,
    order=1
)

ToolInput.objects.create(
    tool=tool6,
    type="number",
    label="Number of Questions",
    placeholder="10",
    required=True,
    order=2
)

print("Creating sample Payments...")
# Create Payments
payment1 = Payment.objects.create(
    payment_type="subscription",
    merchant_reference="PAY001",
    order_tracking_id="ORDER001",
    organisation=school1,
    subscription=subscription1,
    amount=6000.00,
    currency="KES",
    plan=enterprise_plan,
    status="complete",
    paymethod="mpesa",
    payment_method="M-Pesa",
    payer_name="James Kibaki",
    payer_email="admin1@nairobi-intl.edu",
    payer_phone="+254712345678"
)

payment2 = Payment.objects.create(
    payment_type="subscription",
    merchant_reference="PAY002",
    order_tracking_id="ORDER002",
    organisation=school2,
    subscription=subscription2,
    amount=6000.00,
    currency="KES",
    plan=enterprise_plan,
    status="complete",
    paymethod="card",
    payment_method="Credit Card",
    payer_name="Mary Ochieng",
    payer_email="admin2@mombasa-academy.edu",
    payer_phone="+254723456789"
)

payment3 = Payment.objects.create(
    payment_type="topup",
    merchant_reference="PAY003",
    organisation=school1,
    amount=2000.00,
    currency="KES",
    status="pending",
    paymethod="mpesa"
)

print("Creating sample Invoices...")
# Create Invoices
invoice1 = Invoice.objects.create(
    invoice_number="INV-2026-001",
    payment=payment1,
    organisation=school1,
    amount=6000.00,
    currency="KES",
    status="paid",
    due_date="2026-03-15",
    paid_at="2026-02-15"
)

invoice2 = Invoice.objects.create(
    invoice_number="INV-2026-002",
    payment=payment2,
    organisation=school2,
    amount=6000.00,
    currency="KES",
    status="paid",
    due_date="2026-03-10",
    paid_at="2026-02-10"
)

print("Creating sample User AI Usage...")
# Create User AI Usage
UserAIUsage.objects.create(
    user=teacher1,
    total_requests=45,
    total_tokens=15000,
    total_cost=2.25
)

UserAIUsage.objects.create(
    user=student1,
    total_requests=120,
    total_tokens=45000,
    total_cost=7.50
)

print("Creating sample Tool Favorites...")
# Create Tool Favorites
ToolFavorite.objects.create(
    user=teacher1,
    tool=tool1
)

ToolFavorite.objects.create(
    user=teacher1,
    tool=tool2
)

ToolFavorite.objects.create(
    user=teacher2,
    tool=tool3
)

ToolFavorite.objects.create(
    user=student1,
    tool=tool3
)

ToolFavorite.objects.create(
    user=student1,
    tool=tool5
)

ToolFavorite.objects.create(
    user=student2,
    tool=tool5
)

print("Creating sample AI Logs...")
# Create AI Logs
AILog.objects.create(
    user=teacher1,
    tool="Essay Analyzer",
    topic="Literature",
    class_level="Grade 10",
    difficulty="Medium",
    prompt_tokens=150,
    completion_tokens=450,
    prompt="Analyze this essay...",
    response="This essay shows strong understanding of the topic...",
    response_time=2.5
)

AILog.objects.create(
    user=student1,
    tool="Math Problem Solver",
    topic="Algebra",
    class_level="Grade 9",
    difficulty="Easy",
    prompt_tokens=100,
    completion_tokens=300,
    prompt="Solve: 2x + 5 = 15",
    response="x = 5",
    response_time=1.2
)

AILog.objects.create(
    user=teacher2,
    tool="Lesson Plan Generator",
    topic="Science",
    class_level="Grade 11",
    difficulty="Hard",
    prompt_tokens=200,
    completion_tokens=800,
    prompt="Generate a lesson plan for photosynthesis...",
    response="Lesson Plan: Introduction to Photosynthesis...",
    response_time=5.8
)

print("✅ Sample data created successfully!")

