"""
File Name: inject_test_incident.py
Description:
    End-to-end notification test script for SafeLensAI.
    Injects a FAKE safety incident into the database (Events, EventDetection,
    Frame, EventMediaMap tables) and immediately fires the full notification
    pipeline (Email, SMS, WhatsApp) — just like poll_events.py would.

    After the test, it CLEANS UP the injected records automatically so the
    DB remains unchanged (unless you pass --keep to retain them for UI review).

Usage (from database-api/ directory):
    python inject_test_incident.py --type PPE_VIOLATION --subtype VEST
    python inject_test_incident.py --type FALL_DETECTED
    python inject_test_incident.py --type INTRUSION_DETECTED
    python inject_test_incident.py --type PPE_VIOLATION --subtype HELMET --keep
    python inject_test_incident.py --dry-run       # shows what would be sent, no DB write
    python inject_test_incident.py --loop          # inject every 60 seconds continuously
    python inject_test_incident.py --loop --interval 30  # inject every 30 seconds
    python inject_test_incident.py --notify-all    # bypass location filtering (test all users)

Options:
    --type        : Incident type [PPE_VIOLATION | FALL_DETECTED | INTRUSION_DETECTED] (default: PPE_VIOLATION)
    --subtype     : VEST | HELMET (only applies to PPE_VIOLATION, default: VEST)
    --camera-id   : Camera ID to associate with (default: 1 = camera_1 / shopfloor1)
    --keep        : Do NOT delete the injected records after sending (useful for UI testing)
    --dry-run     : Resolve recipients and print the message, but DO NOT inject into DB or send
    --loop        : Run continuously, injecting a new incident on every interval
    --interval    : Seconds between injections when --loop is used (default: 60)
    --notify-all  : Notify ALL active users regardless of location (useful when testing)

Author: SafeLensAI Dev Team
"""

import os
import sys
import argparse
import django
from datetime import datetime

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'safelensai.settings')
django.setup()

# ── Django imports (after setup) ──────────────────────────────────────────────
from django.utils import timezone
from django.core.mail import EmailMessage
from django.conf import settings
from django.contrib.auth.models import User
from apps.api.models import (
    Event, Camera, EventDetection, DetectionModel,
    Frame, EventMediaMap, EventReview,
    EmailAlertTracker, NotificationRecipient, UserProfile
)

try:
    from twilio.rest import Client as TwilioClient
except ImportError:
    TwilioClient = None

# ── Colour helpers ─────────────────────────────────────────────────────────────
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

def ok(msg):   print(f"{GREEN}  ✅ {msg}{RESET}")
def warn(msg): print(f"{YELLOW}  ⚠️  {msg}{RESET}")
def err(msg):  print(f"{RED}  ❌ {msg}{RESET}")
def info(msg): print(f"{CYAN}  ℹ️  {msg}{RESET}")
def hdr(msg):  print(f"\n{BOLD}{msg}{RESET}")

# ── Argument Parsing ───────────────────────────────────────────────────────────
def parse_args():
    p = argparse.ArgumentParser(description="SafeLensAI notification test injector")
    p.add_argument("--type",        default="PPE_VIOLATION",
                   choices=["PPE_VIOLATION", "FALL_DETECTED", "INTRUSION_DETECTED"],
                   help="Type of incident to inject")
    p.add_argument("--subtype",     default="VEST",
                   choices=["VEST", "HELMET"],
                   help="PPE sub-type (only used when --type=PPE_VIOLATION)")
    p.add_argument("--camera-id",   type=int, default=1,
                   help="Camera ID to link the event to (default: 1)")
    p.add_argument("--keep",        action="store_true",
                   help="Keep injected records in DB after test (useful for UI review)")
    p.add_argument("--dry-run",     action="store_true",
                   help="Build message & resolve recipients, but skip DB write and sending")
    p.add_argument("--loop",        action="store_true",
                   help="Run continuously — inject + notify on every interval (Ctrl+C to stop)")
    p.add_argument("--interval",    type=int, default=60,
                   help="Seconds between injections in --loop mode (default: 60)")
    p.add_argument("--notify-all",  action="store_true",
                   help="Notify ALL active users regardless of location (bypass location routing)")
    return p.parse_args()


# ── Helper: build friendly incident label ─────────────────────────────────────
INCIDENT_LABELS = {
    "PPE_VIOLATION":      {"VEST": "No Safety Vest", "HELMET": "No Hard Hat"},
    "FALL_DETECTED":      {"": "Fall Detected"},
    "INTRUSION_DETECTED": {"": "Intrusion Detected"},
}

def get_label(event_type, subtype):
    inner = INCIDENT_LABELS.get(event_type, {})
    return inner.get(subtype, inner.get("", event_type))


# ── Step 1: Inject fake incident rows ─────────────────────────────────────────
def inject_incident(camera, event_type, subtype, dry_run):
    """
    Inserts into: events → events_detections → frames → clips → event_media_map
    Returns (event, frame, clip_path) for later cleanup.
    If dry_run=True, returns (None, None, None) without writing.
    """
    hdr("─── Step 1: Injecting Fake Incident ───")

    if dry_run:
        warn("DRY-RUN: No DB writes will happen.")
        return None, None, None

    now = timezone.now()
    from django.db import connection

    # 1a. Create the Event row
    with connection.cursor() as cur:
        cur.execute(
            "INSERT INTO events (camera_id, event_type, timestamp) VALUES (%s, %s, %s) RETURNING event_id",
            [camera.camera_id, event_type, now]
        )
        event_id = cur.fetchone()[0]

    info(f"Inserted event_id={event_id}  event_type={event_type}  camera={camera.name}  time={now.strftime('%H:%M:%S')}")

    # 1b. Create EventDetection row
    det_model, _ = DetectionModel.objects.get_or_create(
        model_name="TEST_MODEL", defaults={"model_version": "test"}
    )
    det_type = ("VEST" if subtype == "VEST" else "HELMET") if event_type == "PPE_VIOLATION" else event_type
    with connection.cursor() as cur:
        cur.execute(
            """INSERT INTO events_detections (event_id, model_id, detection_type, detection_value, detection_details)
               VALUES (%s, %s, %s, %s, %s)""",
            [event_id, det_model.model_id, det_type,
             "detected=false|violation=true",
             '{"source": "inject_test_incident.py"}']
        )
    info(f"Inserted detection: detection_type={det_type}")

    # 1c. Resolve storage base from config.json (matching manage.sh logic)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(script_dir, "..", ".."))
    
    # 1. Try environment variable
    storage_base = os.environ.get('SYSTEM_STORAGE_DIR')
    
    # 2. Try config.json if Env not set
    if not storage_base:
        try:
            config_path = os.path.join(project_root, "config.json")
            with open(config_path, "r") as f:
                import json
                config = json.load(f)
                storage_dir_rel = config.get("system", {}).get("storage_dir", "storage")
                # Handle relative or absolute in config
                if os.path.isabs(storage_dir_rel):
                    storage_base = storage_dir_rel
                else:
                    storage_base = os.path.join(project_root, storage_dir_rel)
        except Exception:
            # 3. Last resort fallback
            storage_base = os.path.join(project_root, "storage")

    info(f"Using storage_base: {storage_base}")
    
    # 1d. Create folders following SafeLens standard naming
    type_folder = event_type.replace('_', ' ').capitalize().replace(' ', '_')
    subtype_folder = subtype.capitalize()
    
    base_dir = f"{storage_base}/incidents/images/ppe/{subtype_folder}/{camera.location or 'shopfloor1'}/{camera.name}/{now.strftime('%Y-%m-%d')}"
    os.makedirs(base_dir, exist_ok=True)
    fake_image_path = f"{base_dir}/TEST_{ts}.jpg"
    
    source_img = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'test_image_v2.jpg')
    import shutil
    if os.path.exists(source_img):
        shutil.copy(source_img, fake_image_path)
    else:
        with open(fake_image_path, 'wb') as f:
            f.write(bytes([
                0xFF,0xD8,0xFF,0xE0,0x00,0x10,0x4A,0x46,0x49,0x46,0x00,0x01,0x01,0x01,0x00,0x48,
                0x00,0x48,0x00,0x00,0xFF,0xDB,0x00,0x43,0x00,0x08,0x06,0x06,0x07,0x06,0x05,0x08,
                0x07,0x07,0x07,0x09,0x09,0x08,0x0A,0x0C,0x14,0x0D,0x0C,0x0B,0x0B,0x0C,0x19,0x12,
                0x13,0x0F,0x14,0x1D,0x1A,0x1F,0x1E,0x1D,0x1A,0x1C,0x1C,0x20,0x24,0x2E,0x27,0x20,
                0x22,0x2C,0x23,0x1C,0x1C,0x28,0x37,0x29,0x2C,0x30,0x31,0x34,0x34,0x34,0x1F,0x27,
                0x39,0x3D,0x38,0x32,0x3C,0x2E,0x33,0x34,0x32,0xFF,0xDB,0x00,0x43,0x01,0x09,0x09,
                0x09,0x0C,0x0B,0x0C,0x18,0x0D,0x0D,0x18,0x32,0x21,0x1C,0x21,0x32,0x32,0x32,0x32,
                0x32,0x32,0x32,0x32,0x32,0x32,0x32,0x32,0x32,0x32,0x32,0x32,0x32,0x32,0x32,0x32,
                0x32,0x32,0x32,0x32,0x32,0x32,0x32,0x32,0x32,0x32,0x32,0x32,0x32,0x32,0x32,0x32,
                0x32,0x32,0x32,0x32,0x32,0x32,0x32,0x32,0x32,0x32,0x32,0x32,0x32,0x32,0xFF,0xC0,
                0x00,0x11,0x08,0x00,0x01,0x00,0x02,0x03,0x01,0x22,0x00,0x02,0x11,0x01,0x03,0x11,
                0x01,0xFF,0xC4,0x00,0x15,0x00,0x01,0x01,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,
                0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x08,0xFF,0xC4,0x00,0x14,0x10,0x01,0x00,0x00,
                0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0xFF,0xC4,
                0x00,0x14,0x01,0x01,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,
                0x00,0x00,0x00,0x00,0xFF,0xC4,0x00,0x14,0x11,0x01,0x00,0x00,0x00,0x00,0x00,0x00,
                0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0xFF,0xDA,0x00,0x0C,0x03,0x01,
                0x00,0x02,0x11,0x03,0x11,0x00,0x3F,0x00,0xA0,0x00,0xFF,0xD9
            ]))
    info(f"Created placeholder image: {fake_image_path}")

    with connection.cursor() as cur:
        cur.execute("INSERT INTO frames (storage_path) VALUES (%s) RETURNING frame_id", [fake_image_path])
        frame_id = cur.fetchone()[0]
    with connection.cursor() as cur:
        cur.execute("INSERT INTO event_media_map (event_id, media_type, media_id) VALUES (%s, %s, %s)",
                    [event_id, 'FRAME', frame_id])
    info(f"Inserted frame_id={frame_id} → event_media_map (FRAME)")

    # 1e. Create placeholder MP4 video clip (minimal valid MP4 ftyp box)
    fake_video_path = f"{base_dir}/TEST_{ts}.mp4"
    with open(fake_video_path, 'wb') as f:
        # Minimal ftyp box: 'ftypisom' — just enough to be a recognisable MP4 container
        ftyp = (
            b'\x00\x00\x00\x14'  # box size = 20 bytes
            b'ftyp'              # box type
            b'isom'              # major brand
            b'\x00\x00\x02\x00' # minor version
            b'isom'              # compatible brand
        )
        f.write(ftyp)
    info(f"Created placeholder video: {fake_video_path}")

    with connection.cursor() as cur:
        cur.execute("INSERT INTO clips (storage_path) VALUES (%s) RETURNING clip_id", [fake_video_path])
        clip_id = cur.fetchone()[0]
    with connection.cursor() as cur:
        cur.execute("INSERT INTO event_media_map (event_id, media_type, media_id) VALUES (%s, %s, %s)",
                    [event_id, 'CLIP', clip_id])
    info(f"Inserted clip_id={clip_id} → event_media_map (CLIP)")

    event = Event.objects.get(event_id=event_id)
    frame = Frame.objects.get(frame_id=frame_id)

    ok(f"Injected test incident: event_id={event_id}  type={event_type}  sub={subtype or 'N/A'}")
    return event, frame, fake_video_path


# ── Step 2: Resolve notification recipients ────────────────────────────────────
def resolve_recipients(event, camera_location, dry_run, notify_all=False):
    hdr("─── Step 2: Resolving Notification Recipients ───")

    if notify_all:
        warn("--notify-all active: location filtering bypassed.")

    email_list    = []
    sms_list      = []
    whatsapp_list = []

    # Custom external recipients (email only)
    custom = list(NotificationRecipient.objects.filter(is_active=True).values_list('email', flat=True))
    email_list.extend(custom)
    if custom:
        info(f"Custom external recipients: {custom}")

    active_users = User.objects.filter(is_active=True).distinct()
    for user in active_users:
        try:
            profile = user.profile
            notify = False
            reason = ""
            if notify_all:
                notify = True; reason = "--notify-all flag"
            elif profile.role == 'Admin':
                notify = True; reason = "Admin (gets all)"
            elif not profile.location:
                notify = True; reason = "No location set (gets all)"
            elif profile.location and camera_location:
                # Loose match: 'Shopfloor' matches 'shopfloor1', 'shopfloor1' etc.
                ul = profile.location.lower().strip()
                cl = camera_location.lower().strip()
                if ul == cl or cl.startswith(ul) or ul.startswith(cl):
                    notify = True; reason = f"Location match ({profile.location} ≈ {camera_location})"

            if notify:
                tag = f"{user.username} [{reason}]"
                if profile.alerts_email and user.email:
                    email_list.append(user.email)
                    info(f"  📧 Email → {user.email}  ({tag})")
                if profile.phone_number:
                    phone = profile.phone_number.strip()
                    if not phone.startswith('+'): phone = '+91' + phone if len(phone) == 10 else '+' + phone
                    if profile.alerts_sms:
                        sms_list.append(phone)
                        info(f"  📱 SMS → {phone}  ({tag})")
                    if profile.alerts_whatsapp:
                        whatsapp_list.append(phone)
                        info(f"  💬 WhatsApp → {phone}  ({tag})")
            else:
                info(f"  ⏭  Skipped {user.username} (location '{profile.location}' ≠ '{camera_location}')")
        except Exception as e:
            warn(f"Could not read profile for {user.username}: {e}")

    email_list    = list(set(email_list))
    sms_list      = list(set(sms_list))
    whatsapp_list = list(set(whatsapp_list))

    if not email_list and not sms_list and not whatsapp_list:
        warn("No eligible recipients found! Try running with --notify-all to bypass location filtering.")
    else:
        ok(f"Total → Emails: {len(email_list)}  SMS: {len(sms_list)}  WhatsApp: {len(whatsapp_list)}")

    return email_list, sms_list, whatsapp_list


# ── Step 3: Send notifications ─────────────────────────────────────────────────
def send_notifications(event, camera_name, camera_location, event_type, subtype,
                       email_list, sms_list, whatsapp_list, frame, video_path, dry_run):
    hdr("─── Step 3: Sending Notifications ───")

    tracker = EmailAlertTracker.objects.first()
    global_email     = tracker.is_email_enabled    if tracker else True
    global_sms       = tracker.is_sms_enabled      if tracker else False
    global_whatsapp  = tracker.is_whatsapp_enabled if tracker else False

    info(f"Global switches → Email:{global_email}  SMS:{global_sms}  WhatsApp:{global_whatsapp}")

    label   = get_label(event_type, subtype)
    ev_time = event.timestamp.strftime('%Y-%m-%d %H:%M:%S') if event else datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    ev_id   = event.event_id if event else "DRY-RUN"

    subject = f"🛑 [TEST] SAFETY ALERT: {label} at {camera_name}"
    body = (
        f"⚠️  THIS IS AN AUTOMATED NOTIFICATION TEST FROM SafeLensAI  ⚠️\n\n"
        f"A simulated safety incident has been injected for testing purposes.\n\n"
        f"📍 Location   : {camera_location}\n"
        f"📷 Camera     : {camera_name}\n"
        f"🕒 Time       : {ev_time}\n"
        f"⚠️  Incident   : {label}  ({event_type})\n"
        f"🆔 Event ID   : {ev_id}\n\n"
        f"If you received this, notifications are working correctly.\n"
        f"Log in to the SafeLens Dashboard to review and close this incident."
    )

    # SMS body must be < 160 chars to fit in a single segment (avoids error 30044 on Indian carriers)
    sms_body = f"[SafeLensAI TEST] {label} at {camera_name} ({camera_location}). Time: {ev_time}. Check dashboard."

    print(f"\n  Subject  : {subject}")
    print(f"  SMS Body : {sms_body}  [{len(sms_body)} chars]")
    print(f"  Body     :\n{body}\n")

    if dry_run:
        warn("DRY-RUN: Skipping all sends.")
        return

    # ── EMAIL (image + video attached) ────────────────────────────────────────
    if email_list and global_email:
        email = EmailMessage(
            subject=subject, body=body,
            from_email=settings.EMAIL_HOST_USER,
            to=email_list,
        )
        # Attach image
        if frame and frame.storage_path and os.path.isfile(frame.storage_path):
            try:
                with open(frame.storage_path, 'rb') as img:
                    email.attach(os.path.basename(frame.storage_path), img.read(), 'image/jpeg')
                info("📷 Image attached to email.")
            except Exception as e:
                warn(f"Could not attach image: {e}")
        # Attach video
        if video_path and os.path.isfile(video_path):
            try:
                with open(video_path, 'rb') as vid:
                    email.attach(os.path.basename(video_path), vid.read(), 'video/mp4')
                info("🎥 Video clip attached to email.")
            except Exception as e:
                warn(f"Could not attach video: {e}")
        try:
            email.send(fail_silently=False)
            ok(f"Email sent to {len(email_list)} recipient(s): {email_list}")
        except Exception as e:
            err(f"Email send failed: {e}")
    elif email_list and not global_email:
        warn("Email suppressed — Global Email Switch is OFF in Settings.")
    else:
        warn("No email recipients.")

    # ── SMS / WHATSAPP ─────────────────────────────────────────────────────────
    if TwilioClient is None:
        warn("twilio package not installed. Skipping SMS/WhatsApp.")
        return

    twilio_sid      = getattr(settings, 'TWILIO_ACCOUNT_SID',      os.environ.get('TWILIO_ACCOUNT_SID', ''))
    twilio_auth     = getattr(settings, 'TWILIO_AUTH_TOKEN',        os.environ.get('TWILIO_AUTH_TOKEN', ''))
    twilio_number   = getattr(settings, 'TWILIO_PHONE_NUMBER',      os.environ.get('TWILIO_PHONE_NUMBER', ''))
    twilio_whatsapp = getattr(settings, 'TWILIO_WHATSAPP_NUMBER',   os.environ.get('TWILIO_WHATSAPP_NUMBER', 'whatsapp:+14155238886'))
    public_base_url = getattr(settings, 'PUBLIC_BASE_URL',          os.environ.get('PUBLIC_BASE_URL', 'http://192.168.1.59:8000'))

    if not twilio_sid or not twilio_auth:
        warn("Twilio credentials not configured. Skipping SMS/WhatsApp.")
        return

    twilio = TwilioClient(twilio_sid, twilio_auth)

    # Build public media URL for WhatsApp image/video (Twilio needs a public URL, not a local path)
    wa_image_url = None
    wa_video_url = None
    
    # Resolve storage base for relative path generation
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(script_dir, "..", ".."))
    storage_base = os.environ.get('SYSTEM_STORAGE_DIR')
    if not storage_base:
        try:
            config_path = os.path.join(project_root, "config.json")
            with open(config_path, "r") as f:
                import json
                config = json.load(f)
                storage_dir_rel = config.get("system", {}).get("storage_dir", "storage")
                storage_base = os.path.abspath(os.path.join(project_root, storage_dir_rel))
        except Exception:
            storage_base = os.path.abspath(os.path.join(project_root, "storage"))

    if frame and frame.storage_path:
        try:
            # Ensure we're comparing normalized paths
            norm_path = os.path.normpath(frame.storage_path)
            norm_base = os.path.normpath(storage_base)
            
            if norm_path.startswith(norm_base):
                rel = os.path.relpath(norm_path, norm_base)
                wa_image_url = f"{public_base_url}/media/{rel}"
                info(f"WhatsApp image media_url: {wa_image_url}")
            else:
                # Fallback extraction if base mismatch
                if 'storage/' in norm_path:
                    rel = norm_path.split('storage/', 1)[-1]
                    wa_image_url = f"{public_base_url}/media/{rel}"
                elif 'incidents/' in norm_path:
                    rel = norm_path.split('incidents/', 1)[-1]
                    wa_image_url = f"{public_base_url}/media/incidents/{rel}"
        except Exception as e:
            warn(f"Failed to generate WhatsApp image URL: {e}")

    if video_path:
        try:
            norm_path = os.path.normpath(video_path)
            norm_base = os.path.normpath(storage_base)
            
            if norm_path.startswith(norm_base):
                rel_vid = os.path.relpath(norm_path, norm_base)
                wa_video_url = f"{public_base_url}/media/{rel_vid}"
                info(f"WhatsApp video link: {wa_video_url}")
            elif 'storage/' in norm_path:
                rel = norm_path.split('storage/', 1)[-1]
                wa_video_url = f"{public_base_url}/media/{rel}"
        except Exception as e:
            warn(f"Failed to generate WhatsApp video URL: {e}")

    # SMS
    if sms_list and global_sms:
        sent = 0
        for num in sms_list:
            try:
                # Use sms_body (concise) to avoid error 30044
                msg = twilio.messages.create(body=sms_body, from_=twilio_number, to=num)
                ok(f"SMS → {num}  (SID: {msg.sid})")
                sent += 1
            except Exception as e:
                err(f"SMS to {num} failed: {e}")
        if sent:
            ok(f"SMS dispatched to {sent}/{len(sms_list)} recipient(s).")
    elif sms_list and not global_sms:
        warn("SMS suppressed — Global SMS Switch is OFF in Settings.")
    else:
        warn("No SMS recipients (check user profiles: phone + SMS enabled).")

    # WhatsApp (image via media_url; video via clickable link)
    if whatsapp_list and global_whatsapp:
        sent = 0
        wa_body = body
        if wa_video_url:
            wa_body += f"\n\n🎥 Watch Video: {wa_video_url}"
            
        for num in whatsapp_list:
            wa = f"whatsapp:{num}" if not num.startswith("whatsapp:") else num
            try:
                kwargs = dict(body=wa_body, from_=twilio_whatsapp, to=wa)
                
                # Twilio is a cloud service and CANNOT reach local IPs like 192.168.x.x
                if wa_image_url:
                    is_local = any(x in wa_image_url for x in ['192.168.', '127.0.0.1', '10.', 'localhost'])
                    if not is_local:
                        kwargs['media_url'] = [wa_image_url]
                        info(f"  ℹ️  WhatsApp image attached (Public URL: {wa_image_url})")
                    else:
                        warn(f"  ⚠️  WhatsApp media skipped: Twilio cannot reach local IP {wa_image_url}")
                        warn("  ⚠️  To see images in WhatsApp, use a public IP or Ngrok/Tunnel.")

                msg = twilio.messages.create(**kwargs)
                ok(f"WhatsApp → {wa}  (SID: {msg.sid})")
                sent += 1
            except Exception as e:
                err(f"WhatsApp to {wa} failed: {e}")
        if sent:
            ok(f"WhatsApp dispatched to {sent}/{len(whatsapp_list)} recipient(s).")
            if video_path:
                info("ℹ️  Note: WhatsApp does not support video attachments via Twilio media_url directly.\n"
                     "        The video is attached to the email. For WhatsApp video, use Twilio Content Templates.")
    elif whatsapp_list and not global_whatsapp:
        warn("WhatsApp suppressed — Global WhatsApp Switch is OFF in Settings.")
    else:
        warn("No WhatsApp recipients (check user profiles: phone + WhatsApp enabled).")


