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


class UserPermissionToggle(BaseModel):
    """P2.1 (D015): one permission-cell toggle for a single user."""

    module_id: uuid.UUID
    permission_id: uuid.UUID
    granted: bool


class UserPermissionsOut(BaseModel):
    """The role a user ends up on after a toggle, plus that role's full
    grant set — enough for the frontend to update its UI live with no
    extra round trip (D015's "reflect the switch to Custom live" requirement)."""

    role: RoleOut
    grants: list[RolePermissionCell]
