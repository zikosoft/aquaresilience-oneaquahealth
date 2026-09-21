from __future__ import annotations

import os

os.environ.setdefault("POSTGRES_DB", "aquaresilience_test")
os.environ["POSTGRES_DB"] = "aquaresilience_test"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.database import Base, SessionLocal, engine
from app.main import app
from app.seed.seed_data import run as run_seed


@pytest.fixture(scope="session", autouse=True)
def _prepare_schema():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    run_seed()
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def client():
    return TestClient(app)


@pytest.fixture()
def db_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def admin_token(client):
    from app.core.config import settings

    resp = client.post(
        "/api/v1/auth/login",
        json={"email": settings.demo_admin_email, "password": settings.demo_admin_password},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]
