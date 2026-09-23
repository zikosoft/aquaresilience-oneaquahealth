"""AquaResilience API entrypoint."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.errors import register_exception_handlers
from app.core.scheduler import start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(_app: FastAPI):
    start_scheduler()
    try:
        yield
    finally:
        stop_scheduler()


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="AquaResilience — AI-assisted urban freshwater resilience intelligence platform (Track 6).",
    # Never leak internals; docs are disabled in production.
    docs_url="/docs" if not settings.is_production else None,
    redoc_url="/redoc" if not settings.is_production else None,
    openapi_url="/openapi.json" if not settings.is_production else None,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)

app.include_router(api_router, prefix=settings.api_v1_prefix)


@app.get("/")
def root() -> dict:
    return {"name": settings.app_name, "status": "ok", "docs": "/docs"}


# P5: an infra-level liveness probe, deliberately OUTSIDE the versioned API
# (`/api/v1/health/live` already exists for app-level monitoring — this is
# for Docker's own HEALTHCHECK and the reverse proxy's upstream checks,
# which shouldn't need to know or care about the API version prefix).
# Found and fixed in Session 016: `backend/Dockerfile`'s HEALTHCHECK was
# already probing this exact unprefixed `/health` path, which never
# existed — the container's healthcheck had been silently failing (always
# 404) since it was written. Harmless in the dev compose (nothing gates on
# it), but would have hung a production stack forever if a service ever
# waited on `condition: service_healthy` for the backend.
@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
