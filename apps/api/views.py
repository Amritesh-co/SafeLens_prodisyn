"""
File Name: api/views.py
Description: 
    The core Request/Response router for the Safelens REST API. 
    It defines ViewSets for standard CRUD operations (Users, Events, Cameras),
    custom action endpoints for dynamic Analytics graph data, and the 
    `SendNotificationView` responsible for routing multi-channel Twilio SMS, WhatsApp, 
    and Email push notifications to correct managers.
Author: Safelens AI Backend Team
"""
from openpyxl.cell.cell import MergedCell
from io import BytesIO
from datetime import datetime, timedelta
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer)
from tracemalloc import start
from wsgiref import headers
from isort import output
from openpyxl import Workbook, workbook, worksheet
from django.http import HttpResponse, request, response
from django.utils.timezone import now
from openpyxl.styles import Font
from rest_framework import viewsets
from django.contrib.auth.models import User
from reportlab.platypus import Image
# Dynamic table change and for logo display
from django.contrib.staticfiles import finders
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from xml.sax.saxutils import escape
from apps import cameras
from .models import Event, Camera, Location, AccessDecision, EventReview, EmailAlertTracker, UserProfile, UserActivityLog, UserSession, EventMediaMap, Frame, EventDetection, Clip, NotificationRecipient, NotificationDeliveryLog, PpeComplianceDaily, UserLocation, TenantUseCase, TenantLocation, TenantCamera, IncidentConfig, EventCountSummary
from .serializers import EventSerializer, CameraSerializer, AccessDecisionSerializer, OverviewEventSerializer, OverviewSummarySerializer, GraphDataSerializer, GlobalSettingsSerializer, EventCreateSerializer, EventReviewSerializer, NotificationDeliveryLogSerializer,TenantConfigSerializer,UserLocationSerializer, UserSerializer, IncidentConfigSerializer, EventCountSummarySerializer
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from django.http import StreamingHttpResponse
import json
import os
import time as time_module
from datetime import datetime, timedelta, time
from django.conf import settings
from django.db.models import Count, Q, Sum, Exists, OuterRef, Subquery
from django.db.models.functions import TruncHour, TruncDay, ExtractHour
import requests
from django.utils import duration, timezone
from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.authtoken.models import Token
from rest_framework.authentication import TokenAuthentication
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, IsAdminUser, AllowAny
from rest_framework import status
from rest_framework.renderers import BaseRenderer
from dateutil.relativedelta import relativedelta
from django.utils.dateparse import parse_datetime
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.views.generic import TemplateView
from apps.api.notification_retry import retry_failed_whatsapp_logs
from apps.api.utils import derive_incident_display_type, get_boto3_client
from urllib.parse import urlparse
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.core.mail import send_mail
from django.core import signing
from rest_framework.response import Response
from apps.api.utils import send_aws_email  # ◄── Integrates with your existing SES handler 
from .serializers import ForgotPasswordSerializer, ResetPasswordConfirmSerializer
from apps.api.models import PasswordResetEvent,TenantUseCase
import secrets
from collections import defaultdict
import mimetypes
from django.core.cache import cache
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.exceptions import ValidationError, PermissionDenied
from apps.api.utils import  get_whatsapp_template_name
from .roles import Role, DEFAULT_ROLE, TENANT_WIDE_ROLES, LOCATION_SCOPED_ROLES, STAFF_ROLES
from rest_framework import serializers
import logging
from django.shortcuts import render
from django.db import transaction

logger = logging.getLogger(__name__)

class LoginRateThrottle(SimpleRateThrottle):
    scope = "login"
    rate = "3/2m"
 
    def parse_rate(self, rate):
        return (3, 120)
 
    def get_cache_key(self, request, view):
        ident = self.get_ident(request)
        return f"throttle_login_{ident}"
 
    def get_lock_key(self, request):
        ident = self.get_ident(request)
        return f"login_lock_{ident}"
 
    def is_locked(self, request):
        lock_key = self.get_lock_key(request)
        lock_until = cache.get(lock_key)
 
        if lock_until is None:
            return False, 0
 
        remaining = int(lock_until - time_module.time())
 
        if remaining <= 0:
            cache.delete(lock_key)
            return False, 0
 
        return True, remaining
 
    def increment_fail(self, request):
        cache_key = self.get_cache_key(request, None)
        lock_key = self.get_lock_key(request)
 
        now = time_module.time()
 
        history = cache.get(cache_key, [])
 
        history = [
            timestamp
            for timestamp in history
            if now - timestamp < 120
        ]
 
        history.append(now)
 
        if len(history) >= 3:
            lock_until = now + 120
 
            cache.set(
                lock_key,
                lock_until,
                timeout=120
            )
 
            cache.delete(cache_key)
 
            return True
 
        cache.set(
            cache_key,
            history,
            timeout=120
        )
 
        return False
 
    def reset(self, request):
        cache.delete(self.get_cache_key(request, None))
        cache.delete(self.get_lock_key(request))

def get_events(request):
    events = apply_event_access_filter(
        Event.objects
        .select_related('camera')
        .order_by('-timestamp'),
        request
    )

    detections = EventDetection.objects.filter(
        event__in=events
    )

    reviews = EventReview.objects.filter(
        event__in=events
    ).select_related('updated_by')

    media_maps = EventMediaMap.objects.filter(
        event__in=events,
        media_type='FRAME'
    )

    frames = Frame.objects.filter(
        frame_id__in=media_maps.values('media_id')
    )

    detection_map = defaultdict(list)

    for d in detections:
        detection_map[d.event_id].append(d)

    review_map = {
        r.event_id: r
        for r in reviews
    }

    frame_dict = {
        f.frame_id: f.storage_path
        for f in frames
    }

    frame_path_map = {
        m.event_id: frame_dict.get(m.media_id)
        for m in media_maps
    }

    serializer = OverviewEventSerializer(
        events,
        many=True,
        context={
            'request': request,
            'detection_map': detection_map,
            'review_map': review_map,
            'frame_path_map': frame_path_map
        }
    )

    return Response(serializer.data)

def apply_event_access_filter(queryset, request):
    """
    Apply tenant and role-based access filtering to Event queryset.

    Access rules:
    - Admin:
        All events from the user's tenant.
    - Manager:
        Events from assigned locations.
    - Support:
        Events from assigned locations.
    - Unauthenticated / invalid:
        No access.
    """

    user = request.user

    if not user.is_authenticated:
        return queryset.none()

    try:
        profile = user.profile
    except UserProfile.DoesNotExist:
        return queryset.none()

    tenant = profile.tenant

    if not tenant:
        return queryset.none()

    # ---------------------------------------------------------
    # ADMIN
    # ---------------------------------------------------------
    if profile.role in TENANT_WIDE_ROLES:
        return queryset.filter(
            camera__tenant_config__tenant=tenant
        )

    # ---------------------------------------------------------
    # MANAGER / SUPPORT
    # ---------------------------------------------------------
    if profile.role in LOCATION_SCOPED_ROLES:

        assigned_location_ids = (
            UserLocation.objects
            .filter(
                user=user,
                location__tenant=tenant
            )
            .values_list(
                "location__location_id",
                flat=True
            )
        )

        return queryset.filter(
            camera__location_id__in=assigned_location_ids
        )

    return queryset.none()

from datetime import timedelta
from dateutil.relativedelta import relativedelta
from django.db.models import Count
from django.utils import timezone
import pytz

def calculate_event_count_summary():
    """
    Calculate and store dashboard event/PPE count summary.
 
    Weekly:
        Previous 7 complete days.
        Today is excluded.
 
    Monthly:
        Previous 30 complete days.
        Today is excluded.

    All:
        Complete event history up to the start of today.
        Today is excluded.

    Rules:
        - TenantUseCase.match_config is the source of truth.
        - Events are classified using the tenant assigned to the camera.
        - PPE_VIOLATION itself is never stored as an event type.
        - PPE detections are classified using detection_type.
        - Normal events are classified using event_type.
        - Rejected contributes only to rejected count.
        - Rejected does not contribute to total/open/closed.
        - Rejected does not contribute to incidents_over_time.
        - incidents_over_time contains both normal and PPE incidents.
        - Weekly/monthly/all ranges exclude today.
    """
 
    import pytz
    from django.utils import timezone
    from datetime import timedelta
    from collections import defaultdict
 
    # =========================================================
    # REPORT TIMEZONE
    # =========================================================
 
    report_tz = pytz.timezone("Asia/Kolkata")
 
    now = timezone.now()
 
    if timezone.is_naive(now):
        now = report_tz.localize(now)
    else:
        now = timezone.localtime(now, report_tz)
 
    # =========================================================
    # START OF TODAY
    # =========================================================
 
    today_start = now.replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )
 
    # =========================================================
    # TENANT USE CASE CONFIGURATION
    # =========================================================


    tenant_use_cases_by_tenant = defaultdict(list)

    tenant_use_cases = TenantUseCase.objects.filter(
        enabled=True
    )


    for use_case in tenant_use_cases:
        tenant_use_cases_by_tenant[
            use_case.tenant_id
        ].append(use_case)

    # =========================================================
    # CAMERA -> TENANT MAP
    # =========================================================

    camera_tenant_map = {
        tenant_camera.camera_id: tenant_camera.tenant_id
        for tenant_camera in TenantCamera.objects.all()
    }

    # =========================================================
    # EMPTY COUNT
    # =========================================================
 
    def empty_count():
        return {
            "total": 0,
            "open": 0,
            "closed": 0,
            "rejected": 0,
        }
 
    # =========================================================
    # EMPTY EVENT TYPE COUNT
    # =========================================================
 
    def empty_event_type_count(code, name):
        return {
            "code": code,
            "name": name,
            "total": 0,
            "open": 0,
            "closed": 0,
            "rejected": 0,
        }
 
    # =========================================================
    # NORMALIZE CONFIG VALUES
    # =========================================================
 
    def normalize_config_list(values):
        """
        Convert:
 
            "FALL_DETECTION"
 
        or:
 
            ["FALL_DETECTION", "INTRUSION_DETECTION"]
 
        into an uppercase list.
        """
 
        if not values:
            return []
 
        if isinstance(values, str):
            values = [values]
 
        return [
            str(value).strip().upper()
            for value in values
            if str(value).strip()
        ]


    # =========================================================
    # FIND TENANT-SPECIFIC USE CASE
    # =========================================================

    def get_api_event_use_case(
        event_type,
        tenant_use_cases,
        detection_type=None,
    ):
        """
        Resolve an event using ONLY the TenantUseCases
        belonging to the event's tenant.
 
        TenantUseCase.match_config is the source of truth.
        """
 
        event_type_upper = (
            event_type or ""
        ).strip().upper()
 

        detection_type_upper = (
            detection_type or ""
        ).strip().upper()
 
        for use_case in tenant_use_cases:
 
            config = use_case.match_config or {}
 
            configured_event_types = normalize_config_list(
                config.get("event_type")
            )
 
            configured_detection_types = normalize_config_list(
                config.get("detection_type")
            )
 
            # -------------------------------------------------
            # EVENT TYPE MUST MATCH
            # -------------------------------------------------
 
            if event_type_upper not in configured_event_types:
                continue
 
            # -------------------------------------------------
            # DETECTION TYPE
            # -------------------------------------------------
 
            if configured_detection_types:
 
                if not detection_type_upper:
                    continue
 
                if detection_type_upper not in configured_detection_types:
                    continue
 
            return {
                "code": use_case.code,
                "name": use_case.name,
            }
 
        return None
 
    # =========================================================
    # ADD EVENT TYPE COUNT
    # =========================================================
 
    def add_event_type_count(
        container,
        event_type,
        status,
        use_case=None,
    ):
 
        if event_type not in container:
 
            if use_case:
                container[event_type] = empty_event_type_count(
                    use_case["code"],
                    use_case["name"],
                )
 
            else:
                container[event_type] = empty_event_type_count(
                    event_type,
                    event_type,
                )
 
        if status == "rejected":
 
            container[event_type]["rejected"] += 1
 
        elif status == "closed":
 
            container[event_type]["closed"] += 1
            container[event_type]["total"] += 1
 
        else:
 
            container[event_type]["open"] += 1
            container[event_type]["total"] += 1
 
    # =========================================================
    # ADD SUMMARY COUNT
    # =========================================================
 
    def add_summary_count(summary, status):
 
        if status == "rejected":
 
            summary["rejected"] += 1
 
        elif status == "closed":
 
            summary["closed"] += 1
            summary["total"] += 1
 
        else:
 
            summary["open"] += 1
            summary["total"] += 1
 
    # =========================================================
    # ADD INCIDENTS OVER TIME
    # =========================================================
 
    def add_incident_over_time(
        report,
        event_date,
        event_type,
    ):
 
        if not event_type:
            return
 
        if event_date not in report["incidents_over_time"]:
            report["incidents_over_time"][event_date] = {}
 
        if event_type not in report["incidents_over_time"][event_date]:
            report["incidents_over_time"][event_date][event_type] = 0
 
        report["incidents_over_time"][event_date][event_type] += 1
 
    # =========================================================
    # GET EVENT DATE IN ASIA/KOLKATA
    # =========================================================
 
    def get_event_date(event_timestamp):
 
        if timezone.is_naive(event_timestamp):
 
            event_timestamp = report_tz.localize(
                event_timestamp
            )
 
        else:
 
            event_timestamp = timezone.localtime(
                event_timestamp,
                report_tz,
            )
 
        return event_timestamp.strftime("%Y-%m-%d")
 
    # =========================================================
    # ADD INCIDENTS OVER TIME
    # =========================================================

    def add_incident_over_time(
        report,
        event_date,
        event_type,
    ):

        if not event_type:
            return

        if event_date not in report["incidents_over_time"]:
            report["incidents_over_time"][event_date] = {}

        if event_type not in report["incidents_over_time"][event_date]:
            report["incidents_over_time"][event_date][event_type] = 0

        report["incidents_over_time"][event_date][event_type] += 1

    # =========================================================
    # GET EVENT DATE IN ASIA/KOLKATA
    # =========================================================

    def get_event_date(event_timestamp):

        if timezone.is_naive(event_timestamp):

            event_timestamp = report_tz.localize(
                event_timestamp
            )

        else:

            event_timestamp = timezone.localtime(
                event_timestamp,
                report_tz,
            )

        return event_timestamp.strftime("%Y-%m-%d")


    # =========================================================
    # ADD STATUS-AWARE INCIDENTS OVER TIME
    # =========================================================
    # date -> use-case -> {open, closed, rejected}
    def add_status_incident_over_time(
        report,
        event_date,
        event_type,
        event_status,
    ):
        if not event_type:
            return

        normalized_status = (
            event_status or "open"
        ).strip().lower()

        if normalized_status not in (
            "open",
            "closed",
            "rejected",
        ):
            normalized_status = "open"

        if event_date not in report["status_incidents_over_time"]:
            report["status_incidents_over_time"][event_date] = {}

        if event_type not in report["status_incidents_over_time"][event_date]:
            report["status_incidents_over_time"][event_date][event_type] = {
                "open": 0,
                "closed": 0,
                "rejected": 0,
            }

        report["status_incidents_over_time"][event_date][event_type][
            normalized_status
        ] += 1

    # =========================================================
    # CALCULATE COUNTS FOR ONE PERIOD
    # =========================================================

    def calculate_counts(start_date, end_date, include_unconfigured=False):

        # =====================================================
        # FETCH EVENTS
        # =====================================================
 
        events = list(
            Event.objects
            .filter(
                timestamp__gte=start_date,
                timestamp__lt=end_date,
            )
            .select_related(
                "camera",
                "camera__location",
            )
        )
 
        # =====================================================
        # EVENT IDS
        # =====================================================
 
        event_ids = [
            event.event_id
            for event in events
        ]
 
        # =====================================================
        # REVIEW STATUS MAP
        # =====================================================
 
        reviews = EventReview.objects.filter(
            event_id__in=event_ids
        )
 
        review_map = {
            review.event_id: (
                review.status or "Open"
            ).strip().lower()
            for review in reviews
        }
 
        # =====================================================
        # DETECTION MAP
        # =====================================================
 
        detections = EventDetection.objects.filter(
            event_id__in=event_ids
        )
 
        detections_by_event = defaultdict(list)
 
        for detection in detections:
 
            detections_by_event[
                detection.event_id
            ].append(detection)
 
        # =====================================================
        # RESULT
        # =====================================================
 
        result = {
            "summary": empty_count(),
            "event_types": {},
            "locations": {},
            "incidents_over_time": {},
            "status_incidents_over_time": {},
        }
 
        # =====================================================
        # PROCESS EACH EVENT
        # =====================================================
 
        for event in events:

            # =================================================
            # RAW EVENT TYPE
            # =================================================

            event_type = (
                event.event_type or ""
            ).strip().upper()
 
            if not event_type:
                continue
 
            # =================================================
            # STATUS
            # =================================================
 
            status = review_map.get(
                event.event_id,
                "open",
            )
 
            if status not in (
                "open",
                "closed",
                "rejected",
            ):
                status = "open"
 
            # =================================================
            # CAMERA
            # =================================================
 
            camera = event.camera
 
            camera_id = getattr(
                camera,
                "camera_id",
                None,
            )
 
            if camera_id is None:
                camera_id = getattr(
                    camera,
                    "id",
                    None,
                )
 
            camera_key = (
                str(camera_id)
                if camera_id is not None
                else "unknown"
            )
 
            camera_name = (
                getattr(
                    camera,
                    "name",
                    None,
                )
                or f"Camera {camera_key}"
            )
 
            # =================================================
            # LOCATION
            # =================================================
 
            location = getattr(
                camera,
                "location",
                None,
            )
 
            location_id = getattr(
                location,
                "location_id",
                None,
            )
 
            if location_id is None:
                location_id = getattr(
                    location,
                    "id",
                    None,
                )
 
            location_key = (
                str(location_id)
                if location_id is not None
                else "unknown"
            )
 
            location_name = (
                getattr(
                    location,
                    "name",
                    None,
                )
                or "Unknown Location"
            )
 
            # =================================================
            # TENANT
            # =================================================
            #
            # Event
            #   -> Camera
            #   -> TenantCamera
            #   -> Tenant
            #
            # TenantUseCase classification is based on this
            # tenant.
            # =================================================
 
            tenant_id = camera_tenant_map.get(
                camera_id
            )
 
            tenant_use_cases = (
                tenant_use_cases_by_tenant.get(
                    tenant_id,
                    [],
                )
            )
 
            # =================================================
            # TENANT
            # =================================================
            #
            # Event
            #   -> Camera
            #   -> TenantCamera
            #   -> Tenant
            #
            # TenantUseCase classification is based on this
            # tenant.
            # =================================================

            tenant_id = camera_tenant_map.get(
                camera_id
            )

            tenant_use_cases = (
                tenant_use_cases_by_tenant.get(
                    tenant_id,
                    [],
                )
            )

            # =================================================
            # CREATE LOCATION
            # =================================================
 
            if location_key not in result["locations"]:
 
                result["locations"][location_key] = {
                    "name": location_name,
                    "summary": empty_count(),
                    "event_types": {},
                    "cameras": {},
                    "incidents_over_time": {},
                    "status_incidents_over_time": {},
                }
 
            location_data = result["locations"][
                location_key
            ]
 
            # =================================================
            # CREATE CAMERA
            # =================================================
 
            if camera_key not in location_data["cameras"]:
 
                location_data["cameras"][camera_key] = {
                    "name": camera_name,
                    "summary": empty_count(),
                    "event_types": {},
                    "incidents_over_time": {},
                    "status_incidents_over_time": {},
                }
 
            camera_data = location_data["cameras"][
                camera_key
            ]
 
            # =================================================
            # PPE VIOLATION
            # =================================================
 
            if event_type == "PPE_VIOLATION":
 
                event_detections = (
                    detections_by_event.get(
                        event.event_id,
                        [],
                    )
                )
 
                # -------------------------------------------------
                # CLASSIFY EACH PPE DETECTION USING TENANT USE CASE
                # -------------------------------------------------
 
                for detection in event_detections:
 
                    detection_type = (
                        detection.detection_type or ""
                    ).strip().upper()
 
                    if not detection_type:
                        continue
 
                    # ---------------------------------------------
                    # TENANT-SPECIFIC PPE USE CASE
                    # ---------------------------------------------
 
                    use_case = get_api_event_use_case(
                        "PPE_VIOLATION",
                        tenant_use_cases,
                        detection_type=detection_type,
                    )
 
                    # ---------------------------------------------
                    # IMPORTANT:
                    # NO HARD-CODED MAPPING
                    # NO RAW DETECTION FALLBACK
                    #
                    # TenantUseCase is the source of truth.
                    # ---------------------------------------------
 
                    if not use_case:
                        continue
 
                    api_event_code = use_case["code"]
 
                    event_type_info = {
                        "code": use_case["code"],
                        "name": use_case["name"],
                    }
 
                    # ---------------------------------------------
                    # OVERALL EVENT TYPE
                    # ---------------------------------------------
 
                    add_event_type_count(
                        result["event_types"],
                        api_event_code,
                        status,
                        event_type_info,
                    )
 
                    # ---------------------------------------------
                    # LOCATION EVENT TYPE
                    # ---------------------------------------------
 
                    add_event_type_count(
                        location_data["event_types"],
                        api_event_code,
                        status,
                        event_type_info,
                    )
 
                    # ---------------------------------------------
                    # CAMERA EVENT TYPE
                    # ---------------------------------------------
 
                    add_event_type_count(
                        camera_data["event_types"],
                        api_event_code,
                        status,
                        event_type_info,
                    )
 
                    # ---------------------------------------------
                    # INCIDENTS OVER TIME
                    # ---------------------------------------------
                    #
                    # Rejected PPE events are NOT included.
                    #
                    # Store the FINAL TenantUseCase code.
                    #
                    # Example:
                    #
                    # "NO_HELMET": 10
                    #
                    # NOT:
                    #
                    # "PPE_VIOLATION": 10
                    # ---------------------------------------------
 
                    event_date = get_event_date(
                        event.timestamp
                    )

                    add_status_incident_over_time(
                        result,
                        event_date,
                        api_event_code,
                        status,
                    )

                    add_status_incident_over_time(
                        location_data,
                        event_date,
                        api_event_code,
                        status,
                    )

                    add_status_incident_over_time(
                        camera_data,
                        event_date,
                        api_event_code,
                        status,
                    )

                    if status != "rejected":
 
                        event_date = get_event_date(
                            event.timestamp
                        )
 
                        add_incident_over_time(
                            result,
                            event_date,
                            api_event_code,
                        )

                        add_incident_over_time(
                            location_data,
                            event_date,
                            api_event_code,
                        )

                        add_incident_over_time(
                            camera_data,
                            event_date,
                            api_event_code,
                        )
 
                # ---------------------------------------------
                # SUMMARY
                # ---------------------------------------------
                #
                # One PPE parent event = one summary incident.
                #
                # This prevents multiple detections inside the
                # same PPE event from increasing total/open/closed
                # multiple times.
                # ---------------------------------------------
 
                add_summary_count(
                    result["summary"],
                    status,
                )
 
                add_summary_count(
                    location_data["summary"],
                    status,
                )
 
                add_summary_count(
                    camera_data["summary"],
                    status,
                )
 
                continue
 
            # =================================================
            # NORMAL EVENT TYPE
            # =================================================
 
            use_case = get_api_event_use_case(
                event_type,
                tenant_use_cases,
            )
 
            # =================================================
            # IMPORTANT:
            # TenantUseCase is the source of truth.
            #
            # If the event is not configured for this tenant,
            # do not invent a classification.
            # =================================================

            if not use_case:
                # All-time history must include every database event.
                # Week/Month keep the existing TenantUseCase filtering.
                if not include_unconfigured:
                    continue

                # Preserve the raw event type when no enabled TenantUseCase
                # exists, so the All period remains a complete history.
                use_case = {
                    "code": event_type,
                    "name": event_type,
                }

            api_event_code = use_case["code"]

            event_type_info = {
                "code": use_case["code"],
                "name": use_case["name"],
            }
 
            # =================================================
            # OVERALL EVENT TYPE
            # =================================================
 
            add_event_type_count(
                result["event_types"],
                api_event_code,
                status,
                event_type_info,
            )
 
            # =================================================
            # LOCATION EVENT TYPE
            # =================================================
 
            add_event_type_count(
                location_data["event_types"],
                api_event_code,
                status,
                event_type_info,
            )
 
            # =================================================
            # CAMERA EVENT TYPE
            # =================================================
 
            add_event_type_count(
                camera_data["event_types"],
                api_event_code,
                status,
                event_type_info,
            )
 
            # =================================================
            # INCIDENTS OVER TIME
            # =================================================
            #
            # THIS IS THE PART THAT WAS MISSING/INCOMPLETE.
            #
            # Normal events are also added to the chart using
            # the final TenantUseCase code.
            #
            # Example:
            #
            # event.event_type = "INTRUSION_DETECTION"
            #
            # TenantUseCase:
            # code = "INTRUSION_DETECTION"
            #
            # Result:
            #
            # "2026-09-12": {
            #     "INTRUSION_DETECTION": 5
            # }
            # =================================================

            event_date = get_event_date(
                event.timestamp
            )

            add_status_incident_over_time(
                result,
                event_date,
                api_event_code,
                status,
            )

            add_status_incident_over_time(
                location_data,
                event_date,
                api_event_code,
                status,
            )

            add_status_incident_over_time(
                camera_data,
                event_date,
                api_event_code,
                status,
            )

            if status != "rejected":
                add_incident_over_time(
                    result,
                    event_date,
                    api_event_code,
                )

                add_incident_over_time(
                    location_data,
                    event_date,
                    api_event_code,
                )

                add_incident_over_time(
                    camera_data,
                    event_date,
                    api_event_code,
                )

            # =================================================
            # SUMMARY
            # =================================================
 
            add_summary_count(
                result["summary"],
                status,
            )
 
            add_summary_count(
                location_data["summary"],
                status,
            )
 
            add_summary_count(
                camera_data["summary"],
                status,
            )
 
        # =====================================================
        # RETURN PERIOD DATA
        # =====================================================
 
        return result
 
    # =========================================================
    # WEEKLY RANGE
    # =========================================================
 
    weekly_start = today_start - timedelta(days=7)
    weekly_end = today_start
 
    # =========================================================
    # MONTHLY RANGE
    # =========================================================
 
    monthly_start = today_start - timedelta(days=30)
    monthly_end = today_start
 
    # =========================================================
    # ALL RANGE
    # =========================================================
    # Complete database history EXCEPT TODAY.
    # The upper bound is the start of today, so no event from
    # today can be included in the All period.
    # =========================================================

    first_event_timestamp = (
        Event.objects
        .filter(timestamp__lt=today_start)
        .order_by("timestamp")
        .values_list("timestamp", flat=True)
        .first()
    )

    if first_event_timestamp is not None:
        all_start = first_event_timestamp
    else:
        # No historical events exist before today.
        all_start = today_start

    all_end = today_start

    # =========================================================
    # CALCULATE WEEKLY DATA
    # =========================================================
 
    weekly_report = calculate_counts(
        weekly_start,
        weekly_end,
    )
 
    # =========================================================
    # CALCULATE MONTHLY DATA
    # =========================================================
 
    monthly_report = calculate_counts(
        monthly_start,
        monthly_end,
    )

    # =========================================================
    # CALCULATE ALL DATA
    # =========================================================

    all_report = calculate_counts(
        all_start,
        all_end,
        include_unconfigured=True,
    )
 
    # =========================================================
    # SAVE TO DATABASE
    # =========================================================
    # NOTE: EventCountSummary must have an `all_data` JSONField.

    summary = EventCountSummary.objects.create(
        weekly_data=weekly_report,
        monthly_data=monthly_report,
        all_data=all_report,
    )
 
    # =========================================================
    # RETURN
    # =========================================================
 
    return {
        "weekly_data": weekly_report,
        "monthly_data": monthly_report,
        "all_data": all_report,
        "generated_at": summary.generated_at,
    }



class EventCountSummaryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):

        generated_at = request.query_params.get("generated_at")
        report_date = request.query_params.get("date")
        period = request.query_params.get("period", "monthly").lower()

        # =========================================================
        # VALIDATE PERIOD
        # =========================================================
        if period not in ["weekly", "monthly", "all"]:
            return Response(
                {
                    "detail": "Invalid period. Use 'weekly', 'monthly', or 'all'."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # =========================================================
        # GET SPECIFIC REPORT BY GENERATED_AT
        # =========================================================
        if generated_at:

            parsed_datetime = parse_datetime(generated_at)

            if not parsed_datetime:
                return Response(
                    {
                        "detail": "Invalid generated_at format."
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

            summary = EventCountSummary.objects.filter(
                generated_at=parsed_datetime
            ).first()

        # =========================================================
        # GET LATEST REPORT FOR SPECIFIC DATE
        # =========================================================
        elif report_date:

            summary = EventCountSummary.objects.filter(
                generated_at__date=report_date
            ).order_by("-generated_at").first()

        # =========================================================
        # GET LATEST REPORT
        # =========================================================
        else:

            summary = EventCountSummary.objects.order_by(
                "-generated_at"
            ).first()

        # =========================================================
        # REPORT NOT FOUND
        # =========================================================
        if not summary:

            return Response(
                {
                    "detail": "Event count summary not found."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        # =========================================================
        # SELECT PERIOD DATA
        # =========================================================
        if period == "weekly":
            report_data = summary.weekly_data
        elif period == "monthly":
            report_data = summary.monthly_data
        else:  # all
            report_data = summary.all_data

        # =========================================================
        # RETURN RESPONSE
        # =========================================================
        return Response(
            {
                "id": summary.id,
                "generated_at": summary.generated_at,
                "period": period,
                "data": report_data
            },
            status=status.HTTP_200_OK
        )


def build_overview_context(events, request):
    event_ids = [event.event_id for event in events]
    context = {'request': request}
    if not event_ids:
        context.update({
            'review_map': {},
            'image_url_map': {},
            'video_url_map': {},
            'frame_path_map': {},
            'detection_map': {},
        })
        return context

    # 1. Bulk Fetch Reviews
    review_map = {
        review.event_id: review
        for review in EventReview.objects.filter(event_id__in=event_ids).select_related('updated_by')
    }

    # 2. Bulk Fetch Media Mappings
    media_rows = list(EventMediaMap.objects.filter(
        event_id__in=event_ids,
        media_type__in=['FRAME', 'CLIP']
    ))
    
    frame_ids = [row.media_id for row in media_rows if row.media_type == 'FRAME']
    clip_ids = [row.media_id for row in media_rows if row.media_type == 'CLIP']

    # 3. Bulk Fetch Frames and Clips
    frame_map = {
        frame.frame_id: frame.storage_path
        for frame in Frame.objects.filter(frame_id__in=frame_ids)
    }
    clip_map = {
        clip.clip_id: clip.storage_path
        for clip in Clip.objects.filter(clip_id__in=clip_ids)
    }

    # 4. Efficient Link Generation
    # We instantiate the serializer once and reuse it
    serializer_helper = OverviewEventSerializer(context={'request': request})
    
    # Cache storage_base to avoid repeated system calls in get_media_url
    # (Serializer already handles this if we call get_media_url)
    
    image_url_map = {}
    video_url_map = {}
    frame_path_map = {}
    
    for row in media_rows:
        if row.media_type == 'FRAME':
            storage_path = frame_map.get(row.media_id)
            if storage_path:
                frame_path_map[row.event_id] = storage_path
                image_url_map[row.event_id] = serializer_helper.get_media_url(storage_path)
        elif row.media_type == 'CLIP':
            storage_path = clip_map.get(row.media_id)
            if storage_path:
                video_url_map[row.event_id] = serializer_helper.get_media_url(storage_path)

    # 5. Bulk Fetch Detections (Only for relevant events to save memory)
    ppe_event_ids = [event_id for event_id in event_ids] # Actually we might need detections for many types now
    detection_map = {}
    if ppe_event_ids:
        detections = EventDetection.objects.filter(event_id__in=ppe_event_ids).select_related('model')
        for detection in detections:
            detection_map.setdefault(detection.event_id, []).append(detection)

    context.update({
        'review_map': review_map,
        'image_url_map': image_url_map,
        'video_url_map': video_url_map,
        'frame_path_map': frame_path_map,
        'detection_map': detection_map,
    })
    return context


def serialize_overview_events(events, request):
    """
    Serialize overview events and attach backend-resolved tenant use-case
    classification.

    The frontend must never infer use-case classification from:
        - event_type
        - sub_type
        - PPE_VIOLATION
        - detection_type
        - frame path

    Classification is driven exclusively by TenantUseCase.match_config.
    """

    events = list(events)

    serializer = OverviewEventSerializer(
        events,
        many=True,
        context=build_overview_context(events, request),
    )

    data = serializer.data

    # ---------------------------------------------------------
    # Load enabled tenant use cases
    # ---------------------------------------------------------
    use_cases = list(
        get_tenant_use_cases(
            request,
            enabled_only=True
        )
    )

    if not events or not use_cases:
        return data

    # ---------------------------------------------------------
    # Build classification map
    # ---------------------------------------------------------
    classification_map = build_event_use_case_classifications(
        events,
        use_cases
    )

    use_case_map = {
        use_case.code: use_case
        for use_case in use_cases
    }

    # ---------------------------------------------------------
    # Enrich API response
    # ---------------------------------------------------------
    for event_obj, payload in zip(events, data):

        classification = classification_map.get(
            event_obj.event_id,
            {}
        )

        matched_codes = [
            code
            for code, matched in classification.items()
            if matched and code in use_case_map
        ]

        payload["use_case_codes"] = matched_codes

        # Primary display use case.
        #
        # The first configured match is used for the incident table.
        primary_code = (
            matched_codes[0]
            if matched_codes
            else None
        )

        primary_use_case = (
            use_case_map.get(primary_code)
            if primary_code
            else None
        )

        payload["use_case_code"] = primary_code

        payload["use_case_name"] = (
            primary_use_case.name
            if primary_use_case
            else None
        )

        payload["display_type"] = (
            primary_use_case.name
            if primary_use_case
            else payload.get("event_type")
        )

    return data


def format_sse_message(event_name, payload, event_id=None):
    message = []
    if event_name:
        message.append(f"event: {event_name}")
    if event_id is not None:
        message.append(f"id: {event_id}")
    message.append(f"data: {json.dumps(payload, default=str)}")
    return "\n".join(message) + "\n\n"


class EventStreamRenderer(BaseRenderer):
    media_type = 'text/event-stream'
    format = 'event-stream'
    charset = None

    def render(self, data, accepted_media_type=None, renderer_context=None):
        return data


def add_stream_timing(payload, sent_at, poll_seconds):
    enriched = dict(payload)
    enriched['stream_sent_at'] = sent_at.isoformat()
    enriched['stream_poll_interval_ms'] = int(round(max(0, poll_seconds) * 1000))
    return enriched

@method_decorator(csrf_exempt, name="dispatch")
class CustomAuthToken(ObtainAuthToken):
    authentication_classes = []
    permission_classes = []
    throttle_classes = []

    def get_throttles(self):
        return []

    def get(self, request, *args, **kwargs):
        return render(request, "api/login.html")

    def post(self, request, *args, **kwargs):
        # ---------------------------------------------------------
        # 1. Login throttling
        # ---------------------------------------------------------
        throttle = LoginRateThrottle()
        locked, remaining = throttle.is_locked(request)

        if locked:
            response = Response(
                {
                    "detail": "Too many failed login attempts.",
                    "remaining_seconds": remaining,
                },
                status=429,
            )
            response["Retry-After"] = str(remaining)
            return response

        # ---------------------------------------------------------
        # 2. Validate username/password
        # ---------------------------------------------------------
        serializer = self.serializer_class(
            data=request.data,
            context={"request": request},
        )

        try:
            serializer.is_valid(raise_exception=True)

        except ValidationError as exc:
            locked = throttle.increment_fail(request)

            if locked:
                response = Response(
                    {
                        "detail": "Too many failed login attempts.",
                        "remaining_seconds": 120,
                    },
                    status=429,
                )
                response["Retry-After"] = "120"
                return response

            raise exc

        throttle.reset(request)

        authenticated_user = serializer.validated_data["user"]

        # ---------------------------------------------------------
        # 3. Get global session configuration
        # ---------------------------------------------------------
        config = EmailAlertTracker.objects.first()

        max_sessions = (
            config.max_concurrent_sessions
            if config and config.max_concurrent_sessions
            else 1
        )

        # Protect against an invalid/negative configuration.
        max_sessions = max(1, max_sessions)

        # ---------------------------------------------------------
        # 4. Lock this user row while modifying sessions
        #
        # This prevents two simultaneous logins from both seeing
        # the same number of active sessions.
        # ---------------------------------------------------------
        with transaction.atomic():

            user = (
                User.objects
                .select_for_update()
                .get(pk=authenticated_user.pk)
            )

            # -----------------------------------------------------
            # 5. Single Login Mode
            #
            # This is GLOBAL:
            # if another USER is currently logged in, reject this
            # login.
            #
            # We deliberately check UserSession, not UserActivityLog,
            # because UserSession represents real authentication.
            # -----------------------------------------------------
            if config and config.is_single_login_mode:
                other_active_session = (
                    UserSession.objects
                    .select_related("user")
                    .filter(
                        logout_time__isnull=True
                    )
                    .exclude(user=user)
                    .order_by("login_time")
                    .first()
                )

                if other_active_session:
                    active_username = other_active_session.user.username

                    return Response(
                        {
                            "detail": (
                                "Application is in Single Login Mode. "
                                f'User "{active_username}" is currently active. '
                                "Only one user can be logged in at a time."
                            )
                        },
                        status=403,
                    )

            # -----------------------------------------------------
            # 6. Find this user's active sessions
            # -----------------------------------------------------
            active_sessions = list(
                UserSession.objects
                .filter(
                    user=user,
                    logout_time__isnull=True,
                )
                .order_by("login_time")
            )

            # -----------------------------------------------------
            # 7. Enforce max_concurrent_sessions
            #
            # If limit = 1:
            #   old device is logged out automatically.
            #
            # If limit = 3:
            #   the oldest sessions are invalidated until there
            #   is room for the new login.
            # -----------------------------------------------------
            sessions_to_close = max(
                0,
                len(active_sessions) - max_sessions + 1
            )

            if sessions_to_close > 0:
                sessions_being_replaced = active_sessions[
                    :sessions_to_close
                ]

                replacement_time = timezone.now()

                for old_session in sessions_being_replaced:
                    old_session.logout_time = replacement_time
                    old_session.save(
                        update_fields=["logout_time"]
                    )

                    # Close the activity log belonging specifically
                    # to this authentication session.
                    UserActivityLog.objects.filter(
                        session=old_session,
                        logout_time__isnull=True,
                    ).update(
                        logout_time=replacement_time
                    )

            # -----------------------------------------------------
            # 8. Create a NEW authentication token/session
            # -----------------------------------------------------
            session = UserSession.objects.create(
                user=user,
                ip_address=request.META.get("REMOTE_ADDR"),
                user_agent=request.META.get("HTTP_USER_AGENT"),
            )

            # -----------------------------------------------------
            # 9. Create audit activity record
            # -----------------------------------------------------
            UserActivityLog.objects.create(
                user=user,
                session=session,
                ip_address=request.META.get("REMOTE_ADDR"),
            )

            # -----------------------------------------------------
            # 10. Update Django last_login
            # -----------------------------------------------------
            user.last_login = timezone.now()
            user.save(update_fields=["last_login"])

            # -----------------------------------------------------
            # 11. Build user/profile information
            # -----------------------------------------------------
            role = "User"
            location = None
            status = "Active"

            profile, _ = UserProfile.objects.get_or_create(
                user=user
            )

            if user.is_superuser:
                role = "Admin"

                if profile.role != "Admin":
                    profile.role = "Admin"
                    profile.save(update_fields=["role"])
            else:
                role = profile.role

            location = profile.location
            status = profile.status

        # ---------------------------------------------------------
        # 12. Return the NEW session token
        # ---------------------------------------------------------
        return Response(
            {
                "token": session.token,
                "user_id": user.pk,
                "username": user.username,
                "is_admin": user.is_staff or user.is_superuser,
                "is_staff": user.is_staff,
                "is_superuser": user.is_superuser,
                "role": role,
                "location": location,
                "status": status,
                "can_comment": profile.can_comment,
            }
        )

class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            now = timezone.now()

            # request.auth is the exact UserSession that
            # authenticated this request.
            session = request.auth

            if isinstance(session, UserSession):
                # Invalidate this exact authentication session.
                session.logout_time = now
                session.save(
                    update_fields=["logout_time"]
                )

                # Close the activity log belonging to
                # this exact session.
                UserActivityLog.objects.filter(
                    session=session,
                    logout_time__isnull=True,
                ).update(
                    logout_time=now
                )

            print(
                f"DEBUG: Logged out user "
                f"{request.user.username}."
            )

        except Exception as e:
            print(
                f"DEBUG: Logout error for user "
                f"{request.user.username}: {str(e)}"
            )

        return Response(
            {
                "message": "Successfully logged out."
            }
        )


class OpsDashboardView(TemplateView):
    template_name = "api/ops_dashboard.html"


def _proxy_media_response(request, target_url, as_attachment=False):
    if not target_url:
        return Response({"error": "No url provided"}, status=400)

    try:
        if target_url.startswith('/media/'):
            from safelensai.urls import serve_absolute_media
            path = target_url.replace('/media/', '', 1)
            return serve_absolute_media(request, path)

        if target_url.startswith('http'):
            proxy_label = "ProxyDownload" if as_attachment else "ProxyMedia"
            print(f"[{proxy_label}] Fetching: {target_url}")
            parsed = urlparse(target_url)
            host = parsed.netloc.lower()
            path = parsed.path.lstrip('/')
            filename = path.split("/")[-1] or "incident_media"

            # 1. Determine Content-Type
            if '.s3.' in host and path:
                bucket_name = host.split('.s3.')[0]
                s3_client = get_boto3_client('s3')
                s3_object = s3_client.get_object(Bucket=bucket_name, Key=path)
                content_type = s3_object.get('ContentType') or 'application/octet-stream'
                response = StreamingHttpResponse(
                    s3_object['Body'].iter_chunks(chunk_size=8192),
                    content_type=content_type,
                )
            else:
                upstream = requests.get(target_url, stream=True, timeout=15)
                upstream.raise_for_status()
                content_type = upstream.headers.get('Content-Type', 'application/octet-stream')
                response = StreamingHttpResponse(
                    upstream.iter_content(chunk_size=8192),
                    content_type=content_type,
                )

            # 2. Force Correct Mime Type if generic
            guessed_type, _ = mimetypes.guess_type(filename)
            if (content_type == 'application/octet-stream' or not content_type) and guessed_type:
                response['Content-Type'] = guessed_type
            
            # 3. Ensure Filename has extension
            if "." not in filename:
                ext = mimetypes.guess_extension(response['Content-Type']) or ""
                filename = f"{filename}{ext}"

            disposition = 'attachment' if as_attachment else 'inline'
            response['Content-Disposition'] = f'{disposition}; filename="{filename}"'
            response['Access-Control-Allow-Origin'] = '*'
            response['Access-Control-Allow-Methods'] = 'GET, OPTIONS'
            response['Access-Control-Expose-Headers'] = 'Content-Disposition'
            return response

        return Response({"error": "Unsupported URL format"}, status=400)
    except Exception as e:
        proxy_label = "ProxyDownload" if as_attachment else "ProxyMedia"
        print(f"[{proxy_label}] Error: {str(e)}")
        return Response({"error": f"Failed to fetch media: {str(e)}"}, status=500)


class ProxyMediaView(APIView):
    """
    API endpoint to stream incident media inline through EC2.
    Use this for <img> and <video> tags when S3 objects are private.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        return _proxy_media_response(
            request=request,
            target_url=request.query_params.get('url'),
            as_attachment=False,
        )


class ProxyDownloadView(APIView):
    """
    API endpoint to securely proxy-download files from public/private S3 URLs.
    Forces 'Content-Disposition: attachment' to ensure browsers download the file
    instead of playing it, completely bypassing S3 CORS restrictions.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        return _proxy_media_response(
            request=request,
            target_url=request.query_params.get('url'),
            as_attachment=True,
        )



class EventViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows Events (AI Safety Incidents) to be viewed and created.
    Automatically applies Location-Based Role Filtering: 
    - Admins see all events. 
    - Managers/Support only see events that occurred at their assigned `location`.
    """
    def get_serializer_class(self):
        if self.action == 'create':
            return EventCreateSerializer
        return EventSerializer

    def get_permissions(self):
        if self.action == 'create':
            return [AllowAny()] # Or a more strict permission for AI nodes
        return [IsAuthenticated()]

    def get_queryset(self):
        """
        Dynamically filters the returned queryset based on the requesting user's 
        Profile Role and Profile Location.
        """
        queryset = Event.objects.all().order_by('-timestamp')
        return apply_event_access_filter(
            queryset,
            self.request
        )
    def _mark_read(self, event, user): #add is read
        """Get/create the EventReview for `event` and flip it to read, once."""
        review, _created = EventReview.objects.get_or_create(event_id=event.event_id)
        if not review.is_read:
            review.is_read = True
            review.read_at = timezone.now()
            review.read_by = user if getattr(user, 'is_authenticated', False) else None 
            review.save(update_fields=['is_read', 'read_at', 'read_by', 'updated_at'])
        return review

    def retrieve(self, request, *args, **kwargs):
        """Opening an incident's detail view marks it as read automatically."""
        instance = self.get_object()
        self._mark_read(instance, request.user)
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def mark_read(self, request, pk=None):
        """
        Explicitly mark a single incident as read, for UIs that show incidents
        in a list/card without navigating to a dedicated detail route.
        """
        event = self.get_object()
        review = self._mark_read(event, request.user)
        return Response(EventReviewSerializer(review).data)
    
   

class CameraViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoint for viewing cameras.

    Access rules:
    - Admin:
        All cameras belonging to their tenant.
    - Manager / Support:
        Only cameras belonging to their assigned TenantLocations.
    - Invalid / unauthenticated:
        No cameras.
    """

    serializer_class = CameraSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):

        user = self.request.user

        try:
            profile = user.profile
        except (AttributeError, UserProfile.DoesNotExist):
            return Camera.objects.none()

        tenant = profile.tenant

        if not tenant:
            return Camera.objects.none()

        queryset = Camera.objects.filter(
            tenant_config__tenant=tenant
        )

        # -----------------------------------------------------
        # ADMIN -> all tenant cameras
        # -----------------------------------------------------
        if profile.role in TENANT_WIDE_ROLES:
            return queryset

        # -----------------------------------------------------
        # MANAGER / SUPPORT -> assigned locations only
        # -----------------------------------------------------
        if profile.role in LOCATION_SCOPED_ROLES:

            assigned_location_ids = UserLocation.objects.filter(
                user=user,
                location__tenant=tenant
            ).values_list(
                 "location__location_id",
                flat=True
            )

            return queryset.filter(
                location_id__in=assigned_location_ids
            )

        return Camera.objects.none()

class AccessDecisionViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoint for viewing Access Decisions.

    Access is determined from the Event attached to the decision.

    Therefore the same event access rules are reused:
    - Admin -> all tenant decisions
    - Manager / Support -> assigned locations only
    """

    serializer_class = AccessDecisionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):

        queryset = (
            AccessDecision.objects
            .select_related(
                "event",
                "event__camera"
            )
            .order_by("-decision_id")
        )

        user = self.request.user

        try:
            profile = user.profile
        except (AttributeError, UserProfile.DoesNotExist):
            return AccessDecision.objects.none()

        if not profile.tenant:
            return AccessDecision.objects.none()

        # Reuse the central Event access-control logic.
        allowed_events = apply_event_access_filter(
            Event.objects.all(),
            self.request
        )

        return queryset.filter(
            event__in=allowed_events
        )

class EventReviewViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows users to attach Reviews, Statuses (Open/Closed), 
    and Comments to an unmanaged AI Event.
    """
    queryset = EventReview.objects.all().order_by('-updated_at')
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        from .serializers import EventReviewSerializer
        return EventReviewSerializer

    def get_queryset(self):
        try:
            queryset = EventReview.objects.all().order_by('-updated_at')

            allowed_events = apply_event_access_filter(
                Event.objects.all(),
                self.request
            )
            
            # Use 'event_id' instead of 'id' here
            allowed_event_ids = allowed_events.values_list('event_id', flat=True)

            queryset = queryset.filter(
                event_id__in=allowed_event_ids
            )

            event_id = self.request.query_params.get('event_id')
            if event_id:
                queryset = queryset.filter(
                    event_id=event_id
                )

            return queryset
        except Exception as e:
            print(f"CRITICAL GET_QUERYSET ERROR: {str(e)}")
            import traceback
            traceback.print_exc()
            from rest_framework.exceptions import APIException
            raise APIException(f"Error filtering reviews: {str(e)}")

    def perform_create(self, serializer):
        from .serializers import EventReviewSerializer
        """Automatically tags the reviewer as the currently authenticated user and adds timestamp to comments."""
        comments = serializer.validated_data.get('comments', '')
        if comments:
            import pytz
            from datetime import datetime
            try:
                tz = pytz.timezone('Asia/Kolkata')
                ts_str = datetime.now(tz).strftime('%d/%m/%Y %H:%M')
            except Exception:
                ts_str = datetime.now().strftime('%d/%m/%Y %H:%M')
            reviewer_name = self.request.user.username if self.request.user.is_authenticated else "System"
            # Ensure the first comment also gets the timestamp metadata
            serializer.validated_data['comments'] = f"[{ts_str} by {reviewer_name}] - {comments}"
        
        serializer.save(updated_by=self.request.user)

    def perform_update(self, serializer):
        try:
            # DEBUG LOG
            user = self.request.user
            can_comment = getattr(user.profile, 'can_comment', 'MISSING') if hasattr(user, 'profile') else 'NO PROFILE'
            print(f"DEBUG: Update attempt by user={user.username}, can_comment={can_comment}")
            
            # 1. Get current instance and validated data
            instance = self.get_object()
            new_comments = serializer.validated_data.get('comments', '') or ''
            old_history = (instance.comments or '').strip()
            
            # 1. Enforce granular comment permission
            if hasattr(self.request.user, 'profile') and not self.request.user.profile.can_comment:
                # If they don't have permission, they can't change the comments at all
                if new_comments.strip() != old_history:
                    from rest_framework.exceptions import PermissionDenied
                    raise PermissionDenied("You do not have permission to add or modify comments.")
            
            # 2. Add timestamp to the newly added portion if any
            if new_comments:
                import pytz
                from datetime import datetime
                
                # Robustly identify the new part
                stripped_new = new_comments.strip()
                if old_history and stripped_new.startswith(old_history):
                    added_part = stripped_new[len(old_history):].strip()
                else:
                    # If history was tampered or first time
                    added_part = stripped_new
                
                if added_part:
                    # Resolve IST timestamp
                    try:
                        tz = pytz.timezone('Asia/Kolkata')
                        ts_str = datetime.now(tz).strftime('%d/%m/%Y %H:%M')
                    except Exception:
                        ts_str = datetime.now().strftime('%d/%m/%Y %H:%M')
                    
                    reviewer_name = self.request.user.username if self.request.user.is_authenticated else "System"
                    
                    if old_history:
                        final_comments = old_history + "\n" + f"[{ts_str} by {reviewer_name}] - {added_part}"
                    else:
                        final_comments = f"[{ts_str} by {reviewer_name}] - {added_part}"
                                        
                    serializer.validated_data['comments'] = final_comments

            # 3. Handle updated_by safely
            save_kwargs = {}
            if self.request.user and self.request.user.is_authenticated:
                save_kwargs['updated_by'] = self.request.user
                
            serializer.save(**save_kwargs)
        except Exception as e:
            from rest_framework.exceptions import APIException
            raise APIException(detail=f"Update failed: {str(e)}")

class UserViewSet(viewsets.ModelViewSet):
    """
    API endpoint for Administrator User Management.
    Only accessible by users with `IsAdminUser` permission.
    Handles the creation, updating, and deletion of standard Users + their UserProfiles.
    """
    queryset = User.objects.all().order_by('-date_joined')
    serializer_class = UserSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):

        user = self.request.user

        try:
            tenant = user.profile.tenant
        except UserProfile.DoesNotExist:
            return User.objects.none()

        if not tenant:
            return User.objects.none()

        queryset = (
            User.objects
            .filter(profile__tenant=tenant)
            .select_related('profile')
        )

        # ---------------------------------------------------------
        # SEARCH
        # ---------------------------------------------------------
        search = self.request.query_params.get("search", "").strip()

        if search:
            # Search assigned TenantLocation -> core Location
            assigned_location_match = UserLocation.objects.filter(
                user=OuterRef("pk"),
                location__tenant=tenant,
            ).filter(
                Q(location__location__name__icontains=search) |
                Q(location__location__code__icontains=search)
            )

            queryset = queryset.filter(
                Q(username__icontains=search) |
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search) |
                Q(email__icontains=search) |
                Q(profile__phone_number__icontains=search) |
                Q(profile__location__icontains=search) |
                Q(profile__role__icontains=search) |
                Exists(assigned_location_match)
            )

        # ---------------------------------------------------------
        # ROLE FILTER
        # ---------------------------------------------------------
        role = self.request.query_params.get("role")

        if role in Role.values:
            queryset = queryset.filter(profile__role=role)

        # ---------------------------------------------------------
        # STATUS FILTER
        # ---------------------------------------------------------
        status_filter = self.request.query_params.get("status")

        if status_filter == "Active":
            queryset = queryset.filter(is_active=True)

        elif status_filter == "Inactive":
            queryset = queryset.filter(is_active=False)

        # ---------------------------------------------------------
        # SORTING
        # ---------------------------------------------------------
        ordering = self.request.query_params.get(
            "ordering",
            "-date_joined"
        )

        allowed_orderings = {
            "last_login",
            "-last_login",
            "date_joined",
            "-date_joined",
            "username",
            "-username",
        }

        if ordering not in allowed_orderings:
            ordering = "-date_joined"

        queryset = queryset.order_by(ordering)

        return queryset

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["request"] = self.request
        return context

    def perform_update(self, serializer):
        """
        Saves user updates. If the Administrator changed the user's password, 
        this function acts as a forced session termination — deleting their JWT 
        tokens and closing all Active sessions in UserActivityLog instantly.
        """
        user = serializer.save()
        
        # If password was updated, invalidate all tokens and sessions
        if 'password' in serializer.validated_data:
            from rest_framework.authtoken.models import Token
            Token.objects.filter(user=user).delete()
            
            # Close all active sessions
            UserActivityLog.objects.filter(user=user, logout_time__isnull=True).update(logout_time=timezone.now())

    def perform_destroy(self, instance):
        """Delete user's tokens and sessions so they are logged out immediately."""
        from rest_framework.authtoken.models import Token
        Token.objects.filter(user=instance).delete()
        UserActivityLog.objects.filter(user=instance, logout_time__isnull=True).update(logout_time=timezone.now())
        instance.delete()

from .serializers import UserActivityLogSerializer

class UserActivityLogViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoint for tracing Security & Login Audits.
    Allows administrators to see exact timestamp and IP addresses of every user login/logout.
    Restricted to admin users only.
    """
    queryset = UserActivityLog.objects.all().order_by('-login_time')
    serializer_class = UserActivityLogSerializer
    permission_classes = [IsAdminUser]

class LocationListView(APIView):
    """
    Returns locations available to the authenticated user.

    Admin:
        All locations belonging to their tenant.

    Manager / Support:
        Only assigned locations.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):

        user = request.user

        try:
            profile = user.profile
        except (AttributeError, UserProfile.DoesNotExist):
            return Response(
                {
                    "detail": "User profile not found."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        tenant = profile.tenant

        if not tenant:
            return Response([])

        # ---------------------------------------------------------
        # ADMIN -> all tenant locations
        # ---------------------------------------------------------
        if profile.role in TENANT_WIDE_ROLES:

            locations = TenantLocation.objects.filter(
                tenant=tenant
            ).values_list(
               "location__name",
                flat=True
            )

            return Response(list(locations))

        # ---------------------------------------------------------
        # MANAGER / SUPPORT -> assigned locations
        # ---------------------------------------------------------
        if profile.role in LOCATION_SCOPED_ROLES:

            locations = TenantLocation.objects.filter(
                tenant=tenant,
                id__in=UserLocation.objects.filter(
                    user=user,
                    location__tenant=tenant
                ).values_list(
                    "location_id",
                    flat=True
                )
            ).values_list(
                "location__name",
                flat=True
            )

            return Response(list(locations))

        return Response([])

class RoleListView(APIView):
    """
    API endpoint returning the list of valid user roles directly from the Database model choices.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(Role.labels)
    
def use_case_matches_event(
    use_case,
    event,
    detections=None,
    frame_path=None
):
    """
    Generic Python-side matcher.

    Uses the same match_config semantics as build_use_case_query().

    Matching rules:

        Different fields = AND

        Multiple values inside one field = OR

    Example:

        {
            "event_type": [
                "PPE_VIOLATION"
            ],
            "detection_type": [
                "NO_GOGGLE",
                "GOGGLE"
            ]
        }

    Means:

        event_type == PPE_VIOLATION
        AND
        (
            detection_type == NO_GOGGLE
            OR
            detection_type == GOGGLE
        )
    """

    config = use_case.match_config or {}

    event_type = (
        event.event_type or ""
    ).strip().upper()

    detection_list = detections or []

    # =========================================================
    # EVENT TYPE
    # =========================================================

    event_type_rules = _as_upper_list(
        config.get("event_type")
    )

    if event_type_rules:
        event_type_match = any(
            event_type == value
            for value in event_type_rules
        )

        if not event_type_match:
            return False

    # =========================================================
    # DETECTION TYPE
    # =========================================================

    detection_type_rules = _as_upper_list(
        config.get("detection_type")
    )

    if detection_type_rules:

        detection_type_match = False

        for detection in detection_list:

            detection_type = (
                detection.detection_type or ""
            ).strip().upper()

            if detection_type in detection_type_rules:
                detection_type_match = True
                break

        if not detection_type_match:
            return False

    # =========================================================
    # DETECTION VALUE
    # =========================================================

    detection_value_rules = _as_lower_list(
        config.get("detection_value")
    )

    if detection_value_rules:

        detection_value_match = False

        for detection in detection_list:

            detection_value = (
                detection.detection_value or ""
            ).strip().lower()

            if detection_value in detection_value_rules:
                detection_value_match = True
                break

        if not detection_value_match:
            return False

    # =========================================================
    # MISSING PPE ITEM
    # =========================================================

    missing_item_rules = _as_lower_list(
        config.get("missing_item")
    )

    if missing_item_rules:

        missing_item_match = False

        for detection in detection_list:

            details = (
                detection.detection_details
                or {}
            )

            missing_item = ""

            if isinstance(details, dict):
                missing_item = str(
                    details.get(
                        "missing_item",
                        ""
                    )
                ).strip().lower()

            if missing_item in missing_item_rules:
                missing_item_match = True
                break

        if not missing_item_match:
            return False

    # =========================================================
    # FRAME PATH
    # =========================================================

    frame_path_rules = _as_lower_list(
        config.get("frame_path")
    )

    if frame_path_rules:

        if not frame_path:
            return False

        path = str(frame_path).lower()

        frame_path_match = any(
            value in path
            for value in frame_path_rules
        )

        if not frame_path_match:
            return False

    # =========================================================
    # NO RULES
    # =========================================================

    # An empty match_config should never accidentally
    # classify every event as this use case.
    if not any([
        event_type_rules,
        detection_type_rules,
        detection_value_rules,
        missing_item_rules,
        frame_path_rules,
    ]):
        return False

    return True


def classify_incident(
    event,
    use_cases,
    detections=None,
    frame_path=None
):
    """
    Generic incident classification.

    Returns:

        {
            "FALL_DETECTION": True,
            "NO_HARD_HAT": False,
            ...
        }

    The keys come directly from TenantUseCase.code.
    """

    classification = {}

    for use_case in use_cases:

        classification[use_case.code] = (
            use_case_matches_event(
                use_case,
                event,
                detections=detections,
                frame_path=frame_path
            )
        )

    return classification

def build_incident_classification_maps(events):
    """
    Bulk-load detections and frame paths for a collection of events.

    Prevents N+1 database queries when classification is required.
    """

    event_ids = [
        event.event_id
        for event in events
    ]

    if not event_ids:
        return {}, {}

    # -------------------------------------------------
    # Bulk detections
    # -------------------------------------------------

    detections_map = defaultdict(list)

    detections = EventDetection.objects.filter(
        event_id__in=event_ids
    ).only(
        'event_id',
        'detection_type',
        'detection_value',
        'detection_details',
    )

    for detection in detections:
        detections_map[detection.event_id].append(detection)

    # -------------------------------------------------
    # Bulk media mappings
    # -------------------------------------------------

    media_rows = list(
        EventMediaMap.objects.filter(
            event_id__in=event_ids,
            media_type='FRAME'
        ).values(
            'event_id',
            'media_id'
        )
    )

    frame_ids = [
        row['media_id']
        for row in media_rows
    ]

    frame_map = {}

    if frame_ids:
        frame_map = {
            frame.frame_id: frame.storage_path
            for frame in Frame.objects.filter(
                frame_id__in=frame_ids
            ).only(
                'frame_id',
                'storage_path'
            )
        }

    # -------------------------------------------------
    # Event → frame path
    # -------------------------------------------------

    frame_path_map = {}

    for row in media_rows:
        storage_path = frame_map.get(row['media_id'])

        if storage_path:
            frame_path_map[row['event_id']] = storage_path

    return detections_map, frame_path_map

def build_event_use_case_classifications(
    events,
    use_cases
):
    """
    Classify a collection of events against tenant use cases.

    Returns:

        {
            event_id: {
                "FALL_DETECTION": True,
                "NO_HARD_HAT": False,
                ...
            }
        }
    """

    detections_map, frame_path_map = (
        build_incident_classification_maps(
            events
        )
    )

    classification_map = {}

    for event in events:

        classification_map[event.event_id] = (
            classify_incident(
                event,
                use_cases=use_cases,
                detections=detections_map.get(
                    event.event_id,
                    []
                ),
                frame_path=frame_path_map.get(
                    event.event_id
                ),
            )
        )

    return classification_map

def resolve_event_use_case(
    event,
    use_cases,
    classification
):
    """
    Resolve one primary TenantUseCase for an event.

    TenantUseCase.match_config remains the single source
    of truth for event classification.

    Returns:
        {
            "code": "NO_BOOT",
            "name": "No Boot"
        }

    or None when no enabled use case matches.
    """

    for use_case in use_cases:
        if classification.get(use_case.code, False):
            return {
                "code": use_case.code,
                "name": use_case.name,
            }

    return None

def filter_incident_queryset(
    queryset,
    event_type,
    request=None
):
    """
    Filter events by TenantUseCase code.

    The selected type is matched against TenantUseCase.code.
    """

    if not event_type:
        return queryset

    if str(event_type).lower() == 'all':
        return queryset

    if not request:
        return queryset.none()

    selected_code = str(
        event_type
    ).strip().upper()

    use_case = (
        get_tenant_use_cases(
            request,
            enabled_only=True
        )
        .filter(
            code__iexact=selected_code
        )
        .first()
    )

    if not use_case:
        return queryset.none()

    condition = build_use_case_query(
        use_case
    )

    if not condition:
        return queryset.none()

    return queryset.filter(
        condition
    ).distinct()

#====================================================================================
def get_tenant_use_cases(request, enabled_only=True):
    """
    Return use cases configured for the authenticated user's tenant.

    This is the single source of truth for tenant use-case configuration.
    """

    user = request.user

    if not user.is_authenticated:
        return TenantUseCase.objects.none()

    try:
        tenant = user.profile.tenant
    except (AttributeError, UserProfile.DoesNotExist):
        return TenantUseCase.objects.none()

    if not tenant:
        return TenantUseCase.objects.none()

    queryset = TenantUseCase.objects.filter(
        tenant=tenant
    )

    if enabled_only:
        queryset = queryset.filter(enabled=True)

    return queryset.order_by('name')


def _as_upper_list(values):
    """
    Normalize configuration values into uppercase strings.

    Supports either:
        "PPE_VIOLATION"

    or:
        ["PPE_VIOLATION", "FALL_DETECTION"]
    """
    if not values:
        return []

    if isinstance(values, str):
        values = [values]

    return [
        str(value).strip().upper()
        for value in values
        if str(value).strip()
    ]


def _as_lower_list(values):
    """
    Normalize configuration values into lowercase strings.

    Supports either:
        "helmet"

    or:
        ["helmet", "hard_hat"]
    """
    if not values:
        return []

    if isinstance(values, str):
        values = [values]

    return [
        str(value).strip().lower()
        for value in values
        if str(value).strip()
    ]


def build_use_case_query(use_case):
    """
    Convert TenantUseCase.match_config into a Django Q object.

    ---------------------------------------------------------
    MATCH CONFIG FORMAT
    ---------------------------------------------------------

    {
        "event_type": [
            "PPE_VIOLATION"
        ],
        "detection_type": [
            "NO_GOGGLE",
            "GOGGLE"
        ]
    }

    ---------------------------------------------------------
    MATCHING SEMANTICS
    ---------------------------------------------------------

    Different fields = AND

        event_type
        AND detection_type
        AND detection_value
        AND missing_item
        AND frame_path

    Multiple values inside the same field = OR

        detection_type:
            ["NO_GOGGLE", "NO_MASK"]

        means:

            NO_GOGGLE OR NO_MASK

    ---------------------------------------------------------
    SUPPORTED FIELDS
    ---------------------------------------------------------

    event_type
    detection_type
    detection_value
    missing_item
    frame_path

    ---------------------------------------------------------
    EXAMPLES
    ---------------------------------------------------------

    General use case:

        {
            "event_type": [
                "FALL_DETECTION"
            ]
        }

    PPE use case:

        {
            "event_type": [
                "PPE_VIOLATION"
            ],
            "detection_type": [
                "NO_HELMET"
            ]
        }

    Multiple detection types:

        {
            "event_type": [
                "PPE_VIOLATION"
            ],
            "detection_type": [
                "NO_GOGGLE",
                "NO_GLASS"
            ]
        }

    """

    config = use_case.match_config or {}

    # Start with no restriction.
    # Each configured field will then be combined using AND.
    conditions = Q()

    # =========================================================
    # EVENT TYPE
    # =========================================================

    event_type_values = _as_upper_list(
        config.get("event_type")
    )

    if event_type_values:
        event_type_condition = Q()

        for value in event_type_values:
            event_type_condition |= Q(
                event_type__iexact=value
            )

        conditions &= event_type_condition

    # =========================================================
    # DETECTION TYPE
    # =========================================================

    detection_type_values = _as_upper_list(
        config.get("detection_type")
    )

    if detection_type_values:
        detection_type_condition = Q()

        for value in detection_type_values:
            detection_type_condition |= Q(
                detections__detection_type__iexact=value
            )

        conditions &= detection_type_condition

    # =========================================================
    # DETECTION VALUE
    # =========================================================

    detection_value_values = _as_lower_list(
        config.get("detection_value")
    )

    if detection_value_values:
        detection_value_condition = Q()

        for value in detection_value_values:
            detection_value_condition |= Q(
                detections__detection_value__iexact=value
            )

        conditions &= detection_value_condition

    # =========================================================
    # MISSING PPE ITEM
    # =========================================================

    missing_item_values = _as_lower_list(
        config.get("missing_item")
    )

    if missing_item_values:
        missing_item_condition = Q()

        for value in missing_item_values:
            missing_item_condition |= Q(
                detections__detection_details__missing_item__iexact=value
            )

        conditions &= missing_item_condition

    # =========================================================
    # FRAME STORAGE PATH
    # =========================================================

    frame_path_values = _as_lower_list(
        config.get("frame_path")
    )

    if frame_path_values:

        frame_condition = Q()

        for value in frame_path_values:
            frame_condition |= Q(
                storage_path__icontains=value
            )

        frame_ids = Frame.objects.filter(
            frame_condition
        ).values_list(
            "frame_id",
            flat=True
        )

        frame_event_ids = EventMediaMap.objects.filter(
            media_type="FRAME",
            media_id__in=frame_ids
        ).values_list(
            "event_id",
            flat=True
        )

        conditions &= Q(
            event_id__in=frame_event_ids
        )

    return conditions


def filter_enabled_tenant_use_cases(queryset, request):
    """
    Restrict events to use cases enabled for the authenticated tenant.

    IMPORTANT:
        There are NO use-case-specific Python if-statements here.

        The matching behavior comes entirely from:
            TenantUseCase.match_config
    """

    use_cases = get_tenant_use_cases(
        request,
        enabled_only=True
    )

    conditions = Q()

    for use_case in use_cases:
        use_case_query = build_use_case_query(
            use_case
        )

        if use_case_query:
            conditions |= use_case_query

    if not conditions:
        return queryset.none()

    return queryset.filter(
        conditions
    ).distinct()

def build_camera_incident_export_data(events, request):
    use_cases = list(
        get_tenant_use_cases(request, enabled_only=True)
    )

    detections_map, frame_path_map = build_incident_classification_maps(events)

    tenant = request.user.profile.tenant

    cameras_queryset = Camera.objects.select_related(
        'location'
    ).filter(
        tenant_config__tenant=tenant,
        tenant_config__enabled=True
    )

    role = request.user.profile.role

    if role in LOCATION_SCOPED_ROLES:
        assigned_location_ids = list(
            UserLocation.objects.filter(
                user=request.user
            ).values_list('location__location_id', flat=True)
        )

        cameras_queryset = cameras_queryset.filter(
            location_id__in=assigned_location_ids
        )

    cameras = {}

    for camera in cameras_queryset.order_by('name'):
        cameras[camera.camera_id] = {
            'camera': camera.name,
            'location': camera.location.name,
            'counts': {
                use_case.code: 0
                for use_case in use_cases
            }
        }

    for event in events:
        camera = event.camera

        if camera.camera_id not in cameras:
            continue

        classification = classify_incident(
            event,
            use_cases,
            detections=detections_map.get(
                event.event_id,
                []
            ),
            frame_path=frame_path_map.get(
                event.event_id
            )
        )

        for use_case in use_cases:
            if classification.get(
                use_case.code,
                False
            ):
                cameras[
                    camera.camera_id
                ]['counts'][
                    use_case.code
                ] += 1

    return {
        'use_cases': use_cases,
        'cameras': list(cameras.values())
    }


class OverviewIncidentPagination(PageNumberPagination):
    """Server-side pagination for the Overview incident table."""
    page_size = 5
    page_size_query_param = "page_size"
    max_page_size = 50

class OverviewViewSet(viewsets.ViewSet):
    """
    Complex dynamic ViewSet strictly generating aggregated data schemas 
    specifically tailored for rendering Recharts components on the React Dashboard.
    """
    pagination_class = None
    
    def _apply_access_filter(self, queryset, request):
        # Keep the existing tenant/role access rules.
        queryset = apply_event_access_filter(queryset, request)

        # Superadmin can see rejected events.
        # All other users (Admin, Manager, Support) must not receive
        # rejected events from the Overview APIs.
        if not request.user.is_superuser:
            rejected_event_ids = EventReview.objects.filter(
                status__iexact="rejected"
            ).values_list(
                "event_id",
                flat=True
            )

            queryset = queryset.exclude(
                event_id__in=rejected_event_ids
            )

        return queryset

    def _build_overview_context(self, events, request):
        return build_overview_context(events, request)

    def _to_project_datetime(self, value, tz):
        if settings.USE_TZ:
            if timezone.is_naive(value):
                return timezone.make_aware(value, tz)
            return timezone.localtime(value, tz)
        if timezone.is_aware(value):
            return timezone.make_naive(value, tz)
        return value

    def _resolve_time_window(self, request, default_range=None):
        tz = timezone.get_current_timezone()
        now = self._to_project_datetime(timezone.now(), tz)

        date_str = request.query_params.get('date')
        start_str = request.query_params.get('start_date')
        end_str = request.query_params.get('end_date')

        time_range = (
            request.query_params.get('time_range')
            or default_range
            or ''
        ).lower()

        # -------------------------------------------------
        # Exact date
        # -------------------------------------------------

        if date_str:
            try:
                target_date = datetime.strptime(
                    date_str,
                    '%Y-%m-%d'
                ).date()

                start_dt = self._to_project_datetime(
                    datetime.combine(
                        target_date,
                        datetime.min.time()
                    ),
                    tz
                )

                end_dt = start_dt + timedelta(days=1)

                return start_dt, end_dt, time_range, now, True

            except ValueError:
                return None, None, time_range, now, False

        # -------------------------------------------------
        # Custom date range
        # -------------------------------------------------

        if start_str and end_str:
            try:
                start_date = datetime.strptime(
                    start_str,
                    '%Y-%m-%d'
                ).date()

                end_date = datetime.strptime(
                    end_str,
                    '%Y-%m-%d'
                ).date()

                start_dt = self._to_project_datetime(
                    datetime.combine(
                        start_date,
                        datetime.min.time()
                    ),
                    tz
                )

                # Exclusive next-day boundary
                end_dt = self._to_project_datetime(
                    datetime.combine(
                        end_date + timedelta(days=1),
                        datetime.min.time()
                    ),
                    tz
                )

                return start_dt, end_dt, time_range, now, True

            except ValueError:
                return None, None, time_range, now, False

        # -------------------------------------------------
        # Today
        # -------------------------------------------------

        if time_range == 'today':

            start_dt = now.replace(
                hour=0,
                minute=0,
                second=0,
                microsecond=0
            )

            # Exclusive tomorrow
            end_dt = start_dt + timedelta(days=1)

            return start_dt, end_dt, time_range, now, True

        # -------------------------------------------------
        # Week = past 7 calendar days ending yesterday (excluding today)
        # -------------------------------------------------

        if time_range == 'week':

            end_dt = now.replace(
                hour=0,
                minute=0,
                second=0,
                microsecond=0
            )  # Midnight of today (exclusive upper bound)

            start_dt = end_dt - timedelta(days=7)

            return start_dt, end_dt, time_range, now, True

        # -------------------------------------------------
        # Month = past 30 calendar days ending yesterday (excluding today)
        # -------------------------------------------------

        if time_range == 'month':

            end_dt = now.replace(
                hour=0,
                minute=0,
                second=0,
                microsecond=0
            )  # Midnight of today (exclusive upper bound)

            start_dt = end_dt - timedelta(days=30)

            return start_dt, end_dt, time_range, now, True
    
        return None, None, time_range, now, False


    def _apply_time_window(
        self,
        queryset,
        request,
        default_range=None
    ):
        (
            start_dt,
            end_dt,
            time_range,
            now,
            use_exclusive_end
        ) = self._resolve_time_window(
            request,
            default_range
        )

        if start_dt and end_dt:

            if use_exclusive_end:
                queryset = queryset.filter(
                    timestamp__gte=start_dt,
                    timestamp__lt=end_dt
                )
            else:
                queryset = queryset.filter(
                    timestamp__gte=start_dt,
                    timestamp__lte=end_dt
                )

        return (
            queryset,
            time_range,
            now,
            start_dt,
            end_dt
        )

    @action(detail=False, methods=['get'])
    def events(self, request):
        """
        Return paginated Overview incidents.

        Supported query parameters:
            date
            start_date
            end_date
            time_range
            type          -> incident/use-case code
            location_id   -> location id
            camera_id     -> camera id
            status        -> Open / Closed / Rejected
            page          -> page number
            page_size     -> number of incidents per page (frontend uses 5)

        IMPORTANT: All filters are applied BEFORE pagination so every page
        contains up to 5 incidents from the selected filter result set.
        """

        event_type = request.query_params.get('type')
        location_id = request.query_params.get('location_id')
        camera_id = request.query_params.get('camera_id')
        status_filter = request.query_params.get('status')

        queryset = self._apply_access_filter(
            Event.objects
            .select_related('camera', 'camera__location')
            .prefetch_related('detections')
            .all()
            .order_by('-timestamp'),
            request,
        )

        # 1. Date/time filtering
        queryset, _, _, _, _ = self._apply_time_window(
            queryset,
            request
        )

        # 2. Enabled tenant use cases
        queryset = filter_enabled_tenant_use_cases(
            queryset,
            request
        )

        # 3. Incident/use-case type filtering
        queryset = filter_incident_queryset(
            queryset,
            event_type,
            request
        )

        # 4. Location filtering
        if location_id and str(location_id).strip().lower() not in (
            '', 'all', 'all locations'
        ):
            try:
                queryset = queryset.filter(
                    camera__location_id=int(location_id)
                )
            except (TypeError, ValueError):
                queryset = queryset.none()

        # 5. Camera filtering
        if camera_id and str(camera_id).strip().lower() not in (
            '', 'all', 'all cameras'
        ):
            try:
                queryset = queryset.filter(
                    camera_id=int(camera_id)
                )
            except (TypeError, ValueError):
                queryset = queryset.none()

        # 6. Review-status filtering. Event status is derived from EventReview:
        #    no review = Open, review.status = Open/Closed/Rejected otherwise.
        if status_filter and str(status_filter).strip().lower() not in (
            '', 'all', 'all status'
        ):
            normalized_status = str(status_filter).strip().lower()

            review_status = EventReview.objects.filter(
                event_id=OuterRef('event_id')
            ).values('status')[:1]

            if normalized_status == 'open':
                queryset = queryset.annotate(
                    overview_review_status=Subquery(review_status)
                ).filter(
                    Q(overview_review_status__isnull=True)
                    | Q(overview_review_status__iexact='open')
                    | Q(overview_review_status__exact='')
                )
            elif normalized_status in ('closed', 'rejected'):
                queryset = queryset.annotate(
                    overview_review_status=Subquery(review_status)
                ).filter(
                    overview_review_status__iexact=normalized_status
                )
            else:
                queryset = queryset.none()

        # IMPORTANT: pagination happens only after every filter above.
        paginator = OverviewIncidentPagination()
        page = paginator.paginate_queryset(
            queryset,
            request,
            view=self
        )

        serialized_events = serialize_overview_events(
            page,
            request
        )

        return paginator.get_paginated_response(
            serialized_events
        )

    @action(detail=False, methods=['get'])
    def latest(self, request):
        """
        Returns the N most recent incidents for the live alert panel.
        Supports optional `since_id` query param for efficient incremental polling:
          - Without since_id: returns the `limit` most recent events
          - With since_id: returns only events with event_id > since_id (new events only)
        
        Now also respects time_range (defaults to today) to prevent showing 
        yesterday's data in the today-only dashboard views.

        Query params:
          limit       (int, default=10): Max events to return when not using since_id
          since_id    (int, optional):  Only return events newer than this event_id
          time_range  (str, optional):  Filter by today, week, month
        """
        since_id = request.query_params.get('since_id')
        limit = int(request.query_params.get('limit', 10))
        time_range = request.query_params.get('time_range', 'today')

        queryset = self._apply_access_filter(
            Event.objects.select_related('camera').all().order_by('-event_id'),
            request,
        )
        queryset, _, _, _, _ = self._apply_time_window(queryset, request, default_range=time_range)

        queryset = filter_enabled_tenant_use_cases(
            queryset,
            request
        )
        
        if since_id:
            try:
                queryset = queryset.filter(event_id__gt=int(since_id))
            except (ValueError, TypeError):
                pass
        else:
            queryset = queryset[:limit]

        events = list(queryset)
        return Response(serialize_overview_events(events, request))

    @action(detail=False, methods=['get'])
    def summary(self, request):
        """
        Get summary statistics with breakdown by specific incident types.
        Returns counts and percentages for Fall, Intrusion, Helmet, Vest, and other PPE.
        """
        event_type = request.query_params.get('type')
        
        queryset = self._apply_access_filter(
            Event.objects.all(),
            request
        )

        queryset, time_range, now, start_dt, end_dt = (
            self._apply_time_window(
                queryset,
                request
            )
        )

        queryset = filter_enabled_tenant_use_cases(
            queryset,
            request
        )
        # -------------------------------------------------
        # Previous equivalent period
        # -------------------------------------------------

        prev_start = None
        prev_end = None

        if start_dt and end_dt:
            period_duration = end_dt - start_dt

            prev_end = start_dt
            prev_start = start_dt - period_duration

        queryset = filter_incident_queryset(
            queryset,
            event_type,
            request
        )

        # Apply the same dashboard filters used by the paginated incidents
        # endpoint BEFORE calculating summary counts. This keeps metric cards
        # independent from the current 5-row table page.
        location_id = request.query_params.get('location_id')
        camera_id = request.query_params.get('camera_id')
        status_filter = request.query_params.get('status')

        if location_id and str(location_id).strip().lower() not in (
            '', 'all', 'all locations'
        ):
            try:
                queryset = queryset.filter(camera__location_id=int(location_id))
            except (TypeError, ValueError):
                queryset = queryset.none()

        if camera_id and str(camera_id).strip().lower() not in (
            '', 'all', 'all cameras'
        ):
            try:
                queryset = queryset.filter(camera_id=int(camera_id))
            except (TypeError, ValueError):
                queryset = queryset.none()

        # Event status is derived from EventReview. No review/open => Open.
        # The default dashboard scope excludes Rejected from total counts.
        if status_filter and str(status_filter).strip().lower() not in (
            '', 'all', 'all status'
        ):
            normalized_status = str(status_filter).strip().lower()
            review_status = EventReview.objects.filter(
                event_id=OuterRef('event_id')
            ).values('status')[:1]

            queryset = queryset.annotate(
                overview_review_status=Subquery(review_status)
            )

            if normalized_status == 'open':
                queryset = queryset.filter(
                    Q(overview_review_status__isnull=True)
                    | Q(overview_review_status__iexact='open')
                    | Q(overview_review_status__exact='')
                )
            elif normalized_status in ('closed', 'rejected'):
                queryset = queryset.filter(
                    overview_review_status__iexact=normalized_status
                )
            else:
                queryset = queryset.none()
        else:
            # All Status = Open + Closed. Rejected is displayed separately
            # but must not inflate the main incident total.
            review_status = EventReview.objects.filter(
                event_id=OuterRef('event_id')
            ).values('status')[:1]
            queryset = queryset.annotate(
                overview_review_status=Subquery(review_status)
            ).filter(
                Q(overview_review_status__isnull=True)
                | Q(overview_review_status__iexact='open')
                | Q(overview_review_status__iexact='closed')
                | Q(overview_review_status__exact='')
            )

        # -------------------------------------------------
        # Component-level classification & Use Cases
        # -------------------------------------------------
        use_cases = list(
            get_tenant_use_cases(
                request,
                enabled_only=True
            )
        )
        events = list(queryset)
        total_events = len(events)

        classification_map = build_event_use_case_classifications(
            events,
            use_cases
        )

        use_case_counts = {
            use_case.code: 0
            for use_case in use_cases
        }

        for event in events:
            classification = classification_map.get(
                event.event_id,
                {}
            )
            for use_case in use_cases:
                if classification.get(use_case.code, False):
                    use_case_counts[use_case.code] += 1

        # --- Functional Historical Trend Data Pipeline ---
        prev_use_case_counts = {use_case.code: 0 for use_case in use_cases}
        prev_total_events = 0

        if prev_start and prev_end:
            prev_qs = self._apply_access_filter(
                Event.objects.all(),
                request
            ).filter(
                timestamp__gte=prev_start,
                timestamp__lt=prev_end
            )

            prev_qs = filter_enabled_tenant_use_cases(
                prev_qs,
                request
            )
            
            prev_qs = filter_incident_queryset(
                prev_qs,
                event_type,
                request
            )
            prev_events = list(prev_qs)
            prev_total_events = len(prev_events)

            prev_classification_map = build_event_use_case_classifications(
                prev_events,
                use_cases
            )

            for event in prev_events:
                classification = prev_classification_map.get(
                    event.event_id,
                    {}
                )
                for use_case in use_cases:
                    if classification.get(use_case.code, False):
                        prev_use_case_counts[use_case.code] += 1

        # Construct dynamic use case summary structure
        use_case_summary = {}
        for use_case in use_cases:
            count = use_case_counts.get(use_case.code, 0)
            prev_count = prev_use_case_counts.get(use_case.code, 0)
            
            percentage = (
                count / total_events * 100
                if total_events > 0
                else 0
            )

            use_case_summary[use_case.code] = {
                'code': use_case.code,
                'name': use_case.name,
                'count': count,
                'prev_count': prev_count,
                'percentage': round(percentage, 1),
                'enabled': use_case.enabled,
                'show_on_dashboard': use_case.show_on_dashboard,
                'show_in_filters': use_case.show_in_filters,
            }

        # Keep a complete status breakdown for the Today/Range dashboard.
        # These values are calculated from the full filtered queryset, never
        # from the 5-row paginated events response.
        status_summary = {
            'open': 0,
            'closed': 0,
            'rejected': 0,
        }

        status_rows = EventReview.objects.filter(
            event_id__in=[event.event_id for event in events]
        ).values('event_id', 'status')
        review_status_map = {
            row['event_id']: (row.get('status') or 'open').strip().lower()
            for row in status_rows
        }
        for event in events:
            status_value = review_status_map.get(event.event_id, 'open')
            if status_value not in status_summary:
                status_value = 'open'
            status_summary[status_value] += 1

        data = {
            'total_events': total_events,
            'prev_total_events': prev_total_events,
            'use_cases': use_case_summary,
            'status_summary': status_summary,
        }

        if event_type and event_type != 'all':
            type_count = total_events
            percentage = (
                type_count / total_events * 100
            ) if total_events > 0 else 0

            data['type_count'] = type_count
            data['percentage'] = round(percentage, 1)

        return Response(data)

    @action(detail=False, methods=['get'])
    def graph(self, request):

        time_range = (
            request.query_params.get(
                'time_range',
                'today'
            )
            .lower()
        )

        event_type = request.query_params.get('type')

        queryset = self._apply_access_filter(
            Event.objects.all(),
            request
        )

        queryset, time_range, now, start_dt, end_dt = (
            self._apply_time_window(
                queryset,
                request,
                default_range=time_range
            )
        )

        queryset = filter_enabled_tenant_use_cases(
            queryset,
            request
        )
        
        queryset = filter_incident_queryset(
            queryset,
            event_type,
            request
        )

        # Apply the SAME dashboard filters as the paginated table and summary.
        # These are applied BEFORE grouping so pagination can never affect
        # Today/Range Incidents Over Time.
        location_id = request.query_params.get('location_id')
        camera_id = request.query_params.get('camera_id')
        status_filter = request.query_params.get('status')

        if location_id and str(location_id).strip().lower() not in (
            '', 'all', 'all locations'
        ):
            try:
                queryset = queryset.filter(camera__location_id=int(location_id))
            except (TypeError, ValueError):
                queryset = queryset.none()

        if camera_id and str(camera_id).strip().lower() not in (
            '', 'all', 'all cameras'
        ):
            try:
                queryset = queryset.filter(camera_id=int(camera_id))
            except (TypeError, ValueError):
                queryset = queryset.none()

        # Event status comes from EventReview. No review/open => Open.
        # With All Status, rejected is excluded from the main dashboard scope.
        review_status = EventReview.objects.filter(
            event_id=OuterRef('event_id')
        ).values('status')[:1]

        queryset = queryset.annotate(
            overview_review_status=Subquery(review_status)
        )

        if status_filter and str(status_filter).strip().lower() not in (
            '', 'all', 'all status'
        ):
            normalized_status = str(status_filter).strip().lower()

            if normalized_status == 'open':
                queryset = queryset.filter(
                    Q(overview_review_status__isnull=True)
                    | Q(overview_review_status__iexact='open')
                    | Q(overview_review_status__exact='')
                )
            elif normalized_status in ('closed', 'rejected'):
                queryset = queryset.filter(
                    overview_review_status__iexact=normalized_status
                )
            else:
                queryset = queryset.none()
        else:
            queryset = queryset.filter(
                Q(overview_review_status__isnull=True)
                | Q(overview_review_status__iexact='open')
                | Q(overview_review_status__iexact='closed')
                | Q(overview_review_status__exact='')
            )

        return self._get_grouped_graph_data(
            queryset,
            time_range,
            now,
            start_dt,
            end_dt,
            request
        )
    
    
    def _get_simple_graph_data(self, queryset, time_range, now):
        """Original simple graph data for filtered views"""
        data_points = []
        
        if time_range == 'today':
            start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
            queryset = queryset.filter(timestamp__gte=start_time, timestamp__lte=now)
            
            stats = queryset.annotate(hour=TruncHour('timestamp')).values('hour').annotate(count=Count('event_id')).order_by('hour')
            
            hours = {start_time + timedelta(hours=i): 0 for i in range(24)}
            for item in stats:
                if item['hour']:
                    hours[item['hour']] = item['count']
            
            for time_val, count in sorted(hours.items()):
                data_points.append({'label': time_val.strftime('%H:%M'), 'count': count})
                
        elif time_range == 'week':
            start_time = now - timedelta(days=7)
            queryset = queryset.filter(timestamp__gte=start_time, timestamp__lte=now)
            stats = queryset.annotate(day=TruncDay('timestamp')).values('day').annotate(count=Count('event_id')).order_by('day')
            
            total_days = (now.date() - start_time.date()).days + 1
            days = {(start_time + timedelta(days=i)).date(): 0 for i in range(total_days)}
            for item in stats:
                if item['day']:
                    days[item['day'].date()] = item['count']
            
            for date_val, count in sorted(days.items()):
                data_points.append({'label': date_val.strftime('%a'), 'count': count})
                
        elif time_range == 'month':
             start_time = now - timedelta(days=30)
             queryset = queryset.filter(timestamp__gte=start_time, timestamp__lte=now)
             
             stats = queryset.annotate(day=TruncDay('timestamp')).values('day').annotate(count=Count('event_id')).order_by('day')
             
             total_days = (now.date() - start_time.date()).days + 1
             days = {(start_time + timedelta(days=i)).date(): 0 for i in range(total_days)}
             for item in stats:
                 if item['day']:
                     days[item['day'].date()] = item['count']
             
             for date_val, count in sorted(days.items()):
                 data_points.append({'label': date_val.strftime('%b %d'), 'count': count})

        return Response(data_points)
    
    def _get_grouped_graph_data(self, queryset, time_range, now, start_dt, end_dt, request):
        """
        Generate grouped graph data using the SAME
        classify_incident() logic as summary/events.

        Each event may contribute to multiple categories.
        """
        use_cases = list(
            get_tenant_use_cases(
                self.request,
                enabled_only=True
            )
        )

        tz = timezone.get_current_timezone()

        if start_dt and end_dt:
            queryset = queryset.filter(
                timestamp__gte=start_dt,
                timestamp__lt=end_dt
            )

        events = list(
            queryset.select_related('camera')
        )

        (
            detections_map,
            frame_path_map
        ) = build_incident_classification_maps(
            events
        )

        def empty_bucket():
            return {
                use_case.code: 0
                for use_case in use_cases
            }

        def add_classification(
            bucket,
            classification
        ):
            for use_case_code, matched in classification.items():

                if matched and use_case_code in bucket:
                    bucket[use_case_code] += 1

        # -------------------------------------------------
        # TODAY
        # -------------------------------------------------

        if time_range == 'today':

            buckets = {
                hour: empty_bucket()
                for hour in range(24)
            }

            for event in events:

                ts = event.timestamp

                if ts.tzinfo is None:
                    ts = timezone.make_aware(
                        ts,
                        tz
                    )
                else:
                    ts = timezone.localtime(
                        ts,
                        tz
                    )

                classification = classify_incident(
                    event,
                    use_cases=use_cases,
                    detections=detections_map.get(
                        event.event_id,
                        []
                    ),
                    frame_path=frame_path_map.get(
                        event.event_id
                    ),
                )

                add_classification(
                    buckets[ts.hour],
                    classification
                )

            return Response([
                {
                    'label': f'{hour:02d}:00',
                    **buckets[hour]
                }
                for hour in range(24)
            ])

        # -------------------------------------------------
        # WEEK / MONTH
        # -------------------------------------------------

        if time_range in ('week', 'month') or (start_dt and end_dt):

            if not start_dt or not end_dt:
                return Response([])

            total_days = (
                end_dt.date() -
                start_dt.date()
            ).days

            buckets = {
                (
                    start_dt +
                    timedelta(days=i)
                ).date(): empty_bucket()
                for i in range(total_days)
            }

            for event in events:

                ts = event.timestamp

                if ts.tzinfo is None:
                    ts = timezone.make_aware(
                        ts,
                        tz
                    )
                else:
                    ts = timezone.localtime(
                        ts,
                        tz
                    )

                day = ts.date()

                if day not in buckets:
                    continue

                classification = classify_incident(
                    event,
                    use_cases=use_cases,
                    detections=detections_map.get(
                        event.event_id,
                        []
                    ),
                    frame_path=frame_path_map.get(
                        event.event_id
                    ),
                )

                add_classification(
                    buckets[day],
                    classification
                )

            data_points = []

            for day in sorted(buckets.keys()):

                if time_range == 'week':
                    label = day.strftime('%a')
                else:
                    label = day.strftime('%d %b')

                data_points.append({
                    'label': label,
                    **buckets[day]
                })

            return Response(data_points)

        return Response([])
    
    @action(detail=False, methods=['get'])
    def unread_count(self, request):
    
        queryset = self._apply_access_filter(
            Event.objects.all(),
            request
        )
    
        queryset = filter_enabled_tenant_use_cases(
            queryset,
            request
        )
    
        unread_count = 0
    
        for event in queryset:
    
            review = EventReview.objects.filter(
                event_id=event.event_id
            ).first()
    
            if not review or not review.is_read:
                unread_count += 1
    
        return Response({
            'unread_count': unread_count
        })

    def _export_excel(self, export_data, time_range, now, start_dt, end_dt):
        workbook = Workbook()
        worksheet = workbook.active
        worksheet.title = 'Incident Summary'

        use_cases = export_data['use_cases']
        cameras = export_data['cameras']

        worksheet.merge_cells(
            start_row=1,
            start_column=1,
            end_row=1,
            end_column=2 + len(use_cases)
        )

        title_cell = worksheet.cell(
            row=1,
            column=1,
            value='SafeLensAI Incident Summary'
        )

        title_cell.font = Font(
            size=16,
            bold=True
        )

        if  time_range == 'all':
            duration = 'All Time'

        elif time_range == 'today' and (end_dt - start_dt).days == 1:
            duration = f'{start_dt.strftime("%d %b %Y")}'

        elif time_range == 'week':
            duration = (
                f'Weekly '
                f'({start_dt.strftime("%d %b %Y")} - '
                f'{(end_dt - timedelta(days=1)).strftime("%d %b %Y")})'
            )

        elif time_range == 'month':
            duration = (
                f'Monthly '
                f'({start_dt.strftime("%d %b %Y")} - '
                f'{(end_dt - timedelta(days=1)).strftime("%d %b %Y")})'
            )

        elif start_dt and end_dt:
            duration = (
                f'{start_dt.strftime("%d %b %Y")} - '
                f'{(end_dt - timedelta(days=1)).strftime("%d %b %Y")}'
            )

        else:
            duration = 'Selected Period'

        worksheet.merge_cells(
            start_row=2,
            start_column=1,
            end_row=2,
            end_column=2 + len(use_cases)
        )

        duration_cell = worksheet.cell(
            row=2,
            column=1,
            value=f'Duration: {duration}'
        )

        duration_cell.font = Font(
            size=12,
            bold=True
        )

        headers = ['Camera', 'Location']
        headers.extend(use_case.name for use_case in use_cases)

        for column, header in enumerate(headers, start=1):
            cell = worksheet.cell(
                row=4,
                column=column,
                value=header
            )
            cell.font = Font(bold=True)

        for row_number, camera_data in enumerate(cameras, start=5):
            worksheet.cell(
                row=row_number,
                column=1,
                value=camera_data['camera']
            )

            worksheet.cell(
                row=row_number,
                column=2,
                value=camera_data['location']
            )

            for column, use_case in enumerate(use_cases, start=3):
                worksheet.cell(
                row=row_number,
                column=column,
                value=camera_data['counts'].get(use_case.code, 0)
            )

        for column_index in range(1, worksheet.max_column + 1):
            max_length = 0

            for row_index in range(1, worksheet.max_row + 1):
                cell = worksheet.cell(
                    row=row_index,
                    column=column_index
                )

                if cell.value is not None:
                    max_length = max(
                        max_length,
                        len(str(cell.value))
                    )

            column_letter = worksheet.cell(
                row=4,
                column=column_index
            ).column_letter

            worksheet.column_dimensions[column_letter].width = max_length + 2

        footer_row = worksheet.max_row + 2

        worksheet.merge_cells(
            start_row=footer_row,
            start_column=1,
            end_row=footer_row,
            end_column=2 + len(use_cases)
        )

        footer_cell = worksheet.cell(
            row=footer_row,
            column=1,
            value=(
                'For detailed incident information, snapshots, and analytics. ' 
                'please login to SafeLensAI dashboard'
            )
        )

        footer_cell.font = Font(
            size=10,
            bold=True
        )

        footer_row += 1

        worksheet.merge_cells(
            start_row=footer_row,
            start_column=1,
            end_row=footer_row,
            end_column=2 + len(use_cases)
        )

        login_url_cell = worksheet.cell(
            row=footer_row,
            column=1,
            value='https://kmp-safelensai.prodisyn.com/'
        )

        login_url_cell.font = Font(
            size=10,
            bold=True
        )

        footer_row += 1

        worksheet.merge_cells(
            start_row=footer_row,
            start_column=1,
            end_row=footer_row,
            end_column=2 + len(use_cases)
        )

        footer_cell = worksheet.cell(
            row=footer_row,
            column=1,
            value=(
                'About SafeLensAI™: Transforming existing CCTV into '
                'intelligent, real-time AI vision for safer operations, '
                'stronger compliance, and smarter decision-making.'
            )
        )

        footer_cell.font = Font(
            size=10,
            bold=True
        )

        footer_row += 1

        worksheet.merge_cells(
            start_row=footer_row,
            start_column=1,
            end_row=footer_row,
            end_column=2 + len(use_cases)
        )

        powered_by_cell = worksheet.cell(
            row=footer_row,
            column=1,
            value='Powered by ProDiSynAI™ | ProDiSyn Innovations'
        )

        powered_by_cell.font = Font(
            size=10,
            bold=True
        )

        footer_row += 1

        worksheet.merge_cells(
            start_row=footer_row,
            start_column=1,
            end_row=footer_row,
            end_column=2 + len(use_cases)
        )

        exported_date_cell = worksheet.cell(
            row=footer_row,
            column=1,
            value=(
                f'Exported Date: '
                f'{datetime.now().strftime("%d %b %Y")}'
            )
        )

        exported_date_cell.font = Font(
            size=10,
            bold=True
        )

        footer_row += 1

        worksheet.merge_cells(
            start_row=footer_row,
            start_column=1,
            end_row=footer_row,
            end_column=2 + len(use_cases)
        )

        exported_time_cell = worksheet.cell(
            row=footer_row,
            column=1,
            value=(
                f'Exported Time: '
                f'{datetime.now().strftime("%I:%M %p")}'
            )
        )

        exported_time_cell.font = Font(
            size=10,
            bold=True
        )



        output = BytesIO()
        workbook.save(output)
        output.seek(0)

        response = HttpResponse(
            output.getvalue(),
            content_type=(
                'application/vnd.openxmlformats-officedocument.'
                'spreadsheetml.sheet'
            )
        )

        if time_range == 'all':
            filename = (
                f'SafeLensAI_Complete_Report_'
                f'{now.strftime("%d %b %Y")}.xlsx'
            )
            
        elif time_range == 'today':
            filename = (
                f'SafeLensAI_Incident_Report_'
                f'{start_dt.strftime("%d %b %Y")}.xlsx'
            )
            
        elif time_range == 'week':
            filename = (
                f'SafeLensAI_Incident_Report_Weekly_'
                f'({start_dt.strftime("%d %b %Y")} - '
                f'{(end_dt - timedelta(days=1)).strftime("%d %b %Y")}).xlsx'
            )
            
        elif time_range == 'month':
            filename = (
                f'SafeLensAI_Incident_Report_Monthly_'
                f'({start_dt.strftime("%d %b %Y")} - '
                f'{(end_dt - timedelta(days=1)).strftime("%d %b %Y")}).xlsx'
            )
            
        else:
            filename = (
                f'SafeLensAI_Incident_Report_'
                f'({start_dt.strftime("%d %b %Y")} - '
                f'{(end_dt - timedelta(days=1)).strftime("%d %b %Y")}).xlsx'
            )
            
        response['Content-Disposition'] = (
            f'attachment; filename="{filename}"'
        )
        
        return response

    def _export_pdf(self, export_data, time_range, now, start_dt, end_dt):
        output = BytesIO()
        document = SimpleDocTemplate(
            
            output,
            pagesize=landscape(A4),
            rightMargin=25,
            leftMargin=25,
            topMargin=25,
            bottomMargin=25
        )

        styles = getSampleStyleSheet()
        use_cases = export_data['use_cases']
        cameras = export_data['cameras']

        if  time_range == 'all':
            duration = 'All Time'

        elif time_range == 'today' and (end_dt - start_dt).days == 1:
            duration = f'{start_dt.strftime("%d %b %Y")}'

        elif time_range == 'week':
            duration = (
                f'Weekly ({start_dt.strftime("%d %b %Y")} - '
                f'{(end_dt - timedelta(days=1)).strftime("%d %b %Y")})'
            )

        elif time_range == 'month':
            duration = (
                f'Monthly ({start_dt.strftime("%d %b %Y")} - '
                f'{(end_dt - timedelta(days=1)).strftime("%d %b %Y")})'
            )

        elif start_dt and end_dt:
            duration = (
                f'{start_dt.strftime("%d %b %Y")} - '
                f'{(end_dt - timedelta(days=1)).strftime("%d %b %Y")}'
            )

        else:
            duration = 'Selected Period'

        exported_date = datetime.now().strftime("%d %b %Y")
        exported_time = datetime.now().strftime("%I:%M %p")

        elements = []

        table_header_style = ParagraphStyle(
            'TableHeader',
            parent=styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=8,
            leading=9,
            alignment=1
        )

        table_cell_style = ParagraphStyle(
            'TableCell',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=8,
            leading=9
        )

        table_cell_center_style = ParagraphStyle(
            'TableCellCenter',
            parent=table_cell_style,
            alignment=1
        )

        elements.append(
            Paragraph(
                '<b>SafeLensAI Incident Summary</b>',
                styles['Title']
            )
        )

        elements.append(Spacer(1, 10))
        elements.append(
            Paragraph(
                f'<b>Duration:</b> {duration}',
                styles['Normal']
            )
        )

        elements.append(Spacer(1, 15))

        headers = [
            Paragraph('<b>Camera</b>', table_header_style),
            Paragraph('<b>Location</b>', table_header_style)
        ]

        headers.extend(
            Paragraph(
                f'<b>{escape(str(use_case.name))}</b>',
                table_header_style
            )
            for use_case in use_cases
        )

        table_data = [headers]
        for camera_data in cameras:

            row = [
                Paragraph(
                    escape(str(camera_data['camera'])),
                    table_cell_style
                ),

                Paragraph(
                    escape(str(camera_data['location'])),
                    table_cell_style
                )
            ]

            row.extend(
                Paragraph(
                    str(camera_data['counts'].get(use_case.code, 0)),
                    table_cell_center_style
                )
                for use_case in use_cases
            )

            table_data.append(row)

        page_width, page_height = landscape(A4)
        available_width = page_width - document.leftMargin - document.rightMargin

        font_size = 8
        padding = 14

        camera_width = max(
            65,
            min(
                120,
                max(
                    [
                        stringWidth(
                            str(camera_data['camera']),
                            'Helvetica',
                            font_size
                        )
                        for camera_data in cameras
                    ] + [
                        stringWidth(
                            'Camera',
                            'Helvetica-Bold',
                            font_size
                        )
                    ]
                ) + padding
            )
        )

        location_width = max(
            65,
            min(
                120,
                max(
                    [
                        stringWidth(
                            str(camera_data['location']),
                            'Helvetica',
                            font_size
                        )
                        for camera_data in cameras
                    ] + [
                        stringWidth(
                            'Location',
                            'Helvetica-Bold',
                            font_size
                        )
                    ]
                ) + padding
            )
        )

        use_case_widths = []

        for use_case in use_cases:
            width = stringWidth(
                str(use_case.name),
                'Helvetica-Bold',
                font_size
            ) + padding

            use_case_widths.append(
                max(55, min(105, width)))

        col_widths = [
            camera_width,
            location_width,
            *use_case_widths
        ]

        total_width = sum(col_widths)
        if total_width > available_width:
            scale = available_width / total_width
            col_widths = [width * scale for width in col_widths]

        table = Table(
            table_data,
            colWidths=col_widths,
            repeatRows=1,
            hAlign='LEFT'
        )

        table.setStyle(
            TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
                ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                ('ALIGN', (2, 1), (-1, -1), 'CENTER'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('LEFTPADDING', (0, 0), (-1, -1), 6),
                ('RIGHTPADDING', (0, 0), (-1, -1), 6),
                ('TOPPADDING', (0, 0), (-1, -1), 6),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6)
            ])
        )

        elements.append(table)
        elements.append(Spacer(1, 20))

        elements.append(
            Paragraph(
                '<b>For detailed incident information, snapshots, and analytics. '
                'please login to SafeLensAI dashboard.https://kmp-safelensai.prodisyn.com/</b><br/><br/>'
                '<b>About SafeLensAI™:</b> '
                'Transforming existing CCTV into intelligent, real-time AI vision '
                'for safer operations, stronger compliance, and smarter '
                'decision-making.<br/><br/>',
                styles['Normal']
            )
        )

        elements.append(Spacer(1, 8))
        elements.append(
            Paragraph(
                '<b>Powered by ProDiSynAI™ | ProDiSyn Innovations</b>',
                styles['Normal']
            )
        )

        prodisyn_path = finders.find('images/ProDisyn-logo.png')
        if prodisyn_path:
            logo = Image(
                prodisyn_path,
                width=160,
                height=45,
                kind='proportional'
            )
            logo.hAlign = 'LEFT'
            elements.append(Spacer(1, 8))
            elements.append(logo)   

        def add_export_date(canvas, doc):
            canvas.saveState()
            canvas.setTitle(f"SafeLens_AI Report - {duration}")
            page_width, page_height = landscape(A4)

            kmp_logo = finders.find('images/kmp-logo.png')
            safelens_logo = finders.find('images/safelens_logo.png')


            if kmp_logo:
                canvas.drawImage(
                    ImageReader(kmp_logo),
                    25,
                    page_height - 65,
                    width=95,
                    height=50,
                    preserveAspectRatio=True,
                    mask='auto'
                )

            if safelens_logo:
                canvas.drawImage(
                    ImageReader(safelens_logo),
                    page_width - 120,
                    page_height - 65,
                    width=95,
                    height=50,
                    preserveAspectRatio=True,
                    mask='auto'
                )

            exported_date = datetime.now().strftime("%d %b %Y")
            exported_time = datetime.now().strftime("%I:%M %p")

            canvas.setFont(
                'Helvetica',
                9
            )

            date_text = f'Exported Date: {exported_date}'
            time_text = f'Exported Time: {exported_time}'

            date_width = canvas.stringWidth(
                date_text,
                'Helvetica',
                9
            )

            time_width = canvas.stringWidth(
                time_text,
                'Helvetica',
                9
            )

            export_x = (
                page_width - 25 - max(
                    date_width,
                    time_width
                )
            )

            canvas.drawString(
                export_x,
                35,
                date_text
            )

            canvas.drawString(
                export_x,
                22,
                time_text
            )

            canvas.restoreState()

        document.build(
            elements,
            onFirstPage=add_export_date,
            onLaterPages=add_export_date
        )

        output.seek(0)
        response = HttpResponse(
            output.getvalue(),
            content_type='application/pdf'
        )

        if time_range == 'all':
            filename = (
                f'SafeLensAI_Complete_Report_'
                f'{now.strftime("%d %b %Y")}.pdf'
            )
            
        elif time_range == 'today':
            filename = (
                f'SafeLensAI_Incident_Report_'
                f'{start_dt.strftime("%d %b %Y")}.pdf'
            )
        elif time_range == 'week':
            filename = (
                f'SafeLensAI_Incident_Report_Weekly_'
                f'({start_dt.strftime("%d %b %Y")} - '
                f'{(end_dt - timedelta(days=1)).strftime("%d %b %Y")}).pdf'
            )
        
        elif time_range == 'month':
            filename = (
                f'SafeLensAI_Incident_Report_Monthly_'
                f'({start_dt.strftime("%d %b %Y")} - '
                f'{(end_dt - timedelta(days=1)).strftime("%d %b %Y")}).pdf'
            )

        elif time_range == 'range':
            filename = (
                f'SafeLensAI_Incident_Report_Custom_Range_'
                f'({start_dt.strftime("%d %b %Y")} - '
                f'{(end_dt - timedelta(days=1)).strftime("%d %b %Y")}).pdf'
            )

        else:
            filename = 'SafeLensAI_Incident_Report.pdf'

        response['Content-Disposition'] = (
            f'attachment; filename="{filename}"'
        )
        
        return response

    @action(detail=False, methods=['get'])
    def export(self, request):
        print("EXPORT ACTION REACHED")

        export_format = request.query_params.get(
            'export_format',
            'excel'
        ).lower()

        event_type = request.query_params.get('type')

        queryset = Event.objects.select_related(
            'camera',
            'camera__location'
        ).order_by(
            'camera__name',
            'timestamp'
        )

        queryset = self._apply_access_filter(
            queryset,
            request
        )

        (
            queryset,
            time_range,
            now,
            start_dt,
            end_dt
        ) = self._apply_time_window(
            queryset,
            request,
            default_range='today'
        )

        queryset = filter_enabled_tenant_use_cases(
            queryset,
            request
        )

        queryset = filter_incident_queryset(
            queryset,
            event_type,
            request
        )

        rejected_event_ids = set(
            EventReview.objects.filter(
                status='Rejected'
                ).values_list(
                    'event_id',
                    flat=True
                )
            )
        events = [
            event
            for event in queryset
            if event.event_id not in rejected_event_ids
        ]      

        rejected_event_ids = set(
            EventReview.objects.filter(
                status='Rejected'
                ).values_list(
                    'event_id',
                    flat=True
                )
            )

        events = [
            event
            for event in queryset
            if event.event_id not in rejected_event_ids
        ]

        export_data = build_camera_incident_export_data(
            events,
            request
        )

        if export_format == 'excel':
           return self._export_excel(
               export_data,
               time_range,
               now,
               start_dt,
               end_dt
            )


        if export_format == 'pdf':
          return self._export_pdf(
              export_data,
              time_range,
              now,
              start_dt,
              end_dt
            )

        return Response(
            {
                'error': (
                    'Only excel and pdf export are supported.'
                )
            },
            status=400
        )

class IncidentStreamView(APIView):
    """
    Streams new incidents to the UI using Server-Sent Events (SSE).
    The client should load `/api/overview/latest/` first, keep the highest
    `event_id`, and reconnect here with `since_id` to receive new incidents.
    """
    permission_classes = [IsAuthenticated]
    authentication_classes = [TokenAuthentication]
    renderer_classes = [EventStreamRenderer]

    def get(self, request):
        try:
            last_event_id = int(request.query_params.get('since_id', 0))
        except (TypeError, ValueError):
            last_event_id = 0

        try:
            poll_seconds = max(0.5, float(os.environ.get('INCIDENT_STREAM_POLL_SECONDS', '1')))
        except (TypeError, ValueError):
            poll_seconds = 1.0

        try:
            heartbeat_seconds = max(5, int(os.environ.get('INCIDENT_STREAM_HEARTBEAT_SECONDS', '15')))
        except (TypeError, ValueError):
            heartbeat_seconds = 15

        def event_stream():
            current_last_event_id = last_event_id
            last_heartbeat_at = time_module.monotonic()

            yield "retry: 3000\n\n"
            yield format_sse_message(
                "connected",
                {"status": "ok", "since_id": current_last_event_id},
                event_id=current_last_event_id or None,
            )

            while True:
                new_events_queryset = apply_event_access_filter(
                    Event.objects
                    .select_related('camera')
                    .filter(event_id__gt=current_last_event_id)
                    .order_by('event_id'),
                    request,
                )

                new_events_queryset = filter_enabled_tenant_use_cases(
                    new_events_queryset,
                    request
                )

                new_events = list(
                    new_events_queryset[:50]
                )

                if new_events:
                    sent_at = timezone.now()
                    for payload in serialize_overview_events(new_events, request):
                        current_last_event_id = max(current_last_event_id, payload['event_id'])
                        timed_payload = add_stream_timing(payload, sent_at, poll_seconds)
                        yield format_sse_message("incident", timed_payload, event_id=payload['event_id'])
                    last_heartbeat_at = time_module.monotonic()
                elif time_module.monotonic() - last_heartbeat_at >= heartbeat_seconds:
                    yield format_sse_message("heartbeat", {"ts": datetime.utcnow().isoformat()})
                    last_heartbeat_at = time_module.monotonic()

                time_module.sleep(poll_seconds)

        response = StreamingHttpResponse(event_stream(), content_type='text/event-stream')
        response['Cache-Control'] = 'no-cache'
        response['X-Accel-Buffering'] = 'no'
        return response


class SendNotificationView(APIView):
    """
    API endpoint that triggers an email, SMS, and WhatsApp notification for a specific event
    based on the recipient's preferences.
    """
    permission_classes = [IsAuthenticated]

    def log_delivery(self, event_id, channel, recipient, status, provider=None, provider_message_id=None,
                     template_name=None, error_message=None, details=None):
        NotificationDeliveryLog.objects.create(
            event_id=event_id,
            channel=channel,
            recipient=recipient,
            status=status,
            provider=provider,
            provider_message_id=provider_message_id,
            template_name=template_name,
            error_message=error_message,
            details=details or {}
        )

    def media_public_url(self, storage_path):
        from apps.api.utils import resolve_media_path
        resolved = resolve_media_path(storage_path)
        if not resolved:
            return None
        if resolved.startswith('http://') or resolved.startswith('https://'):
            return resolved

        base_url = os.environ.get('PUBLIC_BASE_URL', getattr(settings, 'PUBLIC_BASE_URL', ''))
        if not base_url:
            return None

        storage_base = os.environ.get('SYSTEM_STORAGE_DIR')
        if not storage_base:
            storage_base = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'storage'))

        if resolved.startswith(storage_base):
            rel_path = os.path.relpath(resolved, storage_base)
        elif 'storage/' in resolved:
            rel_path = resolved.split('storage/', 1)[-1].lstrip('/')
        else:
            rel_path = resolved.lstrip('/')

        return f"{base_url}/media/{rel_path}"

    def post(self, request):
        event_id = request.data.get('event_id')

        if not event_id:
            return Response(
                {"error": "event_id is required"},
                status=400
            )

        try:
            event = (
                apply_event_access_filter(
                    Event.objects.select_related("camera"),
                    request
                )
                .filter(pk=event_id)
                .first()
            )

            if not event:
                return Response(
                    {"error": "Event not found"},
                    status=404
                )

        except Exception:
            return Response(
                {"error": "Unable to access event"},
                status=500
            )

        camera_name = event.camera.name if event.camera else "Unknown Camera"
        camera_location = event.camera.location.name if event.camera and event.camera.location else "Unknown Location"
        tz = pytz.timezone('Asia/Kolkata')
        event_time_ist = timezone.localtime(timezone.make_aware(event.timestamp) if timezone.is_naive(event.timestamp) else event.timestamp, timezone=tz)
        event_time_str = event_time_ist.strftime('%d-%m-%Y %H:%M:%S') if event.timestamp else "Unknown Time"

        frame_path = None
        detections = list(event.detections.all()) if hasattr(event, 'detections') else []
        frame_map = EventMediaMap.objects.filter(event_id=event.event_id, media_type='FRAME').first()
        if frame_map:
            frame = Frame.objects.filter(frame_id=frame_map.media_id).first()
            if frame:
                frame_path = frame.storage_path
        display_event_type = derive_incident_display_type(
            event.event_type,
            detections=detections,
            frame_path=frame_path,
        )

        # Resolve Image & Video URLs for body links and attachments
        wa_image_url = None
        wa_video_url = None
        
        img_map = EventMediaMap.objects.filter(event_id=event.event_id, media_type='FRAME').first()
        if img_map:
            frame = Frame.objects.filter(frame_id=img_map.media_id).first()
            if frame and frame.storage_path:
                wa_image_url = self.media_public_url(frame.storage_path)

        vid_map = EventMediaMap.objects.filter(event_id=event.event_id, media_type='CLIP').first()
        if vid_map:
            clip = Clip.objects.filter(clip_id=vid_map.media_id).first()
            if clip and clip.storage_path:
                wa_video_url = self.media_public_url(clip.storage_path)

        base_url = os.environ.get('PUBLIC_BASE_URL', getattr(settings, 'PUBLIC_BASE_URL', '')).rstrip('/')
        media_token = generate_media_access_token(event.event_id)
        short_image_url = (
            f"{base_url}/api/media-redirect/image/{event.event_id}/image.jpg?token={media_token}"
            if wa_image_url else 'N/A'
        )
        short_video_url = (
            f"{base_url}/api/media-redirect/video/{event.event_id}/video.mp4?token={media_token}"
            if wa_video_url else 'N/A'
        )
        subject = f"🚨 Safety Alert: {display_event_type} at {camera_name}"
        message_body = (
            f"SafeLensAI Alert\n\n"
            f"Incident ID: {event.event_id}\n"
            f"Date: {event_time_str}\n"
            f"Location: {camera_location}\n"
            f"Incident Type: {display_event_type}\n\n"
            f"Image: {short_image_url}\n"
            f"Video: {short_video_url}\n\n"
            f"Powered by ProDiSynAI™"
        )

        email_recipients = []
        sms_recipients = []
        whatsapp_recipients = []
        
        # Get Global Master Switches
        from .models import EmailAlertTracker
        global_settings = EmailAlertTracker.objects.first()
        global_email_enabled = global_settings.is_email_enabled if global_settings else True
        global_sms_enabled = global_settings.is_sms_enabled if global_settings else False
        global_whatsapp_enabled = global_settings.is_whatsapp_enabled if global_settings else False

        # 1. Custom Recipients (Email Only)
        if global_email_enabled:
            custom_recipients = list(NotificationRecipient.objects.filter(is_active=True).values_list('email', flat=True))
            email_recipients.extend(custom_recipients)
        
        # 2. System Users (Filtered by Location and Role)
        # We notify "Active" users via Email, SMS, and WhatsApp if they match the location.
        active_users = (
            User.objects
            .filter(
                is_active=True,
                profile__tenant=event.camera.tenant_config.tenant
            )
            .select_related("profile")
            .prefetch_related("assigned_locations__location")
            .distinct()
        )

        event_tenant = (
            event.camera.tenant_config.tenant
            if event.camera and event.camera.tenant_config
            else None
        )
        event_location_id = event.camera.location_id if event.camera else None

        for user in active_users:
            try:
                profile = user.profile

                # ---------------------------------------------------------
                # LOCATION ACCESS
                #
                # Admin:
                #     Can receive notifications for all locations
                #
                # Manager / Support:
                #     Can receive notifications only for locations
                #     assigned through UserLocation.
                # ---------------------------------------------------------

                should_notify = False

                if profile.role in TENANT_WIDE_ROLES:
                    should_notify = True

                elif profile.role in LOCATION_SCOPED_ROLES:
                    should_notify = (
                        event_location_id is not None
                        and UserLocation.objects.filter(
                            user=user,
                            location__location_id=event_location_id,
                            location__tenant=event_tenant
                        ).exists()
                    )

                if not should_notify:
                    continue

                # Check Global + Individual Preference
                if global_email_enabled and profile.alerts_email and user.email:
                    email_recipients.append(user.email)
                
                # SMS/WhatsApp: Now goes to ALL active users (Offline & Online)
                if profile.phone_number:
                    phone = profile.phone_number.strip()
                    if len(phone) == 10 and phone.isdigit():
                        phone = '+91' + phone
                    elif not phone.startswith('+'):
                        phone = '+' + phone

                    if global_sms_enabled and profile.alerts_sms:
                        sms_recipients.append(phone)
                    if global_whatsapp_enabled and profile.alerts_whatsapp:
                        whatsapp_recipients.append(phone)
            except UserProfile.DoesNotExist:
                # Fallback: If no profile, we only send email if it's an admin (staff)
                if user.is_staff and global_email_enabled and user.email:
                    email_recipients.append(user.email)

        # Remove duplicates
        email_recipients = list(set(email_recipients))
        sms_recipients = list(set(sms_recipients))
        whatsapp_recipients = list(set(whatsapp_recipients))

        results = []

        # Send Emails
        if email_recipients and global_email_enabled:
            try:
                from apps.api.utils import send_aws_email
                attachments = []

                if wa_image_url:
                    attachments.append(wa_image_url)
                if wa_video_url:
                    attachments.append(wa_video_url)

                res = send_aws_email(subject, message_body, email_recipients, attachments=attachments)
                if res:
                    for recipient in email_recipients:
                        self.log_delivery(
                            event_id=event.event_id,
                            channel='EMAIL',
                            recipient=recipient,
                            status='SENT',
                            provider='AWS_SES',
                            provider_message_id=res.get('MessageId'),
                            details={'attachment_count': len(attachments), 'trigger': 'manual'}
                        )
                    results.append(f"Email sent to {len(email_recipients)}")
                else:
                    for recipient in email_recipients:
                        self.log_delivery(
                            event_id=event.event_id,
                            channel='EMAIL',
                            recipient=recipient,
                            status='FAILED',
                            provider='AWS_SES',
                            error_message='send_aws_email returned no response',
                            details={'attachment_count': len(attachments), 'trigger': 'manual'}
                        )
                    results.append(f"Email error: Failed to send via AWS SES")
            except Exception as e:
                for recipient in email_recipients:
                    self.log_delivery(
                        event_id=event.event_id,
                        channel='EMAIL',
                        recipient=recipient,
                        status='FAILED',
                        provider='AWS_SES',
                        error_message=str(e),
                        details={'trigger': 'manual'}
                    )
                results.append(f"Email error: {str(e)}")
        elif email_recipients and not global_email_enabled:
            for recipient in email_recipients:
                self.log_delivery(
                    event_id=event.event_id,
                    channel='EMAIL',
                    recipient=recipient,
                    status='SKIPPED',
                    provider='AWS_SES',
                    error_message='Global email switch disabled',
                    details={'trigger': 'manual'}
                )
            results.append("Emails suppressed (Global Switch OFF)")

        from apps.api.utils import send_aws_sms, send_aws_whatsapp

        # Send SMS via AWS SNS
        if sms_recipients and global_sms_enabled:
            sms_body = (
                f"SafeLensAI Incident\n"
                f"Type: {display_event_type}\n"
                f"Loc: {camera_location}\n"
                f"Incident ID: {event.event_id}\n"
                f"Time: {event_time_str}"
            )
            sms_success = 0
            for num in sms_recipients:
                try:
                    response = send_aws_sms(num, sms_body)
                    if response:
                        self.log_delivery(
                            event_id=event.event_id,
                            channel='SMS',
                            recipient=num,
                            status='SENT',
                            provider='AWS_SNS',
                            provider_message_id=response.get('MessageId'),
                            details={'trigger': 'manual'}
                        )
                        sms_success += 1
                    else:
                        self.log_delivery(
                            event_id=event.event_id,
                            channel='SMS',
                            recipient=num,
                            status='FAILED',
                            provider='AWS_SNS',
                            error_message='send_aws_sms returned no response',
                            details={'trigger': 'manual'}
                        )
                except Exception as e:
                    self.log_delivery(
                        event_id=event.event_id,
                        channel='SMS',
                        recipient=num,
                        status='FAILED',
                        provider='AWS_SNS',
                        error_message=str(e),
                        details={'trigger': 'manual'}
                    )
                    print(f"AWS SMS Error to {num}: {e}")
            if sms_success:
                results.append(f"SMS sent to {sms_success}")

        # Send WhatsApp via AWS
        if whatsapp_recipients and global_whatsapp_enabled:
            wa_success = 0
            template_name = None

            whatsapp_body = (
                f"SafeLensAI Alert\n\n"
                f"Incident ID: {event.event_id}\n"
                f"Date: {event_time_str}\n"
                f"Location: {camera_location}\n"
                f"Incident Type: {display_event_type}\n\n"
                f"Image: {short_image_url}\n"
                f"Video: {short_video_url}\n\n"
                f"Powered by ProDiSynAI™"
            )
            template_name = get_whatsapp_template_name(wa_image_url)

            for num in whatsapp_recipients:
                try:
                    response = send_aws_whatsapp(
                        num, 
                        whatsapp_body, 
                        media_url=short_image_url if short_image_url != 'N/A' else None,
                        location=camera_location,
                        time_str=event_time_str,
                        incident_type=display_event_type,
                        event_id=event.event_id,
                        video_url=short_video_url if short_video_url != 'N/A' else None
                    )
                    if response:
                        self.log_delivery(
                            event_id=event.event_id,
                            channel='WHATSAPP',
                            recipient=num,
                            status='SENT',
                            provider='AWS_SOCIAL_MESSAGING',
                            provider_message_id=response.get('messageId'),
                            template_name=template_name,
                            details={'trigger': 'manual', 'has_image': bool(wa_image_url), 'has_video': bool(wa_video_url)}
                        )
                        wa_success += 1
                    else:
                        self.log_delivery(
                            event_id=event.event_id,
                            channel='WHATSAPP',
                            recipient=num,
                            status='FAILED',
                            provider='AWS_SOCIAL_MESSAGING',
                            template_name=template_name,
                            error_message='send_aws_whatsapp returned no response',
                            details={'trigger': 'manual', 'has_image': bool(wa_image_url), 'has_video': bool(wa_video_url)}
                        )

                except Exception as e:
                    self.log_delivery(
                        event_id=event.event_id,
                        channel='WHATSAPP',
                        recipient=num,
                        status='FAILED',
                        provider='AWS_SOCIAL_MESSAGING',
                        template_name=template_name,
                        error_message=str(e),
                        details={'trigger': 'manual', 'has_image': bool(wa_image_url), 'has_video': bool(wa_video_url)}
                    )
                    print(f"AWS WhatsApp Error to {num}: {e}")
            if wa_success:
                results.append(f"WhatsApp sent to {wa_success}")
        
        if sms_recipients and not global_sms_enabled:
            for num in sms_recipients:
                self.log_delivery(
                    event_id=event.event_id,
                    channel='SMS',
                    recipient=num,
                    status='SKIPPED',
                    provider='AWS_SNS',
                    error_message='Global SMS switch disabled',
                    details={'trigger': 'manual'}
                )
            results.append("SMS suppressed (Global Switch OFF)")
        if whatsapp_recipients and not global_whatsapp_enabled:
            for num in whatsapp_recipients:
                self.log_delivery(
                    event_id=event.event_id,
                    channel='WHATSAPP',
                    recipient=num,
                    status='SKIPPED',
                    provider='AWS_SOCIAL_MESSAGING',
                    template_name=get_whatsapp_template_name(None),
                    error_message='Global WhatsApp switch disabled',
                    details={'trigger': 'manual'}
                )
            results.append("WhatsApp suppressed (Global Switch OFF)")

        if not results:
            return Response({"message": "No active recipients configured. Notification skipped."}, status=200)

        return Response({"message": " | ".join(results)})
    
class GlobalSettingsViewSet(viewsets.ViewSet):
    """
    API endpoint for Administrator Global Alert Settings.
    Allows enabling or disabling Email, SMS, and WhatsApp alerts globally 
    across the entire Safelens platform.
    """
    permission_classes = [IsAdminUser]

    def list(self, request):
        """Retrieve the current global master switches."""
        settings, _ = EmailAlertTracker.objects.get_or_create(id=1)
        serializer = GlobalSettingsSerializer(settings)
        return Response(serializer.data)

    @action(detail=False, methods=['patch'])
    def update_switches(self, request):
        """Update the global master switches."""
        settings, _ = EmailAlertTracker.objects.get_or_create(id=1)
        serializer = GlobalSettingsSerializer(settings, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=400)


class NotificationDeliveryLogViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Lightweight read-only notification history API for admin/dashboard visibility.
    Uses simple indexed filters and capped limits to avoid heavy database load.
    """
    serializer_class = NotificationDeliveryLogSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        queryset = NotificationDeliveryLog.objects.all().order_by('-created_at')

        event_id = self.request.query_params.get('event_id')
        channel = self.request.query_params.get('channel')
        status = self.request.query_params.get('status')
        recipient = self.request.query_params.get('recipient')
        limit = self.request.query_params.get('limit')

        if event_id:
            queryset = queryset.filter(event_id=event_id)
        if channel:
            queryset = queryset.filter(channel__iexact=channel)
        if status:
            queryset = queryset.filter(status__iexact=status)
        if recipient:
            queryset = queryset.filter(recipient__icontains=recipient)
        if limit:
            try:
                queryset = queryset[:min(int(limit), 200)]
            except ValueError:
                pass

        return queryset

    @action(detail=False, methods=['get'])
    def summary(self, request):
        queryset = self.get_queryset()
        summary = list(
            queryset.values('channel', 'status')
            .annotate(count=Count('id'))
            .order_by('channel', 'status')
        )
        return Response(summary)


class RetryFailedWhatsAppView(APIView):
    """
    Admin-only API to trigger a controlled WhatsApp retry run.
    This is intentionally scoped and capped to keep it safe for production.
    """
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAdminUser]

    def post(self, request):
        try:
            limit = min(int(request.data.get('limit', 50)), 200)
        except (TypeError, ValueError):
            return Response({'error': 'limit must be an integer'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            hours = int(request.data.get('hours', 24))
        except (TypeError, ValueError):
            return Response({'error': 'hours must be an integer'}, status=status.HTTP_400_BAD_REQUEST)

        recipient = request.data.get('recipient')
        event_id = request.data.get('event_id')
        dry_run = bool(request.data.get('dry_run', False))

        if event_id is not None:
            try:
                event_id = int(event_id)
            except (TypeError, ValueError):
                return Response({'error': 'event_id must be an integer'}, status=status.HTTP_400_BAD_REQUEST)

        result = retry_failed_whatsapp_logs(
            limit=limit,
            hours=hours,
            recipient=recipient,
            event_id=event_id,
            dry_run=dry_run,
            stdout=None,
        )
        return Response(result)


class ModuleControlView(APIView):
    """
    Compatibility endpoint for frontend builds that can request AI module
    pause/resume actions while an incident is being reviewed.

    The EC2 database API does not own those workers, so this endpoint is a
    no-op by default. It keeps the dashboard/backend contract stable and avoids
    false 403/404 console errors in production.
    """
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    allowed_modules = {"fall", "intrusion", "object"}
    allowed_actions = {"pause", "resume"}

    def post(self, request, module, action):
        module = (module or "").lower()
        action = (action or "").lower()

        if module not in self.allowed_modules or action not in self.allowed_actions:
            return Response(
                {"detail": "Unsupported module control action."},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(
            {
                "module": module,
                "action": action,
                "status": "skipped",
                "detail": "Module control is not configured on this API service.",
            },
            status=status.HTTP_200_OK,
        )


class EventIngestView(APIView):
    """
    REST API Ingestion endpoint to support event creation from both Local and Cloud sources.
    POST /api/events/ingest/
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request, *args, **kwargs):
        from apps.api.services.event_processor import process_event
        from rest_framework.exceptions import ValidationError
        
        payload = request.data
        try:
            event = process_event(payload)
            return Response({
                "status": "success",
                "event_id": event.event_id
            }, status=status.HTTP_201_CREATED)
        except ValidationError as e:
            return Response({
                "status": "error",
                "errors": e.detail
            }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"EventIngestView: Internal error: {str(e)}", exc_info=True)
            return Response({
                "status": "error",
                "message": "Internal server error occurred."
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

#==========================================================================
MEDIA_TOKEN_SALT = "safelens-media-access"

def generate_media_access_token(event_id):
    return signing.dumps(
        {"event_id": int(event_id)},
        salt=MEDIA_TOKEN_SALT
    )


def validate_media_access_token(token, event_id):
    try:
        data = signing.loads(
            token,
            salt=MEDIA_TOKEN_SALT,
            max_age=60 * 60 * 24
        )

        return int(data.get("event_id")) == int(event_id)

    except (
        signing.BadSignature,
        signing.SignatureExpired,
        TypeError,
        ValueError,
        KeyError
    ):
        return False

class MediaRedirectView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
 
    def get(self, request, media_type, event_id, filename=None):
        from django.http import Http404, FileResponse, StreamingHttpResponse
        from apps.api.models import Event, EventMediaMap, Frame, Clip
        from apps.api.utils import resolve_media_path
        import os
        import requests
 
        if media_type not in ("image", "video"):
            raise Http404("Invalid media type")
 
        token = request.query_params.get("token")
 
        if not token:
            raise Http404("Media access token required")
 
        if not validate_media_access_token(token, event_id):
            raise Http404("Invalid or expired media access token")
 
        try:
            event = Event.objects.get(pk=event_id)
        except Event.DoesNotExist:
            raise Http404("Event not found")
 
        # ---------------------------------------------------------
        # FIND MEDIA
        # ---------------------------------------------------------
 
        if media_type == "image":
 
            media_map = EventMediaMap.objects.filter(
                event_id=event_id,
                media_type="FRAME"
            ).first()
 
            if not media_map:
                raise Http404("Image media map not found")
 
            frame = Frame.objects.filter(
                frame_id=media_map.media_id
            ).first()
 
            if not frame or not frame.storage_path:
                raise Http404("Image not found")
 
            path = frame.storage_path
            default_filename = "image.jpg"
            content_type = "image/jpeg"
 
        else:
 
            media_map = EventMediaMap.objects.filter(
                event_id=event_id,
                media_type="CLIP"
            ).first()
 
            if not media_map:
                raise Http404("Video media map not found")
 
            clip = Clip.objects.filter(
                clip_id=media_map.media_id
            ).first()
 
            if not clip or not clip.storage_path:
                raise Http404("Video not found")
 
            path = clip.storage_path
            default_filename = "video.mp4"
            content_type = "video/mp4"
 
        # ---------------------------------------------------------
        # RESOLVE STORAGE PATH
        # ---------------------------------------------------------
 
        resolved = resolve_media_path(path)
 
        if not resolved:
            raise Http404("Media path could not be resolved")
 
        download_filename = filename or default_filename
 
        # ---------------------------------------------------------
        # S3 / HTTP MEDIA
        # ---------------------------------------------------------
 
        if resolved.startswith("http://") or resolved.startswith("https://"):
 
            try:
                response = requests.get(
                    resolved,
                    stream=True,
                    timeout=60
                )
 
                response.raise_for_status()
 
            except requests.RequestException as e:
                logger.error(
                    f"Media download failed for event "
                    f"{event_id}: {e}",
                    exc_info=True
                )
                raise Http404("Unable to download media")
 
            django_response = StreamingHttpResponse(
                response.iter_content(chunk_size=1024 * 1024),
                content_type=content_type
            )
 
            django_response["Content-Disposition"] = (
                f'attachment; filename="{download_filename}"'
            )
 
            django_response["Cache-Control"] = "no-store"
 
            if response.headers.get("Content-Length"):
                django_response["Content-Length"] = (
                    response.headers["Content-Length"]
                )
 
            return django_response
 
        # ---------------------------------------------------------
        # LOCAL FILE
        # ---------------------------------------------------------
 
        if os.path.isfile(resolved):
 
            response = FileResponse(
                open(resolved, "rb"),
                as_attachment=True,
                filename=download_filename,
                content_type=content_type
            )
 
            response["Cache-Control"] = "no-store"
 
            return response
 
        raise Http404("Media file not found")


User = get_user_model()

class ForgotPasswordView(APIView):
    """
    Triggers a Password Reset Request.
    Saves an event to the database for poll_events.py to pick up and process asynchronously.
    """
    permission_classes = [AllowAny]
    authentication_classes = [] 

    def post(self, request):
        email = request.data.get('email', '').strip().lower()
        if not email:
            return Response({"error": "Email is required"}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # Match active accounts using your core profile constraint
            user = User.objects.get(email__iexact=email, profile__status='Active')
            
            # Create the reset tracking record
            PasswordResetEvent.objects.create(user=user)
            
            return Response(
                {"detail": "A password reset link has been sent to your email address."},
                status=status.HTTP_200_OK
            )
                
        except User.DoesNotExist:
            # Return an explicit error message to your frontend form client
            return Response(
                {"error": "No active account found registered with this email address."},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            print(f"[CRITICAL] Password recovery queue failure: {str(e)}")
            return Response(
                {"error": "An internal system error occurred. Please try again later."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class ResetPasswordConfirmView(APIView):
    permission_classes = [AllowAny]  
    authentication_classes = []     

    def post(self, request):
        """
        Commits the new password change.
        """
        user_id = request.data.get('uid') or request.data.get('user_id')
        token = request.data.get('token')
        new_password = request.data.get('new_password')
        
        if not all([user_id, token, new_password]):
            return Response({"error": "Missing required validation parameters."}, status=status.HTTP_400_BAD_REQUEST)
            
        reset_event = PasswordResetEvent.objects.filter(user__id=user_id).order_by('-created_at').first()
        
        if not reset_event:
            return Response({"error": "Link expired or invalid."}, status=status.HTTP_400_BAD_REQUEST)

        db_token = str(reset_event.token).strip()
        url_token = str(token).strip()

        if db_token != url_token and not secrets.compare_digest(db_token, url_token):
            return Response({"error": "Link expired or invalid."}, status=status.HTTP_400_BAD_REQUEST)
            
        expiry_limit = reset_event.created_at + timezone.timedelta(minutes=15)
        if timezone.now() > expiry_limit:
            return Response({"error": "The recovery link has expired. Please request a new one."}, status=status.HTTP_400_BAD_REQUEST)
            
        try:
            user = reset_event.user
            user.set_password(new_password)
            user.save()
            
            # Clean up token entry entirely to prevent reuse
            reset_event.delete() 
            return Response({"detail": "Password has been updated successfully."}, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response({"error": "An unexpected system error occurred."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
    def get(self, request):
        """
        Instant validation on page load.
        """
        user_id = request.query_params.get('uid')
        token = request.query_params.get('token')
    
        if not user_id or not token:
            return Response({"error": "Missing validation parameters."}, status=status.HTTP_400_BAD_REQUEST)

        # Look up using user__id relation to avoid field-type mismatch errors
        reset_event = PasswordResetEvent.objects.filter(user__id=user_id).order_by('-created_at').first()
        
        if not reset_event:
            return Response({"error": "No active reset token found for this user."}, status=status.HTTP_400_BAD_REQUEST)

        # Strip strings to avoid character issues
        db_token = str(reset_event.token).strip()
        url_token = str(token).strip()

        if db_token != url_token and not secrets.compare_digest(db_token, url_token):
            return Response({"error": "Link expired."}, status=status.HTTP_400_BAD_REQUEST)
            
        # Check time window expiration bounds
        expiry_limit = reset_event.created_at + timezone.timedelta(minutes=30)
        if timezone.now() > expiry_limit:
            return Response({"error": "The link has expired."}, status=status.HTTP_400_BAD_REQUEST)

        return Response({"valid": True}, status=status.HTTP_200_OK)

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from .serializers import TenantConfigSerializer


class TenantConfigView(APIView):
    """
    Returns tenant configuration according to the authenticated
    user's access level.

    Admin:
        Receives complete tenant configuration.

    Manager / Support:
        Receives only assigned locations and their cameras.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):

        user = request.user

        try:
            profile = user.profile
        except (AttributeError, UserProfile.DoesNotExist):
            return Response(
                {
                    "detail": "User profile not found."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        tenant = profile.tenant

        if not tenant:
            return Response(
                {
                    "detail": "User is not assigned to a tenant."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = TenantConfigSerializer(
            tenant,
            context={
                "request": request
            }
        )

        data = serializer.data

        # ---------------------------------------------------------
        # ADMIN -> complete tenant configuration
        # ---------------------------------------------------------
        if profile.role in TENANT_WIDE_ROLES:
            return Response(data)

        # ---------------------------------------------------------
        # MANAGER / SUPPORT
        # ---------------------------------------------------------

        if profile.role not in LOCATION_SCOPED_ROLES:
            return Response(
                {
                    "detail": "User role does not have configuration access."
                },
                status=status.HTTP_403_FORBIDDEN
            )

        assigned_location_ids = set(
            UserLocation.objects.filter(
                user=user,
                location__tenant=tenant
            ).values_list(
                "location_id",
                flat=True
            )
        )

        # Filter locations.
        #
        # Your serializer should expose the tenant locations under
        # the "locations" key.
        if isinstance(data.get("locations"), list):

            filtered_locations = []

            for location in data["locations"]:

                location_id = location.get("id")

                if location_id in assigned_location_ids:
                    filtered_locations.append(location)

            data["locations"] = filtered_locations

        return Response(data)

class UserLocationViewSet(viewsets.ModelViewSet):
    """
    Manage location assignments for users.

    Only tenant Admin users can create, update or delete
    UserLocation assignments.

    Access model:

        Admin
          ↓
        UserLocation
          ↓
        TenantLocation
    """

    serializer_class = UserLocationSerializer
    permission_classes = [IsAuthenticated]

    def _get_profile(self):
        try:
            return self.request.user.profile
        except (AttributeError, UserProfile.DoesNotExist):
            return None

    def _get_tenant(self):
        profile = self._get_profile()

        if not profile:
            return None

        return profile.tenant

    def _is_admin(self):
        profile = self._get_profile()

        return bool(
            profile
            and profile.role in TENANT_WIDE_ROLES
            and profile.tenant
        )

    def get_queryset(self):
        """
        Admins can view UserLocation assignments belonging
        to their own tenant only.

        Managers/Support cannot view assignments.
        """

        if not self._is_admin():
            return UserLocation.objects.none()

        tenant = self._get_tenant()

        return (
            UserLocation.objects
            .filter(
                user__profile__tenant=tenant,
                location__tenant=tenant,
            )
            .select_related(
                "user",
                "user__profile",
                "location",
                "location__tenant",
                "location__location",
            )
        )

    def _validate_assignment(self, serializer):
        """
        Ensure the selected user and location both belong
        to the authenticated Admin's tenant.
        """

        if not self._is_admin():
            raise PermissionDenied(
                "Only tenant Admin users can manage location assignments."
            )

        tenant = self._get_tenant()

        assigned_user = serializer.validated_data.get("user")
        location = serializer.validated_data.get("location")

        if not assigned_user:
            raise serializers.ValidationError({
                "user": "User is required."
            })

        if not location:
            raise serializers.ValidationError({
                "location": "Location is required."
            })

        # User must belong to the same tenant.
        try:
            assigned_user_profile = assigned_user.profile
        except (AttributeError, UserProfile.DoesNotExist):
            raise serializers.ValidationError({
                "user": "Selected user does not have a profile."
            })

        if assigned_user_profile.tenant_id != tenant.id:
            raise serializers.ValidationError({
                "user": "User does not belong to your tenant."
            })

        # Location must belong to the same tenant.
        if location.tenant_id != tenant.id:
            raise serializers.ValidationError({
                "location": "Location does not belong to your tenant."
            })

        if not location.enabled:
            raise serializers.ValidationError({
                "location": "Selected location is disabled."
            })

    def perform_create(self, serializer):
        self._validate_assignment(serializer)
        serializer.save()

    def perform_update(self, serializer):
        self._validate_assignment(serializer)
        serializer.save()
        
    def perform_destroy(self, instance):
        if not self._is_admin():
            raise PermissionDenied(
                "Only tenant Admin users can manage location assignments."
            )

        tenant = self._get_tenant()

        if (
            instance.user.profile.tenant_id != tenant.id
            or instance.location.tenant_id != tenant.id
        ):
            raise PermissionDenied(
                "You cannot delete assignments outside your tenant."
            )

        instance.delete()

class IncidentConfigViewSet(viewsets.ModelViewSet):
    """
    CRUD API for tenant-specific incident scoring configuration.

    Each TenantUseCase can have one IncidentConfig containing:
        - unit_score
        - weight

    Access:
        - Admin: full CRUD
        - Manager: no access
        - Support: no access

    Tenant is always resolved from:
        request.user.profile.tenant

    The frontend never provides a tenant ID.
    """

    serializer_class = IncidentConfigSerializer
    permission_classes = [IsAuthenticated]

    def _get_tenant(self):
        """
        Return the tenant belonging to the authenticated user.
        """
        user = self.request.user

        try:
            profile = user.profile
        except (AttributeError, UserProfile.DoesNotExist):
            return None

        return profile.tenant

    def _is_admin(self):
        """
        Incident scoring configuration is Admin-only.

        We intentionally check the profile role instead of only
        using IsAdminUser because Managers may have is_staff=True.
        """
        user = self.request.user

        try:
            profile = user.profile
        except (AttributeError, UserProfile.DoesNotExist):
            return False

        return (
            user.is_superuser
            or profile.role  in TENANT_WIDE_ROLES
        )

    def get_queryset(self):
        """
        Return only IncidentConfig records belonging to
        the authenticated user's tenant.

        Non-admin users receive an empty queryset.
        """

        if not self._is_admin():
            return IncidentConfig.objects.none()

        tenant = self._get_tenant()

        if not tenant:
            return IncidentConfig.objects.none()

        return (
            IncidentConfig.objects
            .filter(
                tenant=tenant,
                incident_type__tenant=tenant,
            )
            .select_related(
                "tenant",
                "incident_type",
            )
            .order_by(
                "incident_type__name"
            )
        )

    def perform_create(self, serializer):
        """
        Create configuration for the authenticated
        Admin's tenant.
        """

        if not self._is_admin():
            raise PermissionDenied(
                "Only Admin users can manage incident configuration."
            )

        tenant = self._get_tenant()

        if not tenant:
            raise ValidationError(
                "User is not assigned to a tenant."
            )

        serializer.save(
            tenant=tenant
        )

    def perform_update(self, serializer):
        """
        Update configuration.

        The tenant cannot be changed by the frontend.
        """

        if not self._is_admin():
            raise PermissionDenied(
                "Only Admin users can manage incident configuration."
            )

        tenant = self._get_tenant()

        if not tenant:
            raise ValidationError(
                "User is not assigned to a tenant."
            )

        serializer.save(
            tenant=tenant
        )

    def perform_destroy(self, instance):
        """
        Delete configuration.
        """

        if not self._is_admin():
            raise PermissionDenied(
                "Only Admin users can manage incident configuration."
            )

        instance.delete()


from datetime import timedelta
import math

import pandas as pd

from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (
    Event,
    TenantUseCase,
    TenantLocation,
    UserLocation,
)


class IncidentForecastModel:
    """
    Selects the best simple forecasting method using historical
    daily incident counts.

    The forecasting model is generic and is not tied to PPE
    or any hardcoded event type.
    """

    def __init__(self, historical_series):
        self.values = [
            max(0.0, float(value))
            for value in historical_series.tolist()
        ]

    def _one_step_prediction(self, model_name, values):
        if not values:
            return 0.0

        # ---------------------------------------------------------
        # Same weekday from previous week
        # ---------------------------------------------------------
        if model_name == "seasonal_naive_7":
            if len(values) >= 7:
                return values[-7]

            return values[-1]

        # ---------------------------------------------------------
        # Average of latest 7 days
        # ---------------------------------------------------------
        if model_name == "moving_average_7":
            recent_values = values[-7:]

            return (
                sum(recent_values) / len(recent_values)
                if recent_values
                else 0.0
            )

        # ---------------------------------------------------------
        # Linear trend from latest 14 days
        # ---------------------------------------------------------
        if model_name == "linear_trend_14":
            recent_values = values[-14:]

            if len(recent_values) < 2:
                return (
                    recent_values[-1]
                    if recent_values
                    else 0.0
                )

            x_values = list(range(len(recent_values)))

            x_mean = (
                sum(x_values) / len(x_values)
            )

            y_mean = (
                sum(recent_values) / len(recent_values)
            )

            numerator = sum(
                (x - x_mean) * (y - y_mean)
                for x, y in zip(
                    x_values,
                    recent_values,
                )
            )

            denominator = sum(
                (x - x_mean) ** 2
                for x in x_values
            )

            slope = (
                numerator / denominator
                if denominator
                else 0.0
            )

            intercept = (
                y_mean
                - (slope * x_mean)
            )

            return max(
                0.0,
                intercept
                + (
                    slope
                    * len(recent_values)
                ),
            )

        raise ValueError(
            f"Unknown forecast model: {model_name}"
        )

    def select_best_model(self):
        candidate_models = [
            "seasonal_naive_7",
            "moving_average_7",
            "linear_trend_14",
        ]

        if len(self.values) < 21:
            return {
                "model": "moving_average_7",
                "mae": None,
                "rmse": None,
            }

        validation_days = min(
            14,
            len(self.values) - 7,
        )

        validation_start = (
            len(self.values)
            - validation_days
        )

        model_scores = {}

        for model_name in candidate_models:
            errors = []

            for index in range(
                validation_start,
                len(self.values),
            ):
                training_values = (
                    self.values[:index]
                )

                actual_value = (
                    self.values[index]
                )

                predicted_value = (
                    self._one_step_prediction(
                        model_name,
                        training_values,
                    )
                )

                errors.append(
                    predicted_value
                    - actual_value
                )

            if not errors:
                continue

            mae = (
                sum(
                    abs(error)
                    for error in errors
                )
                / len(errors)
            )

            rmse = math.sqrt(
                sum(
                    error ** 2
                    for error in errors
                )
                / len(errors)
            )

            model_scores[model_name] = {
                "mae": mae,
                "rmse": rmse,
            }

        if not model_scores:
            return {
                "model": "moving_average_7",
                "mae": None,
                "rmse": None,
            }

        best_model = min(
            model_scores,
            key=lambda model_name:
                model_scores[model_name]["mae"],
        )

        return {
            "model": best_model,
            "mae": round(
                model_scores[best_model]["mae"],
                2,
            ),
            "rmse": round(
                model_scores[best_model]["rmse"],
                2,
            ),
        }

    def predict(
        self,
        model_name,
        days=1,
    ):
        values = list(self.values)
        predictions = []

        for _ in range(days):

            prediction = max(
                0,
                round(
                    self._one_step_prediction(
                        model_name,
                        values,
                    )
                ),
            )

            predictions.append(
                int(prediction)
            )

            values.append(
                prediction
            )

        return predictions


class AdvancedAnalyticsView(APIView):

    # =============================================================
    # TENANT
    # =============================================================

    def _get_tenant(self, request):
        profile = getattr(
            request.user,
            "profile",
            None,
        )

        if not profile:
            return None

        return profile.tenant

    # =============================================================
    # USER ALLOWED LOCATIONS
    # =============================================================

    def _get_allowed_tenant_locations(
        self,
        request,
        tenant,
    ):
        """
        Admin:
            All enabled locations belonging to tenant.

        Manager / Support:
            Only UserLocation assigned locations.
        """

        if tenant is None:
            return TenantLocation.objects.none()

        tenant_locations = (
            TenantLocation.objects
            .filter(
                tenant=tenant,
                enabled=True,
            )
        )

        role = getattr(
            getattr(
                request.user,
                "profile",
                None,
            ),
            "role",
            None,
        )

        if role in TENANT_WIDE_ROLES:
            return tenant_locations

        if role in LOCATION_SCOPED_ROLES:
            assigned_location_ids = (
                UserLocation.objects
                .filter(
                    user=request.user,
                    location__tenant=tenant,
                    location__enabled=True,
                )
                .values_list(
                    "location__location_id",
                    flat=True,
                )
            )

            return tenant_locations.filter(
                location_id__in=assigned_location_ids
            )

        return TenantLocation.objects.none()

    def _get_allowed_location_ids(
        self,
        request,
        tenant,
    ):
        return (
            self._get_allowed_tenant_locations(
                request,
                tenant,
            )
            .values_list(
                "location_id",
                flat=True,
            )
        )

    # =============================================================
    # ENABLED USE CASES
    # =============================================================

    def _get_enabled_use_cases(
        self,
        tenant,
    ):
        if tenant is None:
            return TenantUseCase.objects.none()

        return (
            TenantUseCase.objects
            .filter(
                tenant=tenant,
                enabled=True,
            )
            .order_by("id")
        )

    # =============================================================
    # QUERY PARAM HELPERS
    # =============================================================

    def _get_query_values(
        self,
        request,
        *parameter_names,
    ):
        """
        Supports:

            ?location_id=1
            ?location=1
            ?location_ids=1,2

        and:

            ?use_case_id=7
            ?use_case=NO_MASK
            ?incident_type=NO_MASK

        Returns a list of values.
        """

        values = []

        for parameter_name in parameter_names:

            raw_value = request.query_params.get(
                parameter_name
            )

            if raw_value is None:
                continue

            if isinstance(raw_value, str):
                raw_value = raw_value.strip()

                if not raw_value:
                    continue

                if raw_value.lower() in (
                    "all",
                    "all_locations",
                    "all_ppe",
                    "all_ppe_types",
                    "all_incident_types",
                ):
                    continue

                parts = raw_value.split(",")

                for part in parts:
                    part = part.strip()

                    if part:
                        values.append(part)

            else:
                values.append(
                    str(raw_value)
                )

        return list(
            dict.fromkeys(values)
        )

    # =============================================================
    # SELECTED TREND LOCATIONS
    # =============================================================

    def _get_selected_location_ids(
        self,
        request,
        tenant,
    ):
        """
        Determine which locations the Incident Trend should use.

        No location filter:
            All locations the user is allowed to access.

        Selected location:
            Only that location, provided it belongs to the user's
            allowed tenant locations.

        Multiple locations:
            Supports comma-separated IDs.
        """

        allowed_ids = set(
            self._get_allowed_location_ids(
                request,
                tenant,
            )
        )

        selected_values = self._get_query_values(
            request,
            "location_id",
            "location",
            "location_ids",
        )

        # "All Locations"
        if not selected_values:
            return allowed_ids

        selected_ids = set()

        for value in selected_values:

            try:
                location_id = int(value)
            except (
                TypeError,
                ValueError,
            ):
                continue

            # SECURITY:
            # Never allow a user to request a location outside
            # their tenant/location permissions.
            if location_id in allowed_ids:
                selected_ids.add(
                    location_id
                )

        return selected_ids

    # =============================================================
    # SELECTED TREND USE CASES
    # =============================================================

    def _get_selected_use_cases(
        self,
        request,
        tenant,
        enabled_use_cases,
    ):
        """
        Determine which TenantUseCases the Incident Trend uses.

        No use-case filter:
            All enabled tenant use cases.

        Selected use case:
            Only that enabled tenant use case.

        Supports:

            ?use_case_id=7
            ?use_case=NO_MASK
            ?use_case=No%20Mask
            ?incident_type=NO_MASK
        """

        selected_values = self._get_query_values(
            request,
            "use_case_id",
            "use_case",
            "use_case_code",
            "incident_type",
        )

        # "All PPE Types"
        if not selected_values:
            return enabled_use_cases

        selected_ids = set()

        for value in selected_values:

            # -----------------------------------------------------
            # Try ID
            # -----------------------------------------------------

            try:
                use_case_id = int(value)

                matching_ids = (
                    enabled_use_cases
                    .filter(
                        id=use_case_id
                    )
                    .values_list(
                        "id",
                        flat=True,
                    )
                )

                selected_ids.update(
                    matching_ids
                )

                continue

            except (
                TypeError,
                ValueError,
            ):
                pass

            # -----------------------------------------------------
            # Try code
            # -----------------------------------------------------

            matching_ids = (
                enabled_use_cases
                .filter(
                    code__iexact=value
                )
                .values_list(
                    "id",
                    flat=True,
                )
            )

            selected_ids.update(
                matching_ids
            )

            # -----------------------------------------------------
            # Try display name
            # -----------------------------------------------------

            matching_ids = (
                enabled_use_cases
                .filter(
                    name__iexact=value
                )
                .values_list(
                    "id",
                    flat=True,
                )
            )

            selected_ids.update(
                matching_ids
            )

        return enabled_use_cases.filter(
            id__in=selected_ids
        )

    # =============================================================
    # ACCESSIBLE EVENTS
    # =============================================================

    def _get_accessible_events(
        self,
        request,
        tenant,
    ):
        """
        Base event queryset.

        Tenant
            ↓
        User allowed locations
            ↓
        Tenant enabled cameras
            ↓
        Events
            ↓
        Rejected events excluded
        """

        if tenant is None:
            return Event.objects.none()

        allowed_location_ids = (
            self._get_allowed_location_ids(
                request,
                tenant,
            )
        )

        from .models import TenantCamera

        tenant_camera_ids = (
            TenantCamera.objects
            .filter(
                tenant=tenant,
                enabled=True,
                camera__location_id__in=(
                    allowed_location_ids
                ),
            )
            .values_list(
                "camera_id",
                flat=True,
            )
        )

        events = Event.objects.filter(
            camera_id__in=tenant_camera_ids,
        )

        from .models import EventReview

        rejected_event_ids = (
            EventReview.objects
            .filter(
                status="Rejected",
            )
            .values_list(
                "event_id",
                flat=True,
            )
        )

        events = events.exclude(
            event_id__in=rejected_event_ids
        )

        return events

    # =============================================================
    # RESOLVE EVENT USE CASE
    # =============================================================

    def _resolve_event_use_case(
        self,
        event,
        use_cases,
    ):
        classification = classify_incident(
            event,
            detections=event.detections.all(),
            frame_path=getattr(
                event,
                "frame_path",
                None,
            ),
            use_cases=use_cases,
        )

        return resolve_event_use_case(
            event,
            use_cases,
            classification,
        )

    # =============================================================
    # DAILY INCIDENT SERIES
    # =============================================================

    def build_daily_incident_series(
        self,
        request,
        tenant,
        use_cases,
        start_date,
        end_date,
        selected_location_ids=None,
    ):
        """
        Build daily incident counts.

        IMPORTANT:
        This now applies BOTH:

            Location filter
            Incident/use-case filter

        before counting events.
        """

        events = (
            self._get_accessible_events(
                request,
                tenant,
            )
            .filter(
                timestamp__date__range=(
                    start_date,
                    end_date,
                )
            )
            .select_related(
                "camera",
            )
            .prefetch_related(
                "detections",
            )
            .order_by(
                "timestamp"
            )
        )

        # ---------------------------------------------------------
        # Apply selected location filter
        # ---------------------------------------------------------

        if selected_location_ids is not None:

            events = events.filter(
                camera__location_id__in=(
                    selected_location_ids
                )
            )

        dates = pd.date_range(
            start=start_date,
            end=end_date,
            freq="D",
        )

        daily_counts = {
            date.date(): 0
            for date in dates
        }

        # ---------------------------------------------------------
        # Count only events resolving to selected use cases
        # ---------------------------------------------------------

        for event in events:

            if not event.timestamp:
                continue

            resolved = (
                self._resolve_event_use_case(
                    event,
                    use_cases,
                )
            )

            if not resolved:
                continue

            event_date = (
                timezone.localtime(
                    event.timestamp
                ).date()
                if timezone.is_aware(
                    event.timestamp
                )
                else event.timestamp.date()
            )

            if event_date not in daily_counts:
                continue

            daily_counts[event_date] += 1

        values = [
            daily_counts.get(
                date.date(),
                0,
            )
            for date in dates
        ]

        return pd.Series(
            values,
            index=dates,
            dtype=float,
        )

    # =============================================================
    # PARETO
    # =============================================================

    def build_pareto_data(
        self,
        events,
        use_cases,
    ):
        use_case_counts = {}

        for event in events:

            classification = classify_incident(
                event,
                detections=event.detections.all(),
                frame_path=getattr(
                    event,
                    "frame_path",
                    None,
                ),
                use_cases=use_cases,
            )

            resolved = resolve_event_use_case(
                event,
                use_cases,
                classification,
            )

            if not resolved:
                continue

            code = resolved["code"]
            name = resolved["name"]

            if code not in use_case_counts:
                use_case_counts[code] = {
                    "incident_type": name,
                    "count": 0,
                }

            use_case_counts[code]["count"] += 1

        sorted_data = sorted(
            use_case_counts.values(),
            key=lambda item:
                item["count"],
            reverse=True,
        )

        total_events = sum(
            item["count"]
            for item in sorted_data
        )

        if total_events == 0:
            return []

        pareto_data = []
        cumulative_count = 0

        for item in sorted_data:

            count = item["count"]

            cumulative_count += count

            percentage = (
                count / total_events
            ) * 100

            cumulative_percentage = (
                cumulative_count
                / total_events
            ) * 100

            pareto_data.append({
                "incident_type":
                    item["incident_type"],

                "count":
                    count,

                "percentage":
                    round(
                        percentage,
                        2,
                    ),

                "cumulative_percentage":
                    round(
                        min(
                            cumulative_percentage,
                            100,
                        ),
                        2,
                    ),
            })

        return pareto_data

    def build_location_safety_scores(
        self,
        events,
        use_cases,
        tenant
    ):
        """
        Build location-wise Safety Non-Compliance Score.

        Scoring configuration comes from IncidentConfig:

            Tenant
                ↓
            TenantUseCase
                ↓
            IncidentConfig
                ↓
            unit_score × weight

        Event classification comes from the existing
        TenantUseCase / match_config resolution pipeline.

        The frontend/admin never controls the scoring directly.
        """


        # ---------------------------------------------------------
        # Load IncidentConfig for this tenant
        # ---------------------------------------------------------

        incident_configs = (
            IncidentConfig.objects
            .filter(
                tenant=tenant,
                incident_type__tenant=tenant,
                incident_type__enabled=True,
            )
            .select_related(
                "incident_type"
            )
        )

        incident_config_map = {
            config.incident_type.code: {
                "unit_score": config.unit_score,
                "weight": config.weight,
            }
            for config in incident_configs
        }

        # ---------------------------------------------------------
        # If there are no scoring configurations,
        # return zero scores.
        # ---------------------------------------------------------

        if not incident_config_map:
            return []

        # ---------------------------------------------------------
        # Calculate penalty per location
        # ---------------------------------------------------------

        location_penalties = {}

        for event in events:

            # -----------------------------------------------------
            # Resolve event → TenantUseCase
            # -----------------------------------------------------

            classification = classify_incident(
                event,
                detections=event.detections.all(),
                frame_path=getattr(
                    event,
                    "frame_path",
                    None
                ),
                use_cases=use_cases,
            )

            resolved = resolve_event_use_case(
                event,
                use_cases,
                classification,
            )

            if not resolved:
                continue

            use_case_code = resolved.get("code")

            # -----------------------------------------------------
            # Only incidents configured for scoring are considered
            # -----------------------------------------------------

            config = incident_config_map.get(
                use_case_code
            )

            if not config:
                continue

            # -----------------------------------------------------
            # Resolve location
            # -----------------------------------------------------

            if not event.camera:
                continue

            location = event.camera.location

            if not location:
                continue

            # IMPORTANT:
            # Camera.location is a Location model instance.
            # Use its name instead of the model object so that
            # locations can be safely sorted and serialized.
            location_name = location.name

            if not location_name:
                continue

            # -----------------------------------------------------
            # Calculate this event's penalty
            # -----------------------------------------------------

            event_penalty = (
                config["unit_score"]
                * config["weight"]
            )

            location_penalties[location_name] = (
                location_penalties.get(
                    location_name,
                    0.0
                )
                + event_penalty
            )

        # ---------------------------------------------------------
        # Convert penalty → 0-100 non-compliance score
        # ---------------------------------------------------------

        location_scores = []

        for location, penalty_score in sorted(
            location_penalties.items()
        ):

            non_compliance_score = round(
                penalty_score,
                2,
            )


            location_scores.append({
                "location": location,
                "safety_score": non_compliance_score,
                "penalty_score": round(
                    penalty_score,
                    2
                ),
            })

        return location_scores

    # =============================================================
    # HEATMAP
    # =============================================================

    def build_heatmap_data(
        self,
        events,
        use_cases,
    ):
        heatmap_counts = {}

        for event in events:

            if not event.timestamp:
                continue

            classification = classify_incident(
                event,
                detections=event.detections.all(),
                frame_path=getattr(
                    event,
                    "frame_path",
                    None,
                ),
                use_cases=use_cases,
            )

            resolved = resolve_event_use_case(
                event,
                use_cases,
                classification,
            )

            if not resolved:
                continue

            code = resolved["code"]
            name = resolved["name"]

            hour = (
                timezone.localtime(
                    event.timestamp
                ).hour
                if timezone.is_aware(
                    event.timestamp
                )
                else event.timestamp.hour
            )

            key = (
                code,
                name,
                hour,
            )

            heatmap_counts[key] = (
                heatmap_counts.get(
                    key,
                    0,
                )
                + 1
            )

        heatmap_data = []

        for (
            code,
            name,
            hour,
        ), count in heatmap_counts.items():

            heatmap_data.append({
                "incident_type":
                    name,

                "incident_code":
                    code,

                "hour":
                    hour,

                "count":
                    count,
            })

        heatmap_data.sort(
            key=lambda item: (
                item["incident_type"],
                item["hour"],
            )
        )

        return heatmap_data

    # =============================================================
    # INCIDENT TREND
    # =============================================================

    def get_incident_trend(
        self,
        request,
        tenant,
        use_cases,
    ):
        """
        Incident Trend with dynamic filters.

        Example:

            /api/analytics/advanced/?use_case=NO_MASK

        or:

            /api/analytics/advanced/?use_case_id=7

        or:

            /api/analytics/advanced/?location_id=1

        or:

            /api/analytics/advanced/?use_case=NO_MASK&location_id=1

        The forecast is recalculated using ONLY the filtered
        incident history.
        """

        # ---------------------------------------------------------
        # History days
        # ---------------------------------------------------------

        try:
            history_days = int(
                request.query_params.get(
                    "history_days",
                    14,
                )
            )
        except (
            TypeError,
            ValueError,
        ):
            history_days = 14

        # ---------------------------------------------------------
        # Forecast days
        # ---------------------------------------------------------

        try:
            forecast_days = int(
                request.query_params.get(
                    "forecast_days",
                    7,
                )
            )
        except (
            TypeError,
            ValueError,
        ):
            forecast_days = 7

        history_days = min(
            max(history_days, 7),
            90,
        )

        forecast_days = min(
            max(forecast_days, 1),
            7,
        )

        # =========================================================
        # DYNAMIC FILTERS
        # =========================================================

        selected_location_ids = (
            self._get_selected_location_ids(
                request,
                tenant,
            )
        )

        selected_use_cases = (
            self._get_selected_use_cases(
                request,
                tenant,
                use_cases,
            )
        )

        # =========================================================
        # TODAY
        # =========================================================

        now = timezone.now()

        if timezone.is_aware(now):
            today = timezone.localtime(
                now
            ).date()
        else:
            today = now.date()

        # =========================================================
        # TRAINING DATA
        # =========================================================

        training_start = (
            today
            - timedelta(days=89)
        )

        historical_series = (
            self.build_daily_incident_series(
                request=request,
                tenant=tenant,
                use_cases=selected_use_cases,
                start_date=training_start,
                end_date=today,
                selected_location_ids=(
                    selected_location_ids
                ),
            )
        )

        # =========================================================
        # FORECAST MODEL
        # =========================================================

        forecast_engine = (
            IncidentForecastModel(
                historical_series
            )
        )

        model_result = (
            forecast_engine.select_best_model()
        )

        future_predictions = (
            forecast_engine.predict(
                model_result["model"],
                forecast_days,
            )
        )

        # =========================================================
        # DISPLAY HISTORY
        # =========================================================

        display_series = (
            historical_series.tail(
                history_days
            )
        )

        actual_data = [
            {
                "date":
                    date.strftime(
                        "%Y-%m-%d"
                    ),

                "day":
                    date.strftime(
                        "%a"
                    ),

                "count":
                    int(value),
            }
            for date, value
            in display_series.items()
        ]

        # =========================================================
        # HISTORICAL FORECAST / BACKTEST
        # =========================================================

        historical_forecast_data = []

        for (
            date,
            actual_value,
        ) in display_series.items():

            previous_data = (
                historical_series.loc[
                    historical_series.index
                    < date
                ]
            )

            if previous_data.empty:
                continue

            backtest_engine = (
                IncidentForecastModel(
                    previous_data
                )
            )

            backtest_result = (
                backtest_engine
                .select_best_model()
            )

            predicted_count = (
                backtest_engine.predict(
                    backtest_result["model"],
                    1,
                )[0]
            )

            historical_forecast_data.append({
                "date":
                    date.strftime(
                        "%Y-%m-%d"
                    ),

                "day":
                    date.strftime(
                        "%a"
                    ),

                "count":
                    int(predicted_count),

                "actual_count":
                    int(actual_value),

                "model":
                    backtest_result[
                        "model"
                    ],
            })

        # =========================================================
        # FUTURE FORECAST
        # =========================================================

        forecast_data = []

        for index, prediction in enumerate(
            future_predictions,
            start=1,
        ):

            forecast_date = (
                today
                + timedelta(
                    days=index
                )
            )

            forecast_data.append({
                "date":
                    forecast_date.strftime(
                        "%Y-%m-%d"
                    ),

                "day":
                    forecast_date.strftime(
                        "%a"
                    ),

                "count":
                    int(prediction),
            })

        # =========================================================
        # SUMMARY
        # =========================================================

        today_actual = (
            actual_data[-1]["count"]
            if actual_data
            else 0
        )

        tomorrow_prediction = (
            forecast_data[0]["count"]
            if forecast_data
            else 0
        )

        actual_7_day_total = sum(
            item["count"]
            for item in actual_data[-7:]
        )

        forecast_total = sum(
            item["count"]
            for item in forecast_data
        )

        total_incidents = sum(
            item["count"]
            for item in actual_data
        )

        # =========================================================
        # FILTER RESPONSE DATA
        # =========================================================

        allowed_location_ids = list(
            self._get_allowed_location_ids(
                request,
                tenant,
            )
        )

        allowed_locations = list(
            TenantLocation.objects
            .filter(
                tenant=tenant,
                enabled=True,
                location_id__in=(
                    allowed_location_ids
                ),
            )
            .select_related(
                "location"
            )
            .values(
                "location_id",
                "location__name",
            )
            .order_by(
                "location__name"
            )
        )

        enabled_use_case_data = list(
            use_cases.values(
                "id",
                "code",
                "name",
            )
        )

        # =========================================================
        # SELECTED FILTER INFO
        # =========================================================

        selected_location_data = list(
            TenantLocation.objects
            .filter(
                tenant=tenant,
                enabled=True,
                location_id__in=(
                    selected_location_ids
                ),
            )
            .select_related(
                "location"
            )
            .values(
                "location_id",
                "location__name",
            )
            .order_by(
                "location__name"
            )
        )

        selected_use_case_data = list(
            selected_use_cases.values(
                "id",
                "code",
                "name",
            )
        )

        # =========================================================
        # RETURN
        # =========================================================

        return {
            "actual":
                actual_data,

            "historical_forecast":
                historical_forecast_data,

            "forecast":
                forecast_data,

            "summary": {
                "today_actual":
                    today_actual,

                "tomorrow_prediction":
                    tomorrow_prediction,

                "actual_7_day_total":
                    actual_7_day_total,

                "forecast_total":
                    forecast_total,

                "total_incidents":
                    total_incidents,

                "history_days":
                    history_days,

                "forecast_days":
                    forecast_days,
            },

            "model": {
                "selected":
                    model_result["model"],

                "mae":
                    model_result.get(
                        "mae"
                    ),

                "rmse":
                    model_result.get(
                        "rmse"
                    ),
            },

            "filters": {
                "tenant_id":
                    tenant.id
                    if tenant
                    else None,

                "role":
                    getattr(
                        getattr(
                            request.user,
                            "profile",
                            None,
                        ),
                        "role",
                        None,
                    ),

                # All locations user can access
                "locations":
                    allowed_locations,

                # All enabled tenant use cases
                "use_cases":
                    enabled_use_case_data,

                # What is currently applied to trend
                "selected_locations":
                    selected_location_data,

                "selected_use_cases":
                    selected_use_case_data,
            },
        }

    # =============================================================
    # GET
    # =============================================================

    def get(self, request):

        try:

            # =====================================================
            # TENANT
            # =====================================================

            tenant = self._get_tenant(
                request
            )

            if tenant is None:
                return Response(
                    {
                        "error":
                            "Authenticated user is not associated with a tenant."
                    },
                    status=403,
                )

            # =====================================================
            # ENABLED USE CASES
            # =====================================================

            use_cases = (
                self._get_enabled_use_cases(
                    tenant
                )
            )

            # =====================================================
            # BASE ACCESSIBLE EVENTS
            # =====================================================

            events = (
                self._get_accessible_events(
                    request,
                    tenant,
                )
                .select_related(
                    "camera",
                    "camera__location",
                )
                .prefetch_related(
                    "detections",
                )
            )

            # =====================================================
            # 1. PARETO
            # =====================================================

            pareto_data = (
                self.build_pareto_data(
                    events,
                    use_cases,
                )
            )

            # ---------------------------------------------------------
            # 2. Location safety score
            # ---------------------------------------------------------

            location_scores = (
                self.build_location_safety_scores(
                    events,
                    use_cases,
                    tenant,
                )
            )

            # =====================================================
            # 3. HEATMAP
            # =====================================================

            heatmap_data = (
                self.build_heatmap_data(
                    events,
                    use_cases,
                )
            )

            # =====================================================
            # 4. INCIDENT TREND
            #
            # THIS IS NOW DYNAMIC.
            #
            # Frontend query parameters are read here.
            # =====================================================

            incident_trend = (
                self.get_incident_trend(
                    request=request,
                    tenant=tenant,
                    use_cases=use_cases,
                )
            )

            # =====================================================
            # RESPONSE
            # =====================================================

            return Response({
                "pareto":
                    pareto_data,

                "location_scores":
                    location_scores,

                "heatmap":
                    heatmap_data,

                "incident_trend":
                    incident_trend,
            })

        except Exception as error:

            return Response(
                {
                    "error":
                        str(error)
                },
                status=500,
            )
