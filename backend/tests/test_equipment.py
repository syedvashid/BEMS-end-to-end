"""Phase 4 tests. Run: python -m pytest tests/test_equipment.py -q
Adjust DEPT_TYPE / FUND_TYPE below if your Phase 2 CHECK constraints use other values."""
import io
import json
import re
from types import SimpleNamespace
import psycopg
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import DatabaseError, IntegrityError, connection, transaction
from django.test.utils import CaptureQueriesContext

from apps.equipment.models import Equipment, EquipmentCommissioning, EquipmentMovement, EquipmentStateHistory
from apps.foundation.models import AuditLog
from apps.masters.models import Department, EquipmentCategory, EquipmentModel, FundingSource, Location, Vendor

pytestmark = pytest.mark.django_db

DEPT_TYPE = "CLINICAL"
FUND_TYPE = "GOVERNMENT"
BASE = "/api/v1/equipment/"
TAG_RE = re.compile(r"^EQ-\d{4}-\d{6}$")
ROLES = ["SYSTEM_ADMIN", "BIOMED_ADMIN", "BIOMED_ENGINEER", "STORE_OFFICER", "FINANCE", "DEPARTMENT_USER", "AUDITOR"]


# ------------------------------------------------------------------ fixtures / helpers
def make_masters(fac, tag):
    dept = Department.objects.create(facility=fac, code=f"D{tag}", name=f"Dept {tag}", department_type=DEPT_TYPE)
    root = Location.objects.create(facility=fac, location_type="BUILDING", code=f"L{tag}R", name=f"Root {tag}", department=dept)
    child = Location.objects.create(facility=fac, location_type="ROOM", code=f"L{tag}C", name=f"Child {tag}",
                                    parent_location=root, department=dept)
    other = Location.objects.create(facility=fac, location_type="ROOM", code=f"L{tag}O", name=f"Other {tag}")
    mfr = Vendor.objects.create(facility=fac, name=f"Maker {tag}", is_manufacturer=True, is_supplier=True)
    cat = EquipmentCategory.objects.create(facility=fac, code=f"C{tag}", name=f"Cat {tag}", risk_class="MEDIUM",
                                           default_pm_interval_days=90)
    model = EquipmentModel.objects.create(facility=fac, category=cat, manufacturer=mfr,
                                          model_name=f"Model {tag}", model_number=f"MN{tag}")
    model2 = EquipmentModel.objects.create(facility=fac, category=cat, manufacturer=mfr,
                                           model_name=f"Model2 {tag}", model_number=f"MM{tag}")
    fund = FundingSource.objects.create(facility=fac, code=f"F{tag}", name=f"Fund {tag}", source_type=FUND_TYPE)
    return SimpleNamespace(dept=dept, root=root, child=child, other=other, mfr=mfr, cat=cat,
                           model=model, model2=model2, fund=fund)


@pytest.fixture
def mx(world):
    return make_masters(world.fa, "A")


@pytest.fixture
def cl(world, api):
    cache = {}

    def get(role, fac=None):
        fac = fac or world.fa
        key = (role, fac.id)
        if key not in cache:
            name = f"t_{role.lower()}_{fac.id}"
            world.mk(name, fac, role)
            cache[key] = api(name, fac)
        return cache[key]
    return get


def pid(o):
    return str(o.public_id)


def register(c, mx, **over):
    return c.post(BASE, {"equipment_model": pid(mx.model), **over}, format="json")


def mk_eq(c, mx, **over):
    r = register(c, mx, **over)
    assert r.status_code == 201, r.content
    return r.json()


def act(c, eq, action, **body):
    return c.post(f"{BASE}{eq['public_id']}/{action}/", {"row_version": eq["row_version"], **body}, format="json")


def detail(c, eq):
    return c.get(f"{BASE}{eq['public_id']}/").json()


def to_installed(c, mx):
    r = act(c, mk_eq(c, mx), "install", installation_date="2026-01-10", installation_engineer_name="Eng")
    assert r.status_code == 200, r.content
    return r.json()


def commission_body(mx, **over):
    return {"acceptance_test_result": "PASS", "acceptance_date": "2026-01-12", "department": pid(mx.dept),
            "location": pid(mx.child), "handover_received_by_name": "Nurse A", **over}


