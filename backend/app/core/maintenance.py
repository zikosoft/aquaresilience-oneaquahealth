"""Maintenance-mode gate.

Settings > System > Maintenance mode has existed since P0 (stored, shown
and saved in the UI) but nothing ever read it — flipping it changed
nothing (real-machine user report: "le mode maintenance veut dire quoi ?").

Wired here as a genuine cross-cutting gate: while enabled, any
state-changing request (anything but GET/HEAD/OPTIONS) under the
versioned API is refused with 503 for everyone except an authenticated
Administrator — so Operators/Viewers get a clear, translated-on-the-
frontend "read-only, platform in maintenance" response instead of a
confusing failure, and an Administrator can still act (in particular,
still turn the flag back off).

Implemented as ASGI middleware rather than a per-route dependency: the
alternative would mean adding it to every mutating endpoint across 9
router modules, which is both a much larger diff and easy to forget on a
new endpoint added later — one cross-cutting gate here is smaller and
cannot be missed.
"""
from __future__ import annotations

from uuid import UUID

import jwt
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.config import settings as app_settings
from app.core.database import SessionLocal
from app.core.security import TokenType, decode_token

_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
_API_PREFIX = app_settings.api_v1_prefix
# Always allowed, maintenance or not: authenticating (an Administrator must
# be able to log in to turn maintenance back off) and both infra
# healthchecks (Docker / the reverse proxy's upstream checks).
_ALWAYS_ALLOWED_PREFIXES = (f"{_API_PREFIX}/auth/",)
_ALWAYS_ALLOWED_PATHS = {f"{_API_PREFIX}/health/live", f"{_API_PREFIX}/health/ready", "/health"}

_MAINTENANCE_ENVELOPE = {
    "error": {
        "code": "MAINTENANCE_MODE",
        "message": "The platform is in maintenance mode. Read access still works; only an Administrator can make changes right now.",
        "details": None,
    }
}


def _caller_is_administrator(db: Session, request: Request) -> bool:
    auth_header = request.headers.get("authorization", "")
    if not auth_header.lower().startswith("bearer "):
        return False
    try:
        payload = decode_token(auth_header.split(" ", 1)[1])
        if payload.get("type") != TokenType.ACCESS.value:
            return False
        from app.models.user import User  # local import avoids cycles, mirrors deps.py

        user = db.get(User, UUID(payload["sub"]))
        if user is None or not user.is_active:
            return False
        from app.services.rbac_service import user_has_permission  # local import avoids cycles

        return user_has_permission(db, user, "ADMINISTRATION", "EDIT")
    except (jwt.PyJWTError, ValueError, TypeError, KeyError):
        return False


def _is_blocked(request: Request) -> bool:
    """Sync (DB + JWT decode is blocking) — run inside a threadpool by
    `dispatch` below rather than directly on the event loop."""
    db = SessionLocal()
    try:
        from app.models.settings import AppSetting  # local import avoids cycles

        row = db.execute(select(AppSetting).where(AppSetting.key == "system")).scalar_one_or_none()
        if row is None or not (row.value or {}).get("maintenance_mode"):
            return False
        return not _caller_is_administrator(db, request)
    finally:
        db.close()


class MaintenanceModeMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if (
            request.method in _SAFE_METHODS
            or path in _ALWAYS_ALLOWED_PATHS
            or any(path.startswith(p) for p in _ALWAYS_ALLOWED_PREFIXES)
            or not path.startswith(_API_PREFIX)
        ):
            return await call_next(request)

        blocked = await run_in_threadpool(_is_blocked, request)
        if blocked:
            return JSONResponse(status_code=503, content=_MAINTENANCE_ENVELOPE)
        return await call_next(request)
