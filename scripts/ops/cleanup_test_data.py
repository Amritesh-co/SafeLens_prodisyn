"""
Clean Up Test Data for Worker Safety API

This script removes all test data created by generate_test_data.py
It identifies test data by the camera location 'TEST_DATA'

Usage:
    python3 cleanup_test_data.py
"""

import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'safelensai.settings')
django.setup()

from apps.api.models import Event, Camera, EventDetection

def cleanup_test_data():
    """Remove all test data"""
    print("🧹 Worker Safety API - Test Data Cleanup")
    print("="*50)
    
    # Find test camera
    test_camera = Camera.objects.filter(location='TEST_DATA').first()
    
    if not test_camera:
        print("✅ No test data found. Database is clean!")
        return
    
    # Count events before deletion
    events = Event.objects.filter(camera=test_camera)
    event_count = events.count()
    
    if event_count == 0:
        print("✅ No test events found")
        # Delete the test camera
        test_camera.delete()
        print("✅ Removed test camera")
        return
    
    print(f"\n📊 Found {event_count} test events")
    
    # Confirm deletion
    response = input(f"\n⚠️  Are you sure you want to delete {event_count} test events? (yes/no): ")
    
    if response.lower() != 'yes':
        print("❌ Cleanup cancelled")
        return
    
    # Delete event detections first (foreign key relationship)
    detection_count = EventDetection.objects.filter(event__camera=test_camera).count()
    if detection_count > 0:
        EventDetection.objects.filter(event__camera=test_camera).delete()
        print(f"✅ Deleted {detection_count} event detections")
    
    # Delete events
    deleted_events, _ = events.delete()
    print(f"✅ Deleted {event_count} test events")
    
    # Delete test camera
    test_camera.delete()
    print("✅ Removed test camera (ID: 999, Location: TEST_DATA)")
    
    print("\n" + "="*50)
    print("✨ Cleanup complete! Your database is back to original state.")
    print("="*50)

if __name__ == '__main__':
    cleanup_test_data()
