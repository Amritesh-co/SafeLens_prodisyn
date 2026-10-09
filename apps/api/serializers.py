"""
File Name: api/serializers.py
Description: 
    Defines the serialization and deserialization rules for converting Django ORM 
    models into JSON responses for the Safelens REST API. Contains extensive logic 
    for user profile synchronization, dynamic event media linking (locating frames 
    and clips on disk), and complex object representations.
"""

import os
from datetime import datetime
from django.contrib.auth.models import User
from rest_framework import serializers
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from .utils import derive_incident_display_type, derive_ppe_characteristics, derive_ppe_sub_type
from .models import Event, Camera,Location, EventCountSummary, EventDetection, DetectionModel, Subject, AccessDecision, UserActivityLog, EventReview, EmailAlertTracker, NotificationDeliveryLog, Tenant, TenantLocation, TenantCamera, TenantUseCase, IncidentConfig, UserLocation, UserProfile
from django.contrib.auth import get_user_model
from django.db import transaction
from .roles import Role, DEFAULT_ROLE, TENANT_WIDE_ROLES, STAFF_ROLES


class UserSerializer(serializers.ModelSerializer):
    """
    Serializer for the Django User model combined with the custom UserProfile.
    Handles the 2-way sync between Django's native authentication fields (is_staff, is_active)
    and the domain-specific Safelens fields (role, status, alert preferences).
    """
    password = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=False
    )

    is_online = serializers.SerializerMethodField()

    location_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        write_only=True
    )
    phone_number = serializers.CharField(required=False, allow_null=True)
    location = serializers.CharField(required=False, allow_null=True)
    role = serializers.ChoiceField(choices=Role.choices, required=False)
    status = serializers.CharField(required=False)
    alerts_email = serializers.BooleanField(required=False)
    daily_summary = serializers.BooleanField(required=False)
    alerts_sms = serializers.BooleanField(required=False)
    alerts_whatsapp = serializers.BooleanField(required=False)
    alerts_teams = serializers.BooleanField(required=False)
    fall_alerts = serializers.BooleanField(required=False)
    ppe_alerts = serializers.BooleanField(required=False)
    intrusion_alerts = serializers.BooleanField(required=False)
    unattended_object_alerts = serializers.BooleanField(required=False)
    can_comment = serializers.BooleanField(required=False)
    locations = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'username', 'first_name', 'last_name', 'email', 'password',
                  'last_login', 'date_joined', 'is_staff', 'is_superuser', 'is_active',
                  'is_online', 'role', 'phone_number', 'location','location_ids','locations', 'status', 
                  'alerts_email', 'daily_summary', 'alerts_sms', 'alerts_whatsapp', 'alerts_teams',
                  'fall_alerts', 'ppe_alerts', 'intrusion_alerts', 'unattended_object_alerts', 'can_comment']
        extra_kwargs = {
            'is_staff': {'required': False},
            'is_superuser': {'required': False},
        }

    def get_is_online(self, obj):
        """
        Dynamically calculates if a user is currently logged into the React Dashboard.
        It checks the UserActivityLog for a session that has a login_time but no logout_time.
        """
        return UserActivityLog.objects.filter(user=obj, logout_time__isnull=True).exists()

    def get_locations(self, obj):
        assignments = (
            UserLocation.objects
            .filter(user=obj)
            .select_related(
                "location",
                "location__location"
            )
        )

        return [
            {
                "id": assignment.location.id,  # TenantLocation ID
                "location_id": assignment.location.location_id,  # Core Location ID
                "name": assignment.location.location.name,
                "code": assignment.location.location.code,
            }
            for assignment in assignments
        ]

    def validate(self, data):
        """
        Strict server-side validation to enforce business constraints for User creation/updating.
        """
        is_update = self.instance is not None

        # Grab fields being modified
        username = data.get('username')
        email = data.get('email')
        role = data.get('role')
        status = data.get('status')
        phone_number = data.get('phone_number')

        # Require fields for new users
        if not is_update:
            if not username: raise serializers.ValidationError({"username": "Username is required"})
            if not email: raise serializers.ValidationError({"email": "Email is required"})
            if not role: raise serializers.ValidationError({"role": "Role is required"})
            if not status: raise serializers.ValidationError({"status": "Status is required"})
            if not phone_number: raise serializers.ValidationError({"phone_number": "Phone number is required"})
            if not data.get('password'): raise serializers.ValidationError({"password": "Password is required for new users."})
        else:
            # Require fields if explicitly passed as empty strings during an update
            if 'username' in data and not username: raise serializers.ValidationError({"username": "Username is required"})
            if 'email' in data and not email: raise serializers.ValidationError({"email": "Email is required"})
            if 'role' in data and not role: raise serializers.ValidationError({"role": "Role is required"})
            if 'status' in data and not status: raise serializers.ValidationError({"status": "Status is required"})
            if 'phone_number' in data and not phone_number: raise serializers.ValidationError({"phone_number": "Phone number is required"})

        # Email Domain Validation
        check_email = email if email is not None else (self.instance.email if self.instance else None)
        if check_email:
            allowed_domains = ['gmail.com', 'yahoo.com', 'outlook.com', 'prodisyn.com']
            parts = check_email.split('@')
            if len(parts) < 2 or parts[-1].lower() not in allowed_domains:
                raise serializers.ValidationError({"email": "Invalid email domain"})

        # Phone Number Validation
        # Need to also accommodate checking against existing if not provided in payload but that's complex since we're verifying the POST/PUT. 
        # The prompt says "phone validation... must contain digits, exactly 10". If it's provided:
        if phone_number is not None:
            if not str(phone_number).isdigit() or len(str(phone_number)) != 10:
                raise serializers.ValidationError({"phone_number": "Phone number must be a 10-digit Indian number"})

        location_ids = data.get('location_ids', [])

        if location_ids:
            request = self.context.get("request")

            if not request or not hasattr(request.user, "profile"):
                raise serializers.ValidationError({
                    "location_ids": "Unable to determine requesting user."
                })

            requester_profile = request.user.profile

            if requester_profile.role not in TENANT_WIDE_ROLES:
                raise serializers.ValidationError({
                    "location_ids": "Only Admin users can assign locations."
                })

            tenant = requester_profile.tenant

            if not tenant:
                raise serializers.ValidationError({
                    "location_ids": "Admin/Management is not assigned to a tenant."
                })

            # existing tenant/location validation continues here...

            from .models import TenantLocation

            valid_location_ids = set(
                TenantLocation.objects.filter(
                    id__in=location_ids,
                    tenant=tenant,
                    enabled=True
                ).values_list('id', flat=True)
            )

            invalid_location_ids = set(location_ids) - valid_location_ids

            if invalid_location_ids:
                raise serializers.ValidationError({
                    "location_ids": (
                        f"Invalid location IDs for this tenant: "
                        f"{list(invalid_location_ids)}"
                    )
                })

        return data

    @transaction.atomic
    def create(self, validated_data):
        # Extract profile fields
        location_ids = validated_data.pop('location_ids', [])
        phone_number = validated_data.pop('phone_number', None)
        location = validated_data.pop('location', None)
        role = validated_data.pop('role', DEFAULT_ROLE)
        status = validated_data.pop('status', 'Active')
        alerts_email = validated_data.pop('alerts_email', True)
        daily_summary = validated_data.pop('daily_summary', False)
        alerts_sms = validated_data.pop('alerts_sms', False)
        alerts_whatsapp = validated_data.pop('alerts_whatsapp', False)
        alerts_teams = validated_data.pop('alerts_teams', False)
        fall_alerts = validated_data.pop('fall_alerts', True)
        ppe_alerts = validated_data.pop('ppe_alerts', True)
        intrusion_alerts = validated_data.pop('intrusion_alerts', True)
        unattended_object_alerts = validated_data.pop('unattended_object_alerts', True)
        can_comment = validated_data.pop('can_comment', True)
        password = validated_data.pop('password', None)
        
        # Determine is_staff/is_superuser based on role
        # Determine is_staff/is_superuser based on role
        validated_data['is_staff'] = role in STAFF_ROLES
        validated_data['is_superuser'] = False

        # Set is_active based on status
        validated_data['is_active'] = (status == 'Active')

        user = User.objects.create_user(**validated_data)

        if password:
            user.set_password(password)
            user.save()

        profile = user.profile

        profile.phone_number = phone_number
        profile.location = location
        profile.role = role
        profile.status = status

        profile.alerts_email = alerts_email
        profile.daily_summary = daily_summary
        profile.alerts_sms = alerts_sms
        profile.alerts_whatsapp = alerts_whatsapp
        profile.alerts_teams = alerts_teams

        profile.fall_alerts = fall_alerts
        profile.ppe_alerts = ppe_alerts
        profile.intrusion_alerts = intrusion_alerts
        profile.unattended_object_alerts = unattended_object_alerts
        profile.can_comment = can_comment

        # ----------------------------------
        # TENANT
        # ----------------------------------

        request = self.context.get("request")

        if request and hasattr(request.user, "profile"):
            profile.tenant = request.user.profile.tenant

        profile.save()

        # ----------------------------------
        # USER LOCATIONS
        # ----------------------------------

        from .models import UserLocation, TenantLocation

        if location_ids:
            tenant_locations = TenantLocation.objects.filter(
                id__in=location_ids,
                tenant=profile.tenant,
                enabled=True
            )

            UserLocation.objects.bulk_create([
                UserLocation(
                    user=user,
                    location=tenant_location
                )
                for tenant_location in tenant_locations
            ])

        return user
    
    @transaction.atomic
    def update(self, instance, validated_data):
        # Extract profile fields
        location_ids = validated_data.pop('location_ids', None)
        phone_number = validated_data.pop('phone_number', None)
        location = validated_data.pop('location', None)
        role = validated_data.pop('role', None)
        status = validated_data.pop('status', None)
        alerts_email = validated_data.pop('alerts_email', None)
        daily_summary = validated_data.pop('daily_summary', None)
        alerts_sms = validated_data.pop('alerts_sms', None)
        alerts_whatsapp = validated_data.pop('alerts_whatsapp', None)
        alerts_teams = validated_data.pop('alerts_teams', None)
        fall_alerts = validated_data.pop('fall_alerts', None)
        ppe_alerts = validated_data.pop('ppe_alerts', None)
        intrusion_alerts = validated_data.pop('intrusion_alerts', None)
        unattended_object_alerts = validated_data.pop('unattended_object_alerts', None)
        can_comment = validated_data.pop('can_comment', None)
        password = validated_data.pop('password', None)
        
        # Update User fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        
        if password:
            instance.set_password(password)
        
        # Update Role flags if role provided
        if role:
            instance.is_staff = role in STAFF_ROLES
            instance.is_superuser = False
        
        # Sync is_active with status if status provided
        if status is not None:
            instance.is_active = (status == 'Active')
        
        instance.save()
        
        # Update Profile fields
        from .models import UserProfile
        profile, created = UserProfile.objects.get_or_create(user=instance)
        if phone_number is not None: profile.phone_number = phone_number
        if location is not None: profile.location = location
        if role is not None: profile.role = role
        if status is not None: profile.status = status
        
        # Explicitly check if the keys are IN the initial data before updating
        # This prevents `False` values from being overridden by `.pop(key, None)` ignoring it
        if alerts_email is not None: profile.alerts_email = alerts_email
        if daily_summary is not None: profile.daily_summary = daily_summary
        if alerts_sms is not None: profile.alerts_sms = alerts_sms
        if alerts_whatsapp is not None: profile.alerts_whatsapp = alerts_whatsapp
        if alerts_teams is not None: profile.alerts_teams = alerts_teams
        if fall_alerts is not None: profile.fall_alerts = fall_alerts
        if ppe_alerts is not None: profile.ppe_alerts = ppe_alerts
        if intrusion_alerts is not None: profile.intrusion_alerts = intrusion_alerts
        if unattended_object_alerts is not None: profile.unattended_object_alerts = unattended_object_alerts
        if can_comment is not None: profile.can_comment = can_comment
        
        profile.save()

        # UPDATE USER LOCATIONS
        if location_ids is not None:

            from .models import UserLocation, TenantLocation

            tenant = profile.tenant

            if not tenant:
                raise serializers.ValidationError({
                    "location_ids": "User is not assigned to a tenant."
                })

            # Find valid locations belonging to this tenant
            tenant_locations = TenantLocation.objects.filter(
                id__in=location_ids,
                tenant=tenant,
                enabled=True
            )

            valid_location_ids = set(
                tenant_locations.values_list(
                    'id',
                    flat=True
                )
            )

            invalid_location_ids = set(location_ids) - valid_location_ids

            if invalid_location_ids:
                raise serializers.ValidationError({
                    "location_ids": (
                        f"Invalid location IDs for this tenant: "
                        f"{list(invalid_location_ids)}"
                    )
                })

            # Remove existing assignments
            UserLocation.objects.filter(
                user=instance
            ).delete()

            # Create new assignments
            UserLocation.objects.bulk_create([
                UserLocation(
                    user=instance,
                    location=tenant_location
                )
                for tenant_location in tenant_locations
            ])
        
        return instance

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        from .models import UserLocation, UserProfile

        ret['location_ids'] = list(
            UserLocation.objects.filter(
                user=instance
            ).values_list(
                'location_id',
                flat=True
            )
        )
        try:
            from .models import UserProfile
            profile = UserProfile.objects.get(user=instance)
            ret['phone_number'] = profile.phone_number
            ret['location'] = profile.location
            ret['role'] = profile.role
            ret['status'] = profile.status
            ret['alerts_email'] = profile.alerts_email
            ret['daily_summary'] = profile.daily_summary
            ret['alerts_sms'] = profile.alerts_sms
            ret['alerts_whatsapp'] = profile.alerts_whatsapp
            ret['alerts_teams'] = profile.alerts_teams
            ret['fall_alerts'] = profile.fall_alerts
            ret['ppe_alerts'] = profile.ppe_alerts
            ret['intrusion_alerts'] = profile.intrusion_alerts
            ret['unattended_object_alerts'] = profile.unattended_object_alerts
            ret['can_comment'] = profile.can_comment
        except UserProfile.DoesNotExist:
            ret['phone_number'] = None
            ret['location'] = None
            ret['role'] = DEFAULT_ROLE
            ret['status'] = 'Active'
            ret['alerts_email'] = True
            ret['alerts_sms'] = False
            ret['daily_summary'] = False
            ret['alerts_whatsapp'] = False
            ret['alerts_teams'] = False
            ret['fall_alerts'] = True
            ret['ppe_alerts'] = True
            ret['intrusion_alerts'] = True
            ret['unattended_object_alerts'] = True
            ret['can_comment'] = True
        return ret

