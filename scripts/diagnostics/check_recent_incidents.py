import os
import sys
import django
from datetime import datetime

# Add the project root to PYTHONPATH
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)

# Setup Django Environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'safelensai.settings')
django.setup()

from apps.api.models import Event, EventMediaMap, Frame, Clip

def get_media_url(event_id, media_type):
    """Utility to fetch S3 or local path for an event media."""
    media_map = EventMediaMap.objects.filter(event_id=event_id, media_type=media_type).first()
    if not media_map:
        return "None"
    
    if media_type == 'FRAME':
        media_obj = Frame.objects.filter(frame_id=media_map.media_id).first()
    else:
        media_obj = Clip.objects.filter(clip_id=media_map.media_id).first()
        
    return media_obj.storage_path if media_obj else "None"

def check_recent_incidents(limit=10):
    print(f"\n--- Fetching Last {limit} Incidents from AWS RDS ---\n")
    print(f"{'ID':<6} | {'Timestamp (IST)':<20} | {'Type':<15} | {'Camera':<20}")
    print("-" * 70)
    
    events = Event.objects.all().order_by('-timestamp')[:limit]
    
    for e in events:
        ist_time = e.timestamp.strftime("%Y-%m-%d %H:%M:%S")
        print(f"{e.event_id:<6} | {ist_time:<20} | {e.event_type:<15} | {e.camera.name:<20}")
        
        # Fetch Image and Video URLs from DB
        img_url = get_media_url(e.event_id, 'FRAME')
        vid_url = get_media_url(e.event_id, 'CLIP')
        
        if img_url != "None":
            print(f"  └─ Image: {img_url}")
        if vid_url != "None":
            print(f"  └─ Video: {vid_url}")
        print("-" * 10)
    
    # JSON for the absolute latest for copy-pasting to audit
    if events:
        latest = events[0]
        import json
        print(f"\n--- Top Result (ID: {latest.event_id}) Full Media Audit ---")
        audit = {
            "event_id": latest.event_id,
            "timestamp": str(latest.timestamp),
            "image_url": get_media_url(latest.event_id, 'FRAME'),
            "video_url": get_media_url(latest.event_id, 'CLIP')
        }
        print(json.dumps(audit, indent=4))

if __name__ == "__main__":
    check_recent_incidents()
