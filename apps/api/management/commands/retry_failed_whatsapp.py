from django.core.management.base import BaseCommand

from apps.api.notification_retry import retry_failed_whatsapp_logs


class Command(BaseCommand):
    help = "Retry failed WhatsApp notification deliveries from notification_delivery_log."

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=50, help='Maximum failed rows to inspect')
        parser.add_argument('--hours', type=int, default=24, help='How far back to look for failed rows')
        parser.add_argument('--recipient', type=str, help='Retry for one recipient only')
        parser.add_argument('--event-id', type=int, help='Retry for one event only')
        parser.add_argument('--dry-run', action='store_true', help='Preview retries without sending')

    def handle(self, *args, **options):
        retry_failed_whatsapp_logs(
            limit=options['limit'],
            hours=options['hours'],
            recipient=options.get('recipient'),
            event_id=options.get('event_id'),
            dry_run=options['dry_run'],
            stdout=self.stdout,
        )
