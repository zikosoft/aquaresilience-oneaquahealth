from __future__ import annotations

from pydantic import BaseModel, Field


class AppSettingOut(BaseModel):
    category: str
    key: str
    value: dict
    description: str

    model_config = {"from_attributes": True}


class AppSettingUpdate(BaseModel):
    value: dict


class AIProviderConfigOut(BaseModel):
    provider: str
    model: str
    max_output_tokens: int
    scheduled_analysis_interval_minutes: int
    daily_request_ceiling: int
    event_triggered_enabled: bool
    cooldown_seconds: int
    is_configured: bool
    last_connection_test_ok: bool | None

    model_config = {"from_attributes": True}


class AIProviderConfigUpdate(BaseModel):
    provider: str = Field(pattern="^(openai|anthropic)$")
    model: str = Field(min_length=1, max_length=128)
    api_key: str | None = Field(default=None, description="Write-only. Omit to keep the existing stored key.")
    max_output_tokens: int = Field(default=1024, ge=64, le=8000)
    scheduled_analysis_interval_minutes: int = Field(default=240, ge=15, le=1440)
    daily_request_ceiling: int = Field(default=6, ge=1, le=100)
    event_triggered_enabled: bool = False
    cooldown_seconds: int = Field(default=900, ge=0, le=86400)


class AIProviderTestResult(BaseModel):
    ok: bool
    message: str
