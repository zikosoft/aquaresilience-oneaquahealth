"""RBAC resolution and permission-matrix management."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.rbac import Module, Permission, Role, RolePermission, UserRole
from app.models.user import User


def get_user_permission_codes(db: Session, user: User) -> set[str]:
    """Returns a set of "MODULE_CODE:PERMISSION_CODE" strings granted to the user
    across all of their roles."""
    role_ids = [ur.role_id for ur in user.user_roles]
    if not role_ids:
        return set()

    rows = db.execute(
        select(RolePermission).where(RolePermission.role_id.in_(role_ids))
    ).scalars().all()

    return {f"{rp.module.code}:{rp.permission.code}" for rp in rows}


def user_has_permission(db: Session, user: User, module_code: str, permission_code: str) -> bool:
    codes = get_user_permission_codes(db, user)
    return f"{module_code}:{permission_code}" in codes or f"{module_code}:ADMIN" in codes


def get_permission_matrix(db: Session) -> dict:
    roles = db.execute(select(Role).order_by(Role.name)).scalars().all()
    modules = db.execute(select(Module).order_by(Module.sort_order)).scalars().all()
    permissions = db.execute(select(Permission).order_by(Permission.name)).scalars().all()
    grants = db.execute(select(RolePermission)).scalars().all()
    return {
        "roles": roles,
        "modules": modules,
        "permissions": permissions,
        "grants": [
            {"role_id": g.role_id, "module_id": g.module_id, "permission_id": g.permission_id} for g in grants
        ],
    }


def replace_role_grants(db: Session, role_id: uuid.UUID, grants: list[tuple[uuid.UUID, uuid.UUID]]) -> None:
    """Replace all grants for a role with the given (module_id, permission_id) pairs."""
    db.query(RolePermission).filter(RolePermission.role_id == role_id).delete()
    for module_id, permission_id in grants:
        db.add(RolePermission(role_id=role_id, module_id=module_id, permission_id=permission_id))
    db.commit()
