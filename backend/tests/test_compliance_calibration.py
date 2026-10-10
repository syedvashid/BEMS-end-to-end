from datetime import date

import pytest
from django.db import ProgrammingError, connection, transaction

from apps.compliance import services as cs
from apps.compliance.models import CalibrationRecord
from apps.maintenance.models import EquipmentHold, WorkOrder
from apps.maintenance.services import SystemRequest, add_months
from compliance_support import API, audit_count, client, days, make_equipment, record, schedule

pytestmark = pytest.mark.django_db


@pytest.fixture
def c(api, world):
    return client(api, world.sys_a, world.fa)


def test_month_end_clamp_and_status_boundaries():
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    t = date(2026, 6, 10)
    assert cs.status_code(date(2026, 6, 9), 30, t) == "OVERDUE"
    assert cs.status_code(date(2026, 6, 10), 30, t) == "DUE_SOON"
    assert cs.status_code(date(2026, 7, 10), 30, t) == "DUE_SOON"
    assert cs.status_code(date(2026, 7, 11), 30, t) == "OK"


def test_status_not_required_and_unresolved_failure(c, world):
    eq = make_equipment(world.fa)
    assert cs.calibration_status(eq)["status"] == "NOT_REQUIRED"
    schedule(c, eq)
    assert record(c, eq, "FAIL").status_code == 201
    s = cs.calibration_status(eq)
    assert s["has_unresolved_failure"] is True and s["status"] == "OK"
    assert record(c, eq, "PASS").status_code == 201
    assert cs.calibration_status(eq)["has_unresolved_failure"] is False


def test_fail_places_calibration_hold_and_corrective_wo(c, world):
    eq = make_equipment(world.fa)
    schedule(c, eq)
    r = record(c, eq, "FAIL")
    assert r.status_code == 201, r.content
    eq.refresh_from_db()
    assert eq.operational_state == "OUT_OF_SERVICE"
    hold = EquipmentHold.objects.get(equipment=eq, released_at__isnull=True)
    assert hold.source_type == "CALIBRATION" and hold.calibration_record_id
    wo = WorkOrder.objects.get(source_calibration_record_id=hold.calibration_record_id)
    assert wo.work_order_type == "CORRECTIVE" and wo.priority == "HIGH"
    assert audit_count("CALIBRATION_RECORDED") >= 1


def test_fail_with_flags_off(c, world):
    eq = make_equipment(world.fa)
    schedule(c, eq, on_fail_hold_equipment=False, on_fail_open_work_order=False)
    assert record(c, eq, "FAIL").status_code == 201
    eq.refresh_from_db()
    assert eq.operational_state == "IN_SERVICE"
    assert not EquipmentHold.objects.filter(equipment=eq).exists()
    assert not WorkOrder.objects.filter(equipment=eq).exists()


def test_pass_releases_calibration_hold_only(c, world):
    from apps.maintenance import holds
    eq = make_equipment(world.fa)
    schedule(c, eq, on_fail_open_work_order=False)
    record(c, eq, "FAIL")
    holds.place_hold(request=SystemRequest(), equipment=eq, hold_type="MAINTENANCE", source_type="MANUAL",
                     reason="manual hold")
    eq.refresh_from_db()
    assert eq.operational_state == "UNDER_MAINTENANCE"
    assert record(c, eq, "PASS", performed=days(0)).status_code == 201
    eq.refresh_from_db()
    assert eq.operational_state == "UNDER_MAINTENANCE"            # work-order/manual hold remains
    assert not EquipmentHold.objects.filter(equipment=eq, source_type="CALIBRATION", released_at__isnull=True).exists()


def test_pass_returns_state_to_in_service(c, world):
    eq = make_equipment(world.fa)
    schedule(c, eq, on_fail_open_work_order=False)
    record(c, eq, "FAIL")
    record(c, eq, "PASS", performed=days(0))
    eq.refresh_from_db()
    assert eq.operational_state == "IN_SERVICE"


def test_next_due_rules_and_validation(c, world):
    eq = make_equipment(world.fa)
    s = schedule(c, eq, frequency_type="MONTHS", frequency_value=6)
    assert record(c, eq, "PASS", performed=days(-1), next_due_date=days(-1)).status_code == 400
    assert record(c, eq, "PASS", performed=days(5)).status_code == 400                      # future
    assert record(c, eq, "PASS", readings=[{"parameter": "p"}] * 51).status_code == 400
    assert record(c, eq, "PASS", readings=[{"parameter": "p", "bogus": 1}]).status_code == 400
    ok = record(c, eq, "PASS", performed="2026-01-31", readings=[{"parameter": "Output", "nominal": 10, "measured": 10.2}])
    assert ok.status_code == 201
    assert ok.json()["next_due_date"] == "2026-07-31"


def test_equipment_must_be_commissioned_and_scheduled(c, world):
    eq = make_equipment(world.fa)
    assert record(c, eq).status_code == 400                                                  # no schedule
    eq2 = make_equipment(world.fa)
    schedule(c, eq2)
    type(eq2).objects.filter(pk=eq2.pk).update(lifecycle_stage="CONDEMNED")
    assert record(c, eq2).status_code == 400


def test_impact_review_only_fail_and_once(c, world):
    eq = make_equipment(world.fa)
    schedule(c, eq, on_fail_hold_equipment=False, on_fail_open_work_order=False)
    p = record(c, eq, "PASS").json()
    f = record(c, eq, "FAIL", performed=days(0)).json()
    body = {"review_notes": "No patient affected", "patient_impact_found": False}
    assert c.post(f"{API}/calibration-records/{p['public_id']}/review-impact/", body, format="json").status_code == 409
    assert c.post(f"{API}/calibration-records/{f['public_id']}/review-impact/", body, format="json").status_code == 201
    assert c.post(f"{API}/calibration-records/{f['public_id']}/review-impact/", body, format="json").status_code == 409
    assert audit_count("CALIBRATION_IMPACT_REVIEWED") >= 1


def test_records_immutable_for_app_role(c, world):
    eq = make_equipment(world.fa)
    schedule(c, eq)
    record(c, eq)
    for sql in ("update calibration_records set notes = 'x'", "delete from calibration_records"):
        with pytest.raises(ProgrammingError), transaction.atomic(), connection.cursor() as cur:
            cur.execute(sql)
    assert c.delete(f"{API}/calibration-records/{CalibrationRecord.objects.first().public_id}/").status_code in (404, 405)


def test_generate_schedules(c, world):
    eq1, eq2 = make_equipment(world.fa), make_equipment(world.fa)
    schedule(c, eq1)
    cat = eq1.equipment_model.category
    r = c.post(f"{API}/calibration-schedules/generate/", {"category": str(cat.public_id)}, format="json")
    assert r.status_code == 200, r.content
    assert r.json()["skipped_existing"] >= 1 and r.json()["created"] >= 1
    assert audit_count("BULK_CREATE") >= 1


def test_cross_facility_is_404(api, world):
    eq = make_equipment(world.fa)
    schedule(client(api, world.sys_a, world.fa), eq)
    cb = client(api, world.sys_b, world.fb)
    assert cb.post(f"{API}/calibration-records/", {"equipment": str(eq.public_id), "performed_date": days(-1),
                   "performed_by_type": "IN_HOUSE", "performer_name": "x", "result": "PASS"}, format="json").status_code == 400
    assert cb.get(f"{API}/calibration-schedules/").json()["count"] == 0