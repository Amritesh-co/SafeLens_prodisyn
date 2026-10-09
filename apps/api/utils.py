import os
import boto3
import uuid
import logging
import re
from datetime import datetime
from botocore.exceptions import ClientError
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from email.mime.image import MIMEImage


logger = logging.getLogger(__name__)


def _normalize_location_token(value):
    if not value:
        return ''
    return re.sub(r'[^a-z0-9]+', '', str(value).strip().lower())


def parse_location_list(value):
    if not value:
        return []
    return [token for token in (_normalize_location_token(item) for item in str(value).split(',')) if token]


def location_matches(profile_location, camera_location):
    profile_tokens = parse_location_list(profile_location)
    camera_token = _normalize_location_token(camera_location)

    if not profile_tokens:
        return True
    if not camera_token:
        return False
    return camera_token in profile_tokens


def get_whatsapp_template_name(media_url=None):
    if media_url:
        return os.environ.get('AWS_WHATSAPP_TEMPLATE_MEDIA', 'safelens_incident_alert_media')
    return os.environ.get('AWS_WHATSAPP_TEMPLATE_TEXT', 'safelens_incident_alert_text')


def normalize_e164_phone_number(phone_number, default_country_code='91'):
    """
    Normalize local app phone numbers before sending to AWS messaging APIs.
    Plain 10-digit numbers are treated as India mobile numbers by default.
    """
    digits = re.sub(r'\D+', '', str(phone_number or ''))
    if not digits:
        return ''
    if len(digits) == 10:
        digits = f"{default_country_code}{digits}"
    return f"+{digits}"


def _normalize_detection_token(value):
    return re.sub(r'[^a-z0-9]+', '', str(value or '').strip().lower())


def derive_ppe_characteristics(detections=None, frame_path=None):
    detections = detections or []
    has_helmet_violation = False
    has_vest_violation = False

    for detection in detections:
        d_type = _normalize_detection_token(getattr(detection, 'detection_type', ''))
        d_value = _normalize_detection_token(getattr(detection, 'detection_value', ''))
        d_details = getattr(detection, 'detection_details', {}) or {}
        missing_item = _normalize_detection_token(d_details.get('missing_item'))

        if any(token in d_type for token in ['helmet', 'hardhat', 'head']):
            has_helmet_violation = True
        if any(token in d_type for token in ['vest', 'jacket']):
            has_vest_violation = True

        if any(token in d_value for token in ['helmet', 'hardhat']):
            has_helmet_violation = True
        if any(token in d_value for token in ['vest', 'jacket']):
            has_vest_violation = True

        if missing_item == 'helmet':
            has_helmet_violation = True
        if missing_item in ['vest', 'jacket', 'safetyvest']:
            has_vest_violation = True

    if frame_path:
        path_lower = str(frame_path).lower()
        if 'hard-hat' in path_lower or 'helmet' in path_lower:
            has_helmet_violation = True
        if 'safety-vest' in path_lower or 'vest' in path_lower:
            has_vest_violation = True

    return {
        'has_helmet_violation': has_helmet_violation,
        'has_vest_violation': has_vest_violation,
        'missing_items': (
            ['Helmet', 'Vest'] if has_helmet_violation and has_vest_violation
            else ['Helmet'] if has_helmet_violation
            else ['Vest'] if has_vest_violation
            else []
        ),
    }


def derive_ppe_sub_type(detections=None, frame_path=None):
    traits = derive_ppe_characteristics(detections=detections, frame_path=frame_path)
    if traits['has_helmet_violation'] and traits['has_vest_violation']:
        return 'Hard-hat & Safety-vest'
    if traits['has_helmet_violation']:
        return 'Hard-hat'
    if traits['has_vest_violation']:
        return 'Safety-vest'
    return None


def derive_incident_display_type(raw_event_type, detections=None, frame_path=None):
    """
    Converts the backend event_type into a human-readable incident name.

    Generic behavior:
        FIRE_DETECTION -> Fire Detection
        INTRUSION_DETECTED -> Intrusion Detected
        FALL_DETECTED -> Fall Detected
        UNATTENDED_OBJECT -> Unattended Object

    PPE events receive additional classification based on detections/frame path.
    """

    raw_event_type = str(raw_event_type or '').strip()

    if not raw_event_type:
        return 'Unknown Incident'

    normalized_raw = raw_event_type.upper()

    # ---------------------------------------------------------
    # PPE-specific classification only
    # ---------------------------------------------------------
    if 'PPE' in normalized_raw:
        traits = derive_ppe_characteristics(
            detections=detections,
            frame_path=frame_path
        )

        if traits['has_helmet_violation'] and traits['has_vest_violation']:
            return 'No Hard Hat & No Safety Vest'

        if traits['has_helmet_violation']:
            return 'No Hard Hat'

        if traits['has_vest_violation']:
            return 'No Safety Vest'

        return 'PPE Violation'

    # ---------------------------------------------------------
    # Generic fallback for every other use case
    # ---------------------------------------------------------
    return raw_event_type.replace('_', ' ').title()

def get_iam_boto3_client(service_name, region_name=None):
    """
    Initializes a boto3 client forcing fallback to IAM Role by temporarily popping static env credentials.
    """
    old_key = os.environ.pop('AWS_ACCESS_KEY_ID', None)
    old_secret = os.environ.pop('AWS_SECRET_ACCESS_KEY', None)
    try:
        region = region_name or os.environ.get('AWS_REGION', 'ap-south-1')
        session = boto3.Session()
        return session.client(service_name, region_name=region)
    finally:
        if old_key is not None:
            os.environ['AWS_ACCESS_KEY_ID'] = old_key
        if old_secret is not None:
            os.environ['AWS_SECRET_ACCESS_KEY'] = old_secret

def get_boto3_client(service_name):
    """
    Initializes a boto3 client using environment variables.
    """
    if service_name in ('sns', 'socialmessaging'):
        return get_iam_boto3_client(service_name)
    return boto3.client(
        service_name,
        aws_access_key_id=os.environ.get('AWS_ACCESS_KEY_ID'),
        aws_secret_access_key=os.environ.get('AWS_SECRET_ACCESS_KEY'),
        region_name=os.environ.get('AWS_REGION', 'ap-south-1')
    )

def upload_to_s3(file_obj, event_type, media_type, location="unknown", camera_name="unknown"):
    """
    Uploads a file object to S3 from the EC2 server.
    media_type: 'FRAME' or 'CLIP'
    Returns the absolute S3 URL.
    """
    try:
        bucket_name = os.environ.get('AWS_STORAGE_BUCKET_NAME', 'safelensai-data')
        region = os.environ.get('AWS_S3_REGION_NAME', 'ap-south-1')
        
        # 1. Initialize S3 client
        s3 = get_boto3_client('s3')
        
        # 2. Build S3 Key
        today = datetime.now().strftime("%Y-%m-%d")
        timestamp = datetime.now().strftime("%H-%M-%S")
        unique_id = str(uuid.uuid4())[:8]
        ext = ".jpg" if media_type == 'FRAME' else ".mp4"
        subfolder = "images" if media_type == 'FRAME' else "videos"
        
        loc_slug = location.lower().replace(" ", "")
        cam_slug = camera_name.lower().replace(" ", "-")
        event_slug = event_type.lower().replace("_", "-")
        
        filename = f"ec2_upload_{timestamp}_{unique_id}{ext}"
        s3_key = f"storage/incidents/{subfolder}/{event_slug}/{loc_slug}/{cam_slug}/{today}/{filename}"
        
        print(f"   [AWS S3] Uploading to Bucket: {bucket_name}")
        print(f"   [AWS S3] Target Key: {s3_key}")
        
        # 3. Upload
        content_type = 'image/jpeg' if media_type == 'FRAME' else 'video/mp4'
        s3.put_object(
            Bucket=bucket_name,
            Key=s3_key,
            Body=file_obj,
            ContentType=content_type
        )
        
        url = f"https://{bucket_name}.s3.{region}.amazonaws.com/{s3_key}"
        print(f"   [AWS S3] Success! Public URL: {url}")
        logger.info(f"Successfully uploaded {media_type} to S3: {url}")
        return url
    except Exception as e:
        logger.error(f"S3 Upload Failed for {media_type}: {e}", exc_info=True)
        return getattr(file_obj, 'name', 'unknown_file')




