import json
import logging
import time
from django.core.management.base import BaseCommand
from django.conf import settings
import paho.mqtt.client as mqtt
from apps.api.services.event_processor import process_event
from rest_framework.exceptions import ValidationError

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Subscribes to MQTT topic and ingests events locally'

    def handle(self, *args, **options):
        # Startup configuration validation
        deployment_mode = getattr(settings, 'DEPLOYMENT_MODE', 'LOCAL')
        if deployment_mode != 'LOCAL':
            self.stderr.write(self.style.ERROR(
                f"MQTT Consumer is only supported in LOCAL mode. Current mode: {deployment_mode}"
            ))
            return

        host = getattr(settings, 'MQTT_HOST', None)
        port = getattr(settings, 'MQTT_PORT', 1883)
        topic = getattr(settings, 'MQTT_TOPIC', None)
        username = getattr(settings, 'MQTT_USERNAME', '')
        password = getattr(settings, 'MQTT_PASSWORD', '')

        if not host:
            self.stderr.write(self.style.ERROR("MQTT_HOST settings is not configured."))
            return
        if not topic:
            self.stderr.write(self.style.ERROR("MQTT_TOPIC settings is not configured."))
            return

        self.stdout.write(self.style.SUCCESS(f"Starting MQTT Consumer..."))
        self.stdout.write(f"Host: {host}")
        self.stdout.write(f"Port: {port}")
        self.stdout.write(f"Topic: {topic}")

        # Use clean session and standard API
        import uuid
        client_id = f"safelens-local-{uuid.uuid4().hex[:8]}"
        client = mqtt.Client(client_id=client_id, clean_session=True)

        if username:
            client.username_pw_set(username, password)

        def on_connect(client, userdata, flags, rc):
            if rc == 0:
                self.stdout.write(self.style.SUCCESS(f"Successfully connected to MQTT Broker. Subscribing to '{topic}'..."))
                client.subscribe(topic)
            else:
                self.stderr.write(self.style.ERROR(f"Connection failed with code {rc}"))

        def on_message(client, userdata, msg):
            payload_str = msg.payload.decode('utf-8')
            self.stdout.write(f"Received message on topic '{msg.topic}': {payload_str}")
            try:
                payload = json.loads(payload_str)
                # Call common event processor
                event = process_event(payload)
                self.stdout.write(self.style.SUCCESS(f"✅ Event processed and saved. ID: {event.event_id}"))
            except json.JSONDecodeError as e:
                self.stderr.write(self.style.ERROR(f"Failed to parse JSON payload: {e}"))
            except ValidationError as e:
                self.stderr.write(self.style.ERROR(f"Validation failed: {e.detail}"))
            except Exception as e:
                self.stderr.write(self.style.ERROR(f"Error processing MQTT message: {e}"))

        def on_disconnect(client, userdata, rc):
            self.stderr.write(self.style.WARNING(f"MQTT Client disconnected with code {rc}. Reconnecting..."))

        client.on_connect = on_connect
        client.on_message = on_message
        client.on_disconnect = on_disconnect

        # Automatic reconnection loop
        while True:
            try:
                self.stdout.write(f"Connecting to MQTT broker at {host}:{port}...")
                client.connect(host, port, keepalive=60)
                # Loop forever. This will block and automatically handle reconnection attempts if the connection drops.
                client.loop_forever(retry_first_connection=True)
            except Exception as e:
                self.stderr.write(self.style.ERROR(f"MQTT Client loop disconnected: {e}. Reconnecting in 5s..."))
                time.sleep(5)
