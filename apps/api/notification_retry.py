import os
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from apps.api.models import NotificationDeliveryLog, Event, EventMediaMap, Frame, Clip
from apps.api.utils import send_aws_whatsapp, get_whatsapp_template_name


def _write(stdout, message):
    if stdout:
        stdout.write(message)


def log_delivery(event_id, recipient, status, provider_message_id=None, error_message=None, details=None):
    details = details or {}
    NotificationDeliveryLog.objects.create(
        event_id=event_id,
        channel='WHATSAPP',
        recipient=recipient,
        status=status,
        provider='AWS_SOCIAL_MESSAGING',
        provider_message_id=provider_message_id,
        template_name=details.get('template_name'),
        error_message=error_message,
        details=details
    )


def media_public_url(storage_path):
    if not storage_path:
        return None

    path = str(storage_path).strip()
    if path.startswith('http://') or path.startswith('https://'):
        return path

    base_url = os.environ.get('PUBLIC_BASE_URL', getattr(settings, 'PUBLIC_BASE_URL', ''))
    if not base_url:
        return None

    storage_base = os.environ.get('SYSTEM_STORAGE_DIR')
    if not storage_base:
        storage_base = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'storage'))

    if path.startswith(storage_base):
        rel_path = os.path.relpath(path, storage_base)
    elif 'storage/' in path:
        rel_path = path.split('storage/', 1)[-1].lstrip('/')
    else:
        rel_path = path.lstrip('/')

    return f"{base_url}/media/{rel_path}"


def build_event_payload(event):
    camera_name = event.camera.name if event.camera else "Unknown Camera"
    camera_location = event.camera.location if event.camera and event.camera.location else "Unknown Location"

    if event.timestamp:
        dt = event.timestamp
        if timezone.is_naive(dt):
            dt = timezone.make_aware(dt)
        event_time_str = timezone.localtime(dt).strftime('%Y-%m-%d %H:%M:%S')
    else:
        event_time_str = "Unknown Time"

    wa_image_url = None
    wa_video_url = None

    img_map = EventMediaMap.objects.filter(event_id=event.event_id, media_type='FRAME').first()
    if img_map:
        frame = Frame.objects.filter(frame_id=img_map.media_id).first()
        if frame and frame.storage_path:
            wa_image_url = media_public_url(frame.storage_path)

    vid_map = EventMediaMap.objects.filter(event_id=event.event_id, media_type='CLIP').first()
    if vid_map:
        clip = Clip.objects.filter(clip_id=vid_map.media_id).first()
        if clip and clip.storage_path:
            wa_video_url = media_public_url(clip.storage_path)

    whatsapp_body = (
        f"SafeLens AI ALERT\n\n"
        f"Location: {camera_location}\n"
        f"Camera: {camera_name}\n"
        f"Time: {event_time_str}\n"
        f"Incident: {event.event_type}\n"
        f"Event ID: {event.event_id}\n\n"
        f"Powered by prodisyn SafeLens AI"
    )

    return {
        'camera_name': camera_name,
        'camera_location': camera_location,
        'event_time_str': event_time_str,
        'wa_image_url': wa_image_url,
        'wa_video_url': wa_video_url,
        'whatsapp_body': whatsapp_body,
        'template_name': get_whatsapp_template_name(wa_image_url),
    }


