"""Roles / modules / permissions / the role x module x permission matrix."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.deps import require_permission
from app.core.database import get_db
from app.models.rbac import Module, Permission, Role
from app.models.user import User
from app.schemas.rbac import ModuleOut, PermissionMatrixOut, PermissionMatrixUpdate, PermissionOut, RoleOut
from app.services.demo_lock import ensure_role_not_locked
from app.services.rbac_service import get_permission_matrix, replace_role_grants

router = APIRouter()


@router.get("/roles", response_model=list[RoleOut])
def list_roles(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("ADMINISTRATION", "VIEW")),
) -> list[RoleOut]:
    return db.execute(select(Role).order_by(Role.name)).scalars().all()


@router.get("/modules", response_model=list[ModuleOut])
def list_modules(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("ADMINISTRATION", "VIEW")),
) -> list[ModuleOut]:
    return db.execute(select(Module).order_by(Module.sort_order)).scalars().all()


@router.get("/permissions", response_model=list[PermissionOut])
def list_permissions(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("ADMINISTRATION", "VIEW")),
) -> list[PermissionOut]:
    return db.execute(select(Permission).order_by(Permission.name)).scalars().all()


@router.get("/matrix", response_model=PermissionMatrixOut)
def get_matrix(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("ADMINISTRATION", "VIEW")),
) -> PermissionMatrixOut:
    return get_permission_matrix(db)


@router.put("/matrix", response_model=PermissionMatrixOut)
def update_matrix(
    payload: PermissionMatrixUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("ADMINISTRATION", "ADMIN")),
) -> PermissionMatrixOut:
    ensure_role_not_locked(db.get(Role, payload.role_id))
    grants = [(g.module_id, g.permission_id) for g in payload.grants]
    replace_role_grants(db, payload.role_id, grants)
    return get_permission_matrix(db)
