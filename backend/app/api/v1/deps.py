"""Shared FastAPI dependencies: DB session, current user, permission enforcement."""
from __future__ import annotations

import uuid

import jwt
from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.errors import ForbiddenError, UnauthorizedError
from app.core.security import TokenType, decode_token
from app.models.user import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login", auto_error=False)


def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    if not token:
        raise UnauthorizedError(message="Not authenticated")
    try:
        payload = decode_token(token)
    except jwt.ExpiredSignatureError:
        raise UnauthorizedError(message="Token has expired")
    except jwt.PyJWTError:
        raise UnauthorizedError(message="Invalid authentication token")

    if payload.get("type") != TokenType.ACCESS.value:
        raise UnauthorizedError(message="Invalid token type")

    user_id = payload.get("sub")
    try:
        user = db.get(User, uuid.UUID(user_id))
    except (ValueError, TypeError):
        user = None

    if user is None or not user.is_active:
        raise UnauthorizedError(message="User not found or inactive")

    return user


def require_permission(module_code: str, permission_code: str):
    """Backend-enforced RBAC dependency factory.

    Usage: `Depends(require_permission("SETTINGS", "EDIT"))`
    """

    def _dependency(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> User:
        from app.services.rbac_service import user_has_permission  # local import avoids cycles

        if not user_has_permission(db, current_user, module_code, permission_code):
            raise ForbiddenError(
                message=f"Missing permission {module_code}:{permission_code}",
                details={"module": module_code, "permission": permission_code},
            )
        return current_user

    return _dependency
