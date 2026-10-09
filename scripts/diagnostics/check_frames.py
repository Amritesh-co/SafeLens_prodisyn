import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'safelensai.settings')
django.setup()

from apps.api.models import Frame, EventMediaMap, Event

# Check sample frames
print("=== Sample Frames ===")
frames = Frame.objects.all()[:5]
for frame in frames:
    print(f"Frame {frame.frame_id}: {frame.storage_path}")

# Check sample event media mappings
print("\n=== Sample Event Media Map ===")
media_maps = EventMediaMap.objects.filter(media_type='FRAME')[:5]
for mm in media_maps:
    print(f"Event {mm.event_id} -> Frame {mm.media_id}")

# Check sample events with frames
print("\n=== Sample Events with Frames ===")
events = Event.objects.all()[:5]
for event in events:
    media = EventMediaMap.objects.filter(event_id=event.event_id, media_type='FRAME').first()
    if media:
        frame = Frame.objects.filter(frame_id=media.media_id).first()
        if frame:
            print(f"Event {event.event_id} ({event.event_type}): {frame.storage_path}")