from email.mime.image import MIMEImage
def send_aws_email(
    subject,
    body,
    recipients,
    attachments=None,
    html=False,
    inline_images=None,
):
    """
    Sends an email using AWS SES with optional attachments.

    Args:
        subject: Email subject.
        body: Email body.
        recipients: List of recipient email addresses.
        attachments: Optional list of file paths or URLs.
        html: If True, sends the body as HTML.
        Otherwise sends as plain text.
    """

    if not recipients:
        return

    sender = os.environ.get("AWS_SES_SENDER")

    if not sender:
        raise RuntimeError(
            "AWS_SES_SENDER is not configured "
            "(set AWS_SES_SENDER env var)"
        )

    # SES is region-scoped
    ses_region = (
        os.environ.get("AWS_SES_REGION_NAME")
        or os.environ.get("AWS_REGION")
        or "ap-south-1"
    )

    # Use IAM Role for notifications (SES)
    client = get_iam_boto3_client(
        "ses",
        region_name=ses_region
    )

    msg = MIMEMultipart("mixed")

    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)

    # ==========================================================
    # BODY
    # ==========================================================

    
    if html:
        related_part = MIMEMultipart("related")
        alternative_part = MIMEMultipart("alternative")

        alternative_part.attach(
            MIMEText(
                "This email contains an HTML daily incident summary. "
                "Please view it in an HTML-capable email client.",
                "plain",
                "utf-8",
            )
        )
        alternative_part.attach(MIMEText(body, "html", "utf-8"))
        related_part.attach(alternative_part)
        msg.attach(related_part)
    else:
        related_part = msg
        msg.attach(MIMEText(body, "plain", "utf-8"))    

        
    # ==========================================================
    # INLINE CHART IMAGES
    # ==========================================================
    for content_id, image_path in inline_images or []:

        try:
            image_data = None
            display_name = os.path.basename(str(image_path).split("?")[0])

            if image_path and (image_path.startswith("http://") or image_path.startswith("https://")):
                import requests
                resp = requests.get(image_path, timeout=10)
                if resp.status_code == 200:
                    image_data = resp.content
                else:
                    logger.warning(
                        f"Inline image fetch failed (HTTP {resp.status_code}): {image_path}"
                    )
                    continue
            elif image_path and os.path.isfile(image_path):
                with open(image_path, "rb") as image_file:
                    image_data = image_file.read()
            else:
                logger.warning(
                    f"Inline image not found: {image_path}"
                )
                continue

            import mimetypes
            guessed_type, _ = mimetypes.guess_type(
                str(image_path).split("?")[0]
            )
            subtype = (guessed_type or "image/png").split("/")[-1]  # jpg -> jpeg

            image_part = MIMEImage(
                image_data,
                _subtype=subtype,
            )
            image_part.add_header(
                "Content-ID",
                f"<{content_id}>",
            )

            image_part.add_header(
                "Content-Disposition",
                "inline",
                filename=display_name,
            )

            related_part.attach(image_part)

        except Exception as e:
            logger.error(
                f"Error attaching inline image "
                f"{image_path}: {e}"
            )

    # ==========================================================
    # FILE ATTACHMENTS (real-time incident alerts: images/videos)
    # ==========================================================
    for file_path in attachments or []:

        try:
            file_data = None
            filename = None

            if str(file_path).startswith("http://") or str(file_path).startswith("https://"):
                import requests
                resp = requests.get(file_path, timeout=10)
                if resp.status_code == 200:
                    file_data = resp.content
                    filename = str(file_path).split("/")[-1].split("?")[0]
                else:
                    logger.warning(
                        f"Failed to download attachment "
                        f"(HTTP {resp.status_code}): {file_path}"
                    )
                    continue

            elif os.path.isfile(file_path):
                with open(file_path, "rb") as f:
                    file_data = f.read()
                filename = os.path.basename(file_path)

            else:
                logger.warning(f"Attachment not found: {file_path}")
                continue

            part = MIMEApplication(file_data)
            part.add_header(
                "Content-Disposition",
                "attachment",
                filename=filename,
            )
            msg.attach(part)

        except Exception as e:
            logger.error(
                f"Error attaching file {file_path}: {e}"
            )

    # ==========================================================
    # SEND THROUGH SES
    # ==========================================================

    try:
        ses_configuration_set = os.environ.get("SES_CONFIGURATION_SET")
        send_kwargs = {
            "Source": sender,
            "Destinations": recipients,
            "RawMessage": {"Data": msg.as_string()},
        }
        if ses_configuration_set:
            send_kwargs["ConfigurationSetName"] = ses_configuration_set
        response = client.send_raw_email(**send_kwargs)


        logger.info(
            "Email sent via SES: "
            f"{response['MessageId']}"
        )

        return response

    except ClientError as e:
        logger.error(
            "SES Error: "
            f"{e.response['Error']['Message']}"
        )

        raise


