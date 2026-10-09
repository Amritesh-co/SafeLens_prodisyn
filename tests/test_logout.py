import os
import django
from django.utils import timezone
from apps.api.models import User, UserActivityLog
from rest_framework.test import APIClient

# Set up Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'safelensai.settings')
django.setup()

def debug_logout_flow():
    user = User.objects.get(username='admin')
    client = APIClient()
    client.force_authenticate(user=user)

    print(f"--- Starting logout flow test for {user.username} ---")
    
    # 1. Login simulation is already handled by create in LogoutView logic
    # But let's create a fresh one to be sure
    log = UserActivityLog.objects.create(user=user, ip_address='1.2.3.4')
    print(f"Created log ID: {log.id} at {log.login_time}")

    # 2. Call the logout endpoint
    response = client.post('/api/logout/')
    print(f"Logout API Status: {response.status_code}")
    print(f"Logout API Body: {response.data}")

    # 3. Verify
    log.refresh_from_db()
    print(f"Verified log ID {log.id} logout_time: {log.logout_time}")
    
    if log.logout_time:
        print("SUCCESS: Logout time updated correctly.")
    else:
        print("FAILURE: Logout time remains None.")

if __name__ == "__main__":
    debug_logout_flow()