# ── Step 4: Cleanup ─────────────────────────────────────────────────────────────
def cleanup(event, frame, dry_run, video_path=None):
    if dry_run or event is None:
        return
    hdr("─── Step 4: Cleanup ───")
    from django.db import connection
    try:
        with connection.cursor() as cur:
            cur.execute("DELETE FROM event_media_map WHERE event_id=%s", [event.event_id])
            cur.execute("DELETE FROM events_detections WHERE event_id=%s", [event.event_id])
        EventReview.objects.filter(event_id=event.event_id).delete()
        with connection.cursor() as cur:
            cur.execute("DELETE FROM events WHERE event_id=%s", [event.event_id])
        if frame:
            frame_path = frame.storage_path
            with connection.cursor() as cur:
                cur.execute("DELETE FROM frames WHERE frame_id=%s", [frame.frame_id])
            if frame_path and os.path.isfile(frame_path):
                os.remove(frame_path)
        # Clean up video clip too
        if video_path:
            with connection.cursor() as cur:
                cur.execute("DELETE FROM clips WHERE storage_path=%s", [video_path])
            if os.path.isfile(video_path):
                os.remove(video_path)
        ok(f"Cleaned up test event_id={event.event_id} from all tables.")
    except Exception as e:
        err(f"Cleanup failed: {e}")


