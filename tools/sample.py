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
        icon="FileText",
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

    print("Creating teacher dashboard seed data...")
    teacher_category, _ = ToolCategory.objects.get_or_create(
        name="Teacher Tools",
        defaults={
            'description': 'Teacher-focused AI tools',
            'type': 'teacher',
            'icon': 'FileText'
        }
    )

    dashboard_tools_info = [
        ('lesson-plan-generator', 'Lesson Plan Generator', 'Lesson Plan Generator', 'Generate 5E, Madeline Hunter, or custom lesson plans.', '#3B82F6', 'FileText'),
        ('unit-plan-generator', 'Unit Plan Generator', 'Unit Plan Generator', 'Plan your unit sequences with standards, objectives, and assessments.', '#A855F7', 'CheckCircle'),
        ('text-leveler', 'Text Leveler', 'Text Leveler', 'Adjust text complexity for different student levels.', '#F43F5E', 'Zap'),
        ('presentation-generator', 'Presentation Generator', 'Presentation Generator', 'Create classroom-ready lesson presentations.', '#F97316', 'Presentation'),
        ('accommodation-suggestions', 'Accommodation Suggestions', 'Accommodation Suggestions', 'Ideas for supporting diverse learner needs.', '#14B8A6', 'Users'),
        ('vocabulary-scaffolder', 'Vocabulary Scaffolder', 'Vocabulary Scaffolder', 'Tiered vocabulary lists with student-friendly definitions.', '#C026D3', 'Globe'),
        ('lesson-hook-generator', 'Lesson Hook Generator', 'Lesson Hook Generator', 'Engaging starters for any lesson.', '#EAB308', 'Sparkles'),
        ('standards-unpacker', 'Standards Unpacker', 'Standards Unpacker', 'Translate standards into student-friendly goals.', '#4F46E5', 'FileText'),
    ]

    extra_teaching_tools = [
        ('real-world-connections', 'Real World Connections', 'Real World Connections', 'Generate real-world examples for what you are learning.', '#22C55E', 'Link'),
        ('research-assistant', 'Research Assistant', 'Research Assistant', 'Find information and sources for a research project.', '#8B5CF6', 'Search'),
        ('rewrite-it', 'Rewrite It!', 'Rewrite It!', 'Rewrite text with custom criteria.', '#EC4899', 'Edit3'),
        ('song-generator', 'Song Generator', 'Song Generator', 'Write a custom song on any topic.', '#F59E0B', 'Music'),
        ('translate-it', 'Translate It!', 'Translate It!', 'Translate text into any language instantly.', '#0EA5E9', 'Globe'),
        ('summarize-it', 'Summarize It!', 'Summarize It!', 'Summarize text at the length of your choosing.', '#22D3EE', 'FileText'),
        ('5-questions', '5 Questions', '5 Questions', 'Ask 5 questions to deepen thinking on a topic.', '#6EE7B7', 'QuestionMarkCircle'),
        ('book-suggestions', 'Book Suggestions', 'Book Suggestions', 'Discover books that match your interests.', '#A3E635', 'BookOpen'),
        ('conceptual-understanding', 'Conceptual Understanding', 'Conceptual Understanding', 'Generate ideas to grow conceptual understanding.', '#60A5FA', 'Lightbulb'),
        ('expand-on-idea', 'Expand on My Idea', 'Expand on My Idea', 'Use AI to expand on your ideas.', '#F97316', 'LayoutGrid'),
        ('idea-generator', 'Idea Generator', 'Idea Generator', 'Get help coming up with ideas.', '#6366F1', 'Sparkles'),
        ('informational-texts', 'Informational Texts', 'Informational Texts', 'Generate original informational text for your topic.', '#A78BFA', 'AlignJustify'),
        ('joke-creator', 'Joke Creator', 'Joke Creator', 'Generate jokes on any topic.', '#F43F5E', 'Smile'),
        ('make-it-relevant', 'Make it Relevant!', 'Make it Relevant!', 'Generate ideas to connect learning to your background.', '#FB923C', 'Heart'),
        ('multiple-explanations', 'Multiple Explanations', 'Multiple Explanations', 'Generate clear explanations for concepts.', '#0EA5E9', 'BookOpen'),
        ('quiz-me', 'Quiz Me!', 'Quiz Me!', 'Quiz yourself on any topic or text.', '#22C55E', 'ClipboardCheck'),
    ]

    for slug_val, name, friendly, desc, color, icon_name in dashboard_tools_info:
        AITool.objects.update_or_create(
            slug=slug_val,
            defaults={
                'name': name,
                'description': desc,
                'student_friendly_name': friendly,
                'categories': teacher_category,
                'color': color,
                'system_prompt': '',
                'icon': icon_name,
                'is_premium': False,
                'is_recommended': True,
                'is_active': True,
                'preferred_modal': 'gpt-4o-mini'
            }
        )

    for slug_val, name, friendly, desc, color, icon_name in extra_teaching_tools:
        tool_obj, _ = AITool.objects.update_or_create(
            slug=slug_val,
            defaults={
                'name': name,
                'description': desc,
                'student_friendly_name': friendly,
                'categories': teacher_category,
                'color': color,
                'system_prompt': '',
                'icon': icon_name,
                'is_premium': False,
                'is_recommended': True,
                'is_active': True,
                'preferred_modal': 'gpt-4o-mini'
            }
        )

        # Add sample ToolInput fields for each new tool
        ToolInput.objects.update_or_create(
            tool=tool_obj,
            label='Primary input',
            defaults={
                'type': 'textarea',
                'placeholder': 'Enter your content here',
                'required': True,
                'order': 1,
            }
        )

        ToolInput.objects.update_or_create(
            tool=tool_obj,
            label='Optional context',
            defaults={
                'type': 'textarea',
                'placeholder': 'Optional extra context (e.g., audience or tone)',
                'required': False,
                'order': 2,
            }
        )

    # Student-focused tools (writing, reading, math, study, creative, AI literacy)
    student_category, _ = ToolCategory.objects.get_or_create(
        name='Student Tools',
        defaults={'description': 'Tools for students to learn and create', 'type': 'student', 'icon': 'BookOpen'}
    )

    student_tools_info = [
        ('essay-outliner', 'Essay Outliner', 'Essay Outliner', 'Create an outline for your essay with main points.', '#DBEAFE', 'FileText'),
        ('paragraph-generator', 'Paragraph Generator', 'Paragraph Generator', 'Generate a paragraph to help you get started.', '#DBEAFE', 'AlignLeft'),
        ('research-assistant', 'Research Assistant', 'Research Assistant', 'Find information and sources for your project.', '#DBEAFE', 'FileSearch'),
        ('citation-helper', 'Citation Helper', 'Citation Helper', 'Create citations in MLA or APA format.', '#DBEAFE', 'Quote'),
        ('thesis-statement', 'Thesis Statement', 'Thesis Statement', 'Create a strong thesis statement for your essay.', '#DBEAFE', 'Target'),
        ('intro-writer', 'Intro Writer', 'Intro Writer', 'Generate an engaging introduction.', '#DBEAFE', 'ArrowRight'),
        ('conclusion-writer', 'Conclusion Writer', 'Conclusion Writer', 'Write a strong conclusion for your essay.', '#DBEAFE', 'CheckCircle'),
        ('sentence-starter', 'Sentence Starter', 'Sentence Starter', 'Get ideas for starting your sentences.', '#DBEAFE', 'PenLine'),
        ('grammar-check', 'Grammar Check', 'Grammar Check', 'Check your writing for simple mistakes.', '#DBEAFE', 'Check'),
        ('writing-feedback', 'Writing Feedback', 'Writing Feedback', 'Get feedback on your writing.', '#DBEAFE', 'MessageSquare', True),
        ('text-summarizer-student', 'Text Summarizer', 'Text Summarizer', 'Summarize long texts to understand main ideas.', '#DBEAFE', 'Minimize2'),
        ('text-rewriter', 'Text Rewriter', 'Text Rewriter', 'Rewrite text in your own words.', '#DBEAFE', 'RefreshCw'),
        ('word-choice', 'Word Choice', 'Word Choice', 'Find better words to make writing stronger.', '#DBEAFE', 'Zap'),
        ('email-writer', 'Email Writer', 'Email Writer', 'Write a professional email to your teacher.', '#DBEAFE', 'Mail'),
        ('counter-argument', 'Counter-Argument', 'Counter-Argument', 'Find opposing views for your essay.', '#DBEAFE', 'Scale'),
        ('evidence-finder', 'Evidence Finder', 'Evidence Finder', 'Get ideas for evidence to support claims.', '#DBEAFE', 'FileSearch'),
        ('transition-words', 'Transition Words', 'Transition Words', 'Find words to connect your ideas.', '#DBEAFE', 'LinkIcon'),
        ('vocabulary-builder', 'Vocabulary Builder', 'Vocabulary Builder', 'Learn new words related to your topic.', '#DBEAFE', 'BookA'),

        ('reading-comp', 'Reading Comp.', 'Reading Comp.', 'Answer questions to check understanding.', '#DCFCE7', 'BookOpenCheck'),
        ('text-to-speech', 'Text-to-Speech', 'Text-to-Speech', 'Listen to text read aloud.', '#DCFCE7', 'Volume2'),
        ('text-simplifier', 'Text Simplifier', 'Text Simplifier', 'Make difficult text easier to understand.', '#DCFCE7', 'ArrowDown'),
        ('main-idea-finder', 'Main Idea Finder', 'Main Idea Finder', 'Identify the main idea of a text.', '#DCFCE7', 'Focus'),
        ('character-analysis', 'Character Analysis', 'Character Analysis', 'Analyze characters from stories.', '#DCFCE7', 'UserSearch'),
        ('theme-identifier', 'Theme Identifier', 'Theme Identifier', 'Find themes in stories and texts.', '#DCFCE7', 'Lightbulb'),
        ('figurative-lang', 'Figurative Lang.', 'Figurative Lang.', 'Identify metaphors and similes.', '#DCFCE7', 'Sparkles'),
        ('context-clues', 'Context Clues', 'Context Clues', 'Figure out word meanings from context.', '#DCFCE7', 'Search'),

        ('math-tutor', 'Math Tutor', 'Math Tutor', 'Get help solving math problems step-by-step.', '#FFEDD5', 'Calculator'),
        ('word-problems', 'Word Problems', 'Word Problems', 'Understand and solve math word problems.', '#FFEDD5', 'FileText'),
        ('concept-explainer', 'Concept Explainer', 'Concept Explainer', 'Understand difficult math concepts.', '#FFEDD5', 'BrainCircuit'),
        ('fraction-helper', 'Fraction Helper', 'Fraction Helper', 'Work with fractions easily.', '#FFEDD5', 'PieChart'),
        ('geometry-helper', 'Geometry Helper', 'Geometry Helper', 'Calculate area, perimeter, and volume.', '#FFEDD5', 'Triangle'),
        ('formula-ref', 'Formula Ref.', 'Formula Ref.', 'Look up math formulas you need.', '#FFEDD5', 'Sigma'),

        ('ai-tutor', 'AI Tutor', 'AI Tutor', 'Ask questions on any subject.', '#EDE9FE', 'Bot', True),
        ('study-partner', 'Study Partner', 'Study Partner', 'Use AI as a study buddy.', '#EDE9FE', 'Users'),
        ('quiz-yourself', 'Quiz Yourself', 'Quiz Yourself', 'Create a practice quiz on any topic.', '#EDE9FE', 'ClipboardCheck'),
        ('flashcards', 'Flashcards', 'Flashcards', 'Make flashcards to help you study.', '#EDE9FE', 'Layers'),
        ('study-guide', 'Study Guide', 'Study Guide', 'Create a study guide for your test.', '#EDE9FE', 'FileInput'),
        ('note-summarizer', 'Note Summarizer', 'Note Summarizer', 'Turn notes into a quick summary.', '#EDE9FE', 'FileMinus'),
        ('test-prep', 'Test Prep', 'Test Prep', 'Practice questions for upcoming tests.', '#EDE9FE', 'ClipboardList'),
        ('memory-tricks', 'Memory Tricks', 'Memory Tricks', 'Get ideas for remembering information.', '#EDE9FE', 'Brain'),

        ('story-generator-student', 'Story Generator', 'Story Generator', 'Create creative stories with AI.', '#FCE7F3', 'Book'),
        ('poem-writer', 'Poem Writer', 'Poem Writer', 'Write poems about any topic.', '#FCE7F3', 'Feather'),
        ('image-generator', 'Image Generator', 'Image Generator', 'Create images regarding your prompt.', '#FCE7F3', 'ImageIcon', True),
        ('project-ideas', 'Project Ideas', 'Project Ideas', 'Get ideas for school projects.', '#FCE7F3', 'Lightbulb'),
        ('slides-helper', 'Slides Helper', 'Slides Helper', 'Create an outline for your presentation.', '#FCE7F3', 'Presentation'),
        ('writing-prompts', 'Writing Prompts', 'Writing Prompts', 'Get ideas for creative writing.', '#FCE7F3', 'PenTool'),
        ('character-creator', 'Character Creator', 'Character Creator', 'Develop characters for your stories.', '#FCE7F3', 'UserPlus'),
        ('rhyme-finder', 'Rhyme Finder', 'Rhyme Finder', 'Find words that rhyme.', '#FCE7F3', 'Music'),

        ('ask-about-ai', 'Ask About AI', 'Ask About AI', 'Learn how AI works.', '#E0E7FF', 'Bot'),
        ('prompt-helper', 'Prompt Helper', 'Prompt Helper', 'Learn to write better prompts.', '#E0E7FF', 'Terminal'),
        ('character-chat', 'Character Chat', 'Character Chat', 'Chat with a book character.', '#E0E7FF', 'MessageSquarePlus', True),
        ('custom-chatbot', 'Custom Chatbot', 'Custom Chatbot', 'Build a chatbot on any topic.', '#E0E7FF', 'Bot', True),
        ('idea-generator-ai', 'Idea Generator', 'Idea Generator', 'Brainstorm ideas on any topic.', '#E0E7FF', 'CloudLightning'),
        ('translator', 'Translator', 'Translator', 'Translate text to other languages.', '#E0E7FF', 'Languages'),
        ('source-eval', 'Source Eval', 'Source Eval', 'Learn if a source is reliable.', '#E0E7FF', 'ShieldCheck'),
        ('note-template', 'Note Template', 'Note Template', 'Organize your notes better.', '#E0E7FF', 'StickyNote'),
        ('homework-helper', 'Homework Helper', 'Homework Helper', 'Get help understanding homework.', '#E0E7FF', 'LifeBuoy'),
        ('time-planner', 'Time Planner', 'Time Planner', 'Plan your study time.', '#E0E7FF', 'Calendar'),
        ('peer-feedback', 'Peer Feedback', 'Peer Feedback', 'Give helpful feedback to classmates.', '#E0E7FF', 'MessageSquarePlus'),
    ]

    for slug_val, name, friendly, desc, color, icon_name, *flags in student_tools_info:
        is_hot = flags[0] if flags else False
        tool_obj, _ = AITool.objects.update_or_create(
            slug=slug_val,
            defaults={
                'name': name,
                'description': desc,
                'student_friendly_name': friendly,
                'categories': student_category,
                'color': color,
                'system_prompt': '',
                'icon': icon_name,
                'is_premium': False,
                'is_recommended': True,
                'is_active': True,
                'preferred_modal': 'gpt-4o-mini',
            }
        )

        # add inputs
        ToolInput.objects.update_or_create(
            tool=tool_obj,
            label='Main prompt',
            defaults={
                'type': 'textarea',
                'placeholder': 'Enter the main text or topic',
                'required': True,
                'order': 1,
            }
        )

        ToolInput.objects.update_or_create(
            tool=tool_obj,
            label='Use case/examples',
            defaults={
                'type': 'textarea',
                'placeholder': 'Optional details (grade level, style, length)',
                'required': False,
                'order': 2,
            }
        )

    print("✅ Sample and dashboard seed data for tools created successfully!")


if __name__ == "__main__":
    run()
