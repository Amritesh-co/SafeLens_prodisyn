from django.contrib.auth.models import User
from rest_framework.test import APIClient
from apps.api.models import (Tenant, TenantLocation, UserLocation, Event,
                             EmailAlertTracker)
from apps.api.roles import Role, STAFF_ROLES

# ---- EDIT THESE to match your urls.py ----
URL_EVENTS   = "/api/overview/events/"
URL_CAMERAS  = "/api/cameras/"
URL_LOCS     = "/api/locations/"
URL_USERS    = "/api/users/"
URL_GLOBAL   = "/api/settings/"
# ------------------------------------------

tenant = Tenant.objects.first()
tls = list(TenantLocation.objects.filter(tenant=tenant, enabled=True)[:2])
assert len(tls) >= 1, "Tenant needs at least 1 enabled location"
loc1 = tls[0]
print("Tenant:", tenant.name, "| assigned location:", loc1.location.name)

def make(username, role):
    u, _ = User.objects.get_or_create(username=username,
                                      defaults={"email": f"{username}@gmail.com"})
    u.is_staff = role in STAFF_ROLES
    u.is_active = True
    u.set_password("Test@12345")
    u.save()
    p = u.profile
    p.role, p.tenant, p.status = role, tenant, "Active"
    p.phone_number = "9876543210"
    p.alerts_email = True
    p.save()
    return u

users = {
    "Admin":      make("t_admin",   Role.ADMIN),
    "Management": make("t_mgmt",    Role.MANAGEMENT),
    "Manager":    make("t_manager", Role.MANAGER),
    "Supervisor": make("t_super",   Role.SUPERVISOR),
}
for r in ("Manager", "Supervisor"):
    UserLocation.objects.get_or_create(user=users[r], location=loc1)

def client_for(u):
    c = APIClient(SERVER_NAME="localhost")
    c.force_authenticate(user=u)
    return c

def count(resp):
    d = getattr(resp, "data", None)
    if isinstance(d, dict) and "count" in d: return d["count"]
    if isinstance(d, list): return len(d)
    return "-"

print("\n=== TEST 2/3: who sees what (status, count) ===")
for role, u in users.items():
    c = client_for(u)
    row = []
    for name, url in (("events", URL_EVENTS), ("cameras", URL_CAMERAS), ("locations", URL_LOCS)):
        r = c.get(url)
        row.append(f"{name}={r.status_code}/{count(r)}")
    print(f"{role:11}", "  ".join(row))
print("Expect: Admin and Management counts are largest; Manager and Supervisor smaller and equal.")

print("\n=== TEST 4: Manager creates an Admin (expect 400/403) ===")
r = client_for(users["Manager"]).post(URL_USERS, {
    "username": "t_evil", "email": "t_evil@gmail.com", "password": "Test@12345",
    "role": "Admin", "status": "Active", "phone_number": "9876543211"}, format="json")
print("status:", r.status_code, "| user created?", User.objects.filter(username="t_evil").exists())

print("\n=== TEST 5: Manager opens global settings (expect 403) ===")
print("status:", client_for(users["Manager"]).get(URL_GLOBAL).status_code)

print("\n=== TEST 6: Supervisor opens user list (expect 403) ===")
print("status:", client_for(users["Supervisor"]).get(URL_USERS).status_code)

print("\n=== TEST 7: create user with role Support (expect 400) ===")
r = client_for(users["Admin"]).post(URL_USERS, {
    "username": "t_old", "email": "t_old@gmail.com", "password": "Test@12345",
    "role": "Support", "status": "Active", "phone_number": "9876543212"}, format="json")
print("status:", r.status_code, r.data if r.status_code == 400 else "")

print("\n=== TEST 8/9: alert routing (needs the new get_target_recipients(event)) ===")
from apps.api.management.commands.poll_events import Command
cmd = Command()
same = Event.objects.filter(camera__location_id=loc1.location_id,
                            camera__tenant_config__tenant=tenant).order_by("-event_id").first()
other = Event.objects.filter(camera__tenant_config__tenant=tenant).exclude(
    camera__location_id=loc1.location_id).order_by("-event_id").first()
for label, ev in (("assigned location", same), ("different location", other)):
    if not ev:
        print(label, ": no event in DB to test with"); continue
    rec = cmd.get_target_recipients(ev)
    print(f"{label}: event {ev.event_id} -> supervisor alerted? "
          f"{'t_super@gmail.com' in rec['email']}")
print("Expect: True for assigned location, False for different location.")

print("\n=== TEST 10: media link (expect 302 with token, 404 without) ===")
from apps.api.views import generate_media_access_token
ev = same or other
if ev:
    anon = APIClient(SERVER_NAME="localhost")
    base = f"/api/media-redirect/image/{ev.event_id}/image.jpg"
    print("with token   :", anon.get(base, {"token": generate_media_access_token(ev.event_id)}).status_code)
    print("without token:", anon.get(base).status_code)
