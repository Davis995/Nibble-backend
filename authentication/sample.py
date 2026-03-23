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



print("Creating sample Plans...")
# Create Plans
enterprise_plan = Plan.objects.create(
    name="Enterprise Premium",
    use_type="enterprise",
    total_credits=10000,
    max_users=300,
    monthly_price=350000,
    allowed_modals=["gpt-4o-mini","gpt-4", "gpt-3.5", "deepseek-chat"]
)

individual_plan = Plan.objects.create(
    name=" Basic",
    use_type="individual",
    total_credits=12000000,
    max_users=1,
    monthly_price=10000,
    allowed_modals=["gpt-4o-mini","deepseek-chat"]
)

individual_pro_plan = Plan.objects.create(
    name="Pro",
    use_type="individual",
    total_credits=100000,
    max_users=1,
    monthly_price=150.00,
    allowed_modals=["gpt-4", "gpt-3.5","deepseek-chat","gpt-4o-mini"]
)

# Add Free Plan
free_plan = Plan.objects.create(
    name="Free",
    use_type="individual",
    total_credits=120000,
    max_users=1,
    monthly_price=0.00,
    allowed_modals=["deepseek-chat"]
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
    password="DAVIS_1234",
    first_name="James",
    last_name="Kibaki",
    user_type="enterprise",
    role="school_admin",
    organisation=school1,
    is_staff=True
)

admin_user2 = User.objects.create_user(
    email="admin2@mombasa-academy.edu",
    password="DAVIS_1234",
    first_name="Mary",
    last_name="Ochieng",
    user_type="enterprise",
    role="school_admin",
    organisation=school2,
    is_staff=True
)

admin_user3 = User.objects.create_user(
    email="admin3@kisumu-high.edu",
    password="DAVIS_1234",
    first_name="David",
    last_name="Kipchoge",
    user_type="enterprise",
    role="school_admin",
    organisation=school3,
    is_staff=True
)

# Additional staff role for testing (designated curriculum coach)
staff_user1 = User.objects.create_user(
    email="coach1@nairobi-intl.edu",
    password="DAVIS_1234",
    first_name="Grace",
    last_name="Mwangi",
    user_type="enterprise",
    role="curriculum_coach",
    organisation=school1,
    is_staff=True
)

# Additional staff role for communications
staff_user2 = User.objects.create_user(
    email="comm1@mombasa-academy.edu",
    password="DAVIS_1234",
    first_name="Peter",
    last_name="Njoroge",
    user_type="enterprise",
    role="parent_liaison",
    organisation=school2,
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
    password="DAVIS_1234",
    first_name="Sarah",
    last_name="Mwangi",
    user_type="individual",
    role="teacher"
)

teacher2 = User.objects.create_user(
    email="teacher2@email.com",
    password="DAVIS_1234",
    first_name="Michael",
    last_name="Kipchoge",
    user_type="individual",
    role="teacher"
)

student1 = User.objects.create_user(
    email="student1@email.com",
    password="DAVIS_1234",
    first_name="Emma",
    last_name="Johnson",
    user_type="individual"
    
)

student2 = User.objects.create_user(
    email="student2@email.com",
    password="DAVIS_1234",
    first_name="Liam",
    last_name="Smith",
    user_type="individual"
)

print("Creating subscriptions for individual users...")
# Assign plans to users (alternating for demonstration)
teacher1_subscription = Subscription.objects.create(
    max_users=individual_plan.max_users,
    plan=individual_plan,
    user=teacher1,
    start_credits=individual_plan.total_credits,
    remaining_credits=individual_plan.total_credits,
    billing_start_date='2026-03-01',
    billing_end_date='2026-04-01',
    status="active"
)
teacher1.subscription_plan = individual_plan
teacher1.save()


# teacher2 and student2 get Free plan, teacher1 and student1 keep paid plans
teacher2_subscription = Subscription.objects.create(
    max_users=free_plan.max_users,
    plan=free_plan,
    user=teacher2,
    start_credits=free_plan.total_credits,
    remaining_credits=free_plan.total_credits,
    billing_start_date='2026-03-01',
    billing_end_date='2026-04-01',
    status="active"
)
teacher2.subscription_plan = free_plan
teacher2.save()

