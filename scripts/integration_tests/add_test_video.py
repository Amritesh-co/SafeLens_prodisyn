import os
import sys
import django

# Setup Django
sys.path.insert(0, '/home/rajanikanth/database-api')
os.environ['DJANGO_SETTINGS_MODULE'] = 'safelensai.settings'
django.setup()

from apps.api.models import Event, Clip, EventMediaMap

def run():
    video_path = '/home/rajanikanth/14-Worker-Safety-System-GUI/Test_Videos/people-tracking.mp4'
    event_id = 125  # Latest event ID
    
    # Check if event exists
    event = Event.objects.filter(event_id=event_id).first()
    if not event:
        print(f"Error: Event {event_id} not found.")
        return

    # Check if already linked
    existing = EventMediaMap.objects.filter(event_id=event_id, media_type='CLIP').first()
    if existing:
        print(f"Event {event_id} already has a clip linked.")
        return

    # Create the clip
    clip = Clip.objects.create(storage_path=video_path)
    print(f"Created clip ID {clip.clip_id}")

    # Link it to the event
    media_map = EventMediaMap.objects.create(
        event_id=event_id,
        media_id=clip.clip_id,
        media_type='CLIP'
    )
    print(f"Linked event {event_id} to clip {clip.clip_id} successfully.")

if __name__ == '__main__':
    run()
