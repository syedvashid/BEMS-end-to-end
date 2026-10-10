from datetime import date, timedelta

import pytest
from django.db import connection

from apps.compliance.services import bucket_for
from compliance_support import API, client, days, make_equipment, make_vendor
from test_compliance_contracts import amc, warranty

pytestmark = pytest.mark.django_db

EXPECTED_COUNTS = {"SYSTEM_ADMIN": 16, "BIOMED_ADMIN": 16, "BIOMED_ENGINEER": 12, "STORE_OFFICER": 6,
                   "FINANCE": 4, "DEPARTMENT_USER": 1, "AUDITOR": 4}


def test_bucket_boundaries():
    assert [bucket_for(n) for n in (-1, 0, 7, 8, 30, 31, 60, 61, 90, 91)] == [
        "OVERDUE", "D7", "D7", "D30", "D30", "D60", "D60", "D90", "D90", "LATER"]


def test_role_permission_counts():
    with connection.cursor() as cur:
        cur.execute("""select r.code, count(*) from role_permissions rp join roles r on r.id = rp.role_id
                       join permissions p on p.id = rp.permission_id
                       where p.module in ('calibration','warranty','amc','licence') group by 1""")
        got = dict(cur.fetchall())
    for role, n in EXPECTED_COUNTS.items():
        assert got.get(role) == n, role


def test_due_buckets_types_and_documents(api, world):
    from apps.documents.models import Document
    c = client(api, world.sys_a, world.fa)
    eq = make_equipment(world.fa)
    w = warranty(c, eq, start=-300, end=5)
    c.post(f"{API}/calibration-schedules/", {"equipment": str(eq.public_id), "frequency_type": "DAYS", "frequency_value": 30,
           "next_due_date": days(-3)}, format="json")
    Document.objects.create(facility=world.fa, document_type="OTHER", title="Cert", entity_type="warranty",
                            entity_public_id=w["public_id"], expiry_date=date.today() + timedelta(days=20))
    rows = c.get(f"{API}/compliance/due/?equipment={eq.public_id}").json()["results"]
    kinds = {r["item_type"]: r["bucket"] for r in rows}
    assert kinds == {"CALIBRATION": "OVERDUE", "WARRANTY": "D7", "DOCUMENT": "D30"}
    assert [r["due_date"] for r in rows] == sorted(r["due_date"] for r in rows)
    only = c.get(f"{API}/compliance/due/?equipment={eq.public_id}&bucket=OVERDUE").json()["results"]
    assert [r["item_type"] for r in only] == ["CALIBRATION"]


def test_due_filtered_by_permission_and_facility(api, world):
    c = client(api, world.sys_a, world.fa)
    eq = make_equipment(world.fa)
    warranty(c, eq, start=-300, end=5)
    c.post(f"{API}/calibration-schedules/", {"equipment": str(eq.public_id), "frequency_type": "DAYS", "frequency_value": 30,
           "next_due_date": days(5)}, format="json")
    dept = world.mk("t_dept_user", world.fa, "DEPARTMENT_USER")
    got = client(api, dept, world.fa).get(f"{API}/compliance/due/?equipment={eq.public_id}").json()["results"]
    assert {r["item_type"] for r in got} == {"CALIBRATION"}                                   # only calibration.view
    assert client(api, world.sys_b, world.fb).get(f"{API}/compliance/due/").json()["count"] == 0