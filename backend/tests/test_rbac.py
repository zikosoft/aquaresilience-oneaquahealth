import uuid

from sqlalchemy import select

from app.core.security import hash_password
from app.models.rbac import Module, Permission, Role, RolePermission, UserRole
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


# --- P2.1 (D015): per-user "Custom" permission override ---

def _ids(db_session, module_code: str, permission_code: str) -> tuple[str, str]:
    module = db_session.execute(select(Module).where(Module.code == module_code)).scalar_one()
    permission = db_session.execute(select(Permission).where(Permission.code == permission_code)).scalar_one()
    return str(module.id), str(permission.id)


def test_toggling_user_permission_clones_into_a_user_scoped_custom_role(client, admin_token, db_session):
    user_a = _create_viewer_user(db_session, f"viewer-a-{uuid.uuid4().hex[:8]}@aquaresilience.demo", "ViewerPass!2026")
    user_b = _create_viewer_user(db_session, f"viewer-b-{uuid.uuid4().hex[:8]}@aquaresilience.demo", "ViewerPass!2026")
    viewer_role = db_session.execute(select(Role).where(Role.code == "VIEWER")).scalar_one()
    viewer_grant_count = db_session.execute(
        select(RolePermission).where(RolePermission.role_id == viewer_role.id)
    ).scalars().all()
    module_id, permission_id = _ids(db_session, "ALERTS", "EDIT")

    resp = client.patch(
        f"/api/v1/users/{user_a.id}/permissions",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"module_id": module_id, "permission_id": permission_id, "granted": True},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["role"]["code"] == f"custom_{user_a.id}"
    assert body["role"]["name"] == "Custom — Test Viewer"
    assert body["role"]["is_system"] is False
    # The clone starts from every grant the Viewer role had, plus the one just added.
    assert len(body["grants"]) == len(viewer_grant_count) + 1
    assert any(g["module_id"] == module_id and g["permission_id"] == permission_id for g in body["grants"])

    # User A is now on the custom role; the shared Viewer role — and User B,
    # still on it — must be completely untouched.
    users = client.get("/api/v1/users", headers={"Authorization": f"Bearer {admin_token}"}).json()
    a_out = next(u for u in users if u["id"] == str(user_a.id))
    b_out = next(u for u in users if u["id"] == str(user_b.id))
    assert a_out["roles"][0]["code"] == f"custom_{user_a.id}"
    assert b_out["roles"][0]["code"] == "VIEWER"

    matrix = client.get("/api/v1/rbac/matrix", headers={"Authorization": f"Bearer {admin_token}"}).json()
    viewer_grants_after = [g for g in matrix["grants"] if g["role_id"] == str(viewer_role.id)]
    assert len(viewer_grants_after) == len(viewer_grant_count)  # unchanged


def test_toggling_again_reuses_the_same_custom_role(client, admin_token, db_session):
    user = _create_viewer_user(db_session, f"viewer-{uuid.uuid4().hex[:8]}@aquaresilience.demo", "ViewerPass!2026")
    module_id_1, permission_id_1 = _ids(db_session, "ALERTS", "EDIT")
    module_id_2, permission_id_2 = _ids(db_session, "SCENARIOS", "EXECUTE")
    headers = {"Authorization": f"Bearer {admin_token}"}

    first = client.patch(
        f"/api/v1/users/{user.id}/permissions",
        headers=headers,
        json={"module_id": module_id_1, "permission_id": permission_id_1, "granted": True},
    )
    second = client.patch(
        f"/api/v1/users/{user.id}/permissions",
        headers=headers,
        json={"module_id": module_id_2, "permission_id": permission_id_2, "granted": True},
    )
    assert first.status_code == 200 and second.status_code == 200
    assert first.json()["role"]["id"] == second.json()["role"]["id"]  # same custom role, not re-cloned
    # Both grants must now be present together on that one role.
    grant_pairs = {(g["module_id"], g["permission_id"]) for g in second.json()["grants"]}
    assert (module_id_1, permission_id_1) in grant_pairs
    assert (module_id_2, permission_id_2) in grant_pairs

    custom_roles = db_session.execute(
        select(Role).where(Role.code == f"custom_{user.id}")
    ).scalars().all()
    assert len(custom_roles) == 1  # no duplicate custom roles pile up


def test_revoking_a_permission_removes_it_from_the_custom_role(client, admin_token, db_session):
    user = _create_viewer_user(db_session, f"viewer-{uuid.uuid4().hex[:8]}@aquaresilience.demo", "ViewerPass!2026")
    module_id, permission_id = _ids(db_session, "DASHBOARD", "VIEW")  # Viewer already has this
    headers = {"Authorization": f"Bearer {admin_token}"}

    resp = client.patch(
        f"/api/v1/users/{user.id}/permissions",
        headers=headers,
        json={"module_id": module_id, "permission_id": permission_id, "granted": False},
    )
    assert resp.status_code == 200
    grant_pairs = {(g["module_id"], g["permission_id"]) for g in resp.json()["grants"]}
    assert (module_id, permission_id) not in grant_pairs


