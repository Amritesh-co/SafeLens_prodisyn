import os
import django
import requests

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'safelensai.settings')
django.setup()

from apps.api.models import Event, NotificationRecipient

print("Checking configured email recipients...")
recipients = NotificationRecipient.objects.all()
if not recipients.exists():
    print("Warning: No notification recipients configured in the database.")
    print("Please use the Django Admin (/admin) to add an email address.")
else:
    for recipient in recipients:
        print(f" - {recipient.name} ({recipient.email}) [Active: {recipient.is_active}]")

print("\nFinding a test event...")
event = Event.objects.first()
if not event:
    print("Error: No events found in the database. Please generate some test data first.")
else:
    print(f"Found event ID {event.event_id} ({event.event_type}).")
    print(f"\nTo trigger an email notification for this event, you would send a POST request to:")
    print(f"http://127.0.0.1:8000/api/notifications/send/")
    print(f"with body: {{'event_id': {event.event_id}}}")
    
    print("\nAttempting to trigger notification locally (using Django API View)...")
    from django.test import RequestFactory
    from apps.api.views import SendNotificationView
    
    factory = RequestFactory()
    request = factory.post('/api/notifications/send/', {'event_id': event.event_id}, content_type='application/json')
    
    # We bypass authentication for this local test script
    view = SendNotificationView.as_view(permission_classes=[]) 
    response = view(request)
    
    print(f"\nResponse Status: {response.status_code}")
    print(f"Response Body: {response.data}")
