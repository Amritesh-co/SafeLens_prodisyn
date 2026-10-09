"""
Generate Test Data for Worker Safety API

This script creates dummy events for testing the dashboard.
All test data is tagged with a special camera location 'TEST_DATA'
so it can be easily identified and removed.

Usage:
    python3 generate_test_data.py

This will create:
- 50 events for today with various types
- Events spread across the last 12 hours
- Mix of Fall, Intrusion, and PPE violations (Helmet, Vest)
"""

import os
import django
import random
from datetime import datetime, timedelta

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'safelensai.settings')
django.setup()

from django.utils import timezone
from apps.api.models import Event, Camera, EventDetection, DetectionModel

def create_test_camera():
    """Create or get a test camera"""
    camera, created = Camera.objects.get_or_create(
        camera_id=999,
        defaults={
            'name': 'TEST_CAMERA_999',
            'location': 'TEST_DATA'
        }
    )
    if created:
        print("✅ Created test camera (ID: 999, Location: TEST_DATA)")
    else:
        print("ℹ️  Test camera already exists")
    return camera

def create_test_events(camera, count=50):
    """Create test events spread across today"""
    now = timezone.now()  # Use timezone-aware datetime
    start_time = now.replace(hour=8, minute=0, second=0, microsecond=0)
    
    event_types = [
        'FALL_DETECTED',
        'INTRUSION', 
        'PPE_VIOLATION',
        'PPE_VIOLATION',  # More PPE violations for testing
    ]
    
    print(f"\n📊 Creating {count} test events...")
    created_count = 0
    
    for i in range(count):
        # Random time in last 12 hours
        hours_ago = random.randint(0, 12)
        minutes_ago = random.randint(0, 59)
        event_time = now - timedelta(hours=hours_ago, minutes=minutes_ago)
        
        event_type = random.choice(event_types)
        
        event = Event.objects.create(
            camera=camera,
            event_type=event_type,
            timestamp=event_time
        )
        
        # Add detection details for PPE violations
        if event_type == 'PPE_VIOLATION':
            model, _ = DetectionModel.objects.get_or_create(
                model_id=1,
                defaults={'model_name': 'PPE Detection Model'}
            )
            
            # Randomly choose helmet or vest violation
            ppe_type = random.choice(['helmet', 'vest', 'both'])
            
            if ppe_type == 'helmet' or ppe_type == 'both':
                EventDetection.objects.create(
                    event=event,
                    model=model,
                    detection_type='PPE',
                    detection_value='No Helmet',
                    detection_details={'missing_items': ['helmet']}
                )
            
            if ppe_type == 'vest' or ppe_type == 'both':
                EventDetection.objects.create(
                    event=event,
                    model=model,
                    detection_type='PPE',
                    detection_value='No Vest',
                    detection_details={'missing_items': ['vest']}
                )
        
        created_count += 1
        if (i + 1) % 10 == 0:
            print(f"  Created {i + 1}/{count} events...")
    
    print(f"✅ Successfully created {created_count} test events!")

def show_summary():
    """Show summary of test data"""
    camera = Camera.objects.filter(location='TEST_DATA').first()
    if not camera:
        print("\n⚠️  No test data found")
        return
    
    events = Event.objects.filter(camera=camera)
    total = events.count()
    
    fall_count = events.filter(event_type='FALL_DETECTED').count()
    intrusion_count = events.filter(event_type='INTRUSION').count()
    ppe_count = events.filter(event_type='PPE_VIOLATION').count()
    
    print("\n" + "="*50)
    print("📈 TEST DATA SUMMARY")
    print("="*50)
    print(f"Total Events: {total}")
    print(f"  - Fall Detected: {fall_count}")
    print(f"  - Intrusion: {intrusion_count}")
    print(f"  - PPE Violations: {ppe_count}")
    print("="*50)
    print(f"\n💡 Camera Location: TEST_DATA (ID: 999)")
    print("💡 To remove this data, run: python3 cleanup_test_data.py")
    print()

if __name__ == '__main__':
    print("🚀 Worker Safety API - Test Data Generator")
    print("="*50)
    
    # Create test camera
    camera = create_test_camera()
    
    # Check if test data already exists
    existing_events = Event.objects.filter(camera=camera).count()
    if existing_events > 0:
        print(f"\n⚠️  Found {existing_events} existing test events")
        response = input("Do you want to add more test data? (y/n): ")
        if response.lower() != 'y':
            print("❌ Cancelled")
            show_summary()
            exit(0)
    
    # Create test events
    create_test_events(camera, count=50)
    
    # Show summary
    show_summary()
