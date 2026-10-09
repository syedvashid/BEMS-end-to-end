"""Integration tests for Phase 5 (database + API).

ASSUMPTIONS (conftest.py was not visible): `api(username, facility)` returns a DRF-style client with .get/.post/.patch/
.put/.delete(path, data, format="json") and dev headers; `world` has fa, fb, sys_a, admin_a, sys_b, dept_b and
world.mk(username, facility, role_code). Phase 2 master payloads in make_equipment() may need field tweaks.
Run: python -m pytest -q tests/test_maintenance_flow.py
"""
import uuid
from datetime import date, timedelta

import pytest
from django.db import connection
from django.db.utils import ProgrammingError

P = "/api/v1"


_PREFIX = {}


def _prefix(client):
    """Your conftest Api may or may not add /api/v1 itself: probe once with a harmless GET."""
    if "v" not in _PREFIX:
        try:
            r = client.get(f"{P}/facilities/")
            _PREFIX["v"] = P if r.status_code != 404 else ""
        except Exception:
            _PREFIX["v"] = P
    return _PREFIX["v"]


def J(client, method, path, body=None):
    """Calls conftest.Api.<method>(path[, body]); no `format=` argument (your Api does not accept it)."""
    fn = getattr(client, method)
    url = f"{_prefix(client)}{path}"
    return fn(url, body) if body is not None else fn(url)


def must(r, what):
    """Fail loudly with the API error body, so a wrong Phase 2 payload names the missing field."""
    assert r.status_code in (200, 201), f"{what} failed: HTTP {r.status_code} {r.content.decode()[:700]}"
    return r.json()


def make_equipment(admin, tag="1"):
    """Creates category/model/department/location and one COMMISSIONED equipment. Adjust payloads to Phase 2 if needed."""
    cat = must(J(admin, "post", "/equipment-categories/", {"code": f"CAT{tag}", "name": f"Category {tag}", "default_pm_interval_days": 90, "risk_class": "MEDIUM"}), "category")
    dept = must(J(admin, "post", "/departments/", {"code": f"D{tag}", "name": f"Dept {tag}"}), "department")
    loc = must(J(admin, "post", "/locations/", {"code": f"L{tag}", "name": f"Loc {tag}", "location_type": "ROOM", "department": dept["public_id"]}), "location")
    vendor = must(J(admin, "post", "/vendors/", {"name": f"Maker {tag}", "is_manufacturer": True}), "vendor")
    model = must(J(admin, "post", "/equipment-models/", {"category": cat["public_id"], "manufacturer": vendor["public_id"], "model_name": f"M{tag}", "model_number": f"MN{tag}"}), "equipment model")
    eq = must(J(admin, "post", "/equipment/", {"equipment_model": model["public_id"], "name": f"Unit {tag}"}), "equipment")
    eq = must(J(admin, "post", f"/equipment/{eq['public_id']}/install/", {"installation_date": str(date.today()), "row_version": eq["row_version"]}), "install")
    eq = must(J(admin, "post", f"/equipment/{eq['public_id']}/commission/", {
        "acceptance_test_result": "PASS", "acceptance_date": str(date.today()), "department": dept["public_id"],
        "location": loc["public_id"], "handover_received_by_name": "Ward Sister", "row_version": eq["row_version"]}), "commission")
    return eq, dept, cat, model


@pytest.fixture
def ctx(api, world):
    admin = api(world.sys_a.username, world.fa)
    eq, dept, cat, model = make_equipment(admin)
    eng = world.mk("eng_a", world.fa, "BIOMED_ENGINEER")
    ward = world.mk("ward_a", world.fa, "DEPARTMENT_USER")
    return SimpleNamespace_(admin=admin, eq=eq, dept=dept, cat=cat, model=model,
                            eng=api(eng.username, world.fa), ward=api(ward.username, world.fa), eng_user=eng, api=api, world=world)


