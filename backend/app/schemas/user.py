from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.schemas.rbac import RoleOut


class UserOut(BaseModel):
    id: uuid.UUID
    email: EmailStr
    full_name: str
    is_active: bool
    preferred_locale: str
    last_login_at: datetime | None
    created_at: datetime
    roles: list[RoleOut] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(default="", max_length=255)
    role_ids: list[uuid.UUID] = Field(default_factory=list)
    preferred_locale: str = Field(default="en", max_length=8)


class UserUpdate(BaseModel):
    full_name: str | None = None
    is_active: bool | None = None
    preferred_locale: str | None = None
    role_ids: list[uuid.UUID] | None = None


class UserPasswordUpdate(BaseModel):
    password: str = Field(min_length=8, max_length=128)


class MeOut(UserOut):
    permissions: list[str] = Field(default_factory=list, description="module_code:permission_code pairs")
