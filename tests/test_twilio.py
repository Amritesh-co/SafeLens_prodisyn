import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'safelensai.settings')
django.setup()

from django.conf import settings
from twilio.rest import Client
from apps.api.models import UserProfile
from django.contrib.auth.models import User

print("--- Twilio Credential Check ---")
sid = getattr(settings, 'TWILIO_ACCOUNT_SID', '')
token = getattr(settings, 'TWILIO_AUTH_TOKEN', '')
from_num = getattr(settings, 'TWILIO_PHONE_NUMBER', '')

print(f"SID: {sid}")
print(f"Token: {token[:5]}***")
print(f"From Number: {from_num}")

print("\n--- User Profile Check (Admin) ---")
user = User.objects.filter(username='admin').first()
if user:
    print(f"Admin Email: {user.email}")
    try:
        profile = user.profile
        print(f"Admin Phone: {profile.phone_number}")
        print(f"Alerts SMS: {profile.alerts_sms}")
        print(f"Alerts WhatsApp: {profile.alerts_whatsapp}")
        print(f"Alerts Email: {profile.alerts_email}")
        
        if profile.alerts_sms and profile.phone_number:
            print("\n--- Sending Test SMS ---")
            to_num = profile.phone_number
            if not to_num.startswith('+'):
                to_num = '+' + to_num
                
            print(f"Sending to: {to_num} from {from_num}")
            client = Client(sid, token)
            try:
                msg = client.messages.create(
                    body="SafeLens AI Test: Your notification channels are working!",
                    from_=from_num,
                    to=to_num
                )
                print(f"SUCCESS! Message SID: {msg.sid}")
            except Exception as e:
                print(f"FAILED to send SMS: {e}")
        else:
            print("\nCannot send test SMS: Admin does not have a phone number or alerts_sms is False.")
    except Exception as e:
        print(f"Error accessing profile: {e}")
else:
    print("Admin user not found.")