class SimpleNamespace_:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def state(c):
    return J(c.admin, "get", f"/equipment/{c.eq['public_id']}/").json()["operational_state"]


def report(c, unusable=False, client=None):
    r = J(client or c.ward, "post", "/work-orders/report-breakdown/", {
        "equipment": c.eq["public_id"], "problem_description": "Not powering on", "priority": "HIGH",
        "reported_by_name": "Sister A", "reported_by_department": c.dept["public_id"], "equipment_unusable": unusable})
    assert r.status_code == 201, r.content
    return r.json()


def act(client, wo, name, body=None):
    cur = J(client, "get", f"/work-orders/{wo['public_id']}/").json()
    return J(client, "post", f"/work-orders/{wo['public_id']}/{name}/", {**(body or {}), "row_version": cur["row_version"]})


def test_ward_user_can_report_but_not_start(ctx):
    wo = report(ctx)
    assert wo["status"] == "OPEN" and wo["work_order_type"] == "BREAKDOWN" and wo["available_actions"] == []
    assert act(ctx.ward, wo, "start").status_code == 403
    assert J(ctx.ward, "post", "/work-orders/", {"work_order_type": "CORRECTIVE", "equipment": ctx.eq["public_id"]}).status_code == 403
    assert J(ctx.ward, "delete", f"/work-orders/{wo['public_id']}/").status_code in (403, 405)


def test_breakdown_lifecycle_holds_and_derived_state(ctx):
    wo = report(ctx, unusable=True)
    assert state(ctx) == "OUT_OF_SERVICE" and wo["downtime_start"]
    assert act(ctx.eng, wo, "start").status_code == 200
    assert state(ctx) == "UNDER_MAINTENANCE"
    assert act(ctx.eng, wo, "complete").status_code == 400            # action_taken required
    r = act(ctx.eng, wo, "complete", {"action_taken": "Replaced fuse"})
    assert r.status_code == 200 and r.json()["downtime_end"]
    assert state(ctx) == "IN_SERVICE"
    assert act(ctx.eng, wo, "close", {}).status_code == 400            # sign-off required
    assert act(ctx.eng, wo, "close", {"signoff_name": "Sister A"}).json()["status"] == "CLOSED"
    assert J(ctx.eng, "patch", f"/work-orders/{wo['public_id']}/", {"root_cause": "x", "row_version": 99}).status_code in (409, 400)


def test_manual_hold_survives_work_order_completion_and_blocks_in_service(ctx):
    r = J(ctx.eng, "post", f"/equipment/{ctx.eq['public_id']}/set-operational-state/", {"operational_state": "OUT_OF_SERVICE", "reason": "Planned shutdown", "row_version": J(ctx.admin, "get", f"/equipment/{ctx.eq['public_id']}/").json()["row_version"]})
    assert r.status_code == 200 and state(ctx) == "OUT_OF_SERVICE"
    wo = report(ctx)
    act(ctx.eng, wo, "start")
    assert state(ctx) == "UNDER_MAINTENANCE"
    cur = J(ctx.admin, "get", f"/equipment/{ctx.eq['public_id']}/").json()
    blocked = J(ctx.eng, "post", f"/equipment/{ctx.eq['public_id']}/set-operational-state/", {"operational_state": "IN_SERVICE", "reason": "try", "row_version": cur["row_version"]})
    assert blocked.status_code == 409 and blocked.json()["error"]["details"]["blocking_holds"]
    assert J(ctx.eng, "post", f"/equipment/{ctx.eq['public_id']}/set-operational-state/", {"operational_state": "UNDER_MAINTENANCE", "reason": "no", "row_version": cur["row_version"]}).status_code == 400
    act(ctx.eng, wo, "complete", {"action_taken": "ok"})
    assert state(ctx) == "OUT_OF_SERVICE"                                # manual hold survived