# ── MAIN ───────────────────────────────────────────────────────────────────────
def run_once(args, camera):
    """Run a single inject → notify → cleanup cycle."""
    camera_location = camera.location or "Unknown Location"
    subtype = args.subtype if args.type == "PPE_VIOLATION" else ""

    event, frame, video_path = inject_incident(camera, args.type, subtype, args.dry_run)
    email_list, sms_list, whatsapp_list = resolve_recipients(
        event or type('_', (), {'event_id': 'DRY'})(), camera_location,
        args.dry_run, notify_all=args.notify_all
    )
    send_notifications(
        event, camera.name, camera_location,
        args.type, subtype,
        email_list, sms_list, whatsapp_list,
        frame, video_path, args.dry_run
    )
    if not args.keep:
        cleanup(event, frame, args.dry_run, video_path)
    else:
        if event:
            ok(f"Kept test event_id={event.event_id} in DB. Visit the dashboard to see it.")
            print(f"\n  {YELLOW}Remember to manually delete it later:{RESET}")
            print(f"  DELETE FROM events WHERE event_id={event.event_id};")


def main():
    import time as _time
    args = parse_args()
    print(f"\n{'='*60}")
    print(f"  {BOLD}SafeLensAI — Notification Injection Test{RESET}")
    print(f"{'='*60}")
    info(f"Mode      : {'DRY-RUN (no writes/sends)' if args.dry_run else 'LIVE'}")
    info(f"Type      : {args.type}")
    info(f"Sub-type  : {args.subtype if args.type == 'PPE_VIOLATION' else 'N/A'}")
    info(f"Camera ID : {args.camera_id}")
    info(f"Keep rows : {args.keep}")
    if args.loop:
        info(f"Loop mode : ON — injecting every {args.interval}s (Ctrl+C to stop)")

    # Resolve camera once
    try:
        camera = Camera.objects.get(camera_id=args.camera_id)
        info(f"Camera    : {camera.name}  (location: {camera.location or 'N/A'})")
    except Camera.DoesNotExist:
        err(f"Camera ID {args.camera_id} not found. Run with --camera-id <id>.")
        print("Available cameras:")
        for c in Camera.objects.all()[:10]:
            print(f"  id={c.camera_id}  name={c.name}  location={c.location}")
        sys.exit(1)

    if args.loop:
        iteration = 0
        try:
            while True:
                iteration += 1
                print(f"\n{BOLD}{'─'*60}")
                print(f"  Iteration #{iteration}  ({datetime.now().strftime('%H:%M:%S')}){RESET}")
                run_once(args, camera)
                print(f"\n  {CYAN}Next injection in {args.interval}s … (Ctrl+C to stop){RESET}")
                _time.sleep(args.interval)
        except KeyboardInterrupt:
            print(f"\n\n  {YELLOW}Loop stopped by user after {iteration} iteration(s).{RESET}")
    else:
        run_once(args, camera)

    print(f"\n{'='*60}")
    print(f"  {GREEN}{BOLD}Test complete!{RESET}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
