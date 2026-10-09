import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'safelensai.settings')
django.setup()

from apps.api.models import EventReview

# Check event #4505
rev = EventReview.objects.filter(event_id=4505).first()
if rev:
    print(f"ID: {rev.id}")
    print(f"Status: {rev.status}")
    print(f"Comments: {repr(rev.comments)}")
    print(f"Updated by: {rev.updated_by}")
else:
    print("No review found for event 4505")