def to_commissioned(c, mx):
    r = act(c, to_installed(c, mx), "commission", **commission_body(mx))
    assert r.status_code == 200, r.content
    return r.json()


# ------------------------------------------------------------------ registration, tags, serials
def test_register_defaults_and_first_history(cl, mx):
    c = cl("SYSTEM_ADMIN")
    eq = mk_eq(c, mx, current_location=pid(mx.child), owning_department=pid(mx.dept))
    assert TAG_RE.match(eq["asset_tag"]) and re.match(r"^BEMS-[A-Z0-9]{12}$", eq["qr_code_value"])
    assert eq["lifecycle_stage"] == "RECEIVED" and eq["operational_state"] is None
    assert eq["name"] == mx.model.model_name
    assert eq["current_location"]["code"] == mx.child.code
    assert eq["effective_pm_interval_days"] == 90
    hist = c.get(f"{BASE}{eq['public_id']}/state-history/").json()["results"]
    assert [(h["to_value"], h["reason"]) for h in hist] == [("RECEIVED", "Registered")]
    mv = c.get(f"{BASE}{eq['public_id']}/movements/").json()["results"]
    assert len(mv) == 1 and mv[0]["reason"] == "Initial placement"


def test_tags_sequential_and_never_reused(cl, mx):
    c = cl("SYSTEM_ADMIN")
    tags = [mk_eq(c, mx)["asset_tag"] for _ in range(3)]
    nums = [int(t[-6:]) for t in tags]
    assert nums == [nums[0], nums[0] + 1, nums[0] + 2]
    last = mk_eq(c, mx)
    assert c.delete(f"{BASE}{last['public_id']}/").status_code == 204
    assert int(mk_eq(c, mx)["asset_tag"][-6:]) > int(last["asset_tag"][-6:])


def test_serial_unique_per_model(cl, mx):
    c = cl("SYSTEM_ADMIN")
    assert register(c, mx, serial_number="SN1").status_code == 201
    r = register(c, mx, serial_number="sn1")
    assert r.status_code == 400 and "serial_number" in json.dumps(r.json())
    r = c.post(BASE, {"equipment_model": pid(mx.model2), "serial_number": "SN1"}, format="json")
    assert r.status_code == 201


# ------------------------------------------------------------------ lifecycle
def test_full_flow_install_commission(cl, mx):
    c = cl("SYSTEM_ADMIN")
    eq = to_installed(c, mx)
    assert eq["lifecycle_stage"] == "INSTALLED" and eq["commissioning"]["installation_engineer_name"] == "Eng"
    eq = act(c, eq, "commission", **commission_body(mx, acceptance_test_result="CONDITIONAL")).json()
    assert eq["lifecycle_stage"] == "COMMISSIONED" and eq["operational_state"] == "IN_SERVICE"
    assert eq["current_location"]["code"] == mx.child.code and eq["owning_department"]["code"] == mx.dept.code
    assert eq["commissioning"]["commissioning_date"] == "2026-01-12"
    reasons = [m["reason"] for m in c.get(f"{BASE}{eq['public_id']}/movements/").json()["results"]]
    assert "Commissioning handover" in reasons
    hist = c.get(f"{BASE}{eq['public_id']}/state-history/").json()["results"]
    assert {(h["change_type"], h["to_value"]) for h in hist} >= {
        ("LIFECYCLE", "RECEIVED"), ("LIFECYCLE", "INSTALLED"), ("LIFECYCLE", "COMMISSIONED"), ("OPERATIONAL", "IN_SERVICE")}


def test_commission_gates(cl, mx):
    c = cl("SYSTEM_ADMIN")
    assert act(c, mk_eq(c, mx), "commission", **commission_body(mx)).status_code == 409
    inst = to_installed(c, mx)
    assert act(c, inst, "commission", **commission_body(mx, acceptance_test_result="FAIL")).status_code == 400
    for missing in ("department", "location", "handover_received_by_name", "acceptance_date"):
        body = commission_body(mx)
        body.pop(missing)
        assert act(c, inst, "commission", **body).status_code == 400, missing
    assert act(c, inst, "commission", **commission_body(mx)).status_code == 200


def test_reject_paths(cl, mx):
    c = cl("SYSTEM_ADMIN")
    assert act(c, mk_eq(c, mx), "reject", reason="Damaged").json()["lifecycle_stage"] == "REJECTED"
    assert act(c, to_installed(c, mx), "reject", reason="Failed").json()["lifecycle_stage"] == "REJECTED"
    assert act(c, mk_eq(c, mx), "reject").status_code == 400
    assert act(c, to_commissioned(c, mx), "reject", reason="x").status_code == 409


def test_db_trigger_blocks_illegal_transitions(cl, mx, world):
    c = cl("SYSTEM_ADMIN")
    obj = Equipment.objects.get(public_id=mk_eq(c, mx)["public_id"])
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Equipment.objects.filter(pk=obj.pk).update(lifecycle_stage="DISPOSED")
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Equipment.objects.create(facility=world.fa, asset_tag="EQ-2026-900001", qr_code_value="BEMS-AAAAAAAAAAAA",
                                     equipment_model=mx.model, name="x", lifecycle_stage="INSTALLED")
    ok = Equipment.objects.create(facility=world.fa, asset_tag="EQ-2026-900002", qr_code_value="BEMS-BBBBBBBBBBBB",
                                  equipment_model=mx.model, name="legacy", lifecycle_stage="COMMISSIONED",
                                  operational_state="IN_SERVICE", is_legacy_entry=True)
    assert ok.pk


def test_delete_only_received_or_rejected(cl, mx):
    c = cl("SYSTEM_ADMIN")
    assert c.delete(f"{BASE}{mk_eq(c, mx)['public_id']}/").status_code == 204
    rej = act(c, mk_eq(c, mx), "reject", reason="x").json()
    assert c.delete(f"{BASE}{rej['public_id']}/").status_code == 204
    assert c.delete(f"{BASE}{to_installed(c, mx)['public_id']}/").status_code == 409
    assert c.delete(f"{BASE}{to_commissioned(c, mx)['public_id']}/").status_code == 409


def test_operational_state(cl, mx):
    c = cl("SYSTEM_ADMIN")
    assert act(c, mk_eq(c, mx), "set-operational-state", operational_state="OUT_OF_SERVICE", reason="x").status_code == 409
    eq = to_commissioned(c, mx)
    assert act(c, eq, "set-operational-state", operational_state="IN_SERVICE", reason="x").status_code == 400
    assert act(c, eq, "set-operational-state", operational_state="UNDER_MAINTENANCE").status_code == 400
    eq = act(c, eq, "set-operational-state", operational_state="UNDER_MAINTENANCE", reason="PM").json()
    assert eq["operational_state"] == "UNDER_MAINTENANCE"
    hist = c.get(f"{BASE}{eq['public_id']}/state-history/").json()["results"]
    assert hist[0]["change_type"] == "OPERATIONAL" and hist[0]["to_value"] == "UNDER_MAINTENANCE"


# ------------------------------------------------------------------ edit / move
def test_patch_rules(cl, mx):
    c = cl("SYSTEM_ADMIN")
    eq = mk_eq(c, mx)
    url = f"{BASE}{eq['public_id']}/"
    r = c.patch(url, {"name": "Renamed", "row_version": eq["row_version"]}, format="json")
    assert r.status_code == 200 and r.json()["name"] == "Renamed"
    for bad in ({"current_location": pid(mx.child)}, {"owning_department": pid(mx.dept)},
                {"lifecycle_stage": "INSTALLED"}, {"operational_state": "IN_SERVICE"},
                {"asset_tag": "EQ-2026-000099"}, {"equipment_model": pid(mx.model2)}):
        assert c.patch(url, {**bad, "row_version": r.json()["row_version"]}, format="json").status_code == 400, bad
    assert c.patch(url, {"name": "X", "row_version": 1}, format="json").status_code == 409
    assert c.patch(url, {"ownership_type": "LEASED", "row_version": r.json()["row_version"]}, format="json").status_code == 400


