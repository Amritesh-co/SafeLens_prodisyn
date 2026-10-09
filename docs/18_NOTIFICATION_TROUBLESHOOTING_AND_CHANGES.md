# Notification Troubleshooting & Recent Changes

This document helps operators diagnose why incidents are stored (DB/S3) but notifications are not delivered, and it records recent fixes made to the notification subsystem.

## 0) Summary of What We Did (May 22, 2026)

During the investigation we confirmed:
- Incidents were being inserted into DB and media was being uploaded to S3.
- Automatic notifications were not being triggered because the **background poller was not running** under systemd.
- Once the poller was started, **Email initially failed** due to missing environment/permissions. We fixed environment loading and then fixed IAM permissions for SES.
- After SES was allowed, Email started sending successfully and delivery logs showed `SENT` with SES message IDs.

We also found:
- SMS/WhatsApp delivery logs will not appear unless there are eligible phone recipients (users must have `phone_number` set and the relevant channel flags enabled).

### 0.1 Timeline (Services, `.env`, restarts)

What we set up / changed:
- Created and installed a dedicated poller service: `safelens-poll-events.service` (runs `manage.py poll_events`).
- Updated the poller service to load `/home/ubuntu/app/database-api/.env` using systemd `EnvironmentFile`.
- Updated the poller service to set `ENABLE_DB_INIT_ON_STARTUP=0` to suppress privileged DB role creation attempts at startup.
- Updated local helper scripts to start/stop the poller (`scripts/start_server.sh`, `scripts/stop_server.sh`).
- Added an installer script (`scripts/install_poll_events_systemd.sh`) to copy the unit into `/etc/systemd/system/` and enable it.

Operational restart sequence used on the server:
```bash
sudo systemctl daemon-reload
sudo systemctl restart safelens-poll-events.service
sudo systemctl status safelens-poll-events.service --no-pager
sudo journalctl -u safelens-poll-events.service -n 200 --no-pager
```

If you pull new code or change environment variables used by the API, also restart Gunicorn:
```bash
sudo systemctl restart safelens.service
```

## 1) Architecture (What Sends Notifications)

SafeLens has two independent pieces:

1. **API server (Gunicorn/Django)** – serves endpoints, including manual send:
   - `POST /api/notifications/send/`
2. **Background poller** – continuously checks for new rows in the unmanaged `events` table and dispatches Email/SMS/WhatsApp:
   - `./venv/bin/python manage.py poll_events`

If incidents are being stored but no automatic notifications occur, the poller is usually not running.

## 2) Where Logs Are

### 2.1 API (Gunicorn) logs
Configured in `gunicorn_config.py`:
- `/var/log/gunicorn/error.log`
- `/var/log/gunicorn/access.log`

Example:
```bash
sudo tail -n 200 /var/log/gunicorn/error.log
```

### 2.2 Poller logs
If running via systemd:
```bash
sudo journalctl -u safelens-poll-events.service -n 200 --no-pager
sudo journalctl -u safelens-poll-events.service -f
```

If running manually with `nohup`, output goes to the chosen file (commonly `poll_events.log`).

### 2.3 Delivery audit trail (DB)
The `notification_delivery_log` table records:
- `channel` (`EMAIL`, `SMS`, `WHATSAPP`)
- `status` (`SENT`, `FAILED`, `SKIPPED`)
- `error_message` (why it failed or was skipped)

Use Django admin: **API → Notification delivery logs**.

## 3) Common Causes When Email Fails But SMS Sends

Email uses **AWS SES** (`send_aws_email`), while SMS uses **AWS SNS** (`send_aws_sms`). They are configured and permissioned separately.

Most common reasons SES email fails:

- Missing `AWS_SES_SENDER` environment variable.
- SES is in **sandbox mode** (recipient emails must be verified).
- Sender identity not verified in SES (domain/email verification).
- Wrong SES region (set `AWS_SES_REGION_NAME` to the SES region).
- IAM user/role lacks SES permissions (`ses:SendRawEmail`).

### 3.1 The exact failure we hit

We observed an SES failure like:
- `AccessDenied ... not authorized to perform ses:SendRawEmail ...`

Fix:
- Add `ses:SendEmail` and `ses:SendRawEmail` permissions to the instance role used by EC2 (example role name seen: `safelens-ec2-codedeploy-role`).
- Ensure the SES identity (sender domain/email) is verified in the SES region being used.

