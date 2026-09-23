"""Settings framework: General/Languages/Data Sources/Scheduler/Risk Engine/Alerts/System
(generic key-value store) + AI Provider (dedicated model, write-only secret)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.deps import require_permission
from app.core.database import get_db
from app.core.errors import NotFoundError
from app.core.security import decrypt_secret, encrypt_secret
from app.models.settings import AppSetting, SettingCategory
from app.models.user import User
from app.schemas.settings import (
    AIProviderConfigOut,
    AIProviderConfigUpdate,
    AIProviderTestResult,
    AppSettingOut,
    AppSettingUpdate,
)
from app.services.ai_provider_service import get_or_create_ai_config, get_provider

router = APIRouter()

VALID_CATEGORIES = {c.value for c in SettingCategory}


@router.get("/{category}", response_model=list[AppSettingOut])
def list_settings(
    category: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("SETTINGS", "VIEW")),
) -> list[AppSettingOut]:
    category_upper = category.upper()
    rows = db.execute(
        select(AppSetting).where(AppSetting.category == category_upper).order_by(AppSetting.key)
    ).scalars().all()
    return rows


@router.get("/ai-provider/config", response_model=AIProviderConfigOut)
def get_ai_provider_config(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("SETTINGS", "VIEW")),
) -> AIProviderConfigOut:
    config = get_or_create_ai_config(db)
    return AIProviderConfigOut(
        provider=config.provider,
        model=config.model,
        max_output_tokens=config.max_output_tokens,
        scheduled_analysis_interval_minutes=config.scheduled_analysis_interval_minutes,
        daily_request_ceiling=config.daily_request_ceiling,
        event_triggered_enabled=config.event_triggered_enabled,
        cooldown_seconds=config.cooldown_seconds,
        is_configured=config.is_configured,
        last_connection_test_ok=config.last_connection_test_ok,
    )


@router.put("/ai-provider/config", response_model=AIProviderConfigOut)
def update_ai_provider_config(
    payload: AIProviderConfigUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("SETTINGS", "EDIT")),
) -> AIProviderConfigOut:
    config = get_or_create_ai_config(db)
    config.provider = payload.provider
    config.model = payload.model
    config.max_output_tokens = payload.max_output_tokens
    config.scheduled_analysis_interval_minutes = payload.scheduled_analysis_interval_minutes
    config.daily_request_ceiling = payload.daily_request_ceiling
    config.event_triggered_enabled = payload.event_triggered_enabled
    config.cooldown_seconds = payload.cooldown_seconds

    if payload.api_key:  # Only overwrite the stored secret if a new one was provided.
        config.encrypted_api_key = encrypt_secret(payload.api_key)
        config.last_connection_test_ok = None

    db.commit()
    db.refresh(config)
    return AIProviderConfigOut(
        provider=config.provider,
        model=config.model,
        max_output_tokens=config.max_output_tokens,
        scheduled_analysis_interval_minutes=config.scheduled_analysis_interval_minutes,
        daily_request_ceiling=config.daily_request_ceiling,
        event_triggered_enabled=config.event_triggered_enabled,
        cooldown_seconds=config.cooldown_seconds,
        is_configured=config.is_configured,
        last_connection_test_ok=config.last_connection_test_ok,
    )


@router.post("/ai-provider/test", response_model=AIProviderTestResult)
async def test_ai_provider_connection(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("SETTINGS", "EDIT")),
) -> AIProviderTestResult:
    config = get_or_create_ai_config(db)
    if not config.encrypted_api_key:
        return AIProviderTestResult(ok=False, message="No API key configured yet.")

    api_key = decrypt_secret(config.encrypted_api_key)
    if api_key is None:
        return AIProviderTestResult(ok=False, message="Stored key could not be decrypted. Please re-enter it.")

    provider = get_provider(config.provider, api_key=api_key, model=config.model)
    ok, message = await provider.test_connection()

    config.last_connection_test_ok = ok
    db.commit()

    return AIProviderTestResult(ok=ok, message=message)


# NOTE: the generic "/{category}/{key}" route below must stay registered
# AFTER the literal "/ai-provider/..." routes above — FastAPI matches routes
# in registration order, and the parameterized route would otherwise swallow
# every request to /ai-provider/*.
@router.put("/{category}/{key}", response_model=AppSettingOut)
def update_setting(
    category: str,
    key: str,
    payload: AppSettingUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("SETTINGS", "EDIT")),
) -> AppSettingOut:
    category_upper = category.upper()
    setting = db.execute(
        select(AppSetting).where(AppSetting.category == category_upper, AppSetting.key == key)
    ).scalar_one_or_none()
    if setting is None:
        raise NotFoundError(message=f"Setting '{category}.{key}' not found")
    setting.value = payload.value
    db.commit()
    db.refresh(setting)
    return setting