def test_two_work_orders_keep_state_until_both_done(ctx):
    a, b = report(ctx), report(ctx)
    act(ctx.eng, a, "start"); act(ctx.eng, b, "start")
    act(ctx.eng, a, "complete", {"action_taken": "ok"})
    assert state(ctx) == "UNDER_MAINTENANCE"
    act(ctx.eng, b, "cancel", {"reason": "duplicate"})
    assert state(ctx) == "IN_SERVICE"


def test_parts_ledger_insufficient_stock_and_return(ctx):
    part = J(ctx.eng, "post", "/spare-parts/", {"part_code": "FUSE1", "name": "Fuse", "standard_unit_cost": "10.00"}).json()
    assert J(ctx.eng, "post", f"/spare-parts/{part['public_id']}/stock/", {"entry_type": "RECEIPT", "quantity": "5"}).status_code == 403   # no spare_part.stock
    assert J(ctx.admin, "post", f"/spare-parts/{part['public_id']}/stock/", {"entry_type": "RECEIPT", "quantity": "5"}).status_code == 201
    wo = report(ctx)
    assert J(ctx.eng, "post", f"/work-orders/{wo['public_id']}/parts/", {"spare_part": part["public_id"], "quantity": "1"}).status_code == 409  # wo not started
    act(ctx.eng, wo, "start")
    ok = J(ctx.eng, "post", f"/work-orders/{wo['public_id']}/parts/", {"spare_part": part["public_id"], "quantity": "3"})
    assert ok.status_code == 201
    over = J(ctx.eng, "post", f"/work-orders/{wo['public_id']}/parts/", {"spare_part": part["public_id"], "quantity": "3"})
    assert over.status_code == 409 and over.json()["error"]["code"] == "insufficient_stock" and over.json()["error"]["details"]["available"] == "2.000"
    detail = J(ctx.eng, "get", f"/work-orders/{wo['public_id']}/").json()
    assert float(detail["parts_cost"]) == 30.0
    ret = J(ctx.eng, "post", f"/work-orders/{wo['public_id']}/parts/{ok.json()['public_id']}/return/", {})
    assert ret.status_code == 201
    assert float(J(ctx.eng, "get", f"/work-orders/{wo['public_id']}/").json()["parts_cost"]) == 0.0
    assert J(ctx.admin, "delete", f"/spare-parts/{part['public_id']}/").status_code == 409   # stock on hand > 0


def test_ledger_and_events_are_immutable_for_the_app_role(db):
    from django.db import transaction
    for sql in ("update spare_part_stock_entries set reason = 'x'", "delete from spare_part_stock_entries",
                "update work_order_events set note = 'x'", "delete from work_order_events"):
        with pytest.raises(ProgrammingError):          # permission denied for bems_app
            with transaction.atomic(), connection.cursor() as cur:
                cur.execute(sql)


def test_scheduler_is_idempotent_creates_once_and_cancel_needs_new_due_date(ctx):
    from django.core.management import call_command
    plan = J(ctx.admin, "post", "/maintenance-plans/", {
        "name": "Quarterly PM", "equipment": ctx.eq["public_id"], "frequency_type": "DAYS", "frequency_value": 90,
        "lead_days": 7, "start_date": str(date.today() + timedelta(days=5))})
    assert plan.status_code == 201, plan.content
    call_command("generate_pm_work_orders")
    call_command("generate_pm_work_orders")
    wos = J(ctx.admin, "get", f"/work-orders/?equipment={ctx.eq['public_id']}&work_order_type=PREVENTIVE").json()
    assert wos["count"] == 1
    wo = wos["results"][0]
    assert act(ctx.eng, wo, "cancel", {"reason": "not needed"}).status_code == 400            # next_due_date required
    new_due = str(date.today() + timedelta(days=30))
    assert act(ctx.eng, wo, "cancel", {"reason": "not needed", "next_due_date": new_due}).status_code == 200
    assert J(ctx.admin, "get", f"/maintenance-plans/{plan.json()['public_id']}/").json()["next_due_date"] == new_due


