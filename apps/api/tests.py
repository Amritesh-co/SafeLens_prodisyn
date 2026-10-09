from django.contrib.auth.models import User
from django.test import TestCase

from apps.api.views import SendNotificationView


class SendNotificationViewDiagnosticsTests(TestCase):
    def setUp(self):
        self.view = SendNotificationView()

    def create_user(self, username, email, role='Manager', location='shopfloor1', phone='9876543210',
                    alerts_email=True, alerts_sms=False, alerts_whatsapp=False, is_staff=False):
        user = User.objects.create_user(
            username=username,
            email=email,
            password='password123',
            is_staff=is_staff,
            is_superuser=(role == 'Admin'),
            is_active=True,
        )
        profile = user.profile
        profile.role = role
        profile.location = location
        profile.phone_number = phone
        profile.alerts_email = alerts_email
        profile.alerts_sms = alerts_sms
        profile.alerts_whatsapp = alerts_whatsapp
        profile.save()
        return user

    def test_collect_recipients_and_diagnostics_reports_whatsapp_skip_reasons(self):
        eligible_user = self.create_user(
            username='eligible',
            email='eligible@gmail.com',
            role='Manager',
            location='shopfloor1',
            phone='9876543210',
            alerts_whatsapp=True,
        )
        no_phone_user = self.create_user(
            username='no-phone',
            email='nophone@gmail.com',
            role='Manager',
            location='shopfloor1',
            phone='',
            alerts_whatsapp=True,
        )
        toggle_off_user = self.create_user(
            username='toggle-off',
            email='toggleoff@gmail.com',
            role='Manager',
            location='shopfloor1',
            phone='9123456789',
            alerts_whatsapp=False,
        )
        location_mismatch_user = self.create_user(
            username='other-location',
            email='otherlocation@gmail.com',
            role='Manager',
            location='shopfloor2',
            phone='9234567890',
            alerts_whatsapp=True,
        )

        data = self.view.collect_recipients_and_diagnostics(
            active_users=User.objects.filter(
                id__in=[
                    eligible_user.id,
                    no_phone_user.id,
                    toggle_off_user.id,
                    location_mismatch_user.id,
                ]
            ).order_by('id'),
            camera_location='shopfloor1',
            global_email_enabled=True,
            global_sms_enabled=True,
            global_whatsapp_enabled=True,
        )

        self.assertEqual(data['whatsapp_recipients'], ['+919876543210'])
        self.assertEqual(data['whatsapp_diagnostics']['eligible_user_count'], 1)
        self.assertEqual(data['whatsapp_diagnostics']['skipped_user_count'], 3)

        skipped_by_username = {
            entry['username']: entry
            for entry in data['whatsapp_diagnostics']['skipped_users']
        }
        self.assertEqual(skipped_by_username['no-phone']['reason_codes'], ['phone_missing'])
        self.assertEqual(skipped_by_username['toggle-off']['reason_codes'], ['user_whatsapp_disabled'])
        self.assertEqual(skipped_by_username['other-location']['reason_codes'], ['location_mismatch'])
