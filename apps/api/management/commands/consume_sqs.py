"""
File Name: apps/api/management/commands/consume_sqs.py
Description: 
    SQS Consumer that runs as a Django management command on EC2.
    Polls SQS queue for messages from AWS IoT Core, parses the MQTT payload,
    and saves events to RDS using existing EventCreateSerializer.
"""

import os
import json
import time
import logging
import boto3
from datetime import datetime
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.conf import settings

# Import common event processor service
from apps.api.services.event_processor import process_event
from rest_framework.exceptions import ValidationError
from django.db.utils import IntegrityError

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Consumes messages from SQS and creates events in RDS'

    def add_arguments(self, parser):
        parser.add_argument(
            '--queue-url',
            type=str,
            help='SQS Queue URL (overrides environment variable)',
        )
        parser.add_argument(
            '--region',
            type=str,
            default='ap-south-1',
            help='AWS Region (default: ap-south-1)',
        )
        parser.add_argument(
            '--poll-interval',
            type=int,
            default=10,
            help='Seconds between polls (default: 10)',
        )
        parser.add_argument(
            '--max-messages',
            type=int,
            default=10,
            help='Max messages per poll (default: 10, max: 10)',
        )
        parser.add_argument(
            '--wait-time',
            type=int,
            default=20,
            help='Long polling wait time in seconds (default: 20)',
        )

    def handle(self, *args, **options):
        # Startup configuration validation
        deployment_mode = getattr(settings, 'DEPLOYMENT_MODE', 'LOCAL')
        if deployment_mode != 'CLOUD':
            self.stderr.write(self.style.ERROR(
                f"SQS Consumer is only supported in CLOUD mode. Current mode: {deployment_mode}"
            ))
            return

        # Get SQS Queue URL
        queue_url = options.get('queue_url') or getattr(settings, 'SQS_QUEUE_URL', None)
        if not queue_url:
            self.stderr.write(self.style.ERROR(
                'SQS_QUEUE_URL not provided. Set it via --queue-url or settings/environment.'
            ))
            return

        region = options.get('region') or getattr(settings, 'AWS_REGION', 'ap-south-1')
        poll_interval = options.get('poll_interval')
        max_messages = min(options.get('max_messages', 10), 10)
        wait_time = options.get('wait_time')

        self.stdout.write(self.style.SUCCESS(f'Starting SQS Consumer...'))
        self.stdout.write(f'Queue URL: {queue_url}')
        self.stdout.write(f'Region: {region}')
        self.stdout.write(f'Poll Interval: {poll_interval}s')
        self.stdout.write(f'Max Messages: {max_messages}')
        self.stdout.write(f'Wait Time: {wait_time}s')
        self.stdout.write('-' * 60)

        # Initialize SQS client
        sqs_client = boto3.client('sqs', region_name=region)

        # Main loop
        while True:
            try:
                self._poll_messages(sqs_client, queue_url, max_messages, wait_time)
            except Exception as e:
                self.stderr.write(self.style.ERROR(f'Error in poll loop: {e}'))
                time.sleep(poll_interval)

    def _poll_messages(self, sqs_client, queue_url, max_messages, wait_time):
        """Poll SQS for messages and process them"""
        try:
            response = sqs_client.receive_message(
                QueueUrl=queue_url,
                MaxNumberOfMessages=max_messages,
                WaitTimeSeconds=wait_time,
                MessageAttributeNames=['All'],
                AttributeNames=['All']
            )

            messages = response.get('Messages', [])
            
            if not messages:
                return

            self.stdout.write(f'Received {len(messages)} message(s) from SQS')

            for message in messages:
                try:
                    self._process_message(message, sqs_client, queue_url)
                except Exception as e:
                    self.stderr.write(self.style.ERROR(
                        f'Failed to process message {message.get("MessageId")}: {e}'
                    ))

        except Exception as e:
            self.stderr.write(self.style.ERROR(f'Error receiving messages: {e}'))
            raise

    def _process_message(self, message, sqs_client, queue_url):
        """Process a single SQS message"""
        message_id = message.get('MessageId')
        receipt_handle = message.get('ReceiptHandle')
        body = message.get('Body', '{}')

        self.stdout.write(f'Processing message: {message_id}')

        try:
            payload = json.loads(body)
            
            # Map MQTT payload to EventCreateSerializer format
            event_data = self._map_payload_to_event_data(payload)

            # Process the event using the common process_event service
            event = process_event(event_data)
            self.stdout.write(self.style.SUCCESS(
                f'✅ Event created successfully: {event.event_id}'
            ))
            
            # Delete the message from SQS
            sqs_client.delete_message(
                QueueUrl=queue_url,
                ReceiptHandle=receipt_handle
            )
            self.stdout.write(f'🗑️ Deleted message {message_id} from SQS')

        except json.JSONDecodeError as e:
            self.stderr.write(self.style.ERROR(f'Invalid JSON in message: {e}'))
            sqs_client.delete_message(
                QueueUrl=queue_url,
                ReceiptHandle=receipt_handle
            )
            self.stdout.write(f'🗑️ Deleted invalid message {message_id} from SQS')
        except ValidationError as e:
            self.stderr.write(self.style.ERROR(
                f'Validation failed for message {message_id}: {e.detail}'
            ))
            sqs_client.delete_message(
                QueueUrl=queue_url,
                ReceiptHandle=receipt_handle
            )
            self.stdout.write(f'🗑️ Deleted invalid message {message_id} from SQS')
        except IntegrityError as e:
            self.stderr.write(self.style.ERROR(
                f'IntegrityError (duplicate) for message {message_id}: {e}'
            ))
            sqs_client.delete_message(
                QueueUrl=queue_url,
                ReceiptHandle=receipt_handle
            )
            self.stdout.write(f'🗑️ Deleted duplicate message {message_id} from SQS')
        except Exception as e:
            self.stderr.write(self.style.ERROR(f'Error processing message: {e}'))
            raise

    def _map_payload_to_event_data(self, payload):
        """
        Map MQTT payload to EventCreateSerializer expected format.
        """
        # Get media URLs
        media = payload.get('media', {})
        image_url = media.get('image_url')
        video_url = media.get('video_url')

        # Get detections and add edge_id to first detection
        detections = payload.get('detections', [])
        edge_id = payload.get('device_id')
        timestamp_raw = payload.get('timestamp')
        
        # If timestamp is available, combine it with device_id to form a unique event ID.
        # This prevents all events from the same device from being deduplicated/merged.
        if edge_id and timestamp_raw:
            edge_id = f"{edge_id}_{timestamp_raw}"
        
        # Add edge_id to detection details for deduplication
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

        # Build the event data for the serializer
        event_data = {
            "camera_name": payload.get('camera_name', 'Unknown'),
            "camera_location": payload.get('camera_location', 'Unknown'),
            "event_type": payload.get('event_type', 'UNKNOWN'),
            "detections": detections,
            "subjects": payload.get('subjects', []),
            "edge_id": edge_id,
        }

        # Add S3 URLs if available
        if image_url:
            event_data['storage_path'] = image_url
        if video_url:
            event_data['video_storage_path'] = video_url

        # Add timestamp if provided
        if payload.get('timestamp'):
            try:
                timestamp = datetime.fromisoformat(payload['timestamp'].replace('Z', '+00:00'))
                event_data['timestamp'] = timestamp
            except:
                pass

        return event_data