student1_subscription = Subscription.objects.create(
    max_users=individual_plan.max_users,
    plan=individual_plan,
    user=student1,
    start_credits=individual_plan.total_credits,
    remaining_credits=individual_plan.total_credits,
    billing_start_date='2026-03-01',
    billing_end_date='2026-04-01',
    status="active"
)
student1.subscription_plan = individual_plan
student1.save()

student2_subscription = Subscription.objects.create(
    max_users=free_plan.max_users,
    plan=free_plan,
    user=student2,
    start_credits=free_plan.total_credits,
    remaining_credits=free_plan.total_credits,
    billing_start_date='2026-03-01',
    billing_end_date='2026-04-01',
    status="active"
)
student2.subscription_plan = free_plan
student2.save()

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
    name="Learning Enhancement ",
    description="AI tools designed for teachers to enhance classroom experience",
    type="teacher",
    icon="FileText"
)

assessment_category = ToolCategory.objects.create(
    name="planning ",
    description="Tools to create quizzes, tests, and analyze student performance",
    type="teacher",
    icon="CheckCircle"
)

communication_category = ToolCategory.objects.create(
    name="Communication Tools",
    description="Tools for parent-teacher communication and classroom messaging",
    type="teacher",
    icon="MessageSquare"
)

support_category = ToolCategory.objects.create(
    name="Student Support Tools",
    description="Tools for personalized learning accommodations and student support",
    type="teacher",
    icon="Users"
)

student_category = ToolCategory.objects.create(
    name="Student Tools",
    description="AI tools designed for students to improve learning",
    type="student",
    icon="Zap"
)

print("Creating sample AI Tools...")


tool1 = AITool.objects.create(
    slug="Scaffold",
    name="Scaffold",
    description="Analyzes student essays and provides detailed feedback on structure, grammar, and content",
    student_friendly_name="Scaffold",
    categories=teacher_category,
    color="#FF6B6B",
    system_prompt="Explain [topic below] to me as if I were a beginner, then gradually increase the complexity. Start with the basics, and add real-world examples as we progress.if class provided answer in curriculum used in Uganda",
    is_premium=False,
    is_recommended=True,
    is_active=True,
    preferred_modal="gpt-4o-mini"
)


print("Creating sample Tool Inputs...")
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


# Create AI Tools with preferred_modal
tool2 = AITool.objects.create(
    slug="bridge",
    name="Bridge",
    description="This tool helps students see how subjects connect, apply ideas in real life, and think creatively",
    student_friendly_name="Bridge",
    categories=teacher_category,
    color="#FF6B6B",
    icon="",
    system_prompt="Explore how [topic]connects with other fields or disciplines. Provide examples of cross-disciplinary applications, collaborative opportunities, and how integrating insights from different areas can enhance understanding or innovation in [topic].",
    is_premium=False,
    is_recommended=True,
    is_active=True,
    preferred_modal="gpt-4o-mini"
)
print("Creating sample Tool Inputs...")
ToolInput.objects.create(
    tool=tool2,
    type="text",
    label="Topic",
    placeholder="Enter your topic",
    required=True,
    minlength=100,
    order=1,
   


)
ToolInput.objects.create(
    tool=tool2,
    type="dropdown",
    label="Grade Level",
    options=["S1", "S2", "S3", "S4"],
    required=False,
    order=2,

)

tool3 = AITool.objects.create(
    slug="conceptify",
    name="Conceptify",
    description="simplifies complex ideas",
    student_friendly_name="Conceptify",
    categories=student_category,
    color="#95E1D3",
    system_prompt="You are a teacher following the Uganda National Curriculum. Explain the [topic] clearly using simple language suitable for the student’s level. Use well-constructed analogies and comparisons to help learners understand the concept. Relate the principles of the topic to everyday experiences in Uganda, familiar activities, or widely known phenomena. Where possible, connect the concept to examples from other subjects such as science, technology, or daily life so that the idea becomes more tangible, memorable, and easy to understand.",
    is_premium=False,
    is_recommended=True,
    is_active=True,
    icon="Globe",
    preferred_modal="gpt-4o-mini"
)
print("Creating sample Tool Inputs...")
ToolInput.objects.create(
    tool=tool3,
    type="text",
    label="Topic",
    placeholder="Enter your topic",
    required=True,
    minlength=100,
    order=1
)
ToolInput.objects.create(
    tool=tool3,
    type="dropdown",
    label="Grade Level",
    options=["S1", "S2", "S3", "S4"],
    required=False,
    order=2
)


