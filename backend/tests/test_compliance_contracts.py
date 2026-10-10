from datetime import date, timedelta

import pytest
from django.db import IntegrityError, transaction

from apps.compliance.models import Warranty
from apps.maintenance.models import WorkOrder
from compliance_support import API, audit_count, client, days, make_equipment, make_vendor

pytestmark = pytest.mark.django_db


@pytest.fixture
def c(api, world):
    return client(api, world.sys_a, world.fa)


def warranty(c, eq, start=-30, end=300, **kw):
    r = c.post(f"{API}/warranties/", {"equipment": str(eq.public_id), "warranty_type": "STANDARD",
                                      "start_date": days(start), "end_date": days(end), **kw}, format="json")
    assert r.status_code == 201, r.content
    return r.json()


def amc(c, vendor, eqs=(), start=-30, end=300, number=None, ctype="COMPREHENSIVE"):
    r = c.post(f"{API}/amc-contracts/", {"contract_number": number or f"AMC-{date.today().toordinal()}-{len(eqs)}-{start}-{end}",
               "vendor": str(vendor.public_id), "contract_type": ctype, "start_date": days(start), "end_date": days(end),
               "contract_cost": "1000.00"}, format="json")
    assert r.status_code == 201, r.content
    a = r.json()
    if eqs:
        cv = c.put(f"{API}/amc-contracts/{a['public_id']}/coverage/",
                   {"items": [{"equipment": str(e.public_id), "allocated_cost": "100.00"} for e in eqs]}, format="json")
        assert cv.status_code == 200, cv.content
    return a


def coverage(c, eq, on=None):
    return c.get(f"{API}/equipment/{eq.public_id}/coverage/" + (f"?on={on}" if on else "")).json()


def test_coverage_suggestion_matrix(c, world):
    v = make_vendor(world.fa)
    none_eq, w_eq, expired_eq, amc_eq, both_eq, nc_eq = (make_equipment(world.fa) for _ in range(6))
    warranty(c, w_eq)
    warranty(c, expired_eq, start=-400, end=-10)
    amc(c, v, [amc_eq], number="M-1")
    warranty(c, both_eq); amc(c, v, [both_eq], number="M-2")
    amc(c, v, [nc_eq], number="M-3", ctype="NON_COMPREHENSIVE")
    assert coverage(c, none_eq)["coverage_source"] is None
    assert coverage(c, w_eq)["coverage_source"] == "WARRANTY"
    assert coverage(c, expired_eq)["coverage_source"] is None
    assert coverage(c, amc_eq)["coverage_source"] == "AMC"
    assert coverage(c, both_eq)["coverage_source"] == "WARRANTY"                  # warranty wins
    assert "parts" in coverage(c, nc_eq)["message"].lower()


def test_breakdown_autofill_and_override(c, world):
    eq = make_equipment(world.fa)
    w = warranty(c, eq)
    r = c.post(f"{API}/work-orders/report-breakdown/", {"equipment": str(eq.public_id), "problem_description": "dead"}, format="json")
    assert r.status_code == 201, r.content
    assert r.json()["coverage_source"] == "WARRANTY" and r.json()["warranty"]["public_id"] == w["public_id"]
    paid = c.post(f"{API}/work-orders/report-breakdown/", {"equipment": str(eq.public_id), "problem_description": "x", "coverage_source": "PAID"}, format="json")
    assert paid.json()["coverage_source"] == "PAID" and paid.json()["warranty"] is None
    pid = r.json()["public_id"]
    p = c.patch(f"{API}/work-orders/{pid}/", {"row_version": r.json()["row_version"], "coverage_source": "IN_HOUSE"}, format="json")
    assert p.status_code == 200 and p.json()["warranty"] is None


def test_linked_warranty_must_belong_to_equipment(c, world):
    eq, other = make_equipment(world.fa), make_equipment(world.fa)
    w_other = warranty(c, other)
    r = c.post(f"{API}/work-orders/report-breakdown/", {"equipment": str(eq.public_id), "problem_description": "x"}, format="json").json()
    bad = c.patch(f"{API}/work-orders/{r['public_id']}/", {"row_version": r["row_version"], "warranty_id": w_other["public_id"]}, format="json")
    assert bad.status_code == 400