class CameraSerializer(serializers.ModelSerializer):
    location_name = serializers.CharField(
        source='location.name',
        read_only=True
    )

    class Meta:
        model = Camera
        fields = [
            'camera_id',
            'location',
            'location_name',
            'code',
            'name',
            'stream_uri',
            'stream_secret_ref',
            'stream_protocol',
            'resolution_width',
            'resolution_height',
            'fps',
            'is_active',
            'last_heartbeat_at',
        ]


class DetectionModelSerializer(serializers.ModelSerializer):
    class Meta:
        model = DetectionModel
        fields = '__all__'

class EventDetectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = EventDetection
        fields = ['detection_type', 'detection_value', 'detection_details']

class AccessDecisionSerializer(serializers.ModelSerializer):
    class Meta:
        model = AccessDecision
        fields = ['decision', 'decision_details']

class EventReviewSerializer(serializers.ModelSerializer):
    updated_by_name = serializers.SerializerMethodField()
    read_by_name = serializers.SerializerMethodField()

    class Meta:
        model = EventReview #read
        fields = ['id', 'event_id', 'status', 'comments', 'updated_at', 'updated_by', 'updated_by_name','is_read', 'read_at', 'read_by', 'read_by_name']
        read_only_fields = ['updated_at', 'updated_by', 'is_read', 'read_at', 'read_by']

    def get_updated_by_name(self, obj):
        if obj.updated_by:
            return obj.updated_by.username
        return "System"

    def get_read_by_name(self, obj): #read
            if obj.read_by:
                return obj.read_by.username
            return None
    
class EventCountSummarySerializer(serializers.ModelSerializer):

    class Meta:
        model = EventCountSummary
        fields = [
            'id',
            'generated_at',
            'weekly_data',
            'monthly_data',
        ]

class MediaUrlMixin:
    """
    Mixin to provide consistent image and video URL resolution logic
    across different event serializers.
    """

    def get_media_url(self, path):
        if not path:
            return None
        path = str(path).strip()

        if path.startswith('http'):
            return path

        # If the DB stores an S3 object key instead of a full URL, rebuild the
        # public URL so browser clients like Amplify can load it directly.
        if path.startswith('storage/'):
            bucket_name = os.environ.get('AWS_STORAGE_BUCKET_NAME', '').strip()
            region = os.environ.get('AWS_S3_REGION_NAME', '').strip()
            if not bucket_name or not region:
                return None
            return f'https://{bucket_name}.s3.{region}.amazonaws.com/{path.lstrip("/")}'

        if path.startswith('s3://'):
            bucket_and_key = path[5:]
            if '/' in bucket_and_key:
                bucket_name, object_key = bucket_and_key.split('/', 1)
                region = os.environ.get('AWS_S3_REGION_NAME', '').strip()
                if not region:
                    return None
                return f'https://{bucket_name}.s3.{region}.amazonaws.com/{object_key.lstrip("/")}'
            return None
            
        # Optimization: Cache storage_base on the serializer instance or context
        storage_base = getattr(self, '_storage_base_cache', None)
        if storage_base is None:
            storage_base = os.environ.get('SYSTEM_STORAGE_DIR')
            if not storage_base:
                 storage_base = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'storage'))
            storage_base = os.path.normpath(storage_base)
            setattr(self, '_storage_base_cache', storage_base)
        
        # Normalize path only once
        path = os.path.normpath(path)
        
        if path.startswith(storage_base):
            rel = os.path.relpath(path, storage_base)
            return f'/media/{rel}'
        
        # IMPROVED FALLBACK: Handle any project root by splitting on 'storage/'
        if 'storage/' in path:
            rel = path.split('storage/', 1)[-1]
            rel = rel.lstrip('/')
            return f'/media/{rel}'
        
        if not path.startswith('/') and not path.startswith('http'):
            return f'/media/{path}'
            
        return path

    def get_image_url(self, obj):
        image_map = self.context.get('image_url_map') if hasattr(self, 'context') else None
        if image_map is not None:
            return image_map.get(obj.event_id)
        try:
            from .models import EventMediaMap, Frame
            media_map = EventMediaMap.objects.filter(event_id=obj.event_id, media_type='FRAME').first()
            if media_map:
                frame = Frame.objects.filter(frame_id=media_map.media_id).first()
                if frame and frame.storage_path:
                    return self.get_media_url(frame.storage_path)
            return None
        except Exception:
            return None

    def get_video_url(self, obj):
        video_map = self.context.get('video_url_map') if hasattr(self, 'context') else None
        if video_map is not None:
            return video_map.get(obj.event_id)
        try:
            from .models import EventMediaMap, Clip
            media_map = EventMediaMap.objects.filter(event_id=obj.event_id, media_type='CLIP').first()
            if media_map:
                clip = Clip.objects.filter(clip_id=media_map.media_id).first()
                if clip and clip.storage_path:
                    return self.get_media_url(clip.storage_path)
            return None
        except Exception:
            return None

class UserActivityLogSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)

    class Meta:
        model = UserActivityLog
        fields = ['id', 'user', 'username', 'login_time', 'logout_time', 'ip_address']
        read_only_fields = ['id', 'user', 'username', 'login_time', 'logout_time', 'ip_address']

class EventSerializer(MediaUrlMixin, serializers.ModelSerializer):
    """
    Detailed Serializer for a Safety Event.
    Nests the Camera details and any specific Detections (e.g. Bounding boxes or missing PPE).
    Dynamically fetches the absolute file path for the incident's snapshot image.
    """
    camera = CameraSerializer(read_only=True)
    detections = EventDetectionSerializer(many=True, read_only=True)
    image_url = serializers.SerializerMethodField()
    video_url = serializers.SerializerMethodField()
    is_read = serializers.SerializerMethodField() # add is read
   
    class Meta:
        model = Event
        fields = ['event_id', 'event_type', 'timestamp', 'camera', 'detections', 'image_url', 'video_url','is_read'] #read

    def get_is_read(self, obj): #changes
        # No review row yet means this incident has never been opened, i.e. unread.
        review = EventReview.objects.filter(event_id=obj.event_id).first()
        return bool(review and review.is_read)
    
class EventCreateSerializer(serializers.Serializer):
    """
    Input serializer for remote AI nodes to submit incidents.
    Supports camera discovery by name and multipart file uploads.
    Now supports deduplication via edge_id.
    """
    camera_name = serializers.CharField(max_length=100)
    camera_location = serializers.CharField(max_length=100, required=False)
    event_type = serializers.CharField(max_length=50)
    timestamp = serializers.DateTimeField(required=False)
    detections = serializers.JSONField(required=False)
    subjects = serializers.JSONField(required=False)
    file = serializers.FileField(required=False)
    video_file = serializers.FileField(required=False)
    storage_path = serializers.CharField(required=False)
    video_storage_path = serializers.CharField(required=False)
    edge_id = serializers.CharField(required=False, allow_null=True, allow_blank=True) # Unique ID from the edge node to prevent double entries
    
    def create(self, validated_data):
        from .models import Camera, Event, EventMediaMap, Frame, Clip, EventDetection, DetectionModel
        from .utils import upload_to_s3
        import json
        import os
        from django.utils import timezone
        import logging
        logger = logging.getLogger(__name__)
        
        edge_id = validated_data.get('edge_id')
        camera_name = validated_data.get('camera_name')
        camera_location = validated_data.get('camera_location', 'Unknown')
        event_type = validated_data.get('event_type')
        
        # 0. DEDUPLICATION: Check if an event with this edge_id AND type already exists
        existing_event = None
        if edge_id:
            # Optimized lookup: find EventDetection where details contain this edge_id
            det = EventDetection.objects.filter(detection_details__edge_id=edge_id).first()
            if det:
                existing_event = det.event
                print(f"[EC2 GATEWAY] Found existing event for edge_id {edge_id}. Updating instead of creating.")

        if existing_event:
            # UPDATE LOGIC (Mainly for adding video to an existing image-only record)
            uploaded_video = validated_data.get('video_file')
            video_url = validated_data.get('video_storage_path') or validated_data.get('video_path')
            
            if not video_url and uploaded_video:
                print(f"[EC2 GATEWAY] Adding Video to existing event {existing_event.event_id}")
                video_url = upload_to_s3(uploaded_video, event_type, 'CLIP', camera_location, camera_name)
                if not str(video_url).startswith('http'):
                     # Fallback local save if needed
                     pass 

            if video_url:
                clip = Clip.objects.create(storage_path=video_url)
                # Check if CLIP mapping already exists to avoid double mapping
                if not EventMediaMap.objects.filter(event_id=existing_event.event_id, media_type='CLIP').exists():
                    EventMediaMap.objects.create(
                        event_id=existing_event.event_id,
                        media_type='CLIP',
                        media_id=clip.clip_id
                    )
            return existing_event
        
        # 1. Get or create Location
        location, _ = Location.objects.get_or_create(
            name=camera_location,
            defaults={
                'location_type': 'SHOPFLOOR',
            }
        )
        
        # 2. Get or create Camera
        camera, _ = Camera.objects.get_or_create(
            code=camera_name,
            defaults={
                'name': camera_name,
                'location': location,
            }
        )
        
        # 2. Create Event
        event = Event.objects.create(
            camera=camera,
            event_type=event_type,
            timestamp=validated_data.get('timestamp', timezone.now())
        )
        
        # 3. Handle File Uploads (Push to S3 from EC2)
        uploaded_image = validated_data.get('file')
        uploaded_video = validated_data.get('video_file')
        
        # 3.1. Determine Local Storage Base (Fallback if S3 fails/disabled)
        storage_base = os.environ.get('SYSTEM_STORAGE_DIR')
        if not storage_base:
             storage_base = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'storage'))
        
        def save_locally(file_obj, event_type, media_type):
            """Helper to save uploaded file to local EC2 storage as fallback"""
            sub = "images" if media_type == 'FRAME' else "videos"
            today = timezone.now().strftime("%Y-%m-%d")
            rel_dir = os.path.join("incidents", sub, event_type.lower().replace("_", "-"), camera_location.lower().replace(" ", ""), today)
            abs_dir = os.path.join(storage_base, rel_dir)
            
            os.makedirs(abs_dir, exist_ok=True)
            filename = f"local_{timezone.now().strftime('%H%M%S')}_{file_obj.name}"
            final_path = os.path.join(abs_dir, filename)
            
            with open(final_path, 'wb+') as destination:
                for chunk in file_obj.chunks():
                    destination.write(chunk)
            
            return final_path

        # 3.2. Handle Image Upload
        # PRIORITY: Accept S3 URL from edge node first (already uploaded and signed)
        image_url = validated_data.get('storage_path') or validated_data.get('image_path')
        if not image_url and uploaded_image:
            # Fallback: edge node sent file object, upload to S3 from EC2
            print(f"[EC2 GATEWAY] Handling Incoming Image: {uploaded_image.name}")
            image_url = upload_to_s3(uploaded_image, event_type, 'FRAME', camera_location, camera_name)
            # If S3 URL not returned (signifying failure), save locally
            if not str(image_url).startswith('http'):
               image_url = save_locally(uploaded_image, event_type, 'FRAME')
            
        # 3.3. Handle Video Upload
        # PRIORITY: Accept S3 URL from edge node first (already uploaded and signed)
        video_url = validated_data.get('video_storage_path') or validated_data.get('video_path')
        if not video_url and uploaded_video:
            # Fallback: edge node sent file object, upload to S3 from EC2
            print(f"[EC2 GATEWAY] Handling Incoming Video: {uploaded_video.name}")
            video_url = upload_to_s3(uploaded_video, event_type, 'CLIP', camera_location, camera_name)
            # If S3 URL not returned (signifying failure), save locally
            if not str(video_url).startswith('http'):
               video_url = save_locally(uploaded_video, event_type, 'CLIP')
        
        # 4. Save to Database (Frame & Clip)
        if image_url:
            frame = Frame.objects.create(storage_path=image_url)
            EventMediaMap.objects.create(
                event_id=event.event_id,
                media_type='FRAME',
                media_id=frame.frame_id
            )
            
        if video_url:
            clip = Clip.objects.create(storage_path=video_url)
            EventMediaMap.objects.create(
                event_id=event.event_id,
                media_type='CLIP',
                media_id=clip.clip_id
            )

        # 4. Handle Detections
        detections = validated_data.get('detections', [])
        if isinstance(detections, str):
            try: detections = json.loads(detections)
            except: detections = []
            
        default_model, _ = DetectionModel.objects.get_or_create(
            model_name='cloud-api-edge',
            defaults={'model_version': '1.0'}
        )
        
        # Inject edge_id into the first detection details for tracking/deduplication
        if edge_id and not detections:
            detections = [{"type": event_type, "value": "1.0", "details": {"edge_id": edge_id}}]
        elif edge_id and detections:
            if isinstance(detections[0].get('details'), dict):
                detections[0]['details']['edge_id'] = edge_id
            else:
                detections[0]['details'] = {"edge_id": edge_id}
        
        for det in detections:
            EventDetection.objects.create(
                event=event,
                model=default_model,
                detection_type=det.get('type', 'Unknown'),
                detection_value=det.get('value', ''),
                detection_details=det.get('details', {})
            )
            
        return event

    def to_representation(self, instance):
        from .models import EventMediaMap, Frame, Clip

        img_url = None
        vid_url = None
        
        img_map = EventMediaMap.objects.filter(event_id=instance.event_id, media_type='FRAME').first()
        if img_map:
            frame = Frame.objects.filter(frame_id=img_map.media_id).first()
            img_url = frame.storage_path if frame else None
            
        vid_map = EventMediaMap.objects.filter(event_id=instance.event_id, media_type='CLIP').first()
        if vid_map:
            clip = Clip.objects.filter(clip_id=vid_map.media_id).first()
            vid_url = clip.storage_path if clip else None

        data = {
            'event_id': instance.event_id,
            'event_type': instance.event_type,
            'timestamp': instance.timestamp,
            'image_url': img_url,
            'video_url': vid_url,
            'status': 'created successfully'
        }
        
        return data