## 4) Poller “Not Triggering” Even Though Events Exist

The poller only processes events where:
- `event_id > email_alert_tracker.last_event_id`

On first run (when `last_event_id == 0`), it sets `last_event_id` to the current latest event to avoid historical spam. To test delivery, create a new event *after* starting the poller.

## 5) Poller Service Setup (systemd)

### 5.1 Install / enable

From the server:
```bash
cd /home/ubuntu/app/database-api
./scripts/install_poll_events_systemd.sh
```

Or manually:
```bash
sudo cp -f /home/ubuntu/app/database-api/deploy/systemd/safelens-poll-events.service /etc/systemd/system/safelens-poll-events.service
sudo systemctl daemon-reload
sudo systemctl enable --now safelens-poll-events.service
```

### 5.2 Validate it’s running
```bash
ps aux | grep -E "manage.py poll_events" | grep -v grep
sudo systemctl status safelens-poll-events.service --no-pager
```

### 5.3 View recent poller output
```bash
sudo journalctl -u safelens-poll-events.service -n 200 --no-pager
```

### 5.4 Important env behavior

The poller unit file is configured to:
- Load `/home/ubuntu/app/database-api/.env` via `EnvironmentFile=...`
- Set `ENABLE_DB_INIT_ON_STARTUP=0` to avoid privileged role creation attempts on startup

Note: systemd `EnvironmentFile` expects `KEY=value` lines. If your `.env` uses `export KEY=value`, convert it to `KEY=value` so systemd can read it.

## 5) Recent Changes (May 22, 2026)

### 5.1 Auto-start the poller in local scripts
Updated:
- `scripts/start_server.sh` now starts `manage.py poll_events` (writes to `poll_events.log`).
- `scripts/stop_server.sh` now stops the poller process.

### 5.2 Added a systemd unit for the poller
Added:
- `deploy/systemd/safelens-poll-events.service`

Important details:
- Loads environment variables from `/home/ubuntu/app/database-api/.env` (AWS creds, SES sender, DB config, etc.).
- Sets `ENABLE_DB_INIT_ON_STARTUP=0` to avoid attempting privileged role creation at startup.

### 5.3 Added an installer helper
Added:
- `scripts/install_poll_events_systemd.sh`

This copies the unit file into `/etc/systemd/system/`, enables it, and prints status + logs.

### 5.4 Fixed documentation for the manual send endpoint
Updated:
- `docs/10_NOTIFICATION_ARCHITECTURE.md`
- `docs/NOTIFICATION_ARCHITECTURE.md`

Correct endpoint:
- `POST /api/notifications/send/`

### 5.5 Preserve real SES failure reasons
Updated:
- `api/utils.py` (`send_aws_email`)

Behavior change:
- Missing `AWS_SES_SENDER` now raises a clear error (so it appears in `notification_delivery_log.error_message`).
- SES `ClientError` is re-raised so the poller/manual endpoint records the real reason instead of a generic “no response”.

## 6) SMS / WhatsApp Not Appearing (No Delivery Logs)

If you only see `EMAIL` rows in `notification_delivery_log` and no `SMS`/`WHATSAPP` rows:

- This usually means **no eligible phone recipients were generated**.
- For each user to receive SMS/WhatsApp, they must have:
  - `UserProfile.phone_number` set (prefer E.164 like `+91xxxxxxxxxx`)
  - `alerts_sms=true` for SMS and/or `alerts_whatsapp=true` for WhatsApp
  - `User.is_active=true` (this is synced from `UserProfile.status == 'Active'`)
- Global switches must also be ON:
  - `EmailAlertTracker.is_sms_enabled=true`
  - `EmailAlertTracker.is_whatsapp_enabled=true`

To confirm quickly from poller output:
```bash
sudo journalctl -u safelens-poll-events.service -n 300 --no-pager | grep "Recipients:"
```
Look for `Recipients: Email(x), SMS(0), WA(0)` which indicates the recipient list is empty for phone channels.

## 7) Quick Checklist (Operator)

1. Confirm poller is running:
   - `ps aux | grep -E "manage.py poll_events" | grep -v grep`
   - `sudo systemctl status safelens-poll-events.service`
2. Confirm global switch is ON:
   - Admin → **Global Alert Settings** → `is_email_enabled`
3. Confirm recipients exist:
   - Users have `email` set and `alerts_email=true`, or Admin → **Notification recipients**