tool4 = AITool.objects.create(
    slug="learnQuiz",
    name="LearnQuiz",
    description="simplifies complex ideas",
    student_friendly_name="LearnQuiz",
    categories=student_category,
    color="#95E1D3",
    system_prompt="Act as a teacher following the Uganda National Curriculum. Generate 10 mixed-level questions on [topic]. Include multiple-choice, short-answer, and one long essay question. After each question, provide the correct answer and a brief explanation. Ensure the questions progress from basic to advanced understanding and use clear academic language suitable for students.",
    is_recommended=True,
    is_active=True,
    preferred_modal="gpt-4o-mini"
)
print("Creating sample Tool Inputs...")
ToolInput.objects.create(
    tool=tool4,
    type="text",
    label="Topic",
    placeholder="Enter your topic",
    required=True,
    minlength=100,
    order=1
)
ToolInput.objects.create(
    tool=tool4,
    type="dropdown",
    label="Grade Level",
    options=["S1", "S2", "S3", "S4"],
    required=False,
    order=2
)

# Additional search-style teacher tools
extra_tool_data = [
    ('real-world-connections', 'Real World Connections', 'Real World Connections', 'Generate real-world examples for what you are learning about!', '#22C55E', 'Link', 'Topic or concept'),
    ('research-assistant', 'Research Assistant', 'Research Assistant', 'Find information and sources for a research project.', '#8B5CF6', 'Search', 'Research topic or question'),
    ('rewrite-it', 'Rewrite It!', 'Rewrite It!', 'Take any text and rewrite it with custom criteria.', '#EC4899', 'Edit3', 'Text to rewrite'),
    ('song-generator', 'Song Generator', 'Song Generator', 'Write a custom song about any topic to the tune of your choice.', '#F59E0B', 'Music', 'Song theme or topic'),
    ('translate-it', 'Translate It!', 'Translate It!', 'Take any text and translate it into any language instantly.', '#0EA5E9', 'Globe', 'Text to translate'),
    ('summarize-it', 'Summarize It!', 'Summarize It!', 'Take any text and summarize it in whatever length you choose.', '#22D3EE', 'FileText', 'Text to summarize'),
    ('5-questions', '5 Questions', '5 Questions', 'Get AI to ask 5 questions to push your creativity and deepen thinking.', '#6EE7B7', 'QuestionMarkCircle', 'Topic for questions'),
    ('book-suggestions', 'Book Suggestions', 'Book Suggestions', 'Discover books that match your interests.', '#A3E635', 'BookOpen', 'Genre or interest'),
    ('conceptual-understanding', 'Conceptual Understanding', 'Conceptual Understanding', 'Generate ideas about how to grow conceptual understanding of concepts.', '#60A5FA', 'Lightbulb', 'Concept area'),
    ('expand-on-idea', 'Expand on My Idea', 'Expand on My Idea', 'Use AI to expand on your ideas to help you be creative.', '#F97316', 'LayoutGrid', 'Idea description'),
    ('idea-generator', 'Idea Generator', 'Idea Generator', 'Get help coming up with ideas on any topic.', '#6366F1', 'Sparkles', 'Topic or prompt'),
    ('informational-texts', 'Informational Texts', 'Informational Texts', 'Generate original informational texts customized to a topic of your choice.', '#A78BFA', 'AlignJustify', 'Subject text'),
    ('joke-creator', 'Joke Creator', 'Joke Creator', 'Generate jokes based on any topic to be the coolest student out there.', '#F43F5E', 'Smile', 'Topic or keyword'),
    ('make-it-relevant', 'Make it Relevant!', 'Make it Relevant!', 'Generate ideas that make what you’re learning relevant based on your interests and background.', '#FBBF24', 'Heart', 'Learning topic'),
    ('multiple-explanations', 'Multiple Explanations', 'Multiple Explanations', 'Generate clear explanations of concepts that you’re learning to get a better understanding.', '#38BDF8', 'BookOpen', 'Concept to explain'),
    ('quiz-me', 'Quiz Me!', 'Quiz Me!', 'Quiz yourself on any topic or type of text.', '#BBF7D0', 'ClipboardCheck', 'Topic to quiz'),
]

for slug_val, name, friendly, desc, color, icon_name, placeholder in extra_tool_data:
    tool, created = AITool.objects.update_or_create(
        slug=slug_val,
        defaults={
            'name': name,
            'description': desc,
            'student_friendly_name': friendly,
            'categories': teacher_category,
            'color': color,
            'icon': icon_name,
            'system_prompt': '',
            'is_premium': False,
            'is_recommended': True,
            'is_active': True,
            'preferred_modal': 'gpt-4o-mini',
        }
    )
    
    # Determine the input type based on placeholder length/content
    input_type = 'textarea' if 'Text to' in placeholder or 'Subject text' in placeholder else 'text'
    
    ToolInput.objects.get_or_create(
        tool=tool,
        label="Topic" if input_type == 'text' else "Context",
        defaults={
            'type': input_type,
            'placeholder': placeholder,
            'required': True,
            'minlength': 3,
            'order': 1
        }
    )

print("Creating extra sample Student Tools...")
student_tool_data = [
    ('study-buddy', 'Study Buddy', 'Study Buddy', 'Get help understanding difficult concepts in a friendly way.', '#10B981', 'Users', 'Topic you need help with'),
    ('flashcard-maker', 'Flashcard Maker', 'Flashcard Maker', 'Generate flashcards to help memorize facts and definitions.', '#3B82F6', 'CreditCard', 'Subject or list of terms'),
    ('essay-outliner', 'Essay Outliner', 'Essay Outliner', 'Structure your thoughts into a clear essay outline.', '#8B5CF6', 'AlignLeft', 'Essay topic or prompt'),
    ('math-step-by-step', 'Math Step-by-Step', 'Math Solver', 'Get step-by-step breakdowns of math problems.', '#EF4444', 'Hash', 'Math equation or problem'),
    ('grammar-checker', 'Grammar Checker', 'Grammar Fix', 'Check your writing for grammar and spelling mistakes.', '#F59E0B', 'CheckSquare', 'Text to check'),
]