def test_custom_attributes_validation(cl, mx):
    c = cl("SYSTEM_ADMIN")
    assert register(c, mx, custom_attributes={"Voltage": 230, "Has UPS": True, "Note": "ok"}).status_code == 201
    for bad in ({"1bad": "x"}, {"k": ["list"]}, {"k": "x" * 201}, {f"k{i}": 1 for i in range(31)}):
        assert register(c, mx, custom_attributes=bad).status_code == 400


def test_move_writes_movement(cl, mx):
    c = cl("SYSTEM_ADMIN")
    eq = mk_eq(c, mx)
    r = act(c, eq, "move", location=pid(mx.child), reason="Shifted")
    assert r.status_code == 200 and r.json()["current_location"]["code"] == mx.child.code
    assert act(c, r.json(), "move", location=pid(mx.child), reason="again").status_code == 400
    assert act(c, r.json(), "move", location=pid(mx.other)).status_code == 400
    mv = c.get(f"{BASE}{eq['public_id']}/movements/").json()["results"]
    assert len(mv) == 1 and mv[0]["to_location"]["code"] == mx.child.code and mv[0]["reason"] == "Shifted"
    rej = act(c, mk_eq(c, mx), "reject", reason="x").json()
    assert act(c, rej, "move", location=pid(mx.child), reason="x").status_code == 409


def test_history_tables_immutable(cl, mx):
    c = cl("SYSTEM_ADMIN")
    to_commissioned(c, mx)
    for model in (EquipmentStateHistory, EquipmentMovement):
        row = model.objects.first()
        with pytest.raises(DatabaseError):
            with transaction.atomic():
                model.objects.filter(pk=row.pk).update(reason="tampered")
        with pytest.raises(DatabaseError):
            with transaction.atomic():
                model.objects.filter(pk=row.pk).delete()


# ------------------------------------------------------------------ bulk
def test_bulk_create(cl, mx):
    c = cl("SYSTEM_ADMIN")
    body = {"equipment_model": pid(mx.model), "quantity": 3, "serial_numbers": ["B1", "B2", "B3"],
            "names": ["A", "", "C"], "current_location": pid(mx.child)}
    r = c.post(BASE + "bulk-create/", body, format="json")
    assert r.status_code == 201 and r.json()["count"] == 3
    nums = [int(x["asset_tag"][-6:]) for x in r.json()["results"]]
    assert nums == [nums[0], nums[0] + 1, nums[0] + 2]
    assert [x["name"] for x in r.json()["results"]] == ["A", mx.model.model_name, "C"]
    assert AuditLog.objects.filter(action="BULK_CREATE").count() == 1


@pytest.mark.parametrize("over", [
    {"quantity": 3, "serial_numbers": ["A", "B"]}, {"quantity": 3, "names": ["A"]},
    {"quantity": 2, "serial_numbers": ["A", "a"]}, {"quantity": 201}, {"quantity": 0}, {"quantity": 2, "serial_numbers": ["X", "TAKEN"]},
])
def test_bulk_rejects_and_is_all_or_nothing(cl, mx, over):
    c = cl("SYSTEM_ADMIN")
    assert register(c, mx, serial_number="TAKEN").status_code == 201
    before = Equipment.objects.count()
    r = c.post(BASE + "bulk-create/", {"equipment_model": pid(mx.model), **over}, format="json")
    assert r.status_code == 400
    assert Equipment.objects.count() == before


# ------------------------------------------------------------------ import
HDR = "manufacturer,model_number,serial_number,name,department_code,location_code,ownership_type,operational_state,legacy_asset_id\n"


def csv_file(rows, name="eq.csv"):
    return SimpleUploadedFile(name, (HDR + "".join(rows)).encode(), content_type="text/csv")


def post_import(c, path, f, mapping=None):
    data = {"file": f}
    if mapping:
        data["mapping"] = json.dumps(mapping)
    return c.post(BASE + path, data, format="multipart")


def row(mx, i, **over):
    v = {"mfr": mx.mfr.name, "num": mx.model.model_number, "serial": f"SN{i}", "dept": mx.dept.code,
         "loc": mx.child.code, "own": "OWNED", "state": "IN_SERVICE", "legacy": f"OLD{i}", **over}
    return f"{v['mfr']},{v['num']},{v['serial']},,{v['dept']},{v['loc']},{v['own']},{v['state']},{v['legacy']}\n"


