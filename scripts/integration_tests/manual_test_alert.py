"""
File Name: manual_test_alert.py
Description: 
    A standalone automated testing script for the Safelens Notification Engine.
    Simulates the exact same business logic as `poll_events.py` by pulling the 
    most recent incident from the database and forcefully executing the Location-Based 
    Routing rules and Twilio/Email dispatches targeting the 'admin' user profile.
    Used by developers to test credentials and formatting without needing a real camera.
Author: Safelens AI Backend Team
"""

import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'safelensai.settings')
django.setup()

from apps.api.models import Event, EventMediaMap, Frame, UserProfile, EmailAlertTracker
from django.contrib.auth.models import User
from django.core.mail import EmailMessage
from django.conf import settings
try:
    from twilio.rest import Client
except ImportError:
    Client = None

print("\n--- Safelens Notification Test ---")

# 1. Get the most recent event to simulate
event = Event.objects.order_by('-timestamp').first()
if not event:
    print("No events found in the database. Please trigger a real event first.")
    exit()

camera_name = event.camera.name if event.camera else "Unknown Camera"
camera_location = event.camera.location if event.camera and event.camera.location else "Unknown Location"
event_time_str = event.timestamp.strftime('%Y-%m-%d %H:%M:%S') if event.timestamp else "Unknown Time"

# 2. Format the Text Message (Used for Email, SMS, & WhatsApp)
subject = f"🛑 SAFETY ALERT: {event.event_type} at {camera_name}"
message_body = (
    f"An automated Safety Incident has been detected by Safelens AI.\n\n"
    f"📍 Location: {camera_location}\n"
    f"📷 Camera: {camera_name}\n"
    f"🕒 Time: {event_time_str}\n"
    f"⚠️ Incident Type: {event.event_type}\n\n"
    f"Please log in to the Safelens Dashboard immediately to review the footage and take action."
)

print(f"\n[FORMAT] Subject: \n{subject}")
print(f"\n[FORMAT] Message Body: \n{message_body}\n")
print("-" * 40)

# 3. Gather Recipients (Simulating the Admin User)
admin_user = User.objects.filter(username='admin').first()
if not admin_user or not hasattr(admin_user, 'profile'):
    print("Admin user profile not found.")
    exit()

profile = admin_user.profile
email_address = admin_user.email
phone_number = profile.phone_number

if phone_number and not phone_number.startswith('+'):
    phone_number = '+' + phone_number.strip()

print(f"Targeting Admin profile:")
print(f" - Email: {email_address} (Enabled: {profile.alerts_email})")
print(f" - Phone: {phone_number} (SMS: {profile.alerts_sms}, WhatsApp: {profile.alerts_whatsapp})")

# CHECK LOCATION ROUTING
should_notify = False
if profile.role == 'Admin':
    should_notify = True
    print(" - Location Match: TRUE (Reason: User is Admin, receives ALL alerts)")
elif profile.location and camera_location and profile.location.lower() == camera_location.lower():
    should_notify = True
    print(f" - Location Match: TRUE (User Location '{profile.location}' == Camera Location '{camera_location}')")
elif not profile.location:
    should_notify = True
    print(" - Location Match: TRUE (Reason: User has no specific location assigned, defaults to all)")
else:
    print(f" - Location Match: FALSE (User Location '{profile.location}' != Camera Location '{camera_location}')")

print("-" * 40)

if not should_notify:
    print("Notification skipped due to location mismatch. Exiting test.")
    exit()

# CHECK GLOBAL SWITCHES
tracker = EmailAlertTracker.objects.first()
global_email = tracker.is_email_enabled if tracker else True
global_sms = tracker.is_sms_enabled if tracker else False
global_whatsapp = tracker.is_whatsapp_enabled if tracker else False

# 4. Try sending Email (With Image Attachment)
if profile.alerts_email and email_address and global_email:
    print(f"Sending Test Email to {email_address}...")
    email = EmailMessage(
        subject=subject,
        body=message_body,
        from_email=settings.EMAIL_HOST_USER,
        to=[email_address],
    )
    
    # Check for Image Attachment
    media_map = EventMediaMap.objects.filter(event_id=event.event_id, media_type='FRAME').first()
    has_image = False
    if media_map:
        frame = Frame.objects.filter(frame_id=media_map.media_id).first()
        if frame and frame.storage_path and os.path.isfile(frame.storage_path):
            try:
                with open(frame.storage_path, 'rb') as img_file:
                    file_name = os.path.basename(frame.storage_path)
                    email.attach(file_name, img_file.read(), 'image/jpeg')
                has_image = True
                print(f"[ATTACHMENT] Image successfully attached to email: {file_name}")
            except Exception as e:
                print(f"[ATTACHMENT ERROR]: Could not attach image: {str(e)}")
        else:
            print("[ATTACHMENT] Frame found in DB, but image file is missing from disk.")
    else:
        print("[ATTACHMENT] No image frame found in database for this event.")
        
    try:
        email.send(fail_silently=False)
        print(" -> Output: Email sent successfully!")
    except Exception as e:
        print(f" -> Output: Failed to send email: {e}")
elif profile.alerts_email and not global_email:
    print("Email skipped (Global Email Switch is OFF)")

# 5. Try sending Twilio (SMS / WhatsApp)
if Client and phone_number:
    twilio_sid = getattr(settings, 'TWILIO_ACCOUNT_SID', '')
    twilio_auth = getattr(settings, 'TWILIO_AUTH_TOKEN', '')
    twilio_number = getattr(settings, 'TWILIO_PHONE_NUMBER', '')
    twilio_whatsapp = getattr(settings, 'TWILIO_WHATSAPP_NUMBER', 'whatsapp:+14155238886')

    if twilio_sid and twilio_auth:
        twilio_client = Client(twilio_sid, twilio_auth)
        
        # SMS
        if profile.alerts_sms and global_sms:
            print(f"\nSending Test SMS to {phone_number}...")
            try:
                msg = twilio_client.messages.create(
                    body=message_body,
                    from_=twilio_number,
                    to=phone_number
                )
                print(f" -> Output: SMS sent successfully! (Twilio SID: {msg.sid})")
            except Exception as e:
                print(f" -> Output: SMS Twilio Error: {e}")
        elif profile.alerts_sms and not global_sms:
            print("\nSMS skipped (Global SMS Switch is OFF)")
                
        # WhatsApp
        if profile.alerts_whatsapp and global_whatsapp:
            print(f"\nSending Test WhatsApp to {phone_number}...")
            wa_number = f"whatsapp:{phone_number}"
            try:
                msg = twilio_client.messages.create(
                    body=message_body,
                    from_=twilio_whatsapp,
                    to=wa_number
                )
                print(f" -> Output: WhatsApp sent successfully! (Twilio SID: {msg.sid})")
            except Exception as e:
                print(f" -> Output: WhatsApp Twilio Error: {e}")
        elif profile.alerts_whatsapp and not global_whatsapp:
            print("\nWhatsApp skipped (Global WhatsApp Switch is OFF)")
    else:
        print("\nTwilio credentials not found in settings.py")
