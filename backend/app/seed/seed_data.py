"""Idempotent seed: modules, permissions, roles, role_permissions matrix,
default settings rows, and the demo Administrator user.

Run with: `python -m app.seed.seed_data`
Safe to run repeatedly (upserts by unique code/key).
"""
from __future__ import annotations

import sys

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models.rbac import Module, Permission, Role, RolePermission, UserRole
from app.models.settings import AppSetting
from app.models.user import User

MODULES = [
    ("DASHBOARD", "Command Center", 10),
    ("MAP", "Resilience Map", 20),
    ("ALERTS", "Early Warnings", 30),
    ("AI_INTELLIGENCE", "AI Intelligence", 40),
    ("SCENARIOS", "Scenario Simulator", 50),
    ("DATA_SOURCES", "Data Sources", 60),
    ("SETTINGS", "Settings", 70),
    ("ADMINISTRATION", "Administration", 80),
]

PERMISSIONS = [
    ("VIEW", "View"),
    ("CREATE", "Create"),
    ("EDIT", "Edit"),
    ("DELETE", "Delete"),
    ("EXECUTE", "Execute"),
    ("ADMIN", "Administer"),
]

ROLES = [
    ("ADMINISTRATOR", "Administrator", "Full platform access, including Settings and Users & Access.", True),
    ("OPERATOR", "Operator", "Operates the monitoring platform: acknowledges alerts, runs scenarios.", True),
    ("VIEWER", "Viewer", "Read-only access to monitoring, map, alerts, intelligence and scenarios.", True),
]

# Role code -> list of (module_code, permission_code)
OPERATOR_GRANTS_MODULES = ["DASHBOARD", "MAP", "ALERTS", "AI_INTELLIGENCE", "SCENARIOS", "DATA_SOURCES"]
OPERATOR_GRANTS_PERMISSIONS = ["VIEW", "EDIT", "EXECUTE"]

VIEWER_GRANTS_MODULES = ["DASHBOARD", "MAP", "ALERTS", "AI_INTELLIGENCE", "SCENARIOS", "DATA_SOURCES"]
VIEWER_GRANTS_PERMISSIONS = ["VIEW"]

DEFAULT_APP_SETTINGS = [
    ("GENERAL", "general", {"timezone": "Europe/Paris", "date_format": "YYYY-MM-DD"},
     "General platform configuration."),
    ("LANGUAGES", "languages", {
        "default_locale": "en",
        "enabled_locales": ["en", "fr", "es", "pt", "no", "el", "de", "it", "nl"],
    }, "Enabled UI languages and default locale."),
    ("DATA_SOURCES", "sources", {"sources": []}, "Configured environmental data sources (populated in P1)."),
    ("SCHEDULER", "scheduler", {"situation_brief_interval_hours": 4}, "Background scheduler cadence."),
    ("RISK_ENGINE", "risk_engine", {
        "weights": {"rainfall": 0.3, "hydrology": 0.3, "environmental": 0.2, "trend": 0.2},
        "thresholds": {"low": 25, "moderate": 50, "high": 75},
    }, "Deterministic risk engine weights and severity thresholds (implemented in P2)."),
    ("ALERTS", "alerts", {"lifecycle": ["ACTIVE", "ACKNOWLEDGED", "RESOLVED"], "notification_channels": []},
     "Early warning lifecycle and notification configuration."),
    # P2.1: tile provider only — no default lat/lon/zoom stored here. Those
    # already live on the `City` row the GENERAL tab's `city` setting names
    # (D016); duplicating them into a second settings row would just be two
    # places that could drift out of sync for one hackathon-scope city.
    # P4.1: risk_layer_opacity (0-100) added for the map's risk-level circle
    # layer around the river gauge station — user-requested, Settings-only
    # control (no live-reactive push to already-open maps, same "deployment
    # default, takes effect on next load" model tile_provider already has).
    (
        "MAP",
        "map",
        {"tile_provider": "osm", "risk_layer_opacity": 35},
        "Map tile provider (default view comes from the configured city) and risk layer opacity.",
    ),
    ("SYSTEM", "system", {"maintenance_mode": False}, "System-level toggles."),
]


