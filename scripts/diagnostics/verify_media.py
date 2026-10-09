import requests
import json
import os
from datetime import datetime

# Configuration
API_URL = "http://localhost:8000/api/events/"
IMAGE_PATH = "test_image.jpg"
VIDEO_PATH = "test_video.mp4"

# Create dummy media files
with open(IMAGE_PATH, "wb") as f:
    f.write(b"fake image data " * 100)
with open(VIDEO_PATH, "wb") as f:
    f.write(b"fake video data " * 500)

payload = {
    "camera_name": "Test-Camera-Cloud",
    "camera_location": "Verification-Lab",
    "event_type": "PPE_VIOLATION",
    "timestamp": datetime.now().isoformat(),
    "detections": json.dumps([{"type": "Helmet", "value": "Missing"}]),
}

files = {
    "file": open(IMAGE_PATH, "rb"),
    "video_file": open(VIDEO_PATH, "rb"),
}

try:
    print(f"Sending POST to {API_URL}...")
    response = requests.post(API_URL, data=payload, files=files, timeout=30)
    print(f"Status Code: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    
    if response.status_code == 201:
        event_id = response.json().get("event_id")
        print(f"SUCCESS! Event {event_id} created.")
        
        # Now verify media URLs via overview
        print("\nVerifying media URLs via overview API...")
        over_url = f"http://localhost:8000/api/overview/events/?camera_location=Verification-Lab"
        over_res = requests.get(over_url)
        print(f"Overview Response: {json.dumps(over_res.json(), indent=2)}")
        
        # Try to download the media
        first_event = over_res.json().get("results", [])[0] if isinstance(over_res.json(), dict) else over_res.json()[0]
        img_url = first_event.get("image_url")
        vid_url = first_event.get("video_url")
        
        if img_url:
            # If it's relative, prefix it
            full_img_url = img_url if img_url.startswith("http") else f"http://localhost:8000{img_url}"
            print(f"Testing image download: {full_img_url}")
            img_head = requests.head(full_img_url)
            print(f"Image Head Status: {img_head.status_code}")
            
        if vid_url:
            full_vid_url = vid_url if vid_url.startswith("http") else f"http://localhost:8000{vid_url}"
            print(f"Testing video download: {full_vid_url}")
            vid_head = requests.head(full_vid_url)
            print(f"Video Head Status: {vid_head.status_code}")

except Exception as e:
    print(f"ERROR: {e}")
finally:
    files["file"].close()
    files["video_file"].close()
    if os.path.exists(IMAGE_PATH): os.remove(IMAGE_PATH)
    if os.path.exists(VIDEO_PATH): os.remove(VIDEO_PATH)