def test_import_template(cl):
    r = cl("SYSTEM_ADMIN").get(BASE + "import/template/")
    assert r.status_code == 200 and r.content.decode().startswith("manufacturer,model_number")


def test_import_dry_run_reports_without_writing(cl, mx):
    c = cl("SYSTEM_ADMIN")
    before = Equipment.objects.count()
    f = csv_file([row(mx, 1), row(mx, 2, mfr="Nobody", num="ZZ"), row(mx, 1, legacy="OLDX"),
                  row(mx, 4, own="WEIRDVALUE"), row(mx, 5, loc="NOPE")])
    r = post_import(c, "import/dry-run/", f)
    assert r.status_code == 200
    out = r.json()
    assert out["total_rows"] == 5 and out["valid_rows"] == 1
    assert {(e["row"], e["field"]) for e in out["errors"]} >= {
        (3, "equipment_model"), (4, "serial_number"), (5, "ownership_type"), (6, "location_code")}
    assert out["missing_models"] == [{"manufacturer": "Nobody", "model_number": "ZZ", "rows": [3]}]
    assert "WEIRDVALUE" not in json.dumps(out["errors"])
    assert Equipment.objects.count() == before
    assert post_import(c, "import/", csv_file([row(mx, 1), row(mx, 2, mfr="Nobody")])).status_code == 400
    assert Equipment.objects.count() == before


def test_import_confirm_creates_legacy_commissioned(cl, mx):
    c = cl("SYSTEM_ADMIN")
    r = post_import(c, "import/", csv_file([row(mx, 1), row(mx, 2, state="OUT_OF_SERVICE")]))
    assert r.status_code == 201 and r.json()["imported"] == 2
    rows = list(Equipment.objects.filter(is_legacy_entry=True).order_by("id"))
    assert [(e.lifecycle_stage, e.operational_state) for e in rows] == [
        ("COMMISSIONED", "IN_SERVICE"), ("COMMISSIONED", "OUT_OF_SERVICE")]
    assert EquipmentCommissioning.objects.filter(equipment__in=rows).count() == 2
    assert EquipmentMovement.objects.filter(equipment__in=rows).count() == 2
    assert EquipmentStateHistory.objects.filter(equipment__in=rows).count() == 4
    assert AuditLog.objects.filter(action="IMPORT").count() == 1
    assert AuditLog.objects.filter(action="CREATE", entity_type="Equipment").count() == 0
    again = post_import(c, "import/", csv_file([row(mx, 1)]))   # clashes with existing serial/legacy id
    assert again.status_code == 400


def test_import_mapping_and_xlsx(cl, mx):
    import openpyxl
    c = cl("SYSTEM_ADMIN")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Maker", "Model No", "Serial", "Room"])
    ws.append([mx.mfr.name, mx.model.model_number, "X1", mx.child.code])
    buf = io.BytesIO()
    wb.save(buf)
    mapping = {"manufacturer": "Maker", "model_number": "Model No", "serial_number": "Serial", "location_code": "Room"}
    f = SimpleUploadedFile("eq.xlsx", buf.getvalue())
    r = post_import(c, "import/dry-run/", f, mapping)
    assert r.status_code == 200 and r.json()["valid_rows"] == 1 and r.json()["headers"][0] == "Maker"
    f.seek(0)
    assert post_import(c, "import/dry-run/", f).json()["missing_columns"]   # no mapping, headers do not match


def test_import_limits_and_bad_content(cl, mx):
    c = cl("SYSTEM_ADMIN")
    big = SimpleUploadedFile("big.csv", b"a,b\n" + b"x" * (5 * 1024 * 1024))
    assert post_import(c, "import/dry-run/", big).status_code == 400
    many = SimpleUploadedFile("many.csv", (HDR + "a,b,c,d,e,f,g,h,i\n" * 5001).encode())
    assert post_import(c, "import/dry-run/", many).status_code == 400
    assert post_import(c, "import/dry-run/", SimpleUploadedFile("x.xlsx", b"not a zip at all")).status_code == 400
    assert post_import(c, "import/dry-run/", SimpleUploadedFile("x.csv", b"a,b\x00c\n1,2,3\n")).status_code == 400
    assert post_import(c, "import/dry-run/", SimpleUploadedFile("x.txt", b"a,b\n")).status_code == 400
    assert c.post(BASE + "import/dry-run/", {}, format="multipart").status_code == 400


