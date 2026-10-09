"""
Load real snapshot images into the LOCAL demo data as incidents with frames.

    python manage.py seed_snapshot_demo --dir /Users/ignite/Developer/Safelens/Docs

For each known image it copies the file into SYSTEM_STORAGE_DIR/incidents/images/,
creates an incident at the timestamp shown in the image overlay, a media.frames row
and a media.event_media_map FRAME link. Idempotent. LOCAL deployments only.
"""

import os
import shutil
from datetime import datetime

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.api.models import (
    Camera, Event, EventMediaMap, EventReview, Frame, Location, Tenant, TenantCamera,
    TenantLocation, TenantUseCase,
)

# filename -> (event_type, overlay timestamp, camera code, review status)
SNAPSHOTS = {
    'intrusion_video_image_dRRbZW_1791275588.jpg': ('INTRUSION_DETECTED', '2026-10-01 14:03:52', 'DEMO-OFFICE-CAM1', 'Open'),
    'absence_image_9rTTKh_1791278174.jpg': ('WORKER_ABSENCE', '2026-10-01 14:47:01', 'DEMO-OFFICE-CAM1', 'Open'),
    'absence_image_mpSnMR_1791278221.jpg': ('WORKER_ABSENCE', '2026-10-01 14:47:49', 'DEMO-OFFICE-CAM1', 'Closed'),
    'absence_image_MsI7gD_1791369339.jpg': ('WORKER_ABSENCE', '2026-10-07 16:05:36', 'DEMO-FACTORY-CAM1', 'Open'),
}


class Command(BaseCommand):
    help = "Attach real snapshot images to local demo incidents (LOCAL deployments only)."

    def add_arguments(self, parser):
        parser.add_argument('--dir', required=True, help='Folder containing the snapshot .jpg files')

    @transaction.atomic
    def handle(self, *args, **opts):
        if settings.DEPLOYMENT_MODE != 'LOCAL':
            raise CommandError("Refusing to seed demo data outside DEPLOYMENT_MODE=LOCAL.")

        src_dir = opts['dir']
        storage = os.path.abspath(os.environ.get('SYSTEM_STORAGE_DIR') or os.path.join(settings.BASE_DIR, '..', 'storage'))
        dest_dir = os.path.join(storage, 'incidents', 'images', 'demo')
        os.makedirs(dest_dir, exist_ok=True)

        tenant = Tenant.objects.filter(code='DEMO').first()
        if not tenant:
            raise CommandError("Run `python manage.py seed_assistant_demo` first.")
        TenantUseCase.objects.get_or_create(tenant=tenant, code='WORKER_ABSENCE', defaults={'name': 'Worker Absence'})

        office, _ = Location.objects.get_or_create(code='DEMO-OFFICE', defaults={'name': 'Prodisyn Office', 'location_type': 'office'})
        TenantLocation.objects.get_or_create(tenant=tenant, location=office)
        pune = Location.objects.get(code='DEMO-PUNE')

        cameras = {}
        for code, name, loc in [('DEMO-OFFICE-CAM1', 'Office Camera1', office), ('DEMO-FACTORY-CAM1', 'Pune Machine Shop', pune)]:
            cam, _ = Camera.objects.get_or_create(code=code, defaults={'name': name, 'location': loc})
            TenantCamera.objects.get_or_create(camera=cam, defaults={'tenant': tenant})
            cameras[code] = cam

        for filename, (event_type, ts, cam_code, status) in SNAPSHOTS.items():
            src = os.path.join(src_dir, filename)
            if not os.path.isfile(src):
                self.stdout.write(self.style.WARNING(f"Missing {filename}; skipped"))
                continue
            dest = os.path.join(dest_dir, filename)
            shutil.copy2(src, dest)

            frame = Frame.objects.filter(storage_path=dest).first()
            if frame and EventMediaMap.objects.filter(media_type='FRAME', media_id=frame.frame_id).exists():
                self.stdout.write(f"  {filename}: already loaded")
                continue
            frame = frame or Frame.objects.create(storage_path=dest)

            event = Event.objects.create(
                camera=cameras[cam_code], event_type=event_type,
                timestamp=datetime.strptime(ts, '%Y-%m-%d %H:%M:%S'),
            )
            EventMediaMap.objects.create(event_id=event.event_id, media_type='FRAME', media_id=frame.frame_id)
            EventReview.objects.create(event_id=event.event_id, status=status)
            self.stdout.write(f"  {filename}: incident {event.event_id} ({event_type}, {ts}, {cameras[cam_code].name})")

        self.stdout.write(self.style.SUCCESS(f"Snapshots stored in {dest_dir}"))
