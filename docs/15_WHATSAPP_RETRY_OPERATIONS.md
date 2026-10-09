# WhatsApp Retry Operations

## Purpose

This guide explains how to run failed WhatsApp retries safely in production.

## Manual Retry

Run a dry-run first:

```bash
cd /home/ubuntu/P004-SafeLensAI-Demo/SafeLensAI/database-api
./venv/bin/python manage.py retry_failed_whatsapp --hours 24 --limit 20 --dry-run
```

Run a real retry:

```bash
cd /home/ubuntu/P004-SafeLensAI-Demo/SafeLensAI/database-api
./venv/bin/python manage.py retry_failed_whatsapp --hours 24 --limit 50
```

Retry a single event:

```bash
./venv/bin/python manage.py retry_failed_whatsapp --event-id 3823 --limit 20
```

Retry a single recipient:

```bash
./venv/bin/python manage.py retry_failed_whatsapp --recipient +917338595943 --hours 72
```

## API Trigger

Admin-only endpoint:

```text
POST /api/notifications/retry-whatsapp/
```

Example payload:

```json
{
  "hours": 24,
  "limit": 50,
  "dry_run": false
}
```

Optional fields:

- `recipient`
- `event_id`

## Automatic Scheduling with systemd

Files included:

- `deploy/systemd/safelens-whatsapp-retry.service`
- `deploy/systemd/safelens-whatsapp-retry.timer`

Install:

```bash
sudo cp deploy/systemd/safelens-whatsapp-retry.service /etc/systemd/system/
sudo cp deploy/systemd/safelens-whatsapp-retry.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now safelens-whatsapp-retry.timer
```

Check status:

```bash
sudo systemctl status safelens-whatsapp-retry.timer
sudo systemctl list-timers | grep safelens-whatsapp-retry
```

Run the service once manually:

```bash
sudo systemctl start safelens-whatsapp-retry.service
```

## Safety Notes

- retries only target `FAILED` WhatsApp logs
- retries skip records that already have a newer `SENT` row
- limit is capped in the API to avoid heavy runs
- use `dry_run` before enabling automation
