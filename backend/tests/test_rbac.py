import uuid

from sqlalchemy import select

from app.core.security import hash_password
from app.models.rbac import Role, UserRole
from app.models.user import User


def _create_viewer_user(db_session, email: str, password: str) -> User:
    role = db_session.execute(select(Role).where(Role.code == "VIEWER")).scalar_one()
    user = User(email=email, hashed_password=hash_password(password), full_name="Test Viewer", is_active=True)
    db_session.add(user)
    db_session.flush()
    db_session.add(UserRole(user_id=user.id, role_id=role.id))
    db_session.commit()
    return user


def test_unauthenticated_request_is_rejected(client):
    resp = client.get("/api/v1/users")
    assert resp.status_code == 401


def test_admin_can_list_users(client, admin_token):
    resp = client.get("/api/v1/users", headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_viewer_cannot_access_administration_module(client, db_session):
    email = f"viewer-{uuid.uuid4().hex[:8]}@aquaresilience.demo"
    _create_viewer_user(db_session, email, "ViewerPass!2026")

    login = client.post("/api/v1/auth/login", json={"email": email, "password": "ViewerPass!2026"})
    assert login.status_code == 200
    token = login.json()["access_token"]

    resp = client.get("/api/v1/users", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "FORBIDDEN"


def test_viewer_cannot_access_settings_module(client, db_session):
    email = f"viewer-{uuid.uuid4().hex[:8]}@aquaresilience.demo"
    _create_viewer_user(db_session, email, "ViewerPass!2026")

    login = client.post("/api/v1/auth/login", json={"email": email, "password": "ViewerPass!2026"})
    token = login.json()["access_token"]

    resp = client.get("/api/v1/settings/general", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403


def test_permission_matrix_editable_by_admin(client, admin_token):
    resp = client.get("/api/v1/rbac/matrix", headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["roles"]) == 3
    assert len(body["modules"]) == 8
    assert len(body["permissions"]) == 6
