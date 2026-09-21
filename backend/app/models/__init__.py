"""Import all models here so Alembic autogenerate and Base.metadata see them."""
from app.models.rbac import Module, Permission, Role, RolePermission, UserRole  # noqa: F401
from app.models.settings import AIProviderConfig, AppSetting  # noqa: F401
from app.models.user import User  # noqa: F401

__all__ = [
    "User",
    "Role",
    "Module",
    "Permission",
    "RolePermission",
    "UserRole",
    "AppSetting",
    "AIProviderConfig",
]
