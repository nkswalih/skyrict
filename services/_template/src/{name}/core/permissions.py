"""Permission constants and RBAC helpers."""

from __future__ import annotations

from enum import Enum


class Permission(str, Enum):
    """All permissions in the system. Use with require_permission()."""

    # Users
    USERS_READ = "users:read"
    USERS_WRITE = "users:write"
    USERS_DELETE = "users:delete"

    # Organizations
    ORGS_READ = "orgs:read"
    ORGS_WRITE = "orgs:write"
    ORGS_DELETE = "orgs:delete"

    # Settings
    SETTINGS_READ = "settings:read"
    SETTINGS_WRITE = "settings:write"

    # Audit
    AUDIT_READ = "audit:read"

    # Admin
    ADMIN = "admin"


# Role -> permissions mapping
ROLE_PERMISSIONS: dict[str, list[Permission]] = {
    "owner": list(Permission),  # all permissions
    "admin": [
        Permission.USERS_READ,
        Permission.USERS_WRITE,
        Permission.ORGS_READ,
        Permission.ORGS_WRITE,
        Permission.SETTINGS_READ,
        Permission.SETTINGS_WRITE,
        Permission.AUDIT_READ,
    ],
    "member": [
        Permission.USERS_READ,
        Permission.ORGS_READ,
        Permission.SETTINGS_READ,
    ],
    "viewer": [
        Permission.USERS_READ,
    ],
}