def send_aws_sms(phone_number, message):
    """
    Sends an SMS using AWS SNS.

    If AWS_SNS_TOPIC_ARN is defined, it publishes to the topic.
    Otherwise, it publishes directly to the provided phone number.

    Phone numbers are normalized to E.164 format before sending.
    Example:
        9876543210 -> +919876543210
    """

    client = get_boto3_client('sns')
    topic_arn = os.environ.get('AWS_SNS_TOPIC_ARN')

    try:
        # ---------------------------------------------------------
        # Direct SMS to phone number
        # ---------------------------------------------------------
        if phone_number:
            clean_phone = normalize_e164_phone_number(phone_number)

            if not clean_phone:
                logger.error(
                    "SMS recipient phone number is empty or invalid"
                )
                return None

            response = client.publish(
                PhoneNumber=clean_phone,
                Message=message,
                MessageAttributes={
                    'AWS.SNS.SMS.SenderID': {
                        'DataType': 'String',
                        'StringValue': 'SafeLens'
                    },
                    'AWS.SNS.SMS.SMSType': {
                        'DataType': 'String',
                        'StringValue': 'Transactional'
                    }
                }
            )

            logger.info(
                f"SMS sent to {clean_phone} via SNS: "
                f"{response['MessageId']}"
            )

        # ---------------------------------------------------------
        # SNS Topic fallback
        # ---------------------------------------------------------
        elif topic_arn:
            response = client.publish(
                TopicArn=topic_arn,
                Message=message,
                MessageAttributes={
                    'AWS.SNS.SMS.SenderID': {
                        'DataType': 'String',
                        'StringValue': 'SafeLens'
                    },
                    'AWS.SNS.SMS.SMSType': {
                        'DataType': 'String',
                        'StringValue': 'Transactional'
                    }
                }
            )

            logger.info(
                f"SMS sent to Topic {topic_arn} via SNS: "
                f"{response['MessageId']}"
            )

        # ---------------------------------------------------------
        # No recipient configured
        # ---------------------------------------------------------
        else:
            logger.error(
                "Neither phone number nor AWS_SNS_TOPIC_ARN is configured"
            )
            return None

        return response

    except ClientError as e:
        logger.error(
            f"SNS Error: {e.response['Error']['Message']}"
        )
        return None








