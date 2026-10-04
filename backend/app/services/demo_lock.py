"""Optional lock on the shared demo administrator account.

When `LOCK_DEMO_ADMIN=true`, the account whose email is `DEMO_ADMIN_EMAIL`, and
the ADMINISTRATOR role's permission grants, cannot be edited, deactivated,
deleted or re-permissioned through the API. Everything else (creating other
users, changing other roles, all Settings) stays open, so the account that is
handed out for the demo can never be locked out by another person using it.
"""
from __future__ import annotations

from app.core.config import settings
from app.core.errors import ForbiddenError
from app.models.rbac import Role
from app.models.user import User

ADMINISTRATOR_ROLE_CODE = "ADMINISTRATOR"
_MESSAGE = "This is the protected demo administrator account and cannot be modified."


def is_locked_demo_admin(user: User) -> bool:
    return settings.lock_demo_admin and user.email.lower() == settings.demo_admin_email.lower()


def ensure_user_not_locked(user: User) -> None:
    if is_locked_demo_admin(user):
        raise ForbiddenError(message=_MESSAGE)


def ensure_role_not_locked(role: Role | None) -> None:
    if settings.lock_demo_admin and role is not None and role.code == ADMINISTRATOR_ROLE_CODE:
        raise ForbiddenError(message="The Administrator role's permissions are locked in this demo.")
