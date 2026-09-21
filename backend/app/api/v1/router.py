"""Aggregates all /api/v1 routers."""
from fastapi import APIRouter

from app.api.v1 import auth, health, rbac, settings, users

api_router = APIRouter()

api_router.include_router(health.router)
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(rbac.router, prefix="/rbac", tags=["rbac"])
api_router.include_router(settings.router, prefix="/settings", tags=["settings"])