def test_amc_overlap_conflict_dates_and_allocation(c, world):
    v, eq = make_vendor(world.fa), make_equipment(world.fa)
    a1 = amc(c, v, [eq], number="O-1")
    a2 = amc(c, v, [], number="O-2")
    r = c.put(f"{API}/amc-contracts/{a2['public_id']}/coverage/", {"items": [{"equipment": str(eq.public_id)}]}, format="json")
    assert r.status_code == 409 and "O-1" in r.json()["error"]["message"]
    bad = c.post(f"{API}/amc-contracts/", {"contract_number": "BAD", "vendor": str(v.public_id), "contract_type": "COMPREHENSIVE",
                 "start_date": days(10), "end_date": days(1), "contract_cost": "0"}, format="json")
    assert bad.status_code == 400
    ok = c.put(f"{API}/amc-contracts/{a1['public_id']}/coverage/", {"items": [{"equipment": str(eq.public_id)}]}, format="json")
    assert ok.status_code == 200 and ok.json()["coverage"][0]["allocated_cost"] is None
    assert audit_count("AMC_COVERAGE_CHANGED") >= 1


def test_amc_renewal(c, world):
    v, eq = make_vendor(world.fa), make_equipment(world.fa)
    a = amc(c, v, [eq], number="R-1", start=-300, end=-1)
    r = c.post(f"{API}/amc-contracts/{a['public_id']}/renew/", {}, format="json")
    assert r.status_code == 201, r.content
    n = r.json()
    assert n["renewed_from_contract"] == a["public_id"] and n["start_date"] == days(0)
    assert [x["equipment"]["public_id"] for x in n["coverage"]] == [str(eq.public_id)]
    assert c.get(f"{API}/amc-contracts/{a['public_id']}/").json()["end_date"] == a["end_date"]   # old unchanged
    assert c.post(f"{API}/amc-contracts/{a['public_id']}/renew/", {}, format="json").status_code == 409
    assert audit_count("AMC_RENEWED") >= 1


def test_bulk_warranties(c, world):
    from apps.equipment.models import EquipmentCommissioning
    e1, e2 = make_equipment(world.fa), make_equipment(world.fa)
    EquipmentCommissioning.objects.create(facility=world.fa, equipment=e1, acceptance_date=date(2026, 1, 15))
    body = {"warranty_type": "STANDARD", "duration_months": 12}
    r = c.post(f"{API}/warranties/bulk/", {**body, "equipment": [str(e1.public_id)]}, format="json")
    assert r.status_code == 201 and Warranty.objects.get(equipment=e1).start_date == date(2026, 1, 15)
    before = Warranty.objects.count()
    bad = c.post(f"{API}/warranties/bulk/", {**body, "equipment": [str(e1.public_id), str(e2.public_id)]}, format="json")
    assert bad.status_code == 400 and Warranty.objects.count() == before                    # e2 has no acceptance date
    assert c.post(f"{API}/warranties/bulk/", {**body, "equipment": []}, format="json").status_code == 400
    import uuid
    assert c.post(f"{API}/warranties/bulk/", {**body, "equipment": [str(uuid.uuid4()) for _ in range(201)]}, format="json").status_code == 400


def test_licence_crud_and_renewal(c, world):
    eq = make_equipment(world.fa)
    r = c.post(f"{API}/equipment-licences/", {"equipment": str(eq.public_id), "licence_type": "AERB_LICENCE",
               "issue_date": days(-300), "expiry_date": days(30)}, format="json")
    assert r.status_code == 201
    lid = r.json()["public_id"]
    assert c.post(f"{API}/equipment-licences/", {"equipment": str(eq.public_id), "licence_type": "OTHER",
                  "issue_date": days(5), "expiry_date": days(1)}, format="json").status_code == 400
    n = c.post(f"{API}/equipment-licences/{lid}/renew/", {"issue_date": days(30), "expiry_date": days(395)}, format="json")
    assert n.status_code == 201 and n.json()["renewed_from_licence"] == lid
    assert c.post(f"{API}/equipment-licences/{lid}/renew/", {"issue_date": days(30), "expiry_date": days(395)}, format="json").status_code == 409


def test_vendor_delete_gate(c, world):
    v, eq = make_vendor(world.fa), make_equipment(world.fa)
    warranty(c, eq, vendor=str(v.public_id))
    assert c.delete(f"{API}/vendors/{v.public_id}/").status_code == 409


def test_db_rejects_cross_facility_fk(world):
    eq_a, v_b = make_equipment(world.fa), make_vendor(world.fb)
    with pytest.raises(IntegrityError), transaction.atomic():
        Warranty.objects.create(facility=world.fb, equipment=eq_a, vendor=v_b, warranty_type="STANDARD",
                                start_date=date.today(), end_date=date.today() + timedelta(days=5))


def test_documents_attachable_to_new_types():
    from apps.documents.registry import get_attachable
    for t, view, attach in (("calibration_record", "calibration.view", "calibration.record"), ("warranty", "warranty.view", "warranty.change"),
                            ("amc_contract", "amc.view", "amc.change"), ("equipment_licence", "licence.view", "licence.change")):
        a = get_attachable(t)
        assert a and a.view_permission == view and a.attach_permission == attach