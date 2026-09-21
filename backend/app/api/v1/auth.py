"""Authentication endpoints: login, refresh, logout, me."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import jwt
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_user
from app.core.database import get_db
from app.core.errors import UnauthorizedError
from app.core.redis import redis_client
from app.core.security import (
    TokenType,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from app.models.user import User
from app.schemas.auth import LoginRequest, RefreshRequest, TokenResponse
from app.schemas.common import MessageResponse
from app.schemas.user import MeOut
from app.services.auth_service import authenticate_user
from app.services.rbac_service import get_user_permission_codes

router = APIRouter()


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = authenticate_user(db, payload.email, payload.password)
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()

    return TokenResponse(
        access_token=create_access_token(str(user.id)),
        refresh_token=create_refresh_token(str(user.id)),
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)) -> TokenResponse:
    try:
        decoded = decode_token(payload.refresh_token)
    except jwt.PyJWTError:
        raise UnauthorizedError(message="Invalid or expired refresh token")

    if decoded.get("type") != TokenType.REFRESH.value:
        raise UnauthorizedError(message="Invalid token type")

    jti = decoded.get("jti")
    if jti and redis_client.get(f"revoked_token:{jti}"):
        raise UnauthorizedError(message="Refresh token has been revoked")

    try:
        user = db.get(User, uuid.UUID(decoded["sub"]))
    except (ValueError, TypeError):
        user = None
    if user is None or not user.is_active:
        raise UnauthorizedError(message="User not found or inactive")

    return TokenResponse(
        access_token=create_access_token(str(user.id)),
        refresh_token=create_refresh_token(str(user.id)),
    )


@router.post("/logout", response_model=MessageResponse)
def logout(payload: RefreshRequest, current_user: User = Depends(get_current_user)) -> MessageResponse:
    try:
        decoded = decode_token(payload.refresh_token)
        jti = decoded.get("jti")
        exp = decoded.get("exp")
        if jti and exp:
            ttl = max(int(exp - datetime.now(timezone.utc).timestamp()), 1)
            redis_client.setex(f"revoked_token:{jti}", ttl, "1")
    except jwt.PyJWTError:
        pass  # Already invalid/expired: nothing to revoke.
    return MessageResponse(message="Logged out")


@router.get("/me", response_model=MeOut)
def me(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> MeOut:
    permission_codes = sorted(get_user_permission_codes(db, current_user))
    return MeOut(
        **{
            "id": current_user.id,
            "email": current_user.email,
            "full_name": current_user.full_name,
            "is_active": current_user.is_active,
            "preferred_locale": current_user.preferred_locale,
            "last_login_at": current_user.last_login_at,
            "created_at": current_user.created_at,
            "roles": [ur.role for ur in current_user.user_roles],
            "permissions": permission_codes,
        }
    )