def seed_modules(db: Session) -> dict[str, Module]:
    out: dict[str, Module] = {}
    for code, name, order in MODULES:
        module = db.execute(select(Module).where(Module.code == code)).scalar_one_or_none()
        if module is None:
            module = Module(code=code, name=name, sort_order=order)
            db.add(module)
            db.flush()
        else:
            module.name, module.sort_order = name, order
        out[code] = module
    return out


def seed_permissions(db: Session) -> dict[str, Permission]:
    out: dict[str, Permission] = {}
    for code, name in PERMISSIONS:
        perm = db.execute(select(Permission).where(Permission.code == code)).scalar_one_or_none()
        if perm is None:
            perm = Permission(code=code, name=name)
            db.add(perm)
            db.flush()
        out[code] = perm
    return out


def seed_roles(db: Session) -> dict[str, Role]:
    out: dict[str, Role] = {}
    for code, name, description, is_system in ROLES:
        role = db.execute(select(Role).where(Role.code == code)).scalar_one_or_none()
        if role is None:
            role = Role(code=code, name=name, description=description, is_system=is_system)
            db.add(role)
            db.flush()
        else:
            role.name, role.description, role.is_system = name, description, is_system
        out[code] = role
    return out


def seed_role_permissions(
    db: Session, roles: dict[str, Role], modules: dict[str, Module], permissions: dict[str, Permission]
) -> None:
    def grant(role: Role, module: Module, permission: Permission) -> None:
        exists = db.execute(
            select(RolePermission).where(
                RolePermission.role_id == role.id,
                RolePermission.module_id == module.id,
                RolePermission.permission_id == permission.id,
            )
        ).scalar_one_or_none()
        if exists is None:
            db.add(RolePermission(role_id=role.id, module_id=module.id, permission_id=permission.id))

    # Administrator: every permission on every module.
    for module in modules.values():
        for permission in permissions.values():
            grant(roles["ADMINISTRATOR"], module, permission)

    # Operator: VIEW/EDIT/EXECUTE on business modules only (no Settings/Administration).
    for module_code in OPERATOR_GRANTS_MODULES:
        for permission_code in OPERATOR_GRANTS_PERMISSIONS:
            grant(roles["OPERATOR"], modules[module_code], permissions[permission_code])

    # Viewer: VIEW-only on business modules.
    for module_code in VIEWER_GRANTS_MODULES:
        for permission_code in VIEWER_GRANTS_PERMISSIONS:
            grant(roles["VIEWER"], modules[module_code], permissions[permission_code])


def seed_app_settings(db: Session) -> None:
    for category, key, value, description in DEFAULT_APP_SETTINGS:
        row = db.execute(select(AppSetting).where(AppSetting.key == key)).scalar_one_or_none()
        if row is None:
            db.add(AppSetting(category=category, key=key, value=value, description=description))


def seed_demo_admin(db: Session, roles: dict[str, Role]) -> None:
    if not settings.seed_demo_user:
        return
    email = settings.demo_admin_email.lower()
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if user is None:
        user = User(
            email=email,
            hashed_password=hash_password(settings.demo_admin_password),
            full_name="Demo Administrator",
            is_active=True,
            preferred_locale="en",
        )
        db.add(user)
        db.flush()

    has_admin_role = db.execute(
        select(UserRole).where(UserRole.user_id == user.id, UserRole.role_id == roles["ADMINISTRATOR"].id)
    ).scalar_one_or_none()
    if has_admin_role is None:
        db.add(UserRole(user_id=user.id, role_id=roles["ADMINISTRATOR"].id))


def run() -> None:
    db = SessionLocal()
    try:
        modules = seed_modules(db)
        permissions = seed_permissions(db)
        roles = seed_roles(db)
        db.flush()
        seed_role_permissions(db, roles, modules, permissions)
        seed_app_settings(db)
        seed_demo_admin(db, roles)
        db.commit()
        print("Seed complete: modules, permissions, roles, role_permissions, settings, demo admin.", file=sys.stderr)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    from app.seed.seed_geography import run as seed_geography_run

    seed_geography_run()

    # P1: deterministic environmental backfill, so the Command Center/map are
    # never empty on a fresh install — even before the live scheduler has had
    # a chance to run, and even if the deployment network can't reach the
    # live APIs at all. Only fills stations that have no data yet (idempotent).
    from app.seed.seed_environmental import run as seed_environmental_run

    seed_environmental_run()


if __name__ == "__main__":
    run()
