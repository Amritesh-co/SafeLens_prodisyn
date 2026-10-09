import os
import pytest
from rest_framework.test import APIClient
from rest_framework.exceptions import ValidationError
from apps.api.models import Camera, Event, EventDetection
from apps.api.services.event_processor import process_event

# Ensure Django is initialized for pytest
pytestmark = pytest.mark.django_db

@pytest.fixture
def api_client():
    return APIClient()

def test_process_event_success():
    """Test process_event with a valid payload successfully creates models"""
    payload = {
        "camera_name": "TestCam-01",
        "camera_location": "Shopfloor A",
        "event_type": "NO_HELMET",
        "detections": [
            {"type": "NO_HELMET", "value": "detected", "details": {"score": 0.95}}
        ]
    }
    
    event = process_event(payload)
    assert event is not None
    assert event.event_id is not None
    assert event.event_type == "NO_HELMET"
    
    # Check that the camera was created/retrieved correctly
    camera = Camera.objects.get(name="TestCam-01")
    assert camera.location == "Shopfloor A"
    assert event.camera == camera
    
    # Check that detection was created
    detections = EventDetection.objects.filter(event=event)
    assert len(detections) == 1
    assert detections[0].detection_type == "NO_HELMET"

def test_process_event_validation_error():
    """Test process_event raises ValidationError when required fields are missing"""
    # Missing camera_name and event_type
    payload = {
        "camera_location": "Shopfloor A"
    }
    
    with pytest.raises(ValidationError):
        process_event(payload)

def test_rest_api_ingest_success(api_client):
    """Test POST /api/events/ingest/ with valid data returns 201"""
    url = "/api/events/ingest/"
    payload = {
        "camera_name": "REST-Cam-01",
        "camera_location": "Shopfloor B",
        "event_type": "FALL",
        "detections": []
    }
    
    response = api_client.post(url, payload, format='json')
    assert response.status_code == 201
    assert response.data["status"] == "success"
    assert "event_id" in response.data

def test_rest_api_ingest_validation_failure(api_client):
    """Test POST /api/events/ingest/ with invalid data returns 400"""
    url = "/api/events/ingest/"
    payload = {
        # Missing required camera_name and event_type
        "camera_location": "Shopfloor B"
    }
    
    response = api_client.post(url, payload, format='json')
    assert response.status_code == 400
    assert response.data["status"] == "error"
    assert "errors" in response.data