class OverviewEventSerializer(MediaUrlMixin, serializers.ModelSerializer):
    """
    Serializer for the Overview dashboard event list.
    Includes location from camera, image URL from associated frame,
    and specific missing PPE items for PPE violations.
    """
    location = serializers.CharField(source='camera.location.name', read_only=True)

    camera_id = serializers.IntegerField(source='camera.camera_id', read_only=True)
    camera_name = serializers.CharField(source='camera.name', read_only=True)

    event_type = serializers.SerializerMethodField()
    image_url = serializers.SerializerMethodField()
    video_url = serializers.SerializerMethodField()
    missing_items = serializers.SerializerMethodField()
    sub_type = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    comments = serializers.SerializerMethodField()
    updated_by_name = serializers.SerializerMethodField()
    updated_at = serializers.SerializerMethodField()
    is_read = serializers.SerializerMethodField()

    class Meta:
        model = Event
        fields = ['event_id', 'event_type', 'sub_type', 'timestamp', 'location', 'camera_id',
        'camera_name', 'image_url', 'video_url', 'missing_items', 'status', 'comments', 'updated_by_name', 'updated_at','is_read']

    def _get_detections(self, obj):
        return self.context.get('detection_map', {}).get(obj.event_id, [])

    def _get_review(self, obj):
        return self.context.get('review_map', {}).get(obj.event_id)

    def _get_frame_path(self, obj):
        return self.context.get('frame_path_map', {}).get(obj.event_id)

    def get_event_type(self, obj):
        return derive_incident_display_type(obj.event_type, detections=self._get_detections(obj), frame_path=self._get_frame_path(obj))

    def get_status(self, obj):
        review = self._get_review(obj)
        return review.status if review else 'Open'

    def get_comments(self, obj):
        review = self._get_review(obj)
        return review.comments if review else ''

    def get_updated_by_name(self, obj):
        review = self._get_review(obj)
        return review.updated_by.username if review and review.updated_by else None

    def get_updated_at(self, obj):
        review = self._get_review(obj)
        return review.updated_at if review else None

    def get_is_read(self, obj):
        # No review row yet means this incident has never been opened, i.e. unread.
        review = self._get_review(obj)
        return bool(review and review.is_read)

    def get_sub_type(self, obj):
        """
        Determines the PPE sub-type (Safety-vest or Hard-hat) for PPE_VIOLATION events.
        Returns 'Safety-vest' or 'Hard-hat' so the frontend can classify vest vs helmet.
        Returns None for non-PPE events.
        Priority: 1) EventDetection.detection_type, 2) Frame path folder name.
        """
        if 'PPE' not in obj.event_type.upper():
            return None

        try:
            return derive_ppe_sub_type(
                detections=self._get_detections(obj),
                frame_path=self._get_frame_path(obj),
            )
        except Exception:
            pass

        return None

    def get_missing_items(self, obj):
        """
        Extract specific missing PPE items from detection details or image path.
        Returns a normalized list of missing PPE items for the frontend.
        Example:
            ["Hard Hat"]
            ["Gloves"]
            ["Safety Vest", "Boots"]
        """
        if 'PPE' not in obj.event_type.upper():
            return []

        # 1. Collect legacy PPE items
        legacy_items = []
        try:
            res = derive_ppe_characteristics(
                detections=self._get_detections(obj),
                frame_path=self._get_frame_path(obj),
            )
            if res and 'missing_items' in res:
                if isinstance(res['missing_items'], list):
                    legacy_items = [str(i).strip().lower() for i in res['missing_items']]
                else:
                    legacy_items = [str(res['missing_items']).strip().lower()]
        except Exception:
            pass

        detections = self._get_detections(obj)

        # Seed with legacy detections
        detected_missing_items = set(legacy_items)

        # 2. Scan EventDetection records
        for det in detections:
            det_type = str(det.detection_type or "").upper()
            det_value = str(det.detection_value or "").lower()

            det_details = det.detection_details or {}
            details_val = (
                str(det_details.get("value", "")).lower()
                if isinstance(det_details, dict)
                else ""
            )

            # Skip detections that are not marked as missing
            if "missing" not in det_value and "missing" not in details_val:
                continue

            if "GOGGLE" in det_type or "GLASS" in det_type:
                detected_missing_items.add("goggles")
            elif "GLOVE" in det_type:
                detected_missing_items.add("gloves")
            elif "BOOT" in det_type or "SHOE" in det_type:
                detected_missing_items.add("boots")
            elif "HAT" in det_type or "HELMET" in det_type:
                detected_missing_items.add("hard hat")
            elif "VEST" in det_type:
                detected_missing_items.add("safety vest")

        # Keep a consistent display order
        display_order = [
            "hard hat",
            "safety vest",
            "goggles",
            "gloves",
            "boots",
        ]

        display_names = {
            "hard hat": "Hard Hat",
            "safety vest": "Safety Vest",
            "goggles": "Goggles",
            "gloves": "Gloves",
            "boots": "Boots",
        }

        ordered_items = [
            display_names[item]
            for item in display_order
            if item in detected_missing_items
        ]
        return ordered_items


