from django.db import models


class Role(models.TextChoices):
    ADMIN = 'Admin', 'Admin'
    MANAGEMENT = 'Management', 'Management'
    MANAGER = 'Manager', 'Manager'
    SUPERVISOR = 'Supervisor', 'Supervisor'


DEFAULT_ROLE = Role.SUPERVISOR

# Full tenant access, can manage users/config (Management = same as Admin)
TENANT_WIDE_ROLES = (Role.ADMIN, Role.MANAGEMENT)

# Only see their assigned locations
LOCATION_SCOPED_ROLES = (Role.MANAGER, Role.SUPERVISOR)

# Get is_staff=True (needed for IsAdminUser on the user-management API)
STAFF_ROLES = (Role.ADMIN, Role.MANAGEMENT)
