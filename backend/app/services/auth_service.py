"""Authentication business logic: credential verification and login rate limiting."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import RateLimitedError, UnauthorizedError
from app.core.redis import redis_client
from app.core.security import verify_password
from app.models.user import User


def _rate_limit_key(email: str) -> str:
    return f"login_attempts:{email.lower()}"


def check_login_rate_limit(email: str) -> None:
    key = _rate_limit_key(email)
    attempts = redis_client.get(key)
    if attempts is not None and int(attempts) >= settings.login_rate_limit_attempts:
        raise RateLimitedError(
            message="Too many login attempts. Please try again later.",
            details={"retry_after_seconds": redis_client.ttl(key)},
        )


def register_failed_login(email: str) -> None:
    key = _rate_limit_key(email)
    pipe = redis_client.pipeline()
    pipe.incr(key)
    pipe.expire(key, settings.login_rate_limit_window_seconds, nx=True)
    pipe.execute()


def clear_login_attempts(email: str) -> None:
    redis_client.delete(_rate_limit_key(email))


def authenticate_user(db: Session, email: str, password: str) -> User:
    check_login_rate_limit(email)

    user = db.execute(select(User).where(User.email == email.lower())).scalar_one_or_none()
    if user is None or not verify_password(password, user.hashed_password):
        register_failed_login(email)
        raise UnauthorizedError(message="Incorrect email or password")

    if not user.is_active:
        raise UnauthorizedError(message="This account is disabled")

    clear_login_attempts(email)
    return user
