import os
import django
import sys
from pathlib import Path

# Setup Django environment
BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(BASE_DIR))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'safelensai.settings')
django.setup()

from apps.api.services.event_processor import process_event
from django.utils import timezone

# Construct a simulated SQS payload with s3:// paths
payload = {
    'camera_name': 'Test-Camera-S3',
    'camera_location': 'shopfloor1',
    'event_type': 'FALL_DETECTION',
    'device_id': f'test_device_s3_{int(timezone.now().timestamp())}',
    'media': {
        'image_url': 's3://safelensai-dev-storage-data/storage/incidents/images/fall_detection/shopfloor1/camera_1/2026-06-19/Fall_163140_person_person_3_163140.jpg',
        'video_url': 's3://safelensai-dev-storage-data/storage/incidents/videos/ppe/fall/shopfloor1/camera_1/2026-06-19/Fall_163140_person_person_3_163153.mp4'
    },
    'detections': [
        {
            'type': 'FALL_DETECTION',
            'value': 'fall',
            'details': {'confidence': 0.98}
        }
    ]
}

print('Creating event via process_event service...')
event = process_event(payload)
print(f'Success! Event created: ID={event.event_id}, Type={event.event_type}, Location={event.camera.location if event.camera else None}')