class OverviewSummarySerializer(serializers.Serializer):
    """
    Serializer for summary statistics (total events, percentage of type).
    """
    total_events = serializers.IntegerField()
    type_count = serializers.IntegerField()
    percentage = serializers.FloatField()

class GraphDataSerializer(serializers.Serializer):
    """
    Serializer for graph data points.
    """
    label = serializers.CharField()  # Time label (e.g., "10:00", "Mon", "Jan 1")
    count = serializers.IntegerField()

class GlobalSettingsSerializer(serializers.ModelSerializer):
    """
    Serializer for the EmailAlertTracker model, allowing Admins to manage
    global master switches for notification channels.
    """

    class Meta:
        model = EmailAlertTracker

        fields = [
            'is_email_enabled',
            'is_sms_enabled',
            'is_whatsapp_enabled',
            'is_teams_enabled',
            'is_teams_graph_enabled',
            'is_daily_summary_enabled',
            'is_unattended_object_enabled',
            'is_single_login_mode',
            'max_concurrent_sessions',
            'last_checked',
            'last_event_id',
        ]

        read_only_fields = [
            'last_checked',
            'last_event_id',
        ]


class NotificationDeliveryLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationDeliveryLog
        fields = [
            'id', 'event_id', 'channel', 'recipient', 'status',
            'provider', 'provider_message_id', 'template_name',
            'error_message', 'details', 'created_at'
        ]