def send_aws_whatsapp(phone_number, message, media_url=None, location="Unknown", time_str="Unknown", incident_type="Incident", event_id="N/A", video_url=None):
    """
    Sends a WhatsApp message using AWS End User Messaging (Social Messaging).
    Uses the configured AWS template and sends body-only variables so both image and
    video can be included as clickable URLs in the message body.
    """
    import json
    phone_number_id = os.environ.get('AWS_WHATSAPP_PHONE_NUMBER_ID')
    if not phone_number_id:
        logger.error("AWS_WHATSAPP_PHONE_NUMBER_ID not configured in .env")
        return

    client = get_boto3_client('socialmessaging')
    
    try:
        clean_phone = normalize_e164_phone_number(phone_number)
        if not clean_phone:
            logger.error("WhatsApp recipient phone number is empty or invalid")
            return
        template_name = get_whatsapp_template_name(media_url or video_url)
        template_language = os.environ.get('AWS_WHATSAPP_TEMPLATE_LANG', 'en')

        components = []

        # Body parameters (Universal for our templates: ID, Time, Location, Type)
        body_params = [
            {"type": "text", "text": str(event_id)},
            {"type": "text", "text": str(time_str)},
            {"type": "text", "text": str(location)},
            {"type": "text", "text": str(incident_type)}
        ]
        
        # The SafeLens media template body includes Image and Video URL variables.
        if media_url:
            body_params.append({"type": "text", "text": str(media_url)})
        if video_url:
            body_params.append({"type": "text", "text": str(video_url)})

        components.append({
            "type": "body",
            "parameters": body_params
        })

        message_obj = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": clean_phone,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": template_language},
                "components": components
            }
        }

        json_payload = json.dumps(message_obj)
        logger.info(f"   -> AWS WhatsApp Request: {json_payload}")

        response = client.send_whatsapp_message(
            originationPhoneNumberId=phone_number_id,
            message=json_payload.encode('utf-8'),
            metaApiVersion='v20.0'
        )

        logger.info(f"WhatsApp Template Response: {json.dumps(response)}")
        return response


    except Exception as e:
        logger.error(
            f"WhatsApp AWS Error for {clean_phone}: {str(e)}",
            exc_info=True
        )
    
        # Do not silently swallow the AWS error.
        # Let poll_events.py capture the actual exception
        # in Notification Delivery Log.
        raise



def resolve_media_path(db_path):
    """
    Resolves a storage path (from Django models Frame or Clip) to a usable URL or file path.
    1. If the path starts with http:// or https://, returns it as-is.
    2. If the path starts with s3://, parses the bucket and key and generates a 7-day presigned S3 URL.
    3. If the path is a local file, returns it as-is.
    4. If the path is a relative path in system storage, searches for it relative to SYSTEM_STORAGE_DIR.
    """
    if not db_path:
        return None

    path = str(db_path).strip()

    # 1. HTTP(S) URL
    if path.startswith('http://') or path.startswith('https://'):
        return path

    # 2. S3 URI (s3://bucket/key)
    if path.startswith('s3://'):
        try:
            parts = path[5:].split('/', 1)
            if len(parts) == 2:
                bucket = parts[0]
                key = parts[1]
                # Initialize s3 client using standard credentials
                s3_client = boto3.client(
                    's3',
                    aws_access_key_id=os.environ.get('AWS_ACCESS_KEY_ID'),
                    aws_secret_access_key=os.environ.get('AWS_SECRET_ACCESS_KEY'),
                    region_name=os.environ.get('AWS_S3_REGION_NAME') or os.environ.get('AWS_REGION') or 'ap-south-1'
                )
                presigned_url = s3_client.generate_presigned_url(
                    'get_object',
                    Params={'Bucket': bucket, 'Key': key},
                    ExpiresIn=3600*24*7 # 7 Days (Max)
                )
                return presigned_url
        except Exception as e:
            logger.error(f"Error generating presigned URL for {db_path}: {e}")

    # 3. Local File
    if os.path.isfile(path):
        return path

    # 4. Search relative to storage base
    if 'storage/' in path:
        rel_suffix = path.split('storage/')[-1]
        storage_base = os.environ.get('SYSTEM_STORAGE_DIR')
        if not storage_base:
            storage_base = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'storage'))

        alt_path = os.path.join(storage_base, rel_suffix)
        if os.path.isfile(alt_path):
            return alt_path

    return None