def retry_failed_whatsapp_logs(limit=50, hours=24, recipient=None, event_id=None, dry_run=False, stdout=None):
    since = timezone.now() - timedelta(hours=hours)

    queryset = NotificationDeliveryLog.objects.filter(
        channel='WHATSAPP',
        status='FAILED',
        created_at__gte=since
    ).order_by('-created_at')

    if recipient:
        queryset = queryset.filter(recipient=recipient)
    if event_id:
        queryset = queryset.filter(event_id=event_id)

    failed_logs = list(queryset[:limit])

    if not failed_logs:
        _write(stdout, "No failed WhatsApp logs found for retry.")
        return {'attempted': 0, 'sent': 0, 'skipped': 0, 'inspected': 0, 'dry_run': dry_run}

    _write(stdout, f"Found {len(failed_logs)} failed WhatsApp log(s) to inspect.")

    attempted = 0
    sent = 0
    skipped = 0

    for log in failed_logs:
        already_sent = NotificationDeliveryLog.objects.filter(
            event_id=log.event_id,
            channel='WHATSAPP',
            recipient=log.recipient,
            status='SENT',
            created_at__gt=log.created_at
        ).exists()

        if already_sent:
            skipped += 1
            _write(stdout, f"SKIP event={log.event_id} recipient={log.recipient} reason=already_sent_later")
            continue

        try:
            event = Event.objects.get(event_id=log.event_id)
        except Event.DoesNotExist:
            skipped += 1
            log_delivery(
                event_id=log.event_id,
                recipient=log.recipient,
                status='SKIPPED',
                error_message='Event no longer exists for retry',
                details={'retry_of': log.id, 'reason': 'event_missing'}
            )
            _write(stdout, f"SKIP event={log.event_id} recipient={log.recipient} reason=event_missing")
            continue

        payload = build_event_payload(event)
        attempted += 1

        if dry_run:
            _write(
                stdout,
                f"DRY_RUN event={log.event_id} recipient={log.recipient} "
                f"template={payload['template_name']} has_image={bool(payload['wa_image_url'])} "
                f"has_video={bool(payload['wa_video_url'])}"
            )
            continue

        try:
            response = send_aws_whatsapp(
                log.recipient,
                payload['whatsapp_body'],
                media_url=payload['wa_image_url'],
                location=payload['camera_location'],
                time_str=payload['event_time_str'],
                incident_type=event.event_type,
                event_id=event.event_id,
                video_url=payload['wa_video_url']
            )

            if response:
                sent += 1
                log_delivery(
                    event_id=event.event_id,
                    recipient=log.recipient,
                    status='SENT',
                    provider_message_id=response.get('messageId'),
                    details={
                        'retry_of': log.id,
                        'template_name': payload['template_name'],
                        'has_image': bool(payload['wa_image_url']),
                        'has_video': bool(payload['wa_video_url']),
                        'trigger': 'retry_failed_whatsapp',
                    }
                )
                _write(stdout, f"RETRY_SENT event={event.event_id} recipient={log.recipient} template={payload['template_name']}")
            else:
                log_delivery(
                    event_id=event.event_id,
                    recipient=log.recipient,
                    status='FAILED',
                    error_message='Retry returned no provider response',
                    details={
                        'retry_of': log.id,
                        'template_name': payload['template_name'],
                        'has_image': bool(payload['wa_image_url']),
                        'has_video': bool(payload['wa_video_url']),
                        'trigger': 'retry_failed_whatsapp',
                    }
                )
                _write(stdout, f"RETRY_FAILED event={event.event_id} recipient={log.recipient} reason=no_provider_response")
        except Exception as exc:
            log_delivery(
                event_id=event.event_id,
                recipient=log.recipient,
                status='FAILED',
                error_message=str(exc),
                details={
                    'retry_of': log.id,
                    'template_name': payload['template_name'],
                    'has_image': bool(payload['wa_image_url']),
                    'has_video': bool(payload['wa_video_url']),
                    'trigger': 'retry_failed_whatsapp',
                }
            )
            _write(stdout, f"RETRY_FAILED event={event.event_id} recipient={log.recipient} reason={exc}")

    _write(stdout, f"Completed WhatsApp retry scan. attempted={attempted} sent={sent} skipped={skipped} dry_run={dry_run}")
    return {
        'attempted': attempted,
        'sent': sent,
        'skipped': skipped,
        'inspected': len(failed_logs),
        'dry_run': dry_run,
    }
