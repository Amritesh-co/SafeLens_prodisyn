import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'safelensai.settings')
django.setup()

from apps.api.models import Event
from apps.api.serializers import OverviewEventSerializer
import json

# Get the last simulated event
event = Event.objects.filter(camera__name='Cam-01-Simulation').order_by('-event_id').first()
if event:
    serializer = OverviewEventSerializer(event)
    print("IMAGE URL:", serializer.data.get('image_url'))
else:
    print("No simulated event found.")
