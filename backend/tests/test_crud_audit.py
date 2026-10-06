from apps.foundation.models import AuditLog, Role, User


def _member(c, username="new.member", role_code="DEPARTMENT_USER"):
    r = c.post("/users/", {"username": username, "full_name": "New Member"})
    assert r.status_code == 201, r.content
    pid = r.json()["public_id"]
    role_pid = str(Role.objects.get(code=role_code, is_active=True).public_id)
    r2 = c.post(f"/users/{pid}/facility-roles/", {"roles": [role_pid]})
    assert r2.status_code == 200, r2.content
    return r.json()


def test_create_update_soft_delete_are_audited(world, api):
    c = api("sys_a", world.fa)
    u = _member(c)
    pid = u["public_id"]
    r = c.patch(f"/users/{pid}/", {"full_name": "Renamed", "row_version": u["row_version"]})
    assert r.status_code == 200 and r.json()["row_version"] == u["row_version"] + 1
    assert c.delete(f"/users/{pid}/").status_code == 204
    actions = list(AuditLog.objects.filter(entity_public_id=pid).order_by("chain_seq").values_list("action", flat=True))
    assert actions == ["CREATE", "USER_FACILITY_ROLE_CHANGE", "UPDATE", "SOFT_DELETE"]
    upd = AuditLog.objects.get(entity_public_id=pid, action="UPDATE")
    assert "full_name" in upd.changed_fields and upd.previous_value["full_name"] == "New Member"
    assert upd.request_id and upd.http_method == "PATCH" and upd.actor_username == "sys_a"


def test_stale_version_and_missing_version(world, api):
    c = api("sys_a", world.fa)
    u = _member(c)
    pid, v = u["public_id"], u["row_version"]
    assert c.patch(f"/users/{pid}/", {"full_name": "One", "row_version": v}).status_code == 200
    r = c.patch(f"/users/{pid}/", {"full_name": "Two", "row_version": v})
    assert r.status_code == 409 and r.json()["error"]["code"] == "stale_version"
    r = c.patch(f"/users/{pid}/", {"full_name": "Three"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "validation_error"


def test_unknown_and_server_fields_rejected(world, api):
    c = api("sys_a", world.fa)
   # AFTER
    for bad in ("facility_id", "created_by", "public_id_x", "password_hash"):
        r = c.post("/users/", {"username": "bad.field", "full_name": "X", bad: 1})
        assert r.status_code == 400, bad
        assert bad in r.json()["error"]["details"]


def test_soft_delete_and_include_inactive(world, api):
    sysa, admin = api("sys_a", world.fa), api("admin_a", world.fa)
    u = _member(sysa)
    pid = u["public_id"]
    assert sysa.delete(f"/users/{pid}/").status_code == 204
    listing = lambda c, **p: {x["public_id"]: x for x in c.get("/users/", **p).json()["results"]}
    assert pid not in listing(sysa)
    assert listing(sysa, include_inactive="true")[pid]["is_active"] is False   # has user.delete
    assert pid not in listing(admin, include_inactive="true")                    # BIOMED_ADMIN lacks it
    assert sysa.get(f"/users/{pid}/").status_code == 404


def test_cannot_deactivate_self(world, api):
    r = api("sys_a", world.fa).delete(f"/users/{world.sys_a.public_id}/")
    assert r.status_code == 409


def test_privilege_escalation_blocked_and_audited(world, api):
    c = api("admin_a", world.fa)            # BIOMED_ADMIN: user.change but not role.manage etc.
    pid = c.post("/users/", {"username": "target.user", "full_name": "T"}).json()["public_id"]
    sys_role = str(Role.objects.get(code="SYSTEM_ADMIN", is_active=True).public_id)
    r = c.post(f"/users/{pid}/facility-roles/", {"roles": [sys_role]})
    assert r.status_code == 403
    assert AuditLog.objects.filter(action="ACCESS_DENIED", actor_username="admin_a").exists()


def test_roles_custom_system_and_permissions(world, api):
    c = api("sys_a", world.fa)
    r = c.post("/roles/", {"code": "CUSTOM_Y", "name": "Custom Y"})
    assert r.status_code == 201 and r.json()["is_system"] is False
    pid, v = r.json()["public_id"], r.json()["row_version"]
    r = c.put(f"/roles/{pid}/permissions/", {"permission_codes": ["facility.view", "audit.view"], "row_version": v})
    assert r.status_code == 200 and r.json()["permission_codes"] == ["audit.view", "facility.view"]
    assert AuditLog.objects.filter(action="ROLE_PERMISSIONS_CHANGE", entity_public_id=pid).exists()
    assert c.put(f"/roles/{pid}/permissions/", {"permission_codes": [], "row_version": v}).status_code == 409
    assert c.put(f"/roles/{pid}/permissions/", {"permission_codes": ["nope.nope"], "row_version": v + 1}).status_code == 400
    sys_pid = str(Role.objects.get(code="SYSTEM_ADMIN", is_active=True).public_id)
    assert c.delete(f"/roles/{sys_pid}/").status_code == 409
    assert c.put(f"/roles/{sys_pid}/permissions/", {"permission_codes": [], "row_version": 1}).status_code == 409
    assert c.delete(f"/roles/{pid}/").status_code == 204


def test_audit_failure_rolls_back_the_change(world, api, monkeypatch):
    def boom(**kwargs):
        raise RuntimeError("audit down")
    monkeypatch.setattr("apps.core.audit.record", boom)
    r = api("sys_a", world.fa).post("/users/", {"username": "rollback.user", "full_name": "R"})
    assert r.status_code == 500 and r.json()["error"]["code"] == "internal_error"
    assert not User.objects.filter(username="rollback.user").exists()