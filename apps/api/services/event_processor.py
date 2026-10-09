import copy
import logging
from rest_framework.exceptions import ValidationError
from apps.api.serializers import EventCreateSerializer
from django.db import transaction

logger = logging.getLogger(__name__)

def normalize_payload(payload):
    """
    Normalizes a raw event payload (e.g. from SQS or MQTT) into the format
    expected by EventCreateSerializer.
    This includes:
      1. Mapping 'device_id' to 'edge_id'.
      2. Appending 'timestamp' to 'edge_id' to create a unique identifier to prevent false deduplication.
      3. Mapping 'media.image_url' to 'storage_path'.
      4. Mapping 'media.video_url' to 'video_storage_path'.
      5. Ensuring 'edge_id' is propagated into the detections' details.
    """
    # 1. Start with a copy of the payload to avoid side-effects
    data = copy.deepcopy(payload)
    
    # 2. Map media URLs
    media = data.get('media')
    if isinstance(media, dict):
        if 'image_url' in media and not data.get('storage_path'):
            data['storage_path'] = media['image_url']
        if 'video_url' in media and not data.get('video_storage_path'):
            data['video_storage_path'] = media['video_url']
            
    # 3. Map device_id to edge_id and handle uniqueness
    edge_id = data.get('edge_id') or data.get('device_id')
    timestamp_raw = data.get('timestamp')
    
    # Append timestamp to edge_id to make it a unique instance key
    if edge_id and timestamp_raw:
        # Check if the timestamp is already appended to prevent double appending
        if not str(edge_id).endswith(str(timestamp_raw)):
            edge_id = f"{edge_id}_{timestamp_raw}"
            
    if edge_id:
        data['edge_id'] = edge_id

    # 4. Handle detections list mapping
    detections = data.get('detections', [])
    if not isinstance(detections, list):
        detections = []
    else:
        # copy detections list to avoid mutating the original
        detections = copy.deepcopy(detections)
        
    if edge_id:
        if detections:
            # Ensure first detection has the edge_id injected
            if isinstance(detections[0], dict):
                if not isinstance(detections[0].get('details'), dict):
                    detections[0]['details'] = {}
                detections[0]['details']['edge_id'] = edge_id
        else:
            # Create a default detection so the edge_id is stored
            detections = [{
                "type": data.get('event_type', 'UNKNOWN'),
                "value": "detected",
                "details": {"edge_id": edge_id}
            }]
            
    data['detections'] = detections
    
    return data

def process_event(payload):
    """
    Common event processing service that validates and inserts an event.
    Accepts payload dictionary.
    Normalizes/maps payload to expected EventCreateSerializer schema.
    Validates using EventCreateSerializer.
    Saves event.
    Returns created event.
    Raises ValidationError on validation failure.
    """
    logger.info("process_event: Received payload for processing")
    
    # Normalize payload format (maps SQS/MQTT raw formats to serializer fields)
    normalized_payload = normalize_payload(payload)
    
    # Initialize the serializer with the input payload
    serializer = EventCreateSerializer(data=normalized_payload)
    
    # Run validation
    if not serializer.is_valid():
        logger.error(f"process_event: Validation failed with errors: {serializer.errors}")
        raise ValidationError(serializer.errors)
        
    try:
        # Create and save the event
        with transaction.atomic():
            event = serializer.save()
        logger.info(f"process_event: Event processed and saved successfully. Event ID: {event.event_id}")
        return event
    except Exception as e:
        logger.error(f"process_event: Database insertion failed: {str(e)}", exc_info=True)
        raise e

