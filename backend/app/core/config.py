"""Application configuration.

All configuration is sourced from environment variables (see `.env.example`).
Nothing here should contain real secrets — defaults are safe-for-dev only.
"""
from functools import lru_cache
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- General ---
    environment: str = Field(default="development", alias="ENVIRONMENT")
    app_name: str = Field(default="AquaResilience", alias="APP_NAME")
    api_v1_prefix: str = Field(default="/api/v1", alias="API_V1_PREFIX")
    default_city: str = Field(default="toulouse", alias="DEFAULT_CITY")

    # --- Security ---
    secret_key: str = Field(default="dev-only-insecure-secret-key", alias="SECRET_KEY")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    access_token_expire_minutes: int = Field(default=30, alias="ACCESS_TOKEN_EXPIRE_MINUTES")
    refresh_token_expire_minutes: int = Field(default=10080, alias="REFRESH_TOKEN_EXPIRE_MINUTES")
    secrets_encryption_key: str = Field(default="", alias="SECRETS_ENCRYPTION_KEY")

    # --- PostgreSQL ---
    postgres_host: str = Field(default="postgres", alias="POSTGRES_HOST")
    postgres_port: int = Field(default=5432, alias="POSTGRES_PORT")
    postgres_db: str = Field(default="aquaresilience", alias="POSTGRES_DB")
    postgres_user: str = Field(default="aquaresilience", alias="POSTGRES_USER")
    postgres_password: str = Field(default="aquaresilience", alias="POSTGRES_PASSWORD")

    # --- Redis ---
    redis_host: str = Field(default="redis", alias="REDIS_HOST")
    redis_port: int = Field(default=6379, alias="REDIS_PORT")
    redis_db: int = Field(default=0, alias="REDIS_DB")

    # --- CORS ---
    cors_origins: str = Field(default="http://localhost:5173,http://localhost:8080", alias="CORS_ORIGINS")

    # --- Rate limiting ---
    login_rate_limit_attempts: int = Field(default=5, alias="LOGIN_RATE_LIMIT_ATTEMPTS")
    login_rate_limit_window_seconds: int = Field(default=300, alias="LOGIN_RATE_LIMIT_WINDOW_SECONDS")

    # --- Demo / seed ---
    seed_demo_user: bool = Field(default=True, alias="SEED_DEMO_USER")
    demo_admin_email: str = Field(default="admin@aquaresilience.demo", alias="DEMO_ADMIN_EMAIL")
    demo_admin_password: str = Field(default="ChangeMe!2026", alias="DEMO_ADMIN_PASSWORD")

    @field_validator("secrets_encryption_key")
    @classmethod
    def _default_encryption_key(cls, v: str) -> str:
        # A valid urlsafe-base64 32-byte Fernet key, dev-only fallback (NOT for production).
        return v or "PJzn0P3XW_lQjVF2XDv-cXMjkVMXz9KPmqVQVRJbU2E="

    @property
    def sqlalchemy_database_uri(self) -> str:
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def cors_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
