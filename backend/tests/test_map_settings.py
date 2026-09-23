"""P2.1: Settings > Map tab — tile provider setting (generic settings
framework, just a new category) plus the read-only city defaults endpoint
that both this tab and `ResilienceMap.vue` read (D016 — a city already
knows its own map default, per-city lat/lon/zoom duplication avoided)."""
from __future__ import annotations

import uuid

from sqlalchemy import select

from app.core.security import hash_password
from app.models.rbac import Role, UserRole
from app.models.user import User


def test_map_tile_provider_setting_roundtrip(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    get_resp = client.get("/api/v1/settings/map", headers=headers)
    assert get_resp.status_code == 200
    body = get_resp.json()
    assert len(body) == 1
    assert body[0]["value"]["tile_provider"] == "osm"

    put_resp = client.put(
        "/api/v1/settings/map/map",
        headers=headers,
        json={"value": {"tile_provider": "carto_dark"}},
    )
    assert put_resp.status_code == 200
    assert put_resp.json()["value"]["tile_provider"] == "carto_dark"


def test_cities_endpoint_returns_the_seeded_toulouse_default(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = client.get("/api/v1/geography/cities", headers=headers)
    assert resp.status_code == 200
    cities = resp.json()
    assert len(cities) == 1
    toulouse = cities[0]
    assert toulouse["label_en"] == "Toulouse"
    assert toulouse["country_iso2"] == "FR"
    assert toulouse["default_lon"] == 1.4442
    assert toulouse["default_lat"] == 43.6047
    assert toulouse["default_zoom"] == 11


def test_viewer_can_read_cities_but_not_map_settings(client, db_session):
    role = db_session.execute(select(Role).where(Role.code == "VIEWER")).scalar_one()
    email = f"viewer-{uuid.uuid4().hex[:8]}@aquaresilience.demo"
    user = User(email=email, hashed_password=hash_password("ViewerPass!2026"), full_name="Test Viewer", is_active=True)
    db_session.add(user)
    db_session.flush()
    db_session.add(UserRole(user_id=user.id, role_id=role.id))
    db_session.commit()

    login = client.post("/api/v1/auth/login", json={"email": email, "password": "ViewerPass!2026"})
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Viewer has MAP:VIEW (needed to center the map) ...
    assert client.get("/api/v1/geography/cities", headers=headers).status_code == 200
    # ... but not SETTINGS:VIEW (the tile-provider choice is a Settings edit concern).
    assert client.get("/api/v1/settings/map", headers=headers).status_code == 403


def test_map_config_folds_tile_provider_into_a_map_view_gated_endpoint(client, admin_token, db_session):
    """`/map-config` is what `ResilienceMap.vue` actually reads: every role
    that can view the map needs the effective tile provider, not just
    Settings editors — see the module docstring in `app/api/v1/geography.py`."""
    headers = {"Authorization": f"Bearer {admin_token}"}
    client.put(
        "/api/v1/settings/map/map", headers=headers, json={"value": {"tile_provider": "carto_light"}}
    )

    role = db_session.execute(select(Role).where(Role.code == "VIEWER")).scalar_one()
    email = f"viewer-{uuid.uuid4().hex[:8]}@aquaresilience.demo"
    user = User(email=email, hashed_password=hash_password("ViewerPass!2026"), full_name="Test Viewer", is_active=True)
    db_session.add(user)
    db_session.flush()
    db_session.add(UserRole(user_id=user.id, role_id=role.id))
    db_session.commit()
    login = client.post("/api/v1/auth/login", json={"email": email, "password": "ViewerPass!2026"})
    viewer_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    resp = client.get("/api/v1/geography/map-config", headers=viewer_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["tile_provider"] == "carto_light"
    assert len(body["cities"]) == 1
    assert body["cities"][0]["label_en"] == "Toulouse"


def test_map_config_exposes_risk_layer_opacity_with_a_default(client, admin_token):
    """P4.1: the risk-level circle layer's opacity is a Settings > Map field
    — defaults to 35 when never explicitly saved (fresh/seeded install), and
    round-trips through the same generic settings PUT as tile_provider."""
    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = client.get("/api/v1/geography/map-config", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["risk_layer_opacity"] == 35

    client.put(
        "/api/v1/settings/map/map",
        headers=headers,
        json={"value": {"tile_provider": "osm", "risk_layer_opacity": 60}},
    )
    resp2 = client.get("/api/v1/geography/map-config", headers=headers)
    assert resp2.json()["risk_layer_opacity"] == 60
