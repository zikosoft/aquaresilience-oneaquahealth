from app.core.config import settings


def test_login_success(client):
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": settings.demo_admin_email, "password": settings.demo_admin_password},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "access_token" in body and "refresh_token" in body


def test_login_wrong_password(client):
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": settings.demo_admin_email, "password": "definitely-wrong"},
    )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHORIZED"


def test_login_rate_limited_after_too_many_failures(client):
    for _ in range(settings.login_rate_limit_attempts):
        client.post(
            "/api/v1/auth/login",
            json={"email": "rate-limit-target@aquaresilience.demo", "password": "wrong"},
        )
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": "rate-limit-target@aquaresilience.demo", "password": "wrong"},
    )
    assert resp.status_code == 429
    assert resp.json()["error"]["code"] == "RATE_LIMITED"


def test_me_requires_authentication(client):
    resp = client.get("/api/v1/auth/me")
    assert resp.status_code == 401


def test_me_returns_permissions(client, admin_token):
    resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == settings.demo_admin_email
    assert "SETTINGS:ADMIN" in body["permissions"]


def test_logout_revokes_refresh_token(client):
    login = client.post(
        "/api/v1/auth/login",
        json={"email": settings.demo_admin_email, "password": settings.demo_admin_password},
    ).json()
    access_token = login["access_token"]
    refresh_token = login["refresh_token"]

    logout_resp = client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": refresh_token},
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert logout_resp.status_code == 200

    refresh_resp = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert refresh_resp.status_code == 401