for slug_val, name, friendly, desc, color, icon_name, placeholder in student_tool_data:
    tool, created = AITool.objects.update_or_create(
        slug=slug_val,
        defaults={
            'name': name,
            'description': desc,
            'student_friendly_name': friendly,
            'categories': student_category,  # assign to student category
            'color': color,
            'icon': icon_name,
            'system_prompt': '',
            'is_premium': False,
            'is_recommended': True,
            'is_active': True,
            'preferred_modal': 'gpt-4o-mini',
        }
    )
    
    input_type = 'textarea' if 'Text to' in placeholder or 'list of' in placeholder else 'text'
    
    # First input based on placeholder
    ToolInput.objects.get_or_create(
        tool=tool,
        label="Context" if input_type == 'textarea' else "Topic",
        defaults={
            'type': input_type,
            'placeholder': placeholder,
            'required': True,
            'minlength': 3,
            'order': 1
        }
    )
    
    # Second optional dropdown input reflecting the student tools inputs
    ToolInput.objects.get_or_create(
        tool=tool,
        label="Grade Level",
        defaults={
            'type': 'dropdown',
            'options': ["Primary", "S1", "S2", "S3", "S4", "A-Level"],
            'required': False,
            'order': 2
        }
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
ToolFavorite.objects.create(user=teacher1, tool=tool1)
ToolFavorite.objects.create(user=teacher2, tool=tool3)
ToolFavorite.objects.create(user=student1, tool=tool3)
ToolFavorite.objects.create(user=student2, tool=tool1)

# More Favorites for teachers
song_gen = AITool.objects.filter(slug='song-generator').first()
if song_gen:
    ToolFavorite.objects.create(user=teacher1, tool=song_gen)

quiz_me = AITool.objects.filter(slug='quiz-me').first()
if quiz_me:
    ToolFavorite.objects.create(user=teacher2, tool=quiz_me)

# More Favorites for students
study_buddy = AITool.objects.filter(slug='study-buddy').first()
if study_buddy:
    ToolFavorite.objects.create(user=student1, tool=study_buddy)
    ToolFavorite.objects.create(user=student2, tool=study_buddy)

essay_outliner = AITool.objects.filter(slug='essay-outliner').first()
if essay_outliner:
    ToolFavorite.objects.create(user=student1, tool=essay_outliner)

math_solver = AITool.objects.filter(slug='math-step-by-step').first()
if math_solver:
    ToolFavorite.objects.create(user=student2, tool=math_solver)

print("Creating sample AI Logs...")
# Create AI Logs
AILog.objects.create(
    user=teacher1,
    tool="Essay Analyzer",
    topic="Literature",
    class_level="Grade 10",
    difficulty="Medium",
    inputs={
        "topic": "Literature",
        "grade": "Grade 10",
        "difficulty": "Medium",
        "text_to_analyze": "The Great Gatsby represents the decay of the American Dream..."
    },
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
    inputs={
        "topic": "Algebra",
        "grade": "Grade 9",
        "difficulty": "Easy",
        "equation": "2x + 5 = 15"
    },
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
    inputs={
        "topic": "Photosynthesis",
        "grade": "11th Grade",
        "duration": "90 minutes",
        "subject": "Biology"
    },
    prompt_tokens=200,
    completion_tokens=800,
    prompt="Generate a lesson plan for photosynthesis...",
    response="Lesson Plan: Introduction to Photosynthesis...",
    response_time=5.8
)

AILog.objects.create(
    user=teacher1,
    tool="Rubric Generator",
    topic="History Essay Rubric",
    class_level="Grade 10",
    difficulty="Hard",
    inputs={
        "assignment": "History Essay",
        "criteria": "Thesis, Evidence, Organization, Grammar",
        "scale": "4-point"
    },
    prompt_tokens=120,
    completion_tokens=500,
    prompt="Create a 4-point rubric for a high school history essay.",
    response="| Criteria | 4 - Excellent | 3 - Proficient | 2 - Developing | 1 - Beginning |\n|---|---|---|---|---|\n| **Thesis** | Clear, arguable thesis statement. | Thesis is present but could be stronger. | Thesis is vague or weak. | No thesis statement. |\n| **Evidence** | Strong evidence supports all claims. | Good evidence supports most claims. | Some evidence, but weak connections. | Little to no evidence used. |",
    response_time=3.5
)

AILog.objects.create(
    user=student2,
    tool="Multiple Explanations",
    topic="Quantum Computing",
    class_level="Grade 12",
    difficulty="Hard",
    inputs={
        "concept": "Quantum Computing",
        "audience": "High School Student",
        "analogy_preference": "Sports"
    },
    prompt_tokens=90,
    completion_tokens=650,
    prompt="Explain Quantum Computing to a High School Student using Sports analogies.",
    response="Imagine a regular computer as a baseball game where pitches are either fastballs (1s) or curveballs (0s)...",
    response_time=4.1
)

print("✅ Sample data created successfully!")

from authentication.models import User
user = User.objects.create_user(
        email="mugumyadavi@gmail.com",
        password="DAVIS_1234",
        first_name="mugumya",
        last_name="davi",
        user_type="individual",
        role ='sale_manager'
    )
from authentication.models import *
plan = Plan.objects.get(id=3)
user = User.objects.get(id=5)
subscription3 = Subscription.objects.create(
    max_users=plan.max_users,
    plan=plan,
    user=user,
    start_credits=plan.total_credits,
    remaining_credits=plan.total_credits,
    billing_start_date='2026-01-15',
    billing_end_date='2026-02-15',
    status="active")
user.subscription_plan = plan
user.save()

