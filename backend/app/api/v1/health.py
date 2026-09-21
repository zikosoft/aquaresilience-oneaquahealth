"""Liveness/readiness and platform health endpoints (P0 minimal observability)."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter
from sqlalchemy import text

from app.core.database import SessionLocal
from app.core.redis import check_redis

router = APIRouter(tags=["health"])


@router.get("/health/live")
def health_live() -> dict:
    """Process is up. Does not check dependencies."""
    return {"status": "ok", "time": datetime.now(timezone.utc).isoformat()}


@router.get("/health/ready")
def health_ready() -> dict:
    """Process + dependencies (DB, Redis) are ready to serve traffic."""
    checks = {"database": _check_database(), "redis": check_redis()}
    overall_ok = all(checks.values())
    return {
        "status": "ok" if overall_ok else "degraded",
        "checks": checks,
        "time": datetime.now(timezone.utc).isoformat(),
    }


def _check_database() -> bool:
    try:
        db = SessionLocal()
        try:
            db.execute(text("SELECT 1"))
            return True
        finally:
            db.close()
    except Exception:
        return False
