import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'safelensai.settings')
import django
django.setup()

from django.contrib.auth.models import User
from apps.api.serializers import UserSerializer

user = User.objects.get(id=1)
serializer = UserSerializer(user, data={'username': 'raj', 'email': 'raj123@gmail.com', 'alerts_email': False, 'alerts_sms': True, 'alerts_whatsapp': True, 'role': 'Admin', 'status': 'Active', 'phone_number': '9876543210'}, partial=True)

if serializer.is_valid():
    print("VALID", serializer.validated_data)
    serializer.save()
    print("UPDATED PROFILE:")
    print("Email:", user.profile.alerts_email)
    print("SMS:", user.profile.alerts_sms)
    print("WhatsApp:", user.profile.alerts_whatsapp)
else:
    print("ERRORS", serializer.errors)
