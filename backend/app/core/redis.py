"""Redis client (used for rate limiting, caching, and shared scheduler state)."""
import redis

from app.core.config import settings

redis_client = redis.Redis(
    host=settings.redis_host,
    port=settings.redis_port,
    db=settings.redis_db,
    decode_responses=True,
)


def check_redis() -> bool:
    try:
        return bool(redis_client.ping())
    except redis.RedisError:
        return False
