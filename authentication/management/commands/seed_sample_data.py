import uuid
import random
from datetime import datetime, timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction
from django.contrib.auth.hashers import make_password

from authentication.models import Plan, PlanFeature, User, Subscription
from schools.models import School, Student, Staff, Activity, UsageLog
from payments.models import Payment, Invoice, Audit
from tools.models import AITool, AILog, UserAIUsage, ToolCategory, ToolInput, AIModelConfig


class Command(BaseCommand):
    help = 'Seed the database with sample data for testing and development'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear existing sample data before seeding',
        )

    def handle(self, *args, **options):
        if options['clear']:
            self.stdout.write('Clearing existing data...')
            self.clear_data()

        self.stdout.write('Seeding sample data...')
        
        with transaction.atomic():
            plans = self.seed_plans()
            operator = self.seed_operator()
            schools = self.seed_schools(operator)
            self.seed_school_staff_and_students(schools)
            self.seed_individual_users(plans)
            self.seed_payments_and_invoices(schools)
            self.seed_activities(schools)
            
            # New Seeding logic
            self.seed_ai_model_configs()
            tools = self.seed_tools()
            self.seed_ai_logs(tools)
            self.seed_usage_logs(schools, tools)

        self.stdout.write(self.style.SUCCESS('Successfully seeded sample data'))

    def clear_data(self):
        # Clear in reverse order of dependencies
        Activity.objects.all().delete()
        AILog.objects.all().delete()
        UserAIUsage.objects.all().delete()
        UsageLog.objects.all().delete()
        Invoice.objects.all().delete()
        Audit.objects.all().delete()
        Payment.objects.all().delete()
        Student.objects.all().delete()
        Staff.objects.all().delete()
        Subscription.objects.all().delete()
        
        # Delete users BEFORE schools to avoid constraint violation on SET_NULL
        User.objects.exclude(is_superuser=True).delete()
        
        School.objects.all().delete()
        AITool.objects.all().delete()
        ToolCategory.objects.all().delete()
        AIModelConfig.objects.all().delete()
        
        PlanFeature.objects.all().delete()
        Plan.objects.all().delete()

    def seed_plans(self):
        self.stdout.write('Seeding plans...')
        plans = {}
        
        # 1. Free Individual Plan
        free_plan, _ = Plan.objects.get_or_create(
            plan_id='free',
            defaults={
                'name': 'Free Tier',
                'description': 'Essential tools for individual learners to explore AI-powered education.',
                'use_type': 'individual',
                'theme': 'cream',
                'currency': 'UGX',
                'total_credits': 2000,
                'monthly_price': 0,
                'allowed_modals': ['gpt-3.5-turbo', 'deepseek-chat'],
                'cta': 'Start for Free',
                'display_order': 1,
                'is_active': True
            }
        )
        plans['free'] = free_plan
        
        # 2. Pro Individual Plan (MOST POPULAR)
        pro_plan, _ = Plan.objects.get_or_create(
            plan_id='pro',
            defaults={
                'name': 'Individual Pro',
                'description': 'Advanced AI models and higher credit limits for power students and teachers.',
                'use_type': 'individual',
                'theme': 'light',
                'currency': 'UGX',
                'total_credits': 5000,
                'monthly_price': 35000,
                'annual_price': 25000,
                'annual_billed': 300000,
                'badge': 'Save 28%',
                'is_popular': True,
                'is_active': True,
                'allowed_modals': ['gpt-4o', 'claude-3-5-sonnet', 'deepseek-chat'],
                'cta': 'Go Pro',
                'display_order': 2
            }
        )
        plans['pro'] = pro_plan
        
        # 3. Elite Individual Plan
        elite_plan, _ = Plan.objects.get_or_create(
            plan_id='elite',
            defaults={
                'name': 'Individual Elite',
                'description': 'The ultimate AI experience with early access to reasoning models.',
                'use_type': 'individual',
                'theme': 'dark',
                'currency': 'UGX',
                'total_credits': 20000,
                'monthly_price': 120000,
                'annual_price': 90000,
                'annual_billed': 1080000,
                'badge': 'Save 25%',
                'is_active': True,
                'allowed_modals': ['gpt-4o', 'o1-preview', 'claude-3-5-sonnet', 'deepseek-reasoner'],
                'cta': 'Get Elite',
                'display_order': 3
            }
        )
        plans['elite'] = elite_plan

        # 4. Starter School Plan
        starter_school, _ = Plan.objects.get_or_create(
            plan_id='starter_school',
            defaults={
                'name': 'Starter School',
                'description': 'Perfect for small private schools or specialized learning centers.',
                'use_type': 'enterprise',
                'theme': 'cream',
                'currency': 'UGX',
                'total_credits': 50000,
                'max_users': 50,
                'monthly_price': 250000,
                'is_active': True,
                'allowed_modals': ['gpt-4o', 'claude-3-5-sonnet', 'deepseek-chat'],
                'cta': 'Select Starter',
                'display_order': 1
            }
        )
        plans['starter_school'] = starter_school
        
        # 5. Pro School Plan (MOST POPULAR ENTERPRISE)
        pro_school, _ = Plan.objects.get_or_create(
            plan_id='pro_school',
            defaults={
                'name': 'Institutional Pro',
                'description': 'Full-scale AI integration for modern primary and secondary schools.',
                'use_type': 'enterprise',
                'theme': 'light',
                'currency': 'UGX',
                'total_credits': 250000,
                'max_users': 250,
                'monthly_price': 1000000,
                'is_popular': True,
                'is_active': True,
                'allowed_modals': ['gpt-4o', 'claude-3-5-sonnet', 'deepseek-chat'],
                'cta': 'Empower Your School',
                'display_order': 2
            }
        )
        plans['pro_school'] = pro_school
        
        # 6. Institutional Elite Plan
        institutional_elite, _ = Plan.objects.get_or_create(
            plan_id='institutional',
            defaults={
                'name': 'Institutional Elite',
                'description': 'Advanced institutional scale with custom model permissions and priority API access.',
                'use_type': 'enterprise',
                'theme': 'dark',
                'currency': 'UGX',
                'total_credits': 1000000,
                'max_users': 1000,
                'monthly_price': 3500000,
                'is_active': True,
                'allowed_modals': ['gpt-4o', 'o1-preview', 'claude-3-5-sonnet', 'deepseek-reasoner'],
                'cta': 'Contact Sales',
                'display_order': 3
            }
        )
        plans['institutional'] = institutional_elite

        # Seed Plan Features
        features = [
            # Individual Features
            (free_plan, "Access to GPT-3.5 Turbo", True, 1),
            (free_plan, "100 Monthly Credits", True, 2),
            (free_plan, "Standard Response Time", True, 3),
            
            (pro_plan, "Access to GPT-4o & Claude 3.5", True, 1),
            (pro_plan, "5,000 Monthly Credits", True, 2),
            (pro_plan, "Priority Response Time", True, 3),
            (pro_plan, "Advanced Analytics Dashboard", True, 4),
            
            (elite_plan, "Access to Reasoning Models (o1)", True, 1),
            (elite_plan, "20,000 Monthly Credits", True, 2),
            (elite_plan, "Early Access to New Tools", True, 3),
            
            # Enterprise Features
            (starter_school, "Up to 50 Registered Users", True, 1),
            (starter_school, "50,000 Shared Credits", True, 2),
            (starter_school, "Teacher Tools Access", True, 3),
            
            (pro_school, "Up to 250 Registered Users", True, 1),
            (pro_school, "250,000 Shared Credits", True, 2),
            (pro_school, "Administrative Dashboard", True, 3),
            (pro_school, "Bulk User Onboarding", True, 4),
            
            (institutional_elite, "Up to 1,000 Registered Users", True, 1),
            (institutional_elite, "1,000,000 Shared Credits", True, 2),
            (institutional_elite, "Custom System Prompts", True, 3),
            (institutional_elite, "Dedicated Account Success Manager", True, 4),
        ]
        
        for plan, text, included, order in features:
            PlanFeature.objects.get_or_create(
                plan=plan, 
                text=text, 
                defaults={'included': included, 'order': order}
            )
            
        return plans

    def seed_operator(self):
        self.stdout.write('Seeding operator...')
        try:
            operator, created = User.objects.get_or_create(
                email='admin@nibble.ug',
                defaults={
                    'username': 'admin@nibble.ug',
                    'first_name': 'Nibble',
                    'last_name': 'Operator',
                    'user_type': 'nibble',
                    'role': 'operator',
                    'is_staff': True,
                    'is_superuser': True,
                    'is_verified': True,
                    'is_onboarded': True,
                    'password': make_password('password123')
                }
            )
            self.stdout.write(f"Operator seeded: {operator.email}, type: {operator.user_type}")
            return operator
        except Exception as e:
            self.stderr.write(f"Failed to seed operator: {e}")
            raise e

    def seed_schools(self, operator):
        self.stdout.write('Seeding schools...')
        schools_data = [
            ('Greenwood Academy', 'contact@greenwood.edu'),
            ('Hillside International', 'admin@hillside.ac.ug'),
            ('Lakeview Primary', 'info@lakeview.org'),
        ]
        
        schools = []
        enterprise_plan = Plan.objects.get(plan_id='pro_school')
        
        for name, email in schools_data:
            admin_email = f"admin@{email.split('@')[1]}"
            # Create user as individual first to satisfy constraint, then update to enterprise after org is set
            school_admin, _ = User.objects.get_or_create(
                email=admin_email,
                defaults={
                    'username': admin_email,
                    'first_name': f"{name.split(' ')[0]}",
                    'last_name': 'Admin',
                    'user_type': 'individual', # TEMPORARY
                    'role': 'school_admin',
                    'is_verified': True,
                    'password': make_password('password123')
                }
            )
            
            # Create school
            school, _ = School.objects.get_or_create(
                school_email=email,
                defaults={
                    'name': name,
                    'max_students': 500,
                    'admin_user': school_admin,
                    'assigned_staff': operator,
                    'is_active': True,
                    'org_orientation': True
                }
            )
            
            # Update user's organisation and user_type
            school_admin.organisation = school
            school_admin.user_type = 'enterprise'
            school_admin.save()
            
            # Create subscription for school
            Subscription.objects.get_or_create(
                organisation=school,
                defaults={
                    'plan': enterprise_plan,
                    'max_users': 500,
                    'start_credits': 100000,
                    'remaining_credits': 85000,
                    'billing_start_date': timezone.now().date() - timedelta(days=30),
                    'billing_end_date': timezone.now().date() + timedelta(days=335),
                    'status': 'active'
                }
            )
            
            schools.append(school)
            
        return schools

    def seed_school_staff_and_students(self, schools):
        self.stdout.write('Seeding staff and students...')
        roles = ['teacher', 'student']
        
        for school in schools:
            # Seed Teachers
            for i in range(2):
                teacher_email = f"teacher{i+1}@{school.school_email.split('@')[1]}"
                User.objects.get_or_create(
                    email=teacher_email,
                    defaults={
                        'username': teacher_email,
                        'first_name': f"Teacher {i+1}",
                        'last_name': school.name.split(' ')[0],
                        'user_type': 'enterprise',
                        'role': 'teacher',
                        'organisation': school,
                        'is_verified': True,
                        'password': make_password('password123')
                    }
                )
                Staff.objects.get_or_create(
                    school=school,
                    school_email=teacher_email,
                    defaults={
                        'first_name': f"Teacher {i+1}",
                        'last_name': school.name.split(' ')[0],
                        'role': 'teacher',
                        'subject': random.choice(['Mathematics', 'History', 'Physics', 'Biology'])
                    }
                )
            
            # Seed Students
            for i in range(5):
                student_code = f"STU{i+100}"
                student_email = f"student{i+1}@{school.school_email.split('@')[1]}"
                User.objects.get_or_create(
                    email=student_email,
                    defaults={
                        'username': student_email,
                        'first_name': f"Student {i+1}",
                        'last_name': 'Test',
                        'user_type': 'enterprise',
                        'role': 'student',
                        'organisation': school,
                        'is_verified': True,
                        'password': make_password('password123')
                    }
                )
                Student.objects.get_or_create(
                    school=school,
                    student_code=student_code,
                    defaults={
                        'first_name': f"Student {i+1}",
                        'last_name': 'Test',
                        'school_email': student_email,
                        'is_active': True
                    }
                )

    def seed_individual_users(self, plans):
        self.stdout.write('Seeding individual users...')
        plus_plan = plans['pro']
        
        for i in range(3):
            email = f"user{i+1}@gmail.com"
            user, _ = User.objects.get_or_create(
                email=email,
                defaults={
                    'username': email,
                    'first_name': f"Individual {i+1}",
                    'last_name': "User",
                    'user_type': 'individual',
                    'role': 'student',
                    'is_verified': True,
                    'password': make_password('password123')
                }
            )
            
            Subscription.objects.get_or_create(
                user=user,
                defaults={
                    'plan': plus_plan,
                    'max_users': 1,
                    'start_credits': 1000,
                    'remaining_credits': 450,
                    'billing_start_date': timezone.now().date() - timedelta(days=15),
                    'billing_end_date': timezone.now().date() + timedelta(days=15),
                    'status': 'active'
                }
            )

    def seed_payments_and_invoices(self, schools):
        self.stdout.write('Seeding payments and invoices...')
        for school in schools:
            # Payment for enterprise
            payment, _ = Payment.objects.get_or_create(
                merchant_reference=f"REF-{uuid.uuid4().hex[:8].upper()}",
                defaults={
                    'payment_type': 'subscription',
                    'organisation': school,
                    'amount': 1000000.00,
                    'currency': 'UGX',
                    'status': 'complete',
                    'paymethod': 'Mobile Money',
                    'transaction_date': timezone.now() - timedelta(days=30)
                }
            )
            
            Invoice.objects.get_or_create(
                invoice_number=f"INV-{uuid.uuid4().hex[:6].upper()}",
                payment=payment,
                defaults={
                    'organisation': school,
                    'amount': 1000000.00,
                    'currency': 'UGX',
                    'status': 'paid',
                    'paid_at': timezone.now() - timedelta(days=30)
                }
            )

    def seed_activities(self, schools):
        self.stdout.write('Seeding school activities...')
        actions = [
            "Generated a Lesson Plan",
            "Created a Quiz",
            "Marked an Assignment",
            "Logged in",
            "Updated Profile",
            "Generated an Essay",
            "Used Math Tool"
        ]
        
        for school in schools:
            teachers = User.objects.filter(organisation=school, role='teacher')
            students = User.objects.filter(organisation=school, role='student')
            
            for _ in range(15):
                user = random.choice(list(teachers) + list(students))
                Activity.objects.create(
                    school=school,
                    user_name=user.get_full_name(),
                    role=user.get_role_display(),
                    action=random.choice(actions),
                    tool=random.choice(["Lesson Plan Gen", "Quiz Maker", "Essay Helper", "General"]),
                    time="recently",
                    date=timezone.now().date() - timedelta(days=random.randint(0, 7))
                )

    def seed_ai_model_configs(self):
        self.stdout.write('Seeding AI Model Configurations...')
        configs = [
            ('gpt-3.5-turbo', 'GPT-3.5 Turbo', 'openai', 0.50, 1.50, 5, 1.0, 0.0),
            ('gpt-4o', 'GPT-4o Omnimodel', 'openai', 5.00, 15.00, 50, 1.0, 0.1),
            ('o1-preview', 'o1 Preview (Reasoning)', 'openai', 15.0, 60.0, 150, 1.2, 0.15),
            ('claude-3-5-sonnet', 'Claude 3.5 Sonnet', 'anthropic', 3.0, 15.0, 30, 1.0, 0.05),
            ('deepseek-chat', 'DeepSeek V3 Chat', 'deepseek', 0.14, 0.28, 2, 0.5, 0.0),
            ('deepseek-reasoner', 'DeepSeek R1 Reasoner', 'deepseek', 0.55, 2.19, 10, 0.8, 0.0),
        ]
        
        for model_id, name, provider, in_wt, out_wt, min_chrg, mult, disc in configs:
            AIModelConfig.objects.get_or_create(
                model_id=model_id,
                defaults={
                    'name': name,
                    'provider': provider,
                    'input_token_weight': in_wt,
                    'output_token_weight': out_wt,
                    'min_charge': min_chrg,
                    'credit_multiplier': mult,
                    'enterprise_discount': disc,
                    'is_active': True
                }
            )

    def seed_tools(self):
        self.stdout.write('Seeding tools and categories...')
        # Categories
        teacher_cat, _ = ToolCategory.objects.get_or_create(
            name='Teacher Tools',
            defaults={'description': 'Tools for lesson planning, assessment, and classroom management', 'type': 'teacher', 'icon': 'Chalkboard'}
        )
        student_cat, _ = ToolCategory.objects.get_or_create(
            name='Student Tools',
            defaults={'description': 'Tools for writing, research, math, and study support', 'type': 'student', 'icon': 'GraduationCap'}
        )
        
        # Tools Data from Registries
        # Format: (Name, Description, Student Friendly Name, Category, Color, Icon, System Prompt, User Template, Input Fields)
        tools_data = [
            # --- TEACHER TOOLS ---
            (
                'Lesson Plan Generator', 
                'Generate comprehensive, pedagogically sound lesson plans.', 
                'Lesson Builder', 
                teacher_cat, '#3B82F6', 'FileText',
                "You are an expert instructional designer. Create highly engaging, pedagogically sound lesson plans.",
                "Generate a comprehensive lesson plan for {grade} grade students.\nTopic/Objective: {topic}\nAlignment: {standards}\nSpecial Instructions: {additional}\nInclude: Objectives, Materials, Hook, Instruction, Practice, and Assessment.",
                "Grade Level, Topic/Standard/Objective, Additional Criteria, Standards Alignment"
            ),
            (
                'Unit Plan Generator',
                'Create cohesive, multi-lesson unit plans for concept building.',
                'Unit Architect',
                teacher_cat, '#6366F1', 'Library',
                "You are a curriculum architect specializing in multi-lesson unit plans. Ensure logical progression and consistent themes.",
                "Create a {lessons} lesson unit plan for {grade} grade.\nUnit Topic: {topic}\nDuration: {duration}\nRequired Standards: {standards}\nProvide a unit overview and brief lesson outlines.",
                "Grade Level, Unit Topic, Number of Lessons, Standards, Unit Duration"
            ),
            (
                '5E Model Science Lesson',
                'Design inquiry-based science lessons using the 5E model.',
                'Science 5E Helper',
                teacher_cat, '#10B981', 'Beaker',
                "You are a science education expert specializing in the 5E Instructional Model (Engage, Explore, Explain, Elaborate, Evaluate).",
                "Design a science lesson for {grade} grade using the 5E model.\nTopic: {topic}\nNGSS Alignment: {standards}\nMaterials to use: {materials}",
                "Grade Level, Science Topic, NGSS Standards, Available Materials"
            ),
            (
                'Assessment Generator',
                'Create quizzes and tests with various question types.',
                'Quiz Master',
                teacher_cat, '#A855F7', 'ClipboardCheck',
                "You are an assessment specialist. Create reliable multiple-choice questions with clear correct answers and plausible distractors. Always provide an answer key.",
                "Create a {count} question {difficulty} quiz for {grade} grade on {topic}.\nTarget DOK: {dok}\nOutput each question with 4 options and include an Answer Key.",
                "Topic or Standard, Grade Level, Number of Questions, Difficulty, DOK Level"
            ),
            (
                'Rubric Generator',
                'Generate clear, criteria-based rubrics in table format.',
                'Rubric Maker',
                teacher_cat, '#F43F5E', 'Table',
                "You are an expert in criteria-based assessment. Create clear, descriptive rubrics in a table format.",
                "Generate a {scale} rubric with {criteria} criteria for {grade} grade.\nTask to Grade: {description}",
                "Assignment Description, Grade Level, Number of Criteria, Performance Levels"
            ),
            (
                'Report Card Comments',
                'Write polished, balanced, and professional student comments.',
                'Comment Assistant',
                teacher_cat, '#F97316', 'MessageSquare',
                "You are a professional, empathetic teacher. Write report card comments with a balanced feedback structure.",
                "Generate a report card comment for {subject} with these strengths: {strengths} and growth areas: {growth}.\nTone: {tone}",
                "Subject Area, Student Strengths, Areas for Growth, Tone"
            ),
            (
                'IEP Segment Drafter',
                'Draft individualized education plan sections based on data.',
                'IEP Helper',
                teacher_cat, '#14B8A6', 'HeartPulse',
                "You are a Special Education teacher and IEP coordinator. Draft clear, goal-oriented, and legally compliant IEP sections.",
                "Draft IEP segments for an age {grade} student with {disability}.\nPerformance Levels: {performance}\nNeeds: {needs}\nProvide: Present Levels, SMART Goals, and Accommodations.",
                "Student Age/Grade, Disability Category, Performance Levels, Areas of Need"
            ),
            (
                'Social Story Creator',
                'Create Social Stories to help students understand social situations.',
                'Social Story AI',
                teacher_cat, '#06B6D4', 'Users',
                "You are a behavior specialist. Create Social Stories following the Carol Gray model, using simple, literal language.",
                "Create a social story for a student aged {age}.\nSituation: {situation}\nTarget Behavior: {behavior}\nFollow the Social Story structure: Descriptive, Perspective, and Directive sentences.",
                "Student Age, Social Situation/Skill, Desired Behavior"
            ),
            (
                'Professional Email Drafter',
                'Draft clear, respectful emails for parents and colleagues.',
                'Email Pro',
                teacher_cat, '#3B82F6', 'Mail',
                "You are a professional educational communicator. Write clear, concise, and respectful emails.",
                "Draft a {tone} email regarding {purpose}.\nPoints to include: {points}",
                "Email Purpose/Recipient, Key Points, Tone"
            ),
            (
                'Text Summarizer Pro',
                'Boil down long texts to their core "must-know" info.',
                'Fast Summary',
                teacher_cat, '#6366F1', 'Shrink',
                "You are a master of synthesis. Take long, complex texts and boil them down to core information.",
                "Summarize the following text.\nTarget Length: {length}\nFormat: {format}\nText: {text}",
                "Text to Summarize, Summary Length, Format"
            ),

            # --- STUDENT TOOLS ---
            (
                'Essay Outliner',
                'Organize your thoughts into a logical structure for an essay.',
                'Essay Planner',
                student_cat, '#2563EB', 'Layout',
                "You are a writing coach. Help students organize their thoughts into a logical structure. Do not write the essay for them.",
                "Help me outline an essay for my {grade} grade class.\nTopic: {topic}\nEssay Type: {type}\nTarget Paragraphs: {paragraphs}",
                "Topic/Prompt, Essay Type, Number of Paragraphs"
            ),
            (
                'Math Tutor (Step-by-Step)',
                'Get guided help solving math problems step-by-step.',
                'Math Guide',
                student_cat, '#EA580C', 'Calculator',
                "You are a patient math tutor. Guide students through problems step-by-step. Explain logic and ask small questions to check understanding.",
                "Help me with this {grade} grade math problem: {problem}.\nI want you to {type}.\nGuide me through the steps and explain the logic.",
                "Math Problem, Support Type (Solve, Explain, Check)"
            ),
            (
                'Raina for Students',
                'Friendly AI tutor for any school-related question.',
                'Ask Raina',
                student_cat, '#7C3AED', 'Sparkles',
                "You are Raina, a friendly and knowledgeable AI tutor. Use a conversational, encouraging tone and guide students to answers themselves.",
                "Hi Raina, I have a question about {text} for my {grade} grade class. Can you help me understand this better?",
                "Student Question"
            ),
            (
                'Study Guide Creator',
                'Generate organized study guides from your topics.',
                'Study Buddy',
                student_cat, '#9333EA', 'BookOpen',
                "You are an expert at test preparation. Create organized, clear study guides that summarize key concepts and provide practice questions.",
                "Create a study guide for my {grade} grade {subject} test on {date}.\nThe topics I need to know are: {topics}.",
                "Subject, Topics, Test Date"
            ),
            (
                'Story Spinner',
                'Turn your ideas into engaging short stories.',
                'Creative Story',
                student_cat, '#059669', 'Book',
                "You are a creative storyteller. Help students write engaging stories based on genre, character, and setting.",
                "Help me write a {genre} story for my {grade} grade class.\nMain Character: {character}\nSetting: {setting}\nStart: {beginning}",
                "Genre, Main Character, Setting, Beginning"
            ),
            (
                'AI Literacy Coach',
                'Learn how AI works and how to use it ethically.',
                'Learn AI',
                student_cat, '#D97706', 'Cpu',
                "You are an AI literacy coach. Explain how AI works, its benefits, and limitations in a simple, clear way focused on ethics.",
                "Explain {text} to me. How does this work in AI?\nProvide examples and explain why it's important to know this.",
                "Student Question about AI"
            ),
            (
                'Character Chat',
                'Chat with historical figures or book characters.',
                'History Talk',
                student_cat, '#06B6D4', 'User',
                "You are a role-play expert. Step into the shoes of a specific historical figure or book character and respond in-character.",
                "I want to talk to {name} from {source}.\nMy question is: {text}",
                "Character Name, Source (Book/History), Student Question"
            ),
            (
                'Grammar & Style Check',
                'Correct mistakes and learn the "why" behind them.',
                'Writing Lab',
                student_cat, '#2563EB', 'CheckCircle',
                "You are a helpful editor. Identify and correct grammar/spelling while explaining the 'why' so the student can learn.",
                "Check this text for grammar and spelling errors:\nText: {text}",
                "Student Text"
            ),
            (
                'Citation Helper',
                'Format your sources correctly in MLA, APA, or Chicago.',
                'Cite It',
                student_cat, '#06B6D4', 'Quote',
                "You are a citation expert. Help students format sources correctly following the latest style guides.",
                "Format this {type} as a {style} citation.\nAuthor: {author}\nTitle: {title}\nURL/Source: {url}\nDate: {date}",
                "Citation Style, Source Type, Source Details"
            ),
            (
                'Flashcard Generator',
                'Turn your notes into effective study flashcards.',
                'Flashcards',
                student_cat, '#9333EA', 'Layers',
                "You are an organizational study coach. Take a topic and create concise, effective flashcards.",
                "Create {count} flashcards for {topic} based on these details: {info}.",
                "Topic, Key Info, Number of Cards"
            ),
        ]
        
        tools = []
        for name, desc, s_name, cat, color, icon, sys_prompt, user_temp, input_fields in tools_data:
            tool, created = AITool.objects.get_or_create(
                slug=slugify(name),
                defaults={
                    'name': name,
                    'description': desc,
                    'student_friendly_name': s_name,
                    'categories': cat,
                    'color': color,
                    'icon': icon,
                    'is_active': True,
                    'system_prompt': sys_prompt,
                    'user_prompt_template': user_temp
                }
            )
            
            # Create Inputs
            if created:
                fields = [f.strip() for f in input_fields.split(',')]
                for i, field_label in enumerate(fields):
                    # Guess type based on label
                    input_type = 'text'
                    if any(word in field_label.lower() for word in ['criteria', 'text', 'description', 'notes', 'performance', 'details', 'info']):
                        input_type = 'textarea'
                    elif any(word in field_label.lower() for word in ['number', 'count', 'age', 'lessons', 'slides']):
                        input_type = 'number'
                    
                    ToolInput.objects.create(
                        tool=tool,
                        label=field_label,
                        type=input_type,
                        required=True,
                        order=i
                    )
            
            tools.append(tool)
            
        self.stdout.write(f'Created/Updated {len(tools)} tools.')
        return tools

    def seed_ai_logs(self, tools):
        self.stdout.write('Seeding AI logs...')
        users = User.objects.all()
        for user in users:
            # Skip if tool count is 0
            if not tools:
                continue
                
            # Create a usage summary for the user
            usage, _ = UserAIUsage.objects.get_or_create(user=user)
            
            for _ in range(random.randint(5, 15)):
                tool = random.choice(tools)
                p_tokens = random.randint(100, 500)
                c_tokens = random.randint(200, 1000)
                credits_spent = random.randint(5, 50)
                
                log = AILog.objects.create(
                    user=user,
                    tool=tool.name,
                    title=f"Sample {tool.name} analysis",
                    prompt="Sample prompt text for testing logs.",
                    response="Sample AI response generation for log visibility.",
                    prompt_tokens=p_tokens,
                    completion_tokens=c_tokens,
                    total_tokens=p_tokens + c_tokens,
                    credits=credits_spent,
                    provider=random.choice(['openai', 'deepseek']),
                    response_time=random.uniform(0.5, 3.5)
                )
                
                # Update usage stats
                usage.total_requests += 1
                usage.total_tokens += log.total_tokens
                usage.total_credits += log.credits
                # No need to update cost manually, it's calculated in save()
                usage.last_request_at = log.created_at
            
            usage.save()

    def seed_usage_logs(self, schools, tools):
        self.stdout.write('Seeding student usage logs...')
        for school in schools:
            students = Student.objects.filter(school=school)
            for student in students:
                for _ in range(random.randint(3, 8)):
                    tool = random.choice(tools)
                    UsageLog.objects.create(
                        student=student,
                        school=school,
                        tool=tool.name,
                        request_count=random.randint(1, 10)
                    )

from django.utils.text import slugify