# ------------------------------------------------------------------ QR / barcode / labels / scan
def test_qr_barcode_labels_scan(cl, mx, world):
    c = cl("SYSTEM_ADMIN")
    eq = mk_eq(c, mx, legacy_asset_id="OLD-77")
    assert c.get(f"{BASE}{eq['public_id']}/qr/").content.startswith(b"\x89PNG")
    assert c.get(f"{BASE}{eq['public_id']}/barcode/").content.startswith(b"\x89PNG")
    r = c.post(BASE + "labels/", {"equipment": [eq["public_id"]]}, format="json")
    assert r.status_code == 200 and r["Content-Type"] == "application/pdf" and r.content.startswith(b"%PDF")
    for code in (eq["qr_code_value"], eq["asset_tag"], "OLD-77", "old-77"):
        assert c.get(f"{BASE}scan/{code}/").json()["public_id"] == eq["public_id"], code
    assert c.get(f"{BASE}scan/NOPE-1/").status_code == 404
    other = cl("SYSTEM_ADMIN", world.fb)
    assert other.get(f"{BASE}scan/{eq['asset_tag']}/").status_code == 404
    assert other.get(f"{BASE}{eq['public_id']}/qr/").status_code == 404
    assert other.post(BASE + "labels/", {"equipment": [eq["public_id"]]}, format="json").status_code == 404
    unknown = "00000000-0000-4000-8000-000000000000"
    assert c.post(BASE + "labels/", {"equipment": [eq["public_id"], unknown]}, format="json").status_code == 404
    assert c.post(BASE + "labels/", {"equipment": [eq["public_id"]] * 1 + [unknown] * 0, "x": 1}, format="json").status_code == 400


# ------------------------------------------------------------------ isolation / permissions
def test_cross_facility_isolation(cl, mx, world):
    mb = make_masters(world.fb, "B")
    a, b = cl("SYSTEM_ADMIN"), cl("SYSTEM_ADMIN", world.fb)
    eq = mk_eq(a, mx)
    assert b.get(f"{BASE}{eq['public_id']}/").status_code == 404
    assert b.get(BASE).json()["count"] == 0
    assert b.patch(f"{BASE}{eq['public_id']}/", {"name": "x", "row_version": 1}, format="json").status_code == 404
    assert act(b, eq, "reject", reason="x").status_code == 404
    assert a.post(BASE, {"equipment_model": pid(mb.model)}, format="json").status_code == 400
    for field, obj in (("current_location", mb.child), ("owning_department", mb.dept), ("supplier_vendor", mb.mfr),
                       ("funding_source", mb.fund)):
        assert register(a, mx, **{field: pid(obj), "current_location": pid(mx.child)}).status_code == 400, field
    with pytest.raises(IntegrityError):   # composite FK at database level
        with transaction.atomic():
            Equipment.objects.create(facility=world.fa, asset_tag="EQ-2026-900010", qr_code_value="BEMS-CCCCCCCCCCCC",
                                     equipment_model=mb.model, name="x")


@pytest.mark.parametrize("role,view,add,transition,delete", [
    ("SYSTEM_ADMIN", 1, 1, 1, 1), ("BIOMED_ADMIN", 1, 1, 1, 1), ("BIOMED_ENGINEER", 1, 1, 1, 0),
    ("STORE_OFFICER", 1, 1, 0, 0), ("FINANCE", 1, 0, 0, 0), ("DEPARTMENT_USER", 1, 0, 0, 0), ("AUDITOR", 1, 0, 0, 0),
])
def test_permissions_per_role(cl, mx, role, view, add, transition, delete):
    admin = cl("SYSTEM_ADMIN")
    target, doomed = mk_eq(admin, mx), mk_eq(admin, mx)
    c = cl(role)
    assert c.get(BASE).status_code == (200 if view else 403)
    assert register(c, mx).status_code == (201 if add else 403)
    assert act(c, target, "reject", reason="x").status_code == (200 if transition else 403)
    assert c.delete(f"{BASE}{doomed['public_id']}/").status_code == (204 if delete else 403)
    assert c.get(BASE + "import/template/").status_code == (200 if role in ("SYSTEM_ADMIN", "BIOMED_ADMIN") else 403)


