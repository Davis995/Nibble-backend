"""
Seed script for sample notifications.
Run: python manage.py shell < leads/seed_notifications.py
"""
import django
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')

from django.utils import timezone
from datetime import timedelta
from authentication.models import User
from leads.models import Notification

# Get all users (teacher and student roles)
users = User.objects.filter(role__in=['teacher', 'student'])

if not users.exists():
    # Fallback: get any user
    users = User.objects.all()[:2]

print(f"Found {users.count()} users to seed notifications for.")

SAMPLE_NOTIFICATIONS = [
    {
        "notification_type": "alert",
        "title": "New AI Model Available",
        "body": "Experience enhanced lesson planning with our latest Nibble-Pro model. Now 2x faster with improved accuracy!",
        "priority": "high",
        "is_read": False,
        "time_offset": timedelta(hours=2),
    },
    {
        "notification_type": "success",
        "title": "Weekly Achievement Unlocked",
        "body": "Great job! You've generated 20+ teaching resources this week. Keep up the amazing work!",
        "priority": "medium",
        "is_read": False,
        "time_offset": timedelta(hours=5),
    },
    {
        "notification_type": "system",
        "title": "System Maintenance Scheduled",
        "body": "Scheduled maintenance on Saturday, March 29th (2:00 AM - 4:00 AM UTC). Some features may be briefly unavailable.",
        "priority": "medium",
        "is_read": False,
        "time_offset": timedelta(days=1),
    },
    {
        "notification_type": "info",
        "title": "Welcome to NibbleLearn Plus",
        "body": "Your subscription has been successfully upgraded. Explore your new premium features including advanced AI tools!",
        "priority": "low",
        "is_read": True,
        "time_offset": timedelta(days=2),
    },
    {
        "notification_type": "achievement",
        "title": "5-Day Streak Unlocked!",
        "body": "You've used NibbleLearn for 5 consecutive days. You're building a great learning habit!",
        "priority": "medium",
        "is_read": False,
        "time_offset": timedelta(hours=8),
    },
]

now = timezone.now()
created_count = 0

for user in users:
    for notif in SAMPLE_NOTIFICATIONS:
        obj, created = Notification.objects.get_or_create(
            user=user,
            title=notif["title"],
            defaults={
                "notification_type": notif["notification_type"],
                "body": notif["body"],
                "priority": notif["priority"],
                "is_read": notif["is_read"],
                "created_at": now - notif["time_offset"],
            }
        )
        if created:
            created_count += 1
            # Override created_at since auto_now_add might set it
            Notification.objects.filter(pk=obj.pk).update(created_at=now - notif["time_offset"])
            print(f"  ✓ Created: '{notif['title']}' for {user.email}")
        else:
            print(f"  → Already exists: '{notif['title']}' for {user.email}")

print(f"\nDone! Created {created_count} new notifications.")