4. Inspect failure reason:
   - Admin → **Notification delivery logs** → open failed EMAIL row and read `error_message`\n\n\n\n## 8) June 19, 2026: SQS Ingestion, Notification Upgrades & Bug Fixes

During the SQS worker migration and notification troubleshooting, we resolved several critical bugs related to SQS validation, background daemons, credentials caching, media path resolution, URL formatting, and file duplications.

### 8.1 SQS Ingestion & Consumer Daemon Integration

#### 1. SQS Consumer Validation Fix (`edge_id` validation)
* **Issue**: paylods submitted from the SQS queue or edge nodes containing null or blank `edge_id` failed serializer validation in `EventCreateSerializer`. This caused the SQS consumer to raise a `ValidationError`, halting queue processing and blocking event ingestion.
* **Fix**: Aligned the remote repository checkout with the latest commit on `origin/release/v1.0.0` branch. This pulled in the critical validation fix allowing events with null/blank `edge_id` to be successfully parsed and saved, resolving queue blockages.

#### 2. SQS Ingestion Daemon (`safelens-consume-sqs.service`)
* **Setup**: Created and enabled a systemd service file at `/etc/systemd/system/safelens-consume-sqs.service` to run the SQS consumer (`python manage.py consume_sqs`) continuously in the background.
* **Configuration**:
  ```ini
  [Unit]
  Description=SafeLensAI SQS consumer (consume_sqs)
  After=network.target

  [Service]
  Type=simple
  User=ubuntu
  WorkingDirectory=/home/ubuntu/safelensai-demo-platform/backend-api-server
  Environment=DJANGO_SETTINGS_MODULE=safelensai.settings
  Environment=SKIP_DB_INIT=1
  Environment=PYTHONUNBUFFERED=1
  EnvironmentFile=-/home/ubuntu/safelensai-demo-platform/backend-api-server/.env
  ExecStart=/home/ubuntu/safelensai-backend-api-server/venv/bin/python manage.py consume_sqs
  Restart=always
  RestartSec=5

  [Install]
  WantedBy=multi-user.target
  ```
* **Operations**:
  * Check status: `sudo systemctl status safelens-consume-sqs.service`
  * Check logs: `sudo journalctl -u safelens-consume-sqs.service -n 100 --no-pager`

### 8.2 Summary of Solved Issues & Fixes

#### 1. AWS Credentials Session Caching Conflict
* **Issue**: SQS and S3 clients require static `.env` keys (`safelens-s3-dev-user`), while notifications (SES, SNS, SocialMessaging) require falling back to the EC2 Instance Profile IAM role (`safelens-ec2-codedeploy-role`). Standard `boto3` client initialization cached the static keys in the default session, leading to `AccessDenied` errors when sending notifications.
* **Fix**: Added `get_iam_boto3_client()` in `apps/api/utils.py` to temporarily pop static credentials from the environment and initialize a fresh `boto3.Session()` for SES, SNS, and SocialMessaging clients.

#### 2. Media Path Resolution for SQS Incidents (`s3://` URLs)
* **Issue**: Real incidents ingested from SQS store frame and video paths as raw `s3://<bucket>/<key>` URIs. The notification system previously failed to parse `s3://` URIs, resulting in `N/A` for images and videos.
* **Fix**: Added `resolve_media_path()` in `apps/api/utils.py`. If a media path starts with `s3://`, the resolver parses the bucket and key and dynamically generates a secure **7-day presigned S3 URL** using standard credentials.

#### 3. URL Shortening & Redirection Route
* **Issue**: S3 presigned URLs contain long query strings (signatures, credential keys, timestamps), cluttering notification messages.
* **Fix**:
  - Created a URL redirection endpoint `/api/media-redirect/<image|video>/<event_id>/` in `apps/api/views.py`. It resolves the event's path to the presigned S3 URL and redirects the browser (HTTP 302).
  - Set `PUBLIC_BASE_URL` in `.env` to `https://safelensai-api.prodisyn.com`.
  - Configured Email/WhatsApp text bodies to use clean, short redirection links:
    * **Image**: `https://safelensai-api.prodisyn.com/api/media-redirect/image/<id>/`
    * **Video**: `https://safelensai-api.prodisyn.com/api/media-redirect/video/<id>/`
  - WhatsApp media header cards and email attachments continue using the direct S3 presigned URLs for rich media rendering.

