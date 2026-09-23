"""Aggregates all /api/v1 routers."""
from fastapi import APIRouter

from app.api.v1 import auth, environmental, geography, health, intelligence, rbac, risk, settings, users

api_router = APIRouter()

api_router.include_router(health.router)
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(rbac.router, prefix="/rbac", tags=["rbac"])
api_router.include_router(settings.router, prefix="/settings", tags=["settings"])
api_router.include_router(environmental.router, prefix="/environmental", tags=["environmental"])
api_router.include_router(risk.router, prefix="/risk", tags=["risk"])
api_router.include_router(geography.router, prefix="/geography", tags=["geography"])
api_router.include_router(intelligence.router, prefix="/intelligence", tags=["intelligence"])
