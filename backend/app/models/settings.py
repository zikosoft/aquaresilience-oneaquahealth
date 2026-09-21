"""Application settings storage: generic key/value settings + AI provider config."""
from __future__ import annotations

from enum import StrEnum

from sqlalchemy import Boolean, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class SettingCategory(StrEnum):
    GENERAL = "GENERAL"
    LANGUAGES = "LANGUAGES"
    DATA_SOURCES = "DATA_SOURCES"
    SCHEDULER = "SCHEDULER"
    RISK_ENGINE = "RISK_ENGINE"
    ALERTS = "ALERTS"
    SYSTEM = "SYSTEM"


class AppSetting(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Generic typed key/value settings store, grouped by category/tab."""

    __tablename__ = "app_settings"

    category: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    value: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    description: Mapped[str] = mapped_column(String(512), default="", nullable=False)


class AIProviderName(StrEnum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"


class AIProviderConfig(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Single active AI provider configuration. The API key is stored encrypted
    and is NEVER returned to the frontend once saved (write-only secret rule)."""

    __tablename__ = "ai_provider_config"

    provider: Mapped[str] = mapped_column(String(32), nullable=False, default=AIProviderName.OPENAI.value)
    # Must stay non-blank: AIProviderConfigUpdate requires `model` to be at
    # least 1 character, so a row created with an empty default would fail
    # its own first save unless the admin happened to also type a model name.
    model: Mapped[str] = mapped_column(String(128), nullable=False, default="gpt-4o-mini")
    encrypted_api_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    max_output_tokens: Mapped[int] = mapped_column(Integer, default=1024, nullable=False)
    scheduled_analysis_interval_minutes: Mapped[int] = mapped_column(Integer, default=240, nullable=False)
    daily_request_ceiling: Mapped[int] = mapped_column(Integer, default=6, nullable=False)
    event_triggered_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    cooldown_seconds: Mapped[int] = mapped_column(Integer, default=900, nullable=False)
    last_connection_test_ok: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    @property
    def is_configured(self) -> bool:
        return bool(self.encrypted_api_key)
