import pytest

from apps.foundation.models import AuditLog

ROLES = ["SYSTEM_ADMIN", "BIOMED_ADMIN", "BIOMED_ENGINEER", "STORE_OFFICER", "DEPARTMENT_USER", "FINANCE", "AUDITOR"]
ALL = set(ROLES)
VIEWERS = {"SYSTEM_ADMIN", "BIOMED_ADMIN", "AUDITOR"}

CASES = [
    ("GET", "/me/", None, ALL),
    ("GET", "/facilities/", None, ALL),
    ("POST", "/facilities/", {"code": "NEWF", "name": "New Facility", "facility_type": "CLINIC"}, {"SYSTEM_ADMIN"}),
    ("GET", "/users/", None, VIEWERS),
    ("POST", "/users/", {"username": "matrix.user", "full_name": "Matrix User"}, {"SYSTEM_ADMIN", "BIOMED_ADMIN"}),
    ("GET", "/roles/", None, VIEWERS),
    ("POST", "/roles/", {"code": "CUSTOM_X", "name": "Custom X"}, {"SYSTEM_ADMIN"}),
    ("GET", "/permissions/", None, VIEWERS),
    ("GET", "/audit-logs/", None, VIEWERS),
]


@pytest.mark.parametrize("role", ROLES)
@pytest.mark.parametrize("method,path,body,allowed", CASES)
def test_permission_matrix(world, api, role, method, path, body, allowed):
    user = world.mk(f"m_{role.lower()}", world.fa, role)
    resp = api(user.username, world.fa).call(method, path, body)
    if role in allowed:
        assert resp.status_code in (200, 201), resp.content
    else:
        assert resp.status_code == 403, resp.content
        assert resp.json()["error"]["code"] == "permission_denied"
        assert AuditLog.objects.filter(action="ACCESS_DENIED", actor_username=user.username).exists()