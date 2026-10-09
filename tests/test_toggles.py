import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'safelensai.settings')
django.setup()

from django.contrib.auth.models import User
from apps.api.serializers import UserSerializer

print("--- Testing UserSerializer Updates ---")
user = User.objects.filter(username='admin').first()
if not user:
    print("Admin user not found")
    exit()

print("-- Initial Representation --")
print(UserSerializer(user).data)

print("\n-- Updating alerts_sms to True --")
serializer = UserSerializer(user, data={'alerts_sms': True, 'alerts_whatsapp': True}, partial=True)
if serializer.is_valid():
    serializer.save()
    print("Update successful")
else:
    print("Validation failed:", serializer.errors)

print("\n-- Verification --")
user.refresh_from_db()
print(UserSerializer(user).data)

print("\n-- Reverting alerts_sms to False --")
serializer = UserSerializer(user, data={'alerts_sms': False, 'alerts_whatsapp': False}, partial=True)
if serializer.is_valid():
    serializer.save()
    print("Revert successful")
else:
    print("Validation failed:", serializer.errors)

print("\n-- Final Verification --")
user.refresh_from_db()
print(UserSerializer(user).data)