#### 4. Duplicate Code Cleanup in `poll_events.py`
* **Issue**: The poller file [poll_events.py] contained duplicated methods (`resolve_path`, `process_event`, `handle`, `log_processing_failure`) appended at the end of the file due to an earlier poor merge. Because Python executes top-to-bottom, the duplicate unpatched versions overrode our patched versions.
* **Fix**: Checked out a clean copy of the original branch and re-applied the patches cleanly, ensuring no duplication or indentation errors remained.

#### 5. Manual Sharing Email Attachments Resolution
* **Issue**: In `apps/api/views.py`, manual email notifications attempted to attach raw `s3://` paths directly, causing failure.
* **Fix**: Updated `SendNotificationView` to resolve storage paths to presigned S3 URLs before adding them to email attachments.

### 8.3 Summary of File Modifications

| File | Changes Made |
| :--- | :--- |
| **`apps/api/utils.py`** | <ul><li>Added `get_iam_boto3_client()` for credentials isolation.</li><li>Modified `get_boto3_client()` to route SES/SNS/SocialMessaging.</li><li>Added `resolve_media_path()` supporting S3, S3 URI, and local resolution.</li></ul> |
| **`apps/api/management/commands/poll_events.py`** | <ul><li>Restored file to clean version to remove duplicated methods.</li><li>Updated `resolve_path()` to use `resolve_media_path()`.</li><li>Formatted Email/WhatsApp messages to use short redirect links.</li></ul> |
| **`apps/api/views.py`** | <ul><li>Added `MediaRedirectView` class redirecting to resolved S3 presigned URLs.</li><li>Updated `media_public_url()` to use `resolve_media_path()`.</li><li>Updated `SendNotificationView` message formatting and attachments resolution.</li></ul> |
| **`apps/api/urls.py`** | <ul><li>Registered the `media-redirect/` URL route.</li></ul> |
| **`safelensai/settings.py`** | <ul><li>CORS Origin updates.</li></ul> |
| **`.env`** | <ul><li>Updated `PUBLIC_BASE_URL` to `https://safelensai-api.prodisyn.com`.</li></ul> |

---

## 9) Understanding Why Alerts/Notifications Are Skipped

When a new incident is created, the notification poller might decide to skip sending alerts. These are the rules and why they trigger a skip:

### 9.1 Stale Event Skipping (The Freshness Window)
* **Rule**: To prevent "alert fatigue" and spamming off-duty staff when the server restarts or catches up on SQS backlogs, the poller checks the event age:
  $$\text{Age} = \text{Current Time} - \text{Event Timestamp}$$
  If the age exceeds the maximum age threshold (configured via `ALERT_MAX_AGE_SECONDS`, default **120 seconds**), the event is skipped as **stale**.
* **Log Entry**: `Skipping stale CRITICAL incident <id> (<type>) age=<age>s max_age=120s`
* **Fix/Workaround**: Ensure that edge nodes or test scripts submit incidents in real-time. If simulating, set the timestamp to the current local time or omit it.

### 9.2 Location-Based Routing Skip
* **Rule**: Managers and recipients are registered to specific locations (e.g., `'shopfloor1'`). The system compares the camera location with the user's registered location (case-insensitive).
  * **Except**: Users with the `Admin` role or a blank/null location bypass this check and receive alerts for all locations.
* **Log Entry**: `No eligible active recipients (matching location) found for <id>.`
* **Fix/Case Study**: Verify that user profiles have the correct location string assigned, or are marked as `Admin` / wildcard location in Django Admin.
  * *Note on User Creation Timestamps*: If a user was recently created (e.g., user `Nivya` joined at `17:03:22` IST), they will naturally NOT receive alerts for historical incidents processed before their account existed (e.g. event `752` processed at `16:41:58` IST), even if location matching matches. For any events created *after* the account exists (e.g., event `766` created at `17:09:46` IST), notifications are successfully sent.

### 9.3 "Online Only" SMS/WhatsApp Restriction
* **Rule**: While emails are sent 24/7, SMS and WhatsApp messages are only sent to managers who are currently **online** (have an active session in `UserActivityLog` with `logout_time` being null).
* **Fix**: Log into the SafeLens Control Panel/Dashboard to mark the session as online.

### 9.4 Global Master Switches
* **Rule**: Checkbox toggles in `EmailAlertTracker` globally disable Email, SMS, or WhatsApp channels.
* **Fix**: Enable them in Django Admin under **Global Alert Settings**.
