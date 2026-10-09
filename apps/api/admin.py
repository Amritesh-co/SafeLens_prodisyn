"""
File Name: api/admin.py
Description: 
    Registers the Django Models with the built-in Django Admin Interface.
    Overrides the default User Admin to inline the custom UserProfile fields 
    (Role, Location, Toggles) so they can be securely edited by superusers.
Author: Safelens AI Backend Team
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from .models import UserActivityLog, NotificationRecipient, EmailAlertTracker, UserProfile, EventReview, Event,Camera,Location, NotificationDeliveryLog, Tenant, TenantLocation, TenantCamera,TenantUseCase,UserLocation, IncidentConfig, AssistantQueryLog

class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    verbose_name_plural = 'User Profile'

class UserAdmin(BaseUserAdmin):
    """
    Overrides the default Django Authentication UserAdmin panel.
    Displays custom UserProfile fields directly in the user list view 
    so administrators can instantly see Roles, Locations, and Twilio active channels.
    """
    inlines = (UserProfileInline,)
    # list_display = BaseUserAdmin.list_display + ('get_role', 'get_status', 'get_assigned_locations', 'get_alerts_email', 'get_alerts_sms', 'get_alerts_whatsapp', 'get_alerts_teams')
    list_display = BaseUserAdmin.list_display + ('get_role', 'get_status', 'get_assigned_locations', 'get_alerts_email', 'get_alerts_sms', 'get_alerts_whatsapp', 'get_alerts_teams', 'get_daily_summary')
    
    def get_inline_instances(self, request, obj=None):
        if not obj:
            return []
        return super().get_inline_instances(request, obj)
    
    def get_role(self, obj):
        return obj.profile.role if hasattr(obj, 'profile') else 'User'
    get_role.short_description = 'Role'

    def get_status(self, obj):
        return obj.profile.status if hasattr(obj, 'profile') else 'Active'
    get_status.short_description = 'Status'

    def get_assigned_locations(self, obj):
        locations = (
            UserLocation.objects
            .filter(user=obj)
            .select_related('location__location')
            .order_by('location__location__name')
        )

        location_names = [
            assignment.location.location.name
            for assignment in locations
            if assignment.location and assignment.location.location
        ]

        return ', '.join(location_names) if location_names else 'No locations assigned'

    get_assigned_locations.short_description = 'Assigned Locations'

    def get_alerts_email(self, obj):
        return obj.profile.alerts_email if hasattr(obj, 'profile') else True
    get_alerts_email.short_description = 'Email Alerts'
    get_alerts_email.boolean = True

    def get_alerts_sms(self, obj):
        return obj.profile.alerts_sms if hasattr(obj, 'profile') else False
    get_alerts_sms.short_description = 'SMS Alerts'
    get_alerts_sms.boolean = True

    def get_alerts_whatsapp(self, obj):
        return obj.profile.alerts_whatsapp if hasattr(obj, 'profile') else False
    get_alerts_whatsapp.short_description = 'WhatsApp Alerts'
    get_alerts_whatsapp.boolean = True

    def get_alerts_teams(self, obj):
        return obj.profile.alerts_teams if hasattr(obj, 'profile') else False
    get_alerts_teams.short_description = 'Teams 1:1'
    get_alerts_teams.boolean = True

    def get_daily_summary(self, obj):
        return obj.profile.daily_summary if hasattr(obj, 'profile') else False
    get_daily_summary.short_description = 'Daily Summary'
    get_daily_summary.boolean = True

# Re-register UserAdmin
admin.site.unregister(User)
admin.site.register(User, UserAdmin)

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):

    list_display = (
        'user',
        'role',
        'get_assigned_locations',
        'phone_number',
        'status',
        'alerts_email',
        'alerts_sms',
        'alerts_whatsapp',
        'alerts_teams',
        'daily_summary',
    )

    list_filter = (
        'role',
        'status',
        'alerts_email',
        'alerts_sms',
        'alerts_whatsapp',
        'alerts_teams',
        'daily_summary',
    )

    search_fields = (
        'user__username',
        'location',
        'phone_number',
        'user__email',
    )
# @admin.register(UserProfile)
# class UserProfileAdmin(admin.ModelAdmin):
#     list_display = ('user', 'role', 'get_assigned_locations', 'phone_number', 'status', 'alerts_email', 'alerts_sms', 'alerts_whatsapp', 'alerts_teams')
#     list_filter = ('role', 'status', 'alerts_email', 'alerts_sms', 'alerts_whatsapp', 'alerts_teams')
#     search_fields = ('user__username', 'location', 'phone_number', 'user__email')


    def get_assigned_locations(self, obj):
        locations = (
            UserLocation.objects
            .filter(user=obj.user)
            .select_related('location__location')
            .order_by('location__location__name')
        )

        location_names = [
            assignment.location.location.name
            for assignment in locations
            if assignment.location and assignment.location.location
        ]

        return ', '.join(location_names) if location_names else 'No locations assigned'

    get_assigned_locations.short_description = 'Assigned Locations'

@admin.register(UserActivityLog)
class UserActivityLogAdmin(admin.ModelAdmin):
    list_display = ('user', 'login_time', 'logout_time', 'ip_address')
    list_filter = ('user', 'login_time')
    search_fields = ('user__username', 'ip_address')

@admin.register(NotificationRecipient)
class NotificationRecipientAdmin(admin.ModelAdmin):
    list_display = ('email', 'name', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('email', 'name')

@admin.register(EmailAlertTracker)
class EmailAlertTrackerAdmin(admin.ModelAdmin):
    """
    Admin explicitly for the Global Alert Settings.
    Exposes list_editable so superusers can check/uncheck the global kill switches 
    for SMS, WhatsApp, and Email directly from the admin list view.
    """
    list_display = ('id', 'is_email_enabled', 'is_sms_enabled', 'is_whatsapp_enabled', 'is_teams_graph_enabled', 'is_daily_summary_enabled','daily_summary_time', 'last_event_id', 'last_checked')
    list_editable = ('is_email_enabled', 'is_sms_enabled', 'is_whatsapp_enabled', 'is_teams_graph_enabled', 'is_daily_summary_enabled','daily_summary_time',)

@admin.register(EventReview)
class EventReviewAdmin(admin.ModelAdmin):
    """
    Admin for Managing Incident Comments and Statuses.
    Allows Superusers to audit, update, and delete manager reviews.
    """
    list_display = ('event_id', 'get_location', 'status', 'comments', 'updated_by', 'updated_at')
    list_filter = ('status', 'updated_by', 'updated_at')
    search_fields = ('event_id', 'comments')
    readonly_fields = ('updated_at',)

    def get_location(self, obj):
        """
        Dynamically fetches the location from the unmanaged Event table.
        This provides context (Location) without requiring a physical foreign key.
        """
        try:
            event = Event.objects.get(event_id=obj.event_id)
            return event.camera.location if event.camera else "Unknown"
        except Event.DoesNotExist:
            return "N/A (Event Deleted)"
    get_location.short_description = 'Incident Location'


@admin.register(NotificationDeliveryLog)
class NotificationDeliveryLogAdmin(admin.ModelAdmin):
    list_display = (
        'created_at', 'event_id', 'channel', 'recipient', 'status',
        'provider', 'provider_message_id', 'template_name'
    )
    list_filter = ('channel', 'status', 'provider', 'template_name', 'created_at')
    search_fields = ('recipient', 'provider_message_id', 'event_id', 'error_message')
    readonly_fields = (
        'created_at', 'event_id', 'channel', 'recipient', 'status',
        'provider', 'provider_message_id', 'template_name', 'error_message', 'details'
    )

@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'code',
        'is_active',
        'created_at',
        'updated_at',
    )
    list_filter = ('is_active',)
    search_fields = ('name', 'code')
    readonly_fields = ('created_at', 'updated_at')

@admin.register(TenantLocation)
class TenantLocationAdmin(admin.ModelAdmin):
    list_display = (
        'get_location',
        'tenant',
        'enabled',
    )

    list_filter = (
        'tenant',
        'enabled',
    )

    search_fields = (
        'location__name',
        'location__code',
        'tenant__name',
        'tenant__code',
    )

    autocomplete_fields = (
        'tenant',
        'location',
    )

    def get_location(self, obj):
        return obj.location.name

    get_location.short_description = 'Location'

@admin.register(TenantCamera)
class TenantCameraAdmin(admin.ModelAdmin):
    list_display = (
        'camera',
        'tenant',
        'get_location',
        'enabled',
    )

    list_filter = (
        'tenant',
        'enabled',
    )

    search_fields = (
        'camera__name',
        'camera__code',
        'tenant__name',
        'tenant__code',
        'camera__location__name',
        'camera__location__code',
    )

    autocomplete_fields = (
        'camera',
        'tenant',
    )

    def get_location(self, obj):
        if obj.camera and obj.camera.location:
            return obj.camera.location.name
        return 'Unknown'

    get_location.short_description = 'Location'

@admin.register(TenantUseCase)
class TenantUseCaseAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'code',
        'tenant',
        'enabled',
        'show_on_dashboard',
        'show_in_filters',
    )

    list_filter = (
        'tenant',
        'enabled',
        'show_on_dashboard',
        'show_in_filters',
    )

    search_fields = (
        'name',
        'code',
        'tenant__name',
    )

@admin.register(IncidentConfig)
class IncidentConfigAdmin(admin.ModelAdmin):
    list_display = (
        'get_incident_type',
        'get_incident_code',
        'tenant',
        'unit_score',
        'weight',
    )

    list_filter = (
        'tenant',
        'incident_type',
    )

    search_fields = (
        'incident_type__name',
        'incident_type__code',
        'tenant__name',
        'tenant__code',
    )

    autocomplete_fields = (
        'tenant',
        'incident_type',
    )

    def get_incident_type(self, obj):
        return obj.incident_type.name

    get_incident_type.short_description = 'Incident'

    def get_incident_code(self, obj):
        return obj.incident_type.code

    get_incident_code.short_description = 'Code'

@admin.register(UserLocation)
class UserLocationAdmin(admin.ModelAdmin):
    list_display = (
        'user',
        'location',
        'get_tenant',
    )

    list_filter = (
        'location__tenant',
        'location',
    )

    search_fields = (
        'user__username',
        'location__name',
        'location__tenant__name',
    )

    autocomplete_fields = (
        'user',
        'location',
    )

    def get_tenant(self, obj):
        return obj.location.tenant

    get_tenant.short_description = 'Tenant'


@admin.register(Camera)
class CameraAdmin(admin.ModelAdmin):
    list_display = (
        'camera_id',
        'name',
        'location',
        'stream_uri',
        'is_active',
    )

    list_filter = (
        'is_active',
        'location',
    )

    search_fields = (
        'name',
        'location',
        'stream_uri',
    )

    readonly_fields = (
        'camera_id',
        'name',
        'location',
        'stream_uri',
        'is_active',
    )

@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ('location_id', 'name', 'code', 'location_type', 'timezone')
    search_fields = ('name', 'code', 'timezone')

@admin.register(AssistantQueryLog)
class AssistantQueryLogAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'user', 'tenant', 'status', 'short_question', 'latency_ms')
    list_filter = ('status', 'tenant', 'model_name')
    search_fields = ('question', 'answer', 'user__username')
    readonly_fields = [f.name for f in AssistantQueryLog._meta.fields]

    def short_question(self, obj):
        return obj.question[:80]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