def test_pm_completion_advances_plan_from_completion_date(ctx):
    plan = J(ctx.admin, "post", "/maintenance-plans/", {"name": "Monthly", "equipment": ctx.eq["public_id"], "frequency_type": "MONTHS",
                                                         "frequency_value": 1, "start_date": str(date.today())}).json()
    wo = J(ctx.admin, "post", f"/maintenance-plans/{plan['public_id']}/generate-work-order/", {}).json()
    act(ctx.eng, wo, "start")
    assert act(ctx.eng, wo, "complete").status_code == 200
    after = J(ctx.admin, "get", f"/maintenance-plans/{plan['public_id']}/").json()
    assert after["last_performed_date"] == str(date.today()) and after["next_due_date"] > str(date.today())


def test_checklist_gate_and_auto_fail(ctx):
    tpl = J(ctx.admin, "post", "/checklist-templates/", {"name": "PM list", "items": [
        {"item_text": "Visual check", "item_type": "CHECK"},
        {"item_text": "Leakage current", "item_type": "MEASUREMENT", "unit": "uA", "min_value": "0", "max_value": "100"}]}).json()
    wo = J(ctx.admin, "post", "/work-orders/", {"work_order_type": "CORRECTIVE", "equipment": ctx.eq["public_id"],
                                                  "problem_description": "x", "checklist_template": tpl["public_id"]}).json()
    act(ctx.eng, wo, "start")
    assert act(ctx.eng, wo, "complete", {"action_taken": "done"}).status_code == 400          # items without result
    J(ctx.eng, "put", f"/work-orders/{wo['public_id']}/checklist/", {"items": [
        {"sequence": 1, "result": "PASS"}, {"sequence": 2, "result": "PASS", "measured_value": "250"}]})
    items = J(ctx.eng, "get", f"/work-orders/{wo['public_id']}/").json()["checklist_items"]
    assert items[1]["result"] == "FAIL"
    # later template edits never change the snapshot
    J(ctx.admin, "patch", f"/checklist-templates/{tpl['public_id']}/", {"items": [{"item_text": "Other", "item_type": "CHECK"}], "row_version": tpl["row_version"]})
    assert len(J(ctx.eng, "get", f"/work-orders/{wo['public_id']}/").json()["checklist_items"]) == 2


def test_assignee_must_be_a_facility_member_with_execute(ctx):
    wo = report(ctx)
    r = act(ctx.admin, wo, "assign", {"assigned_to": str(uuid.uuid4())})
    assert r.status_code == 400
    ok = act(ctx.admin, wo, "assign", {"assigned_to": str(ctx.eng_user.public_id)})
    assert ok.status_code == 200 and ok.json()["status"] == "ASSIGNED"


def test_cross_facility_is_404_and_db_rejects_foreign_equipment(ctx):
    other = ctx.api(ctx.world.sys_b.username, ctx.world.fb)
    wo = report(ctx)
    assert J(other, "get", f"/work-orders/{wo['public_id']}/").status_code == 404
    with connection.cursor() as cur, pytest.raises(Exception):
        cur.execute("""insert into work_orders (facility_id, wo_number, work_order_type, equipment_id)
                       select f.id, 'WO-2026-999999', 'CORRECTIVE', e.id from facilities f, equipment e
                        where f.id <> e.facility_id limit 1""")


def test_delete_gates_on_masters(ctx):
    J(ctx.admin, "post", "/checklist-templates/", {"name": "Gate", "category": ctx.cat["public_id"]})
    assert J(ctx.admin, "delete", f"/equipment-categories/{ctx.cat['public_id']}/").status_code == 409


def test_work_orders_accept_documents_registry():
    from apps.documents.registry import get_attachable
    att = get_attachable("work_order")
    assert att and att.view_permission == "work_order.view" and att.attach_permission == "work_order.change"