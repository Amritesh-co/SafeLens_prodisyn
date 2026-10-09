from django.apps import AppConfig
from django.db.utils import IntegrityError    


class ApiConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.api'

    def ready(self):
        """
        Optionally runs database bootstrap when Django starts.

        This creates/updates schemas and PostgreSQL roles:
          - db_server_admin  (Database Server team — full access)
          - ai_backend_user  (AI Backend team — incident INSERT only)

        Keep this disabled by default in production. Run schema setup through
        migrations, SQL scripts, or a controlled one-off command unless a
        deployment explicitly opts in.
        """
        import os
        if os.environ.get('ENABLE_DB_INIT_ON_STARTUP') == '1':
            from django.conf import settings
            if settings.DATABASES['default']['ENGINE'] != 'django.db.backends.sqlite3':
                from .db_setup import initialize_database
                initialize_database()

        # Start background consumers if running as a web server process
        if self.should_start_consumers():
            self.start_background_consumers()

    def should_start_consumers(self):
        import sys
        import os
        # 1. Do not start during test execution or migrations
        if 'test' in sys.argv or 'pytest' in sys.argv or any('pytest' in arg for arg in sys.argv) or 'migrate' in sys.argv or 'makemigrations' in sys.argv:
            return False
            
        # 2. If running manage.py runserver, only start in the main reload process
        if 'runserver' in sys.argv:
            return os.environ.get('RUN_MAIN') == 'true'
            
        # 3. For WSGI/ASGI servers (Gunicorn, uwsgi, etc.), sys.argv usually doesn't contain runserver
        # but we want to run them. We want to avoid starting them if we are running other management commands
        # like collectstatic, shell, dbshell, etc.
        non_server_commands = {'collectstatic', 'shell', 'dbshell', 'check', 'showmigrations', 'inspectdb','poll_events','daily_incident_summary'}
        if any(cmd in sys.argv for cmd in non_server_commands):
            return False
            
        return True

    def start_background_consumers(self):
        import threading
        from django.conf import settings
        import logging
        
        logger = logging.getLogger(__name__)
        deployment_mode = getattr(settings, 'DEPLOYMENT_MODE', 'LOCAL')
        
        if deployment_mode == 'LOCAL':
            logger.info("Starting background MQTT consumer thread...")
            thread = threading.Thread(target=self.run_mqtt_consumer, daemon=True, name="MQTTConsumerThread")
            thread.start()
        elif deployment_mode == 'CLOUD':
            logger.info("Starting background SQS consumer thread...")
            thread = threading.Thread(target=self.run_sqs_consumer, daemon=True, name="SQSConsumerThread")
            thread.start()

    def run_mqtt_consumer(self):
        import logging
        import time
        from django.conf import settings
        import paho.mqtt.client as mqtt
        from apps.api.services.event_processor import process_event
        from rest_framework.exceptions import ValidationError
        import json

        logger = logging.getLogger("apps.api.mqtt_background")
        
        host = getattr(settings, 'MQTT_HOST', 'localhost')
        port = getattr(settings, 'MQTT_PORT', 1883)
        topic = getattr(settings, 'MQTT_TOPIC', 'safelens/events')
        username = getattr(settings, 'MQTT_USERNAME', '')
        password = getattr(settings, 'MQTT_PASSWORD', '')
        import uuid
        client_id = f"safelens-bg-{uuid.uuid4().hex[:8]}"
        client = mqtt.Client(client_id=client_id, clean_session=True)
        if username:
            client.username_pw_set(username, password)

        def on_connect(client, userdata, flags, rc):
            if rc == 0:
                logger.info(f"Connected to MQTT Broker. Subscribing to '{topic}'...")
                client.subscribe(topic)
            else:
                logger.error(f"Connection failed with code {rc}")

        def on_message(client, userdata, msg):
            payload_str = msg.payload.decode('utf-8')
            logger.debug(f"Received message on topic '{msg.topic}': {payload_str}")
            try:
                payload = json.loads(payload_str)
                event = process_event(payload)
                logger.info(f"MQTT BG: Event processed and saved. ID: {event.event_id}")
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON payload: {e}")
            except ValidationError as e:
                logger.error(f"Validation failed: {e.detail}")
            except Exception as e:
                logger.error(f"Error processing MQTT message: {e}")

        def on_disconnect(client, userdata, rc):
            logger.warning(f"MQTT Client disconnected with code {rc}. Reconnecting...")

        client.on_connect = on_connect
        client.on_message = on_message
        client.on_disconnect = on_disconnect

        while True:
            try:
                logger.info(f"Connecting to MQTT broker at {host}:{port}...")
                client.connect(host, port, keepalive=60)
                client.loop_forever(retry_first_connection=True)
            except Exception as e:
                logger.error(f"MQTT Client loop disconnected: {e}. Reconnecting in 5s...")
                time.sleep(5)

    def run_sqs_consumer(self):
        import logging
        import time
        from django.conf import settings
        import boto3
        import json
        from apps.api.services.event_processor import process_event
        from rest_framework.exceptions import ValidationError
        from datetime import datetime

        logger = logging.getLogger("apps.api.sqs_background")
        
        queue_url = getattr(settings, 'SQS_QUEUE_URL', None)
        region = getattr(settings, 'AWS_REGION', 'ap-south-1')

        if not queue_url:
            logger.error("SQS_QUEUE_URL not provided. SQS consumer thread stopped.")
            return

        logger.info(f"Starting SQS background consumer for: {queue_url} ({region})")
        sqs_client = boto3.client('sqs', region_name=region)

        def map_payload_to_event_data(payload):
            media = payload.get('media', {})
            image_url = media.get('image_url')
            video_url = media.get('video_url')
            detections = payload.get('detections', [])
            edge_id = payload.get('device_id')
            timestamp_raw = payload.get('timestamp')
            
            # If timestamp is available, combine it with device_id to form a unique event ID.
            # This prevents all events from the same device from being deduplicated/merged.
            if edge_id and timestamp_raw:
                edge_id = f"{edge_id}_{timestamp_raw}"
            
            if detections and edge_id:
                if isinstance(detections[0].get('details'), dict):
                    detections[0]['details']['edge_id'] = edge_id
                else:
                    detections[0]['details'] = {'edge_id': edge_id}
            elif edge_id and not detections:
                detections = [{
                    "type": payload.get('event_type', 'UNKNOWN'),
                    "value": "detected",
                    "details": {"edge_id": edge_id}
                }]

            event_data = {
                "camera_name": payload.get('camera_name', 'Unknown'),
                "camera_location": payload.get('camera_location', 'Unknown'),
                "event_type": payload.get('event_type', 'UNKNOWN'),
                "detections": detections,
                "subjects": payload.get('subjects', []),
                "edge_id": edge_id,
            }
            if image_url:
                event_data['storage_path'] = image_url
            if video_url:
                event_data['video_storage_path'] = video_url
            if payload.get('timestamp'):
                try:
                    timestamp = datetime.fromisoformat(payload['timestamp'].replace('Z', '+00:00'))
                    event_data['timestamp'] = timestamp
                except:
                    pass
            return event_data

        while True:
            try:
                response = sqs_client.receive_message(
                    QueueUrl=queue_url,
                    MaxNumberOfMessages=10,
                    WaitTimeSeconds=20,
                    MessageAttributeNames=['All'],
                    AttributeNames=['All']
                )

                messages = response.get('Messages', [])
                for message in messages:
                    message_id = message.get('MessageId')
                    receipt_handle = message.get('ReceiptHandle')
                    body = message.get('Body', '{}')

                    try:
                        payload = json.loads(body)
                        event_data = map_payload_to_event_data(payload)
                        event = process_event(event_data)
                        logger.info(f"SQS BG: Event created successfully: {event.event_id}")
                        
                        sqs_client.delete_message(
                            QueueUrl=queue_url,
                            ReceiptHandle=receipt_handle
                        )
                        logger.info(f"SQS BG: Deleted message {message_id} from SQS")
                    except json.JSONDecodeError as e:
                        logger.error(f"Invalid JSON in SQS message: {e}")
                        sqs_client.delete_message(
                            QueueUrl=queue_url,
                            ReceiptHandle=receipt_handle
                        )
                    except ValidationError as e:
                        logger.error(f"Validation failed for SQS message {message_id}: {e.detail}")
                        sqs_client.delete_message(QueueUrl=queue_url, ReceiptHandle=receipt_handle)   
                    except IntegrityError as e:                                                        
                        logger.warning(f"IntegrityError (duplicate data) for SQS message {message_id}: {e}")   
                        sqs_client.delete_message(QueueUrl=queue_url, ReceiptHandle=receipt_handle)   
                    except Exception as e:
                        logger.error(f"Error processing SQS message: {e}")

            except Exception as e:
                logger.error(f"Error in background SQS loop: {e}")
                time.sleep(10)
