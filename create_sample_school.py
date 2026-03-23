from authentication.models import User
from schools.models import School
from tools.models import AILog
import uuid

def create_sample_data():
    # 1. Create School
    school = School.objects.create(
        name="Sample Reflection School",
        school_email=f"admin_{uuid.uuid4().hex[:6]}@reflection-school.edu",
        max_students=100
    )

    # 2. Create Admin
    admin_user = User.objects.create_user(
        email=f"admin_{uuid.uuid4().hex[:6]}@reflection.edu",
        password="DAVIS_1234",
        first_name="Admin",
        last_name="Reflect",
        user_type="enterprise",
        role="school_admin",
        organisation=school,
        is_staff=True
    )
    school.admin_user = admin_user
    school.save()

    # 3. Create Teacher
    teacher = User.objects.create_user(
        email=f"teacher_{uuid.uuid4().hex[:6]}@reflection.edu",
        password="DAVIS_1234",
        first_name="Teacher",
        last_name="Reflect",
        user_type="enterprise",
        role="teacher",
        organisation=school,
        is_staff=True
    )

    # 4. Create Students
    student1 = User.objects.create_user(
        email=f"student1_{uuid.uuid4().hex[:6]}@reflection.edu",
        password="DAVIS_1234",
        first_name="Student",
        last_name="One",
        user_type="enterprise",
        role="student",
        organisation=school
    )

    student2 = User.objects.create_user(
        email=f"student2_{uuid.uuid4().hex[:6]}@reflection.edu",
        password="DAVIS_1234",
        first_name="Student",
        last_name="Two",
        user_type="enterprise",
        role="student",
        organisation=school
    )

    # 5. Create Reflections (AILogs)
    AILog.objects.create(
        user=teacher,
        tool="Teacher Reflection",
        topic="Class Progress",
        class_level="Grade 10",
        difficulty="Medium",
        inputs={"reflection": "The class is making great progress in algebra."},
        prompt_tokens=50,
        completion_tokens=100,
        prompt="Reflect on class progress...",
        response="Here is a structured reflection on the algebra class: the students are showing strong foundational understanding.",
        response_time=1.5
    )

    AILog.objects.create(
        user=student1,
        tool="Student Reflection",
        topic="Math Exam",
        class_level="Grade 10",
        difficulty="Hard",
        inputs={"reflection": "I struggled with the final question but felt good overall."},
        prompt_tokens=40,
        completion_tokens=80,
        prompt="Reflect on the recent math exam...",
        response="It's completely normal to struggle with advanced test questions. Focus on reviewing the core concepts.",
        response_time=1.2
    )

    print(f"Successfully created School '{school.name}'.")
    print(f"Admin: {admin_user.email} | Password: DAVIS_1234")
    print(f"Teacher: {teacher.email} | Password: DAVIS_1234")
    print(f"Student 1: {student1.email} | Password: DAVIS_1234")
    print(f"Student 2: {student2.email} | Password: DAVIS_1234")
    print("Added reflection logs for teacher and student.")

if __name__ == "__main__":
    create_sample_data()