def send_teams_notification(message):
    """
    Sends a notification to a Microsoft Teams channel via Incoming Webhook.
    Uses the Adaptive Card payload format required by MS Teams connectors.

    Args:
        message (str): The notification text to display in the Teams channel.

    Returns:
        True on successful delivery (HTTP 200/202), False otherwise.
    """
    import requests as http_client

    webhook_url = os.environ.get('TEAMS_WEBHOOK_URL')
    if not webhook_url:
        logger.error("TEAMS_WEBHOOK_URL is not configured (set TEAMS_WEBHOOK_URL env var)")
        return False

    payload = {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": {
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard",
                    "version": "1.2",
                    "body": [
                        {
                            "type": "TextBlock",
                            "text": message,
                            "wrap": True
                        }
                    ]
                }
            }
        ]
    }

    try:
        response = http_client.post(
            webhook_url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        if response.status_code in (200, 202):
            logger.info("Teams notification delivered successfully")
            return True
        else:
            logger.error(f"Teams webhook returned HTTP {response.status_code}: {response.text[:200]}")
            return False
    except http_client.RequestException as e:
        logger.error(f"Teams webhook request failed: {e}")
        return False


# ---------------------------------------------------------------------------
# Microsoft Graph — Teams 1:1 Notifications (Delegated / Service Account)
# ---------------------------------------------------------------------------
# Uses MSAL token cache for silent token renewal.
# Service account token captured once via teams_token_capture.py.
# ---------------------------------------------------------------------------

import threading

_graph_token_lock = threading.Lock()
_graph_token_cache = {
    'access_token': None,
    'expires_at': 0,
}

GRAPH_SCOPES = [
    "Chat.Create",
    "ChatMessage.Send",
    "User.Read",
    "User.ReadBasic.All",
]


def _get_msal_app_and_cache():
    """
    Initialise an MSAL PublicClientApplication backed by the on-disk
    SerializableTokenCache.  Returns (app, cache) or raises RuntimeError.
    """
    import msal

    client_id = os.environ.get('MS_CLIENT_ID')
    tenant_id = os.environ.get('MS_TENANT_ID')
    cache_path = os.environ.get('MS_TOKEN_CACHE_FILE')

    if not client_id or not tenant_id:
        raise RuntimeError("MS_CLIENT_ID / MS_TENANT_ID not configured in .env")
    if not cache_path:
        raise RuntimeError("MS_TOKEN_CACHE_FILE not configured in .env")
    if not os.path.exists(cache_path):
        raise RuntimeError(
            f"MSAL token cache file not found: {cache_path}. "
            "Run teams_token_capture.py first to create it."
        )

    authority = f"https://login.microsoftonline.com/{tenant_id}"
    cache = msal.SerializableTokenCache()
    with open(cache_path, 'r') as f:
        cache.deserialize(f.read())

    app = msal.PublicClientApplication(
        client_id=client_id,
        authority=authority,
        token_cache=cache,
    )
    return app, cache, cache_path


def _save_token_cache(cache, cache_path):
    """Persist the token cache back to disk if it changed (updated refresh token)."""
    if cache.has_state_changed:
        try:
            with open(cache_path, 'w') as f:
                f.write(cache.serialize())
            os.chmod(cache_path, 0o600)
        except Exception as e:
            logger.error(f"Failed to save MSAL token cache to {cache_path}: {e}")


def get_graph_access_token():
    """
    Acquire a valid Microsoft Graph access token using silent MSAL refresh.
    Thread-safe.  Returns the access token string or raises RuntimeError.
    """
    import time as _time

    with _graph_token_lock:
        # Return cached in-memory token if still valid (with 2-minute buffer)
        if (_graph_token_cache['access_token']
                and _graph_token_cache['expires_at'] > _time.time() + 120):
            return _graph_token_cache['access_token']

        app, cache, cache_path = _get_msal_app_and_cache()

        accounts = app.get_accounts()
        if not accounts:
            raise RuntimeError(
                "No accounts found in MSAL token cache. "
                "Run teams_token_capture.py to authenticate the service account."
            )

        # Use the first (and typically only) cached account
        result = app.acquire_token_silent(scopes=GRAPH_SCOPES, account=accounts[0])

        if not result or 'access_token' not in result:
            error_desc = (result or {}).get('error_description', 'unknown error')
            raise RuntimeError(
                f"MSAL silent token acquisition failed: {error_desc}. "
                "The refresh token may have expired (90-day limit). "
                "Re-run teams_token_capture.py to re-authenticate."
            )

        _save_token_cache(cache, cache_path)

        # Cache in memory
        # MSAL tokens typically expire in 3600s; use 'expires_in' if provided
        expires_in = result.get('expires_in', 3600)
        _graph_token_cache['access_token'] = result['access_token']
        _graph_token_cache['expires_at'] = _time.time() + int(expires_in)

        logger.info("Graph access token acquired/refreshed silently for Teams 1:1")
        return result['access_token']


def resolve_teams_user_id(email, access_token):
    """
    Look up a Microsoft user by email/UPN.
    Returns the user's Entra object ID (aadObjectId) string, or None on failure.
    """
    import requests as http_client

    url = f"https://graph.microsoft.com/v1.0/users/{email}"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    try:
        resp = http_client.get(url, headers=headers, timeout=15)
        if resp.status_code == 200:
            user_id = resp.json().get('id')
            logger.info(f"Graph user resolved: {email} -> {user_id}")
            return user_id
        else:
            body = resp.text[:300]
            logger.error(f"Graph user lookup failed for {email}: HTTP {resp.status_code} — {body}")
            return None
    except Exception as e:
        logger.error(f"Graph user lookup exception for {email}: {e}")
        return None


def get_or_create_teams_chat(service_account_user_id, target_user_id, access_token):
    """
    Create (or return existing) 1:1 chat between the service account and target user.
    Graph returns the existing chat if one already exists between these two users.
    Returns the chat ID string, or None on failure.
    """
    import requests as http_client

    url = "https://graph.microsoft.com/v1.0/chats"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    payload = {
        "chatType": "oneOnOne",
        "members": [
            {
                "@odata.type": "#microsoft.graph.aadUserConversationMember",
                "roles": ["owner"],
                "user@odata.bind": f"https://graph.microsoft.com/v1.0/users('{service_account_user_id}')"
            },
            {
                "@odata.type": "#microsoft.graph.aadUserConversationMember",
                "roles": ["owner"],
                "user@odata.bind": f"https://graph.microsoft.com/v1.0/users('{target_user_id}')"
            }
        ]
    }

    try:
        resp = http_client.post(url, headers=headers, json=payload, timeout=15)
        if resp.status_code in (200, 201):
            chat_id = resp.json().get('id')
            logger.info(f"Graph 1:1 chat ready: {chat_id}")
            return chat_id
        else:
            body = resp.text[:300]
            logger.error(f"Graph chat creation failed: HTTP {resp.status_code} — {body}")
            return None
    except Exception as e:
        logger.error(f"Graph chat creation exception: {e}")
        return None


def send_teams_graph_message(chat_id, message_html, access_token):
    """
    Send a message to a specific Teams 1:1 chat via Microsoft Graph.
    Returns the Graph message ID string on success, or None on failure.
    """
    import requests as http_client

    url = f"https://graph.microsoft.com/v1.0/chats/{chat_id}/messages"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    payload = {
        "body": {
            "contentType": "html",
            "content": message_html,
        }
    }

    try:
        resp = http_client.post(url, headers=headers, json=payload, timeout=15)
        if resp.status_code in (200, 201):
            msg_id = resp.json().get('id')
            logger.info(f"Graph Teams message sent: {msg_id}")
            return msg_id
        else:
            body = resp.text[:300]
            logger.error(f"Graph message send failed: HTTP {resp.status_code} — {body}")
            return None
    except Exception as e:
        logger.error(f"Graph message send exception: {e}")
        return None


def send_teams_1on1_notification(recipient_email, message_html, user_profile=None):
    """
    High-level orchestrator for Teams 1:1 Graph notification.

    Flow:
        1. Acquire Graph access token (silent refresh)
        2. Resolve the service account's own user ID (from /me, cached)
        3. Resolve target user's Entra ID (or use stored teams_user_id)
        4. Get/create 1:1 chat (or use stored teams_chat_id)
        5. Send the message
        6. Persist teams_user_id and teams_chat_id back to UserProfile

    Args:
        recipient_email: The target user's Microsoft email/UPN.
        message_html:    HTML content to send.
        user_profile:    Optional UserProfile instance for caching chat/user IDs.

    Returns:
        dict with 'success' (bool), 'message_id' (str or None), 'error' (str or None)
    """
    try:
        token = get_graph_access_token()
    except RuntimeError as e:
        return {'success': False, 'message_id': None, 'error': str(e)}

    # --- Resolve service account's own user ID ---
    svc_user_id = _get_service_account_user_id(token)
    if not svc_user_id:
        return {'success': False, 'message_id': None, 'error': 'Could not resolve service account user ID from /me'}

    # --- Resolve target user ---
    target_user_id = None
    if user_profile and user_profile.teams_user_id:
        target_user_id = user_profile.teams_user_id
    else:
        target_user_id = resolve_teams_user_id(recipient_email, token)
        if not target_user_id:
            return {'success': False, 'message_id': None, 'error': f'Could not resolve Microsoft user: {recipient_email}'}
        # Persist for future lookups
        if user_profile:
            user_profile.teams_user_id = target_user_id
            user_profile.save(update_fields=['teams_user_id'])

    # --- Get or create 1:1 chat ---
    chat_id = None
    if user_profile and user_profile.teams_chat_id:
        chat_id = user_profile.teams_chat_id
    else:
        chat_id = get_or_create_teams_chat(svc_user_id, target_user_id, token)
        if not chat_id:
            return {'success': False, 'message_id': None, 'error': 'Could not create/find 1:1 Teams chat'}
        # Persist for future messages
        if user_profile:
            user_profile.teams_chat_id = chat_id
            user_profile.save(update_fields=['teams_chat_id'])

    # --- Send the message ---
    msg_id = send_teams_graph_message(chat_id, message_html, token)
    if msg_id:
        return {'success': True, 'message_id': msg_id, 'error': None}
    else:
        return {'success': False, 'message_id': None, 'error': 'Graph message POST failed (check logs for HTTP details)'}


# Cache service account /me ID in memory — it never changes
_service_account_user_id = None
_service_account_lock = threading.Lock()


# def _get_service_account_user_id(access_token):
#     """
#     Call GET /me with the service account token to discover its own Entra user ID.
#     Result is cached in memory since it never changes.
#     """
#     import requests as http_client

#     global _service_account_user_id
#     with _service_account_lock:
#         if _service_account_user_id:
#             return _service_account_user_id

#         try:
#             resp = http_client.get(
#                 "https://graph.microsoft.com/v1.0/me",
#                 headers={"Authorization": f"Bearer {access_token}"},
#                 timeout=15,
#             )
#             if resp.status_code == 200:
#                 _service_account_user_id = resp.json().get('id')
#                 logger.info(f"Service account user ID resolved: {_service_account_user_id}")
#                 return _service_account_user_id
#             else:
#                 logger.error(f"Graph /me failed for service account: HTTP {resp.status_code}")
#                 return None
#         except Exception as e:
#             logger.error(f"Graph /me exception: {e}")
#             return None

def _get_service_account_user_id(access_token):
    """
    Call GET /me with the service account token to discover its own Entra user ID.
    Result is cached in memory since it never changes.
    """
    import requests as http_client

    global _service_account_user_id

    with _service_account_lock:
        if _service_account_user_id:
            return _service_account_user_id

        try:
            resp = http_client.get(
                "https://graph.microsoft.com/v1.0/me",
                headers={
                    "Authorization": f"Bearer {access_token}"
                },
                timeout=15,
            )

            if resp.status_code == 200:
                _service_account_user_id = resp.json().get("id")

                logger.info(
                    f"Service account user ID resolved: "
                    f"{_service_account_user_id}"
                )

                return _service_account_user_id

            else:
                logger.error(
                    f"Graph /me failed for service account: "
                    f"HTTP {resp.status_code}"
                )

                return None

        except Exception as e:
            logger.error(
                f"Graph /me exception: {e}"
            )

            return None
