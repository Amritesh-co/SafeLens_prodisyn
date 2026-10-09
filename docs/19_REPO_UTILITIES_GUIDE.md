# Repo Utilities Guide (Scripts, Tests, SQL)

This repo contains a mix of **production/ops utilities**, **diagnostics**, and **one-off developer test scripts**. This document helps you quickly decide what’s safe/useful and when to run it.

## 1) Quick Rules of Thumb

- If it runs `manage.py` and uses Django models, it needs the correct `DJANGO_SETTINGS_MODULE` and DB connectivity.
- Prefer **systemd services** for long-running processes (API + poller). Avoid `nohup` for production.
- Treat scripts with **hard-coded IPs/paths/credentials** as *developer-only*; update them before using.
- SQL files in `database/` are potentially destructive; run only if you know which environment you’re targeting.

## 2) Ops / Production-Useful

These are the scripts you’ll typically use on servers.

- `scripts/install_poll_events_systemd.sh`
  - **Use when:** You need to install/enable the notification poller systemd service.
  - **What it does:** Copies `deploy/systemd/safelens-poll-events.service` into `/etc/systemd/system/`, reloads systemd, enables + starts the service, prints status/log tail.

- `deploy/systemd/safelens-poll-events.service`
  - **Use when:** You want the background poller to run continuously under systemd.
  - **Notes:** Loads `/home/ubuntu/app/database-api/.env` via `EnvironmentFile` and sets `ENABLE_DB_INIT_ON_STARTUP=0`.

- `scripts/start_server.sh`
  - **Use when:** Quick local/dev start (runserver + poller).
  - **What it does:** Runs migrations, starts `manage.py runserver`, starts `manage.py poll_events` with `nohup`.
  - **Notes:** Not recommended for production; use systemd + gunicorn.

- `scripts/stop_server.sh`
  - **Use when:** Stop dev processes started via `runserver`/`gunicorn` and the `poll_events` process.
  - **Notes:** Uses `pkill` (broad); use carefully on shared hosts.

- `scripts/validate.sh`
  - **Use when:** Basic “is the app responding” check on `http://localhost:8000`.

- `gunicorn_config.py`
  - **Use when:** Understanding where gunicorn logs go (`/var/log/gunicorn/access.log`, `/var/log/gunicorn/error.log`).

- `manage.py`
  - **Use when:** Running Django management commands (migrations, poller, retry jobs, tests, etc.).

## 3) Notification / Channel Testing (Good for Debugging)

These help validate AWS/SMS/WhatsApp/email wiring without needing a real camera feed.

- `scripts/test_aws_notifications.py`
  - **Use when:** You want to directly test AWS SES/SNS/WhatsApp functions from `api/utils.py`.
  - **How:** `./venv/bin/python scripts/test_aws_notifications.py --email you@x.com --phone +91... --all`

- `scripts/inject_test_incident.py`
  - **Use when:** You want a full end-to-end test: insert a fake incident into DB + trigger the full notification pipeline.
  - **Notes:** Supports `--dry-run`, `--keep`, `--loop`.

- `scripts/manual_test_alert.py`
  - **Use when:** You want to re-run the poller-like routing logic on the **most recent** event, typically targeting the `admin` profile.
  - **Notes:** Mentions Twilio; this may not reflect current AWS-based SMS/WhatsApp behavior.

## 4) Simulators (Developer / Demo)

These scripts simulate the “edge/camera → gateway API” flow by POSTing media + metadata to `/api/events/`.

- `scripts/simulate_ai_incident.py`
- `scripts/simulate_cloud_incident.py`
- `scripts/simulate_unattended.py`
- `scripts/refined_cloud_sync.py`

**Use when:** You want to generate incidents without real cameras (demo/testing).

**Notes:** Several include hard-coded URLs/paths; review and update before using.

## 5) Diagnostics / Data Inspection

Useful for confirming what’s in DB and how media paths map.

- `scripts/check_recent_incidents.py`
  - **Use when:** You want a quick dump of latest incidents + their mapped frame/clip storage paths/URLs.

- `scripts/check_frames.py`
  - **Use when:** You want to inspect a few `Frame` rows and `EventMediaMap` entries.

- `verify_media.py`
  - **Use when:** Verifying media path validity / availability (local/S3 mapping).

- `fix_remote_paths.py`
  - **Use when:** Repairing/normalizing stored media paths (often after moving storage directories).
  - **Notes:** Review carefully; path rewriting is risky.

- `diag_review.py`
  - **Use when:** Small/one-off diagnostic helper (read the file before use).

## 6) DB / Auth Helpers

- `scripts/create_superuser.py`
  - **Use when:** Bootstrapping an `admin` superuser in a new environment.
  - **Warning:** Uses a weak default password (`admin`); change immediately.

- `scripts/get_token.py`
  - **Use when:** Getting/creating a DRF auth token for `admin`.

- `scripts/sql_shell.py`
  - **Use when:** Running quick queries against a local `db.sqlite3`.
  - **Warning:** This does **not** query Postgres/RDS; it’s for local sqlite only.

## 7) Migrations / Data Moves (Use With Extreme Care)

These can be destructive and/or environment-specific.

- `scripts/migrate_to_rds.py`
  - **Use when:** Migrating from sqlite to Postgres (RDS).
  - **Notes:** Requires RDS env vars; read the script before running.

- `scripts/migrate_to_s3.py`
  - **Use when:** Bulk media migration to S3.
  - **Warning:** Contains hard-coded DB/S3 configuration patterns; verify before use.

- `scripts/worker_safety_export.sql`
  - **Use when:** Importing/restoring a database export.
  - **Warning:** Large and potentially destructive; run only against the intended DB.

## 8) Tests (Repo-level)

There are two kinds of tests here:

### 8.1 Django-style tests
- `tests/test_imports.py`
- `tests/test_logout.py`
- `tests/test_serializer.py`
- `tests/test_toggles.py`
- `tests/test_twilio.py`

**Use when:** You can run `./venv/bin/python manage.py test` in an environment where the DB is reachable and configured.

**Note:** Some tests reference Twilio (legacy path). Current production notifications are AWS-based, so treat Twilio tests as historical unless you still use Twilio.

### 8.2 Ad-hoc root tests
- `test_api.py`
- `test_serializer.py`
- `test_serializer_get.py`
- `api/tests.py` (diagnostics-style test case)

**Use when:** Quick sanity checks during development. These are not a full CI suite.

## 9) SQL Files (`database/`)

- `database/create_schema.sql`
- `database/17_LOCAL_DB_CREATE_SCHEMA.sql`
- `database/18_PRODUCTION_SCHEMA.sql`
- `database/19_PRODUCTION_SCHEMA_FIX.sql`
- `database/production_schema.sql`
- `database/fix_production_schema.sql`

**Use when:** You need to create or repair DB schema manually.

**Warning:** These may be destructive and may not match your current DB state. Prefer Django migrations when possible; use these only when you know exactly what you’re applying.

## 10) Legacy / Unsafe by Default (Review Before Running)

These are commonly “developer scratchpad” scripts that should not be used as-is in production:

- `scripts/pure_twilio.py` (hard-coded Twilio credentials / phone numbers)
- `scripts/add_test_video.py` (hard-coded paths and event IDs)
- `scripts/check_api.py` (hard-coded LAN IP and dates)

If you want, I can also:
- mark legacy scripts clearly in their headers, or
- move “unsafe” scripts into a `scripts/legacy/` folder (requires agreement because it changes paths/imports).

