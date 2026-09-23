"""Users & Access administration (admin-only account creation — no public signup)."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_user, require_permission
from app.core.database import get_db
from app.core.errors import ConflictError, NotFoundError
from app.core.security import hash_password
from app.models.rbac import Role, RolePermission, UserRole
from app.models.user import User
from app.schemas.common import MessageResponse
from app.schemas.rbac import RolePermissionCell, RoleOut, UserPermissionsOut, UserPermissionToggle
from app.schemas.user import UserCreate, UserOut, UserPasswordUpdate, UserUpdate
from app.services.rbac_service import set_user_permission

router = APIRouter()


@router.get("", response_model=list[UserOut])
def list_users(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("ADMINISTRATION", "VIEW")),
) -> list[UserOut]:
    users = db.execute(select(User).order_by(User.email)).scalars().all()
    return [_to_user_out(u) for u in users]


@router.post("", response_model=UserOut, status_code=201)
def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("ADMINISTRATION", "CREATE")),
) -> UserOut:
    existing = db.execute(select(User).where(User.email == payload.email.lower())).scalar_one_or_none()
    if existing is not None:
        raise ConflictError(message="A user with this email already exists")

    user = User(
        email=payload.email.lower(),
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        preferred_locale=payload.preferred_locale,
    )
    db.add(user)
    db.flush()

    for role_id in payload.role_ids:
        role = db.get(Role, role_id)
        if role is not None:
            db.add(UserRole(user_id=user.id, role_id=role.id))

    db.commit()
    db.refresh(user)
    return _to_user_out(user)


@router.patch("/{user_id}", response_model=UserOut)
def update_user(
    user_id: uuid.UUID,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("ADMINISTRATION", "EDIT")),
) -> UserOut:
    user = db.get(User, user_id)
    if user is None:
        raise NotFoundError(message="User not found")

    if payload.full_name is not None:
        user.full_name = payload.full_name
    if payload.is_active is not None:
        user.is_active = payload.is_active
    if payload.preferred_locale is not None:
        user.preferred_locale = payload.preferred_locale
    if payload.role_ids is not None:
        db.query(UserRole).filter(UserRole.user_id == user.id).delete()
        for role_id in payload.role_ids:
            role = db.get(Role, role_id)
            if role is not None:
                db.add(UserRole(user_id=user.id, role_id=role.id))

    db.commit()
    db.refresh(user)
    return _to_user_out(user)


@router.put("/{user_id}/password", response_model=MessageResponse)
def set_user_password(
    user_id: uuid.UUID,
    payload: UserPasswordUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("ADMINISTRATION", "EDIT")),
) -> MessageResponse:
    user = db.get(User, user_id)
    if user is None:
        raise NotFoundError(message="User not found")
    user.hashed_password = hash_password(payload.password)
    db.commit()
    return MessageResponse(message="Password updated")


@router.patch("/{user_id}/permissions", response_model=UserPermissionsOut)
def update_user_permission(
    user_id: uuid.UUID,
    payload: UserPermissionToggle,
    db: Session = Depends(get_db),
    # P2.1 (D015): same "ADMIN" bar as the shared role matrix (`PUT
    # /rbac/matrix`) — granting/revoking permissions is admin-only either way.
    _: User = Depends(require_permission("ADMINISTRATION", "ADMIN")),
) -> UserPermissionsOut:
    user = db.get(User, user_id)
    if user is None:
        raise NotFoundError(message="User not found")

    role = set_user_permission(db, user, payload.module_id, payload.permission_id, payload.granted)
    grants = db.execute(select(RolePermission).where(RolePermission.role_id == role.id)).scalars().all()
    return UserPermissionsOut(
        role=RoleOut.model_validate(role),
        grants=[
            RolePermissionCell(role_id=g.role_id, module_id=g.module_id, permission_id=g.permission_id)
            for g in grants
        ],
    )


@router.delete("/{user_id}", response_model=MessageResponse)
def delete_user(
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("ADMINISTRATION", "DELETE")),
) -> MessageResponse:
    if user_id == current_user.id:
        raise ConflictError(message="You cannot delete your own account")
    user = db.get(User, user_id)
    if user is None:
        raise NotFoundError(message="User not found")
    db.delete(user)
    db.commit()
    return MessageResponse(message="User deleted")


def _to_user_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        is_active=user.is_active,
        preferred_locale=user.preferred_locale,
        last_login_at=user.last_login_at,
        created_at=user.created_at,
        roles=[ur.role for ur in user.user_roles],
    )
