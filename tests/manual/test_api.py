import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'safelensai.settings')
django.setup()

from django.test import Client
import json

client = Client()
payload = {
    "camera_name": "Cam-01-Simulation",
    "event_type": "NO_VEST",
    "storage_path": "test.jpg"
}

response = client.post('/api/events/', json.dumps(payload), content_type='application/json')
print("Status Code:", response.status_code)
if response.status_code == 500:
    print(response.content)
    try:
        raise Exception("API threw 500")
    except Exception as e:
        # In a real test case, client.post raises the exception if DEBUG=True, but let's see.
        pass