User = get_user_model()

class ForgotPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()

class ResetPasswordConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(write_only=True, min_length=8)


class TenantConfigLocationSerializer(serializers.ModelSerializer):
    """
    Serializes a TenantLocation while exposing the actual
    core Location name/code to the frontend.

    TenantLocation:
        tenant
        location -> core.Location
        enabled
    """

    name = serializers.CharField(source="location.name")
    code = serializers.CharField(source="location.code", allow_null=True)

    class Meta:
        model = TenantLocation
        fields = [
            "id",
            "name",
            "code",
            "enabled",
        ]


class TenantConfigCameraSerializer(serializers.ModelSerializer):
    """
    Serializes a TenantCamera.

    Location is derived from:
        TenantCamera -> Camera -> Location

    because TenantCamera no longer has its own location FK.
    """

    camera_id = serializers.IntegerField(
        source="camera.camera_id"
    )

    code = serializers.CharField(
        source="camera.code"
    )

    name = serializers.CharField(
        source="camera.name"
    )

    stream_uri = serializers.CharField(
        source="camera.stream_uri",
        allow_null=True
    )

    location_id = serializers.IntegerField(
        source="camera.location.location_id"
    )

    location = serializers.CharField(
        source="camera.location.name"
    )

    class Meta:
        model = TenantCamera
        fields = [
            "camera_id",
            "code",
            "name",
            "stream_uri",
            "location_id",
            "location",
            "enabled",
        ]


class TenantConfigUseCaseSerializer(serializers.ModelSerializer):
    """
    Serializes tenant use-case configuration.

    match_config is intentionally returned as-is because the
    backend uses it as the single source of truth for incident
    classification.
    """

    class Meta:
        model = TenantUseCase
        fields = [
            "id",
            "code",
            "name",
            "enabled",
            "show_on_dashboard",
            "show_in_filters",
            "match_config",
        ]


class TenantConfigSerializer(serializers.ModelSerializer):
    """
    Complete tenant configuration returned to the frontend.

    Contains:
        - enabled locations
        - enabled tenant cameras
        - enabled tenant use cases
    """

    locations = serializers.SerializerMethodField()
    cameras = serializers.SerializerMethodField()
    use_cases = serializers.SerializerMethodField()

    class Meta:
        model = Tenant
        fields = [
            "id",
            "name",
            "code",
            "locations",
            "cameras",
            "use_cases",
        ]

    def get_user(self):
        request = self.context.get("request")

        if not request:
            return None

        return request.user

    def is_admin(self):
        user = self.get_user()

        if not user:
            return False

        try:
            return user.profile.role in TENANT_WIDE_ROLES
        except Exception:
            return False

    def get_assigned_location_ids(self, tenant):
        user = self.get_user()

        if not user:
            return []

        return UserLocation.objects.filter(
            user=user,
            location__tenant=tenant
        ).values_list(
            "location_id",
            flat=True
        )

    def get_locations(self, obj):

        locations = obj.locations.filter(
            enabled=True
        ).select_related(
            "location"
        )

        if not self.is_admin():

            assigned_location_ids = (
                self.get_assigned_location_ids(obj)
            )

            locations = locations.filter(
                id__in=assigned_location_ids
            )

        return TenantConfigLocationSerializer(
            locations,
            many=True
        ).data

    def get_cameras(self, obj):

        cameras = obj.cameras.filter(
            enabled=True
        ).select_related(
            "camera",
            "camera__location"
        )

        if not self.is_admin():

            assigned_location_ids = (
                self.get_assigned_location_ids(obj)
            )

            cameras = cameras.filter(
                camera__location__tenant_locations__id__in=assigned_location_ids
            )

        return TenantConfigCameraSerializer(
            cameras,
            many=True
        ).data

    def get_use_cases(self, obj):

        use_cases = obj.use_cases.filter(
            enabled=True
        ).order_by("name")

        return TenantConfigUseCaseSerializer(
            use_cases,
            many=True
        ).data

