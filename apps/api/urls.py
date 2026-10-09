"""
File Name: api/urls.py
Description: 
    URL routing logic for the Safelens REST API. 
    Uses Django Rest Framework Routers to automatically generate 
    standardized endpoints (GET, POST, PUT, DELETE) for nested ViewSets.
    Also registers standalone views like Login/Logout and Notifications.
Author: Safelens AI Backend Team
"""

from django.urls import path, include
from rest_framework import routers

from .views import EventViewSet,EventCountSummaryView, CameraViewSet, AccessDecisionViewSet, OverviewViewSet, CustomAuthToken, LogoutView, UserViewSet, UserActivityLogViewSet, SendNotificationView, EventReviewViewSet, GlobalSettingsViewSet, LocationListView, RoleListView, NotificationDeliveryLogViewSet, RetryFailedWhatsAppView, IncidentStreamView, ProxyDownloadView, ProxyMediaView, ModuleControlView, EventIngestView, ForgotPasswordView, ResetPasswordConfirmView, AdvancedAnalyticsView, UserLocationViewSet, IncidentConfigViewSet
from rest_framework.authtoken.views import obtain_auth_token
from .assistant.views import AssistantAskView

router = routers.DefaultRouter()
router.register(r'events', EventViewSet, basename='event')
router.register(r'cameras', CameraViewSet, basename='camera')
router.register(r'decisions', AccessDecisionViewSet, basename='decision')
router.register(r'users', UserViewSet)
router.register(
    r'user-locations',
    UserLocationViewSet,
    basename='user-locations'
)
router.register(r'activity-logs', UserActivityLogViewSet, basename='activity-log')
router.register(r'overview', OverviewViewSet, basename='overview')
router.register(r'reviews', EventReviewViewSet, basename='review')
router.register(r'settings', GlobalSettingsViewSet, basename='settings')
router.register(r'notification-history', NotificationDeliveryLogViewSet, basename='notification-history')
router.register(
    r'incident-config',
    IncidentConfigViewSet,
    basename='incident-config'
)

# Import MediaRedirectView
from .views import MediaRedirectView, TenantConfigView

urlpatterns = [
    path('auth/reset-password-confirm/', ResetPasswordConfirmView.as_view(), name='reset-password-confirm'),
    path('auth/forgot-password/', ForgotPasswordView.as_view(), name='forgot-password'),
    path('events/ingest/', EventIngestView.as_view(), name='event-ingest'),
    path('', include(router.urls)),
    path('locations/', LocationListView.as_view()),
    path('roles/', RoleListView.as_view()),
    path('login/', CustomAuthToken.as_view()),
    path('logout/', LogoutView.as_view()),
    path('incidents/stream/', IncidentStreamView.as_view()),
    path('notifications/send/', SendNotificationView.as_view()),
    path('notifications/retry-whatsapp/', RetryFailedWhatsAppView.as_view()),
    path('proxy-media/', ProxyMediaView.as_view()),
    path('proxy-download/', ProxyDownloadView.as_view()),
    path('assistant/ask/', AssistantAskView.as_view(), name='assistant-ask'),
    path('<str:module>/<str:action>', ModuleControlView.as_view()),
    path('media-redirect/<str:media_type>/<int:event_id>/', MediaRedirectView.as_view(), name='media-redirect'),
    path('media-redirect/<str:media_type>/<int:event_id>/<str:filename>', MediaRedirectView.as_view(), name='media-redirect-file'),
    path('analytics/advanced/', AdvancedAnalyticsView.as_view(), name='advanced-analytics'),
    path("event-dashboard-summary/", EventCountSummaryView.as_view(), name="event-count-summary"),
    
    path(
        "config/",
        TenantConfigView.as_view(),
        name="tenant-config"
    ),
]




