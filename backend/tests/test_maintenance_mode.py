"""Session 017 — maintenance-mode gate.

Settings > System > Maintenance mode has existed since P0 (stored, shown
and saved in the UI) but nothing ever read it (real-machine user report:
"le mode maintenance veut dire quoi ?"). `MaintenanceModeMiddleware`
(app.core.maintenance) wires it up: while enabled, any state-changing
(non-GET/HEAD/OPTIONS) request under /api/v1 is refused with 503 for
everyone except an authenticated Administrator.

Uses the real Postgres test DB directly (same idiom as test_intelligence.py
— no per-test transaction isolation across the whole app), so every test
here resets `maintenance_mode` back to False in a `finally` block: leaving
it True would silently break unrelated tests in other files that run a
write request afterwards.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select

from app.models.rbac import Role, UserRole
from app.models.settings import AppSetting
from app.models.user import User
from app.core.security import hash_password


def _set_maintenance_mode(db_session, enabled: bool) -> None:
    row = db_session.execute(select(AppSetting).where(AppSetting.key == "system")).scalar_one()
    row.value = {**row.value, "maintenance_mode": enabled}
    db_session.commit()


def _login_as(client, db_session, role_code: str) -> dict:
    role = db_session.execute(select(Role).where(Role.code == role_code)).scalar_one()
    email = f"{role_code.lower()}-{uuid.uuid4().hex[:8]}@aquaresilience.demo"
    user = User(email=email, hashed_password=hash_password("TestPass!2026"), full_name="Test User", is_active=True)
    db_session.add(user)
    db_session.flush()
    db_session.add(UserRole(user_id=user.id, role_id=role.id))
    db_session.commit()
    login = client.post("/api/v1/auth/login", json={"email": email, "password": "TestPass!2026"})
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def test_maintenance_mode_off_by_default_writes_work_normally(client, admin_token, db_session):
    try:
        _set_maintenance_mode(db_session, False)
        resp = client.post(
            "/api/v1/intelligence/analyze",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={},
        )
        assert resp.status_code == 200  # reaches the route at all (ok=False is a graceful business outcome, not a block)
    finally:
        _set_maintenance_mode(db_session, False)


def test_maintenance_mode_blocks_non_admin_writes(client, db_session):
    try:
        operator_headers = _login_as(client, db_session, "OPERATOR")
        _set_maintenance_mode(db_session, True)

        resp = client.post("/api/v1/intelligence/analyze", headers=operator_headers, json={})
        assert resp.status_code == 503
        body = resp.json()
        assert body["error"]["code"] == "MAINTENANCE_MODE"
    finally:
        _set_maintenance_mode(db_session, False)


def test_maintenance_mode_still_allows_administrator_writes(client, admin_token, db_session):
    """An Administrator must still be able to act — in particular, to turn
    maintenance back off — while it's enabled."""
    try:
        _set_maintenance_mode(db_session, True)
        resp = client.post(
            "/api/v1/intelligence/analyze",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={},
        )
        assert resp.status_code == 200
    finally:
        _set_maintenance_mode(db_session, False)


def test_maintenance_mode_never_blocks_reads(client, db_session):
    try:
        operator_headers = _login_as(client, db_session, "OPERATOR")
        _set_maintenance_mode(db_session, True)

        resp = client.get("/api/v1/risk/current", headers=operator_headers)
        assert resp.status_code == 200
    finally:
        _set_maintenance_mode(db_session, False)


def test_maintenance_mode_never_blocks_login(client, db_session):
    try:
        _set_maintenance_mode(db_session, True)
        from app.core.config import settings

        resp = client.post(
            "/api/v1/auth/login",
            json={"email": settings.demo_admin_email, "password": settings.demo_admin_password},
        )
        assert resp.status_code == 200
    finally:
        _set_maintenance_mode(db_session, False)


def test_maintenance_mode_never_blocks_infra_healthchecks(client, db_session):
    try:
        _set_maintenance_mode(db_session, True)
        assert client.get("/health").status_code == 200
        assert client.get("/api/v1/health/live").status_code == 200
    finally:
        _set_maintenance_mode(db_session, False)
