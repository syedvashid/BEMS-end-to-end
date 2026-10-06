import subprocess
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

from apps.foundation.context import RequestContext
from apps.foundation.models import AuditLog, UserFacilityRole
from apps.foundation.viewsets import FacilityScopedViewSet

BACKEND = Path(__file__).resolve().parents[1]


def test_health_is_public(db, api):
    assert api().get("/health/").status_code == 200


def test_no_header_is_401(world, api):
    r = api(None, world.fa).get("/facilities/")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "not_authenticated"


def test_unknown_or_inactive_user_is_401(world, api):
    assert api("nobody.here", world.fa).get("/facilities/").status_code == 401
    world.sys_a.is_active = False
    world.sys_a.save(update_fields=["is_active"])
    assert api("sys_a", world.fa).get("/facilities/").status_code == 401


def test_dev_header_ignored_when_debug_off(world, api, settings):
    settings.DEBUG = False
    assert api("sys_a", world.fa).get("/facilities/").status_code == 401


def test_missing_facility_header_is_400(world, api):
    r = api("sys_a").get("/users/")
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "facility_required"


def test_non_member_unknown_and_garbage_facility_are_404(world, api):
    assert api("sys_a", world.fb).get("/users/").status_code == 404
    assert api("sys_a", str(uuid.uuid4())).get("/users/").status_code == 404
    assert api("sys_a", "not-a-uuid").get("/users/").status_code == 404


def test_facility_list_and_retrieve_only_member(world, api):
    c = api("sys_a", world.fa)
    ids = {f["public_id"] for f in c.get("/facilities/").json()["results"]}
    assert ids == {str(world.fa.public_id)}
    assert c.get(f"/facilities/{world.fb.public_id}/").status_code == 404


def test_cannot_update_or_delete_other_facility(world, api):
    c = api("sys_a", world.fa)
    assert c.patch(f"/facilities/{world.fb.public_id}/", {"name": "x", "row_version": 1}).status_code == 404
    assert c.delete(f"/facilities/{world.fb.public_id}/").status_code == 404


def test_users_scoped_to_current_facility(world, api):
    c = api("sys_a", world.fa)
    names = {u["username"] for u in c.get("/users/").json()["results"]}
    assert names == {"sys_a", "admin_a"}
    assert c.get(f"/users/{world.sys_b.public_id}/").status_code == 404


def test_audit_logs_scoped_to_current_facility(world, api):
    api("sys_b", world.fb).post("/users/", {"username": "only.in.b", "full_name": "B"})
    api("sys_a", world.fa).post("/users/", {"username": "only.in.a", "full_name": "A"})
    rows = api("sys_a", world.fa).get("/audit-logs/").json()["results"]
    assert rows and all(r["request_path"] for r in rows)
    assert not AuditLog.objects.filter(facility=world.fa, entity_type="User", new_value__username="only.in.b").exists()
    assert all(r["new_value"] is None or r["new_value"].get("username") != "only.in.b" for r in rows)


def test_facility_scoped_viewset_filters_hides_inactive_and_sets_facility(world):
    class V(FacilityScopedViewSet):
        queryset = UserFacilityRole.objects.all()
        serializer_class = None
        required_permissions = {}

    ctx = RequestContext(world.sys_a, world.fa, frozenset(), frozenset())
    v = V()
    v.action = "list"
    v.request = SimpleNamespace(bems=ctx, query_params={}, user=world.sys_a)
    qs = v.get_queryset()
    assert qs.exists() and set(qs.values_list("facility_id", flat=True)) == {world.fa.id}
    row = qs.first()
    row.is_active = False
    row.save(update_fields=["is_active"])
    assert not v.get_queryset().filter(pk=row.pk).exists()
    assert v.server_fields("create")["facility"] == world.fa
    assert v.server_fields("create")["created_by"] == world.sys_a.id


def _boot(debug, dev_auth):
    import os
    env = {**os.environ, "DJANGO_DEBUG": debug, "BEMS_DEV_AUTH": dev_auth, "DJANGO_SECRET_KEY": "x" * 50}
    return subprocess.run([sys.executable, "-c", "import config.settings"], cwd=BACKEND, env=env,
                          capture_output=True, text=True)


def test_refuses_to_start_dev_auth_without_debug():
    r = _boot("false", "true")
    assert r.returncode != 0 and "BEMS_DEV_AUTH" in r.stderr


def test_starts_with_debug_and_dev_auth_or_neither():
    assert _boot("true", "true").returncode == 0
    assert _boot("false", "false").returncode == 0