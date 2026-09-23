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


# --- P2.1 (D015): per-user "Custom" permission override ---
#
# The shared role x module x permission matrix above is deliberately
# per-role, not per-user — editing it changes every user on that role.
# D015 adds a per-user override without a separate override table: the
# first time an operator edits one user's permissions, that user's current
# role is cloned into a new role scoped to exactly that user (never
# mutating the shared role — other users on it are unaffected), and the
# user is reassigned to the clone. Every permission this user holds lives
# in that same clone from then on; the existing "Edit user" role dropdown
# still works unchanged (a "Custom — <name>" role is a normal Role row, and
# an operator can reassign the user away from it there at any time — an
# accepted trade-off of the clone-on-edit approach, not prevented).

CUSTOM_ROLE_CODE_PREFIX = "custom_"


def custom_role_code(user_id: uuid.UUID) -> str:
    return f"{CUSTOM_ROLE_CODE_PREFIX}{user_id}"


def get_user_effective_role(user: User) -> Role | None:
    """The single role driving a user's permissions today (per the current
    single-role-per-user UX — `user_roles` is a many-to-many table, but the
    UI only ever assigns one)."""
    return user.user_roles[0].role if user.user_roles else None


def set_user_permission(
    db: Session, user: User, module_id: uuid.UUID, permission_id: uuid.UUID, granted: bool
) -> Role:
    """Toggle one permission cell for exactly this user, cloning their role
    into a user-scoped "Custom" role on first edit (see module docstring
    above). Returns the role the user ends up on (the clone, or their
    existing custom role if they were already on one)."""
    current_role = get_user_effective_role(user)
    code = custom_role_code(user.id)

    if current_role is not None and current_role.code == code:
        target_role = current_role
    else:
        target_role = db.execute(select(Role).where(Role.code == code)).scalar_one_or_none()
        if target_role is None:
            display_name = user.full_name.strip() if user.full_name.strip() else user.email
            target_role = Role(
                code=code,
                name=f"Custom — {display_name}",
                description=(
                    f"Per-user permission override, cloned from '{current_role.name}'."
                    if current_role
                    else "Per-user permission override."
                ),
                is_system=False,
            )
            db.add(target_role)
            db.flush()
        else:
            # A stale custom role from before the user was reassigned away
            # from it (e.g. via the role dropdown) — reset it before
            # re-cloning so grants never silently accumulate or duplicate.
            db.query(RolePermission).filter(RolePermission.role_id == target_role.id).delete()

        if current_role is not None:
            source_grants = db.execute(
                select(RolePermission).where(RolePermission.role_id == current_role.id)
            ).scalars().all()
            for g in source_grants:
                db.add(RolePermission(role_id=target_role.id, module_id=g.module_id, permission_id=g.permission_id))

        db.query(UserRole).filter(UserRole.user_id == user.id).delete()
        db.add(UserRole(user_id=user.id, role_id=target_role.id))
        db.flush()

    existing_cell = db.execute(
        select(RolePermission).where(
            RolePermission.role_id == target_role.id,
            RolePermission.module_id == module_id,
            RolePermission.permission_id == permission_id,
        )
    ).scalar_one_or_none()

    if granted and existing_cell is None:
        db.add(RolePermission(role_id=target_role.id, module_id=module_id, permission_id=permission_id))
    elif not granted and existing_cell is not None:
        db.delete(existing_cell)

    db.commit()
    db.refresh(target_role)
    return target_role
