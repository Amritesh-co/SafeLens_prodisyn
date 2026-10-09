import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'safelensai.settings')
django.setup()

from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token

try:
    user = User.objects.get(username='admin')
    token, _ = Token.objects.get_or_create(user=user)
    print(token.key)
except Exception as e:
    print(f"Error: {e}")
