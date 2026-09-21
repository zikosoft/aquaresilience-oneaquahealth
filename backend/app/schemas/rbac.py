from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


class ModuleOut(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    sort_order: int

    model_config = {"from_attributes": True}


class PermissionOut(BaseModel):
    id: uuid.UUID
    code: str
    name: str

    model_config = {"from_attributes": True}


class RoleOut(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    description: str
    is_system: bool

    model_config = {"from_attributes": True}


class RolePermissionCell(BaseModel):
    role_id: uuid.UUID
    module_id: uuid.UUID
    permission_id: uuid.UUID


class PermissionMatrixOut(BaseModel):
    roles: list[RoleOut]
    modules: list[ModuleOut]
    permissions: list[PermissionOut]
    grants: list[RolePermissionCell]


class PermissionMatrixUpdate(BaseModel):
    """Full replacement of a single role's grants."""

    role_id: uuid.UUID
    grants: list[RolePermissionCell] = Field(default_factory=list)
