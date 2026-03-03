from leads.models import Lead, Notification, DemoSchedule, Onboarding, Logs
from authentication.models import User
from schools.models import School
from datetime import date, time, timedelta


def run():
    print("Clearing existing leads data...")
    Logs.objects.all().delete()
    Onboarding.objects.all().delete()
    DemoSchedule.objects.all().delete()
    Notification.objects.all().delete()
    Lead.objects.all().delete()

    print("Creating sample schools and staff users...")
    schools_data = [
        {"name": "Nairobi International School", "email": "admin@nairobi-intl.edu", "max": 500},
        {"name": "Mombasa Academy", "email": "admin@mombasa-academy.edu", "max": 300},
        {"name": "Kisumu High School", "email": "admin@kisumu-high.edu", "max": 200},
    ]
    
    schools = []
    staff_users = []
    
    for idx, school_data in enumerate(schools_data):
        school, _ = School.objects.get_or_create(
            name=school_data["name"],
            defaults={"school_email": school_data["email"], "max_students": school_data["max"]}
        )
        schools.append(school)
        
        user, _ = User.objects.get_or_create(
            email=f"staff{idx+1}@school.edu",
            defaults={
                "first_name": f"Staff{idx+1}", 
                "last_name": "Manager", 
                "user_type": "enterprise", 
                "password": "pass1234"
            }
        )
        staff_users.append(user)

    print("Creating comprehensive lead samples...")
    leads_data = [
        {
            "firstname": "John",
            "secondname": "Okonkwo",
            "phonenumber": "+254712345678",
            "workemail": "john.okonkwo@nairobi-intl.edu",
            "jobtitle": "Principal",
            "institution": "school",
            "categories": "education",
            "institution_name": "Nairobi International School",
            "size_of_institution": "500-1000",
            "country": "Kenya",
            "city": "Nairobi",
            "question_on_preference": "email",
            "status": "demo_scheduled",
            "staff": staff_users[0]
        },
        {
            "firstname": "Grace",
            "secondname": "Kariuki",
            "phonenumber": "+254723456789",
            "workemail": "grace.kariuki@mombasa-academy.edu",
            "jobtitle": "ICT Coordinator",
            "institution": "school",
            "categories": "education",
            "institution_name": "Mombasa Academy",
            "size_of_institution": "1000+",
            "country": "Kenya",
            "city": "Mombasa",
            "question_on_preference": "website",
            "status": "contacted",
            "staff": staff_users[1]
        },
        {
            "firstname": "Peter",
            "secondname": "Nyambura",
            "phonenumber": "+254734567890",
            "workemail": "peter.nyambura@example.com",
            "jobtitle": "Education Director",
            "institution": "corporate",
            "categories": "corporate",
            "institution_name": "Tech Training Institute",
            "size_of_institution": "100-500",
            "country": "Kenya",
            "city": "Kisumu",
            "question_on_preference": "referral",
            "status": "new",
            "staff": None
        },
        {
            "firstname": "Alice",
            "secondname": "Mutua",
            "phonenumber": "+254745678901",
            "workemail": "alice.mutua@example.com",
            "jobtitle": "Superintendent",
            "institution": "government",
            "categories": "government",
            "institution_name": "Ministry of Education",
            "size_of_institution": "1000+",
            "country": "Kenya",
            "city": "Nairobi",
            "question_on_preference": "email",
            "status": "negotiated",
            "staff": staff_users[0]
        },
        {
            "firstname": "Michael",
            "secondname": "Kipchoge",
            "phonenumber": "+254756789012",
            "workemail": "michael.kipchoge@example.com",
            "jobtitle": "Head of Department",
            "institution": "school",
            "categories": "education",
            "institution_name": "Valley School",
            "size_of_institution": "200-500",
            "country": "Kenya",
            "city": "Nairobi",
            "question_on_preference": "phone",
            "status": "qualified",
            "staff": staff_users[2]
        }
    ]
    
    leads = []
    for lead_data in leads_data:
        staff = lead_data.pop("staff")
        lead = Lead.objects.create(
            assigned_staff=staff,
            **lead_data
        )
        leads.append(lead)

    print("Creating notifications for leads...")
    notification_types = ["new_lead", "lead_assigned", "demo_scheduled", "follow_up_due"]
    for idx, lead in enumerate(leads[:3]):
        Notification.objects.create(
            user=staff_users[idx % len(staff_users)],
            notification_type=notification_types[idx],
            title=f"Action required for {lead.firstname}",
            body=f"Lead {lead.firstname} {lead.secondname} needs attention",
            priority="high" if idx % 2 == 0 else "medium"
        )

    print("Scheduling demos...")
    for idx, lead in enumerate(leads[:3]):
        DemoSchedule.objects.create(
            lead=lead,
            assigned_staff=staff_users[idx % len(staff_users)],
            status="online" if idx % 2 == 0 else "offline",
            meeting_link="https://meet.google.com/demo" + str(idx+1) if idx % 2 == 0 else None,
            date=date.today() + timedelta(days=idx+1),
            time=time(hour=10+idx, minute=0),
            demo_type="online" if idx % 2 == 0 else "in-person",
            demo_status="scheduled" if idx == 0 else "completed" if idx == 2 else "pending"
        )

    print("Creating onboarding entries...")
    for idx, school in enumerate(schools):
        Onboarding.objects.create(
            school=school,
            status="inprogress" if idx == 0 else "completed" if idx == 1 else "onhold",
            onboarding_manager=staff_users[idx],
            startdate=date.today() - timedelta(days=7*idx),
            expected_go_live_date=date.today() + timedelta(days=30),
            onboarding_type="online",
            percentage=25*(idx+1)
        )

    print("Logging lead activities...")
    activity_types = ["lead_created", "lead_assigned", "demo_scheduled", "followup_sent", "converted"]
    for idx, lead in enumerate(leads):
        Logs.objects.create(
            lead=lead,
            log_type=activity_types[idx % len(activity_types)],
            description=f"Activity: {activity_types[idx % len(activity_types)]} for {lead.firstname}"
        )


if __name__ == "__main__":
    run()
