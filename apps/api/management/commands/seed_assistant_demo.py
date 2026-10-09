"""
Seed a LOCAL database with demo data for trying the AI assistant.

    python manage.py seed_assistant_demo --admin admin

Creates a "Demo Tenant" with two locations, four cameras and ~60 days of
incidents, links the given admin user to the tenant, and creates a
location-scoped supervisor (demo_supervisor) to verify access scoping.
Refuses to run when DEPLOYMENT_MODE is not LOCAL.
"""

import random
from datetime import datetime, timedelta

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.api.models import (
    Camera, Event, EventReview, Location, Tenant, TenantCamera, TenantLocation,
    TenantUseCase, UserLocation, UserProfile,
)

EVENT_TYPES = [
    ('PPE_VIOLATION', 0.45),
    ('FALL_DETECTED', 0.15),
    ('INTRUSION_DETECTED', 0.25),
    ('UNATTENDED_OBJECT', 0.15),
]


class Command(BaseCommand):
    help = "Seed local demo data for the AI assistant (LOCAL deployments only)."

    def add_arguments(self, parser):
        parser.add_argument('--admin', default='admin', help='Existing username to link as tenant Admin')
        parser.add_argument('--days', type=int, default=60)
        parser.add_argument('--seed', type=int, default=42)

    @transaction.atomic
    def handle(self, *args, **opts):
        if settings.DEPLOYMENT_MODE != 'LOCAL':
            raise CommandError("Refusing to seed demo data outside DEPLOYMENT_MODE=LOCAL.")

        rng = random.Random(opts['seed'])
        tenant, _ = Tenant.objects.get_or_create(code='DEMO', defaults={'name': 'Demo Tenant'})

        for code, name in [('PPE_DETECTION', 'PPE Detection'), ('FALL_DETECTION', 'Fall Detection'),
                           ('INTRUSION_DETECTION', 'Intrusion Detection'), ('UNATTENDED_OBJECT', 'Unattended Object')]:
            TenantUseCase.objects.get_or_create(tenant=tenant, code=code, defaults={'name': name})

        sites = {}
        for code, name in [('DEMO-PUNE', 'Pune Plant'), ('DEMO-CHENNAI', 'Chennai Warehouse')]:
            loc, _ = Location.objects.get_or_create(code=code, defaults={'name': name, 'location_type': 'site'})
            tl, _ = TenantLocation.objects.get_or_create(tenant=tenant, location=loc)
            sites[code] = (loc, tl)

        cameras = []
        for code, name, site in [('DEMO-CAM-1', 'Pune Gate', 'DEMO-PUNE'), ('DEMO-CAM-2', 'Pune Assembly Line', 'DEMO-PUNE'),
                                 ('DEMO-CAM-3', 'Chennai Dock', 'DEMO-CHENNAI'), ('DEMO-CAM-4', 'Chennai Racks', 'DEMO-CHENNAI')]:
            cam, _ = Camera.objects.get_or_create(code=code, defaults={'name': name, 'location': sites[site][0]})
            TenantCamera.objects.get_or_create(camera=cam, defaults={'tenant': tenant})
            cameras.append(cam)

        created = 0
        if not Event.objects.filter(camera__in=cameras).exists():
            now = datetime.now()
            types, weights = zip(*EVENT_TYPES)
            for day in range(opts['days']):
                for _ in range(rng.randint(0, 6)):
                    ts = (now - timedelta(days=day)).replace(
                        hour=rng.randint(6, 21), minute=rng.randint(0, 59), second=rng.randint(0, 59), microsecond=0)
                    if ts > now:
                        ts -= timedelta(days=1)
                    ev = Event.objects.create(camera=rng.choice(cameras), event_type=rng.choices(types, weights)[0], timestamp=ts)
                    created += 1
                    if day > 2 and rng.random() < 0.7:
                        EventReview.objects.create(
                            event_id=ev.event_id,
                            status=rng.choices(['Closed', 'Rejected', 'Open'], [0.7, 0.15, 0.15])[0],
                            is_read=True,
                        )

        admin = User.objects.filter(username=opts['admin']).first()
        if admin:
            profile, _ = UserProfile.objects.get_or_create(user=admin)
            profile.tenant = tenant
            profile.role = 'Admin'
            profile.save()
        else:
            self.stdout.write(self.style.WARNING(f"User '{opts['admin']}' not found; skipped admin link."))

        sup, sup_created = User.objects.get_or_create(username='demo_supervisor')
        if sup_created:
            sup.set_password('DemoSupervisor#2026')
            sup.save()
        sp, _ = UserProfile.objects.get_or_create(user=sup)
        sp.tenant = tenant
        sp.role = 'Supervisor'
        sp.save()
        UserLocation.objects.get_or_create(user=sup, location=sites['DEMO-PUNE'][1])

        self.stdout.write(self.style.SUCCESS(
            f"Demo tenant ready: {len(cameras)} cameras, {created} new incidents. "
            f"demo_supervisor (password DemoSupervisor#2026) sees Pune Plant only."
        ))
