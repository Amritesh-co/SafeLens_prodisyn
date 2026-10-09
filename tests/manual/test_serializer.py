import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'safelensai.settings')
django.setup()

from apps.api.serializers import EventCreateSerializer

payload = {
    "camera_name": "Cam-01-Simulation",
    "camera_location": "Shopfloor 1",
    "event_type": "NO_VEST",
    "storage_path": "test.jpg",
    "detections": []
}

serializer = EventCreateSerializer(data=payload)
if serializer.is_valid(raise_exception=True):
    serializer.save()
    print("Success")