def test_only_administration_admin_can_toggle_user_permissions(client, db_session):
    operator_role = db_session.execute(select(Role).where(Role.code == "OPERATOR")).scalar_one()
    email = f"operator-{uuid.uuid4().hex[:8]}@aquaresilience.demo"
    operator = User(email=email, hashed_password=hash_password("OperatorPass!2026"), full_name="Test Operator", is_active=True)
    db_session.add(operator)
    db_session.flush()
    db_session.add(UserRole(user_id=operator.id, role_id=operator_role.id))
    db_session.commit()

    target = _create_viewer_user(db_session, f"viewer-{uuid.uuid4().hex[:8]}@aquaresilience.demo", "ViewerPass!2026")
    login = client.post("/api/v1/auth/login", json={"email": email, "password": "OperatorPass!2026"})
    token = login.json()["access_token"]
    module_id, permission_id = _ids(db_session, "ALERTS", "EDIT")

    resp = client.patch(
        f"/api/v1/users/{target.id}/permissions",
        headers={"Authorization": f"Bearer {token}"},
        json={"module_id": module_id, "permission_id": permission_id, "granted": True},
    )
    assert resp.status_code == 403


# --- Optional lock on the shared demo administrator account (LOCK_DEMO_ADMIN) ---


def _demo_admin_id(client, admin_token) -> str:
    from app.core.config import settings

    users = client.get("/api/v1/users", headers={"Authorization": f"Bearer {admin_token}"}).json()
    return next(u["id"] for u in users if u["email"] == settings.demo_admin_email.lower())


def test_demo_admin_is_protected_when_locked(client, admin_token, db_session, monkeypatch):
    from app.core.config import settings

    headers = {"Authorization": f"Bearer {admin_token}"}
    admin_id = _demo_admin_id(client, admin_token)
    module_id, permission_id = _ids(db_session, "ALERTS", "EDIT")
    monkeypatch.setattr(settings, "lock_demo_admin", True)

    assert client.patch(f"/api/v1/users/{admin_id}", headers=headers, json={"is_active": False}).status_code == 403
    assert client.put(f"/api/v1/users/{admin_id}/password", headers=headers, json={"password": "Another!Pass2026"}).status_code == 403
    # deleting yourself is already refused (409) before the lock applies; either way it is blocked
    assert client.delete(f"/api/v1/users/{admin_id}", headers=headers).status_code in (403, 409)
    toggle = {"module_id": module_id, "permission_id": permission_id, "granted": False}
    assert client.patch(f"/api/v1/users/{admin_id}/permissions", headers=headers, json=toggle).status_code == 403

    admin_role = db_session.execute(select(Role).where(Role.code == "ADMINISTRATOR")).scalar_one()
    assert client.put("/api/v1/rbac/matrix", headers=headers, json={"role_id": str(admin_role.id), "grants": []}).status_code == 403


def test_other_users_and_roles_stay_editable_when_locked(client, admin_token, db_session, monkeypatch):
    from app.core.config import settings

    headers = {"Authorization": f"Bearer {admin_token}"}
    monkeypatch.setattr(settings, "lock_demo_admin", True)
    target = _create_viewer_user(db_session, f"viewer-{uuid.uuid4().hex[:8]}@aquaresilience.demo", "ViewerPass!2026")

    assert client.patch(f"/api/v1/users/{target.id}", headers=headers, json={"full_name": "Renamed"}).status_code == 200
    assert client.put(f"/api/v1/users/{target.id}/password", headers=headers, json={"password": "NewViewer!2026"}).status_code == 200
    viewer_role = db_session.execute(select(Role).where(Role.code == "VIEWER")).scalar_one()
    current = client.get("/api/v1/rbac/matrix", headers=headers).json()
    grants = [g for g in current["grants"] if g["role_id"] == str(viewer_role.id)]
    resp = client.put("/api/v1/rbac/matrix", headers=headers, json={"role_id": str(viewer_role.id), "grants": grants})
    assert resp.status_code == 200
    assert client.delete(f"/api/v1/users/{target.id}", headers=headers).status_code == 200


def test_demo_admin_is_editable_when_not_locked(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    admin_id = _demo_admin_id(client, admin_token)
    resp = client.patch(f"/api/v1/users/{admin_id}", headers=headers, json={"full_name": "Demo Administrator"})
    assert resp.status_code == 200
