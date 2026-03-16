from schools.models import School, Student, Staff, UsageLog
from authentication.models import User, Plan, Subscription
from datetime import date, timedelta
import random


def run():
    print("Clearing existing school data...")
    UsageLog.objects.all().delete()
    Staff.objects.all().delete()
    Student.objects.all().delete()
    School.objects.all().delete()

    print("Creating plans for schools...")
    enterprise_plan, _ = Plan.objects.get_or_create(
        name="Enterprise Premium",
        use_type="enterprise",
        defaults={
            "total_credits": 10000,
            "max_users": 300,
            "monthly_price": 6000.00,
            "allowed_modals": ["gpt-4", "gpt-3.5", "deepseek-chat"]
        }
    )

    print("Creating comprehensive school data...")
    schools_data = [
        {"name": "Nairobi International School", "email": "admin@nairobi-intl.edu", "max": 500},
        {"name": "Mombasa Academy", "email": "admin@mombasa-academy.edu", "max": 300},
        {"name": "Kisumu High School", "email": "admin@kisumu-high.edu", "max": 200},
        {"name": "Eldoret Preparatory School", "email": "admin@eldoret-prep.edu", "max": 400},
        {"name": "Nakuru School of Excellence", "email": "admin@nakuru-excellence.edu", "max": 350},
    ]
    
    schools = []
    for school_data in schools_data:
        school = School.objects.create(
            name=school_data["name"],
            school_email=school_data["email"],
            max_students=school_data["max"]
        )
        schools.append(school)
        
        # Create subscription for each school
        Subscription.objects.create(
            max_users=enterprise_plan.max_users,
            plan=enterprise_plan,
            organisation=school,
            start_credits=enterprise_plan.total_credits,
            remaining_credits=random.randint(5000, 10000),
            billing_start_date=date.today(),
            billing_end_date=date.today() + timedelta(days=30),
            status="active"
        )

    print("Creating sample students for each school...")
    student_data = [
        {"first": "John", "last": "Doe", "code": "STU001"},
        {"first": "Jane", "last": "Smith", "code": "STU002"},
        {"first": "Michael", "last": "Johnson", "code": "STU003"},
        {"first": "Sarah", "last": "Williams", "code": "STU004"},
        {"first": "David", "last": "Brown", "code": "STU005"},
        {"first": "Emily", "last": "Davis", "code": "STU006"},
        {"first": "James", "last": "Miller", "code": "STU007"},
        {"first": "Lisa", "last": "Wilson", "code": "STU008"},
    ]
    
    students = []
    for school_idx, school in enumerate(schools):
        for std_idx, std_data in enumerate(student_data[:4]):  # 4 students per school
            student = Student.objects.create(
                school=school,
                first_name=std_data["first"],
                last_name=std_data["last"],
                school_email=f"{std_data['first'].lower()}.{std_data['last'].lower()}@{school.school_email.split('@')[1]}",
                student_code=f"{school.name.replace(' ', '')[:3]}{std_data['code']}"
            )
            students.append(student)

    print("Creating sample staff for each school...")
    staff_roles = ["principal", "teacher", "ict_coordinator", "administrator"]
    staff_data = [
        {"first": "Jane", "last": "Smith", "role": "principal"},
        {"first": "Robert", "last": "Johnson", "role": "teacher"},
        {"first": "Patricia", "last": "Williams", "role": "ict_coordinator"},
        {"first": "Thomas", "last": "Brown", "role": "administrator"},
        {"first": "Lisa", "last": "Davis", "role": "teacher"},
        {"first": "Peter", "last": "Miller", "role": "teacher"},
    ]
    
    staff_members = []
    for school_idx, school in enumerate(schools):
        for staff_idx, stf_data in enumerate(staff_data[:3]):  # 3 staff per school
            staff = Staff.objects.create(
                school=school,
                first_name=stf_data["first"],
                last_name=stf_data["last"],
                school_email=f"{stf_data['first'].lower()}.{stf_data['last'].lower()}@{school.school_email.split('@')[1]}",
                role=stf_data["role"]
            )
            staff_members.append(staff)

    print("Logging tool usage for students...")
    tools = [
        "Essay Analyzer",
        "Math Problem Solver",
        "Writing Assistant",
        "Exam Preparation Assistant",
        "Lesson Plan Generator",
        "Quiz Generator"
    ]
    
    for school_idx, school in enumerate(schools):
        school_students = Student.objects.filter(school=school)
        for student in school_students[:2]:  # Log usage for first 2 students per school
            UsageLog.objects.create(
                student=student,
                school=school,
                tool=random.choice(tools),
                request_count=random.randint(5, 50)
            )
            
            # Create additional usage logs
            UsageLog.objects.create(
                student=student,
                school=school,
                tool=random.choice(tools),
                request_count=random.randint(3, 30)
            )

    print("✅ Schools app sample data created successfully!")
    print(f"   - Created {School.objects.count()} schools")
    print(f"   - Created {Student.objects.count()} students")
    print(f"   - Created {Staff.objects.count()} staff members")
    print(f"   - Created {UsageLog.objects.count()} usage logs")
    print(f"   - Created {Subscription.objects.count()} subscriptions")


if __name__ == "__main__":
    run()
