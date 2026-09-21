"""Password hashing, JWT issuance/verification, and secret encryption."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from enum import StrEnum

import bcrypt
import jwt
from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings

_BCRYPT_MAX_BYTES = 72  # bcrypt silently truncates beyond this; reject longer inputs explicitly.


def hash_password(password: str) -> str:
    password_bytes = password.encode("utf-8")
    if len(password_bytes) > _BCRYPT_MAX_BYTES:
        raise ValueError("Password must be at most 72 bytes long")
    return bcrypt.hashpw(password_bytes, bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except ValueError:
        return False


class TokenType(StrEnum):
    ACCESS = "access"
    REFRESH = "refresh"


def _create_token(subject: str, token_type: TokenType, expires_delta: timedelta) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "type": token_type.value,
        "iat": now,
        "exp": now + expires_delta,
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def create_access_token(subject: str) -> str:
    return _create_token(subject, TokenType.ACCESS, timedelta(minutes=settings.access_token_expire_minutes))


def create_refresh_token(subject: str) -> str:
    return _create_token(subject, TokenType.REFRESH, timedelta(minutes=settings.refresh_token_expire_minutes))


def decode_token(token: str) -> dict:
    """Raises jwt.PyJWTError subclasses on invalid/expired tokens."""
    return jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])


_fernet = Fernet(settings.secrets_encryption_key.encode() if isinstance(settings.secrets_encryption_key, str) else settings.secrets_encryption_key)


def encrypt_secret(plain_text: str) -> str:
    return _fernet.encrypt(plain_text.encode("utf-8")).decode("utf-8")


def decrypt_secret(cipher_text: str) -> str | None:
    try:
        return _fernet.decrypt(cipher_text.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        return None