# ------------------------------------------------------------------ filters / list
def test_filters_search_summary_inactive(cl, mx):
    c = cl("SYSTEM_ADMIN")
    a = mk_eq(c, mx, serial_number="ALPHA-1", current_location=pid(mx.child), owning_department=pid(mx.dept))
    b = mk_eq(c, mx, serial_number="BETA-2", current_location=pid(mx.other))

    def ids(**params):
        return {x["public_id"] for x in c.get(BASE, params).json()["results"]}
    assert ids(location=pid(mx.root)) == {a["public_id"]}
    assert ids(location=pid(mx.root), location_subtree="false") == set()
    assert ids(location=pid(mx.child)) == {a["public_id"]}
    assert ids(search="ALPHA") == {a["public_id"]}
    assert ids(search=b["asset_tag"]) == {b["public_id"]}
    assert ids(search=mx.model.model_number) == {a["public_id"], b["public_id"]}
    assert ids(search=mx.mfr.name) == {a["public_id"], b["public_id"]}
    assert ids(department=pid(mx.dept)) == {a["public_id"]}
    assert ids(category=pid(mx.cat), lifecycle_stage="RECEIVED,INSTALLED") == {a["public_id"], b["public_id"]}
    assert ids(lifecycle_stage="COMMISSIONED") == set()
    s = c.get(BASE, {"summary": "true"}).json()["results"][0]
    assert set(s) == {"public_id", "asset_tag", "name", "category", "lifecycle_stage", "operational_state",
                      "current_location", "qr_code_value"}
    assert c.delete(f"{BASE}{a['public_id']}/").status_code == 204
    assert a["public_id"] not in ids()
    assert a["public_id"] in ids(include_inactive="true")
    assert a["public_id"] not in {x["public_id"] for x in cl("BIOMED_ENGINEER").get(BASE, {"include_inactive": "true"}).json()["results"]}


def test_list_query_count_is_constant(cl, mx):
    c = cl("SYSTEM_ADMIN")
    r = c.post(BASE + "bulk-create/", {"equipment_model": pid(mx.model), "quantity": 30,
                                       "current_location": pid(mx.child), "supplier_vendor": pid(mx.mfr)}, format="json")
    assert r.status_code == 201

    def n(size):
        with CaptureQueriesContext(connection) as q:
            assert c.get(BASE, {"page_size": size}).status_code == 200
        return len(q)
    assert n(5) == n(25)


# ------------------------------------------------------------------ gates / audit
def test_master_delete_gates_extended(cl, mx):
    c = cl("SYSTEM_ADMIN")
    mk_eq(c, mx, current_location=pid(mx.child), owning_department=pid(mx.dept),
          funding_source=pid(mx.fund), supplier_vendor=pid(mx.mfr))
    for path, obj in (("locations", mx.child), ("departments", mx.dept), ("vendors", mx.mfr),
                      ("funding-sources", mx.fund), ("equipment-models", mx.model)):
        assert c.delete(f"/api/v1/{path}/{pid(obj)}/").status_code == 409, path


def test_audit_actions_written(cl, mx):
    c = cl("SYSTEM_ADMIN")
    eq = to_commissioned(c, mx)
    eq = act(c, eq, "set-operational-state", operational_state="OUT_OF_SERVICE", reason="x").json()
    act(c, eq, "move", location=pid(mx.other), reason="x")
    c.delete(f"{BASE}{mk_eq(c, mx)['public_id']}/")
    c.post(BASE + "bulk-create/", {"equipment_model": pid(mx.model), "quantity": 2}, format="json")
    post_import(c, "import/", csv_file([row(mx, 9)]))
    actions = set(AuditLog.objects.values_list("action", flat=True))
    assert {"CREATE", "SOFT_DELETE", "BULK_CREATE", "IMPORT", "LIFECYCLE_CHANGE",
            "OPERATIONAL_STATE_CHANGE", "MOVEMENT"} <= actions
