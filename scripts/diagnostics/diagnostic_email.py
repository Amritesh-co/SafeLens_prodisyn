import os
import django
from django.conf import settings
from django.core.mail import send_mail
from apps.api.models import Event, EmailAlertTracker, UserProfile, User, UserActivityLog

# Set up Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'safelensai.settings')
django.setup()

def test_notification_flow(event_id):
    try:
        event = Event.objects.get(pk=event_id)
        print(f"Testing for Event {event_id} ({event.event_type}) at {event.camera.location}")
        
        # Replicate poll_events logic
        camera_location = event.camera.location or "Unknown"
        
        online_users = User.objects.filter(
            is_active=True,
            useractivitylog__logout_time__isnull=True
        ).distinct()
        
        print(f"Online users found: {[u.username for u in online_users]}")
        
        email_recipients = []
        for user in online_users:
            try:
                profile = user.profile
                should_notify = False
                if profile.role == 'Admin':
                    should_notify = True
                elif profile.location and camera_location and profile.location.lower() == camera_location.lower():
                    should_notify = True
                elif not profile.location:
                    should_notify = True
                
                if should_notify and profile.alerts_email and user.email:
                    email_recipients.append(user.email)
                    print(f" -> Adding {user.username} ({user.email}) to recipient list")
            except Exception as e:
                print(f" -> Error checking profile for {user.username}: {e}")

        if not email_recipients:
            print("FAILED: No eligible email recipients found!")
            return

        print(f"Attempting to send email to: {email_recipients}")
        send_mail(
            subject=f"Manual Test: {event.event_type}",
            message="This is a diagnostic test of the Safelens notification system.",
            from_email=settings.EMAIL_HOST_USER,
            recipient_list=email_recipients,
            fail_silently=False,
        )
        print("SUCCESS: Email dispatched successfully!")

    except Exception as e:
        print(f"ERROR: {str(e)}")

if __name__ == "__main__":
    test_notification_flow(168)