class UserLocationSerializer(serializers.ModelSerializer):
    user_id = serializers.IntegerField(write_only=True)
    location_id = serializers.IntegerField(write_only=True)

    user = serializers.SerializerMethodField(read_only=True)
    location = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = UserLocation
        fields = [
            "id",
            "user_id",
            "user",
            "location_id",
            "location",
        ]

    def get_user(self, obj):
        return {
            "id": obj.user.id,
            "username": obj.user.username,
            "name": obj.user.get_full_name() or obj.user.username,
            "role": getattr(obj.user.profile, "role", None),
        }

    def get_location(self, obj):
        return {
            "id": obj.location.id,
            "location_id": obj.location.location_id,
            "name": obj.location.location.name,
            "code": obj.location.location.code,
        }

    def validate(self, attrs):
        request = self.context.get("request")

        if not request or not request.user.is_authenticated:
            raise serializers.ValidationError(
                "Authentication is required."
            )

        user_id = attrs["user_id"]
        location_id = attrs["location_id"]

        # -------------------------------------------------
        # Get requesting admin's tenant
        # -------------------------------------------------
        try:
            admin_profile = request.user.profile
        except UserProfile.DoesNotExist:
            raise serializers.ValidationError(
                "Authenticated user does not have a profile."
            )

        if admin_profile.role not in TENANT_WIDE_ROLES and not request.user.is_superuser:
            raise serializers.ValidationError(
                "Only Admin users can assign locations."
            )

        tenant = admin_profile.tenant

        if not tenant:
            raise serializers.ValidationError(
                "Admin is not associated with a tenant."
            )

        # -------------------------------------------------
        # Validate target user
        # -------------------------------------------------
        try:
            target_user = User.objects.select_related("profile").get(
                id=user_id
            )
        except User.DoesNotExist:
            raise serializers.ValidationError({
                "user_id": "User does not exist."
            })

        target_profile = getattr(target_user, "profile", None)

        if not target_profile:
            raise serializers.ValidationError({
                "user_id": "User does not have a profile."
            })

        # User must belong to same tenant
        if target_profile.tenant_id != tenant.id:
            raise serializers.ValidationError({
                "user_id": "User does not belong to your tenant."
            })

        # -------------------------------------------------
        # Validate location
        # -------------------------------------------------
        try:
            location = TenantLocation.objects.get(
                id=location_id,
                tenant=tenant
            )
        except TenantLocation.DoesNotExist:
            raise serializers.ValidationError({
                "location_id": "Location does not belong to your tenant."
            })

        # -------------------------------------------------
        # Prevent duplicate assignment
        # -------------------------------------------------
        if self.instance is None:
            if UserLocation.objects.filter(
                user=target_user,
                location=location
            ).exists():
                raise serializers.ValidationError(
                    "This location is already assigned to this user."
                )

        attrs["user"] = target_user
        attrs["location"] = location

        return attrs

class IncidentConfigSerializer(serializers.ModelSerializer):
    """
    Serializer for tenant-specific incident scoring configuration.

    Each enabled TenantUseCase can have one IncidentConfig
    containing its unit score and weight.
    """

    incident_type_name = serializers.CharField(
        source="incident_type.name",
        read_only=True
    )

    incident_type_code = serializers.CharField(
        source="incident_type.code",
        read_only=True
    )

    class Meta:
        model = IncidentConfig

        fields = [
            "id",
            "incident_type",
            "incident_type_name",
            "incident_type_code",
            "unit_score",
            "weight",
        ]

        read_only_fields = [
            "id",
            "incident_type_name",
            "incident_type_code",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        request = self.context.get("request")

        if request and request.user.is_authenticated:

            tenant = getattr(
                getattr(request.user, "profile", None),
                "tenant",
                None
            )

            if tenant:
                self.fields["incident_type"].queryset = (
                    TenantUseCase.objects
                    .filter(tenant=tenant)
                    .order_by("name")
                )
            else:
                self.fields["incident_type"].queryset = (
                    TenantUseCase.objects.none()
                )

    def validate(self, attrs):

        request = self.context.get("request")

        if not request or not request.user.is_authenticated:
            raise serializers.ValidationError(
                "Unable to determine requesting user."
            )

        tenant = getattr(
            getattr(request.user, "profile", None),
            "tenant",
            None
        )

        if not tenant:
            raise serializers.ValidationError(
                "User is not associated with a tenant."
            )

        incident_type = attrs.get(
            "incident_type",
            getattr(
                self.instance,
                "incident_type",
                None
            )
        )

        if not incident_type:
            raise serializers.ValidationError({
                "incident_type": "Incident type is required."
            })

        # Make sure the use case belongs to the
        # same tenant as the logged-in administrator.
        if incident_type.tenant_id != tenant.id:
            raise serializers.ValidationError({
                "incident_type": (
                    "This incident type does not belong "
                    "to your tenant."
                )
            })

        # Only enabled use cases should have active
        # scoring configuration.
        if not incident_type.enabled:
            raise serializers.ValidationError({
                "incident_type": (
                    "Incident configuration can only be "
                    "created for an enabled use case."
                )
            })

        unit_score = attrs.get(
            "unit_score",
            getattr(
                self.instance,
                "unit_score",
                None
            )
        )

        weight = attrs.get(
            "weight",
            getattr(
                self.instance,
                "weight",
                None
            )
        )

        if unit_score is not None and unit_score < 0:
            raise serializers.ValidationError({
                "unit_score": (
                    "Unit score cannot be negative."
                )
            })

        if weight is not None and weight < 0:
            raise serializers.ValidationError({
                "weight": (
                    "Weight cannot be negative."
                )
            })

        # One configuration per tenant + use case.
        existing = IncidentConfig.objects.filter(
            tenant=tenant,
            incident_type=incident_type,
        )

        if self.instance:
            existing = existing.exclude(
                pk=self.instance.pk
            )

        if existing.exists():
            raise serializers.ValidationError({
                "incident_type": (
                    "A scoring configuration already "
                    "exists for this use case."
                )
            })

        return attrs
