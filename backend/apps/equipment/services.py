"""Equipment business rules. Views stay thin; every function runs in transaction.atomic(),
locks the equipment row, validates the stage, then writes history and the audit event.

move_equipment is the ONLY writer of current_location / owning_department.
set_operational_state is the manual entry point (IN_SERVICE / OUT_OF_SERVICE holds only).
_write_operational_state is the ONLY writer of operational_state after commissioning; it is called only by
apps.maintenance.holds.recompute_operational_state, which derives the state from open holds.
"""
import secrets
from datetime import datetime
from zoneinfo import ZoneInfo

from django.db import IntegrityError, connection, transaction
from rest_framework.exceptions import NotFound, ValidationError

from apps.core import audit
from apps.core.errors import StaleVersion
from apps.masters.models import Department, Location

from .errors import Conflict
from .models import Equipment, EquipmentCommissioning, EquipmentMovement, EquipmentStateHistory

ENTITY = "Equipment"
IST = ZoneInfo("Asia/Kolkata")
OPERATIONAL_STATES = ("IN_SERVICE", "UNDER_MAINTENANCE", "OUT_OF_SERVICE")
MANUAL_OPERATIONAL_STATES = ("IN_SERVICE", "OUT_OF_SERVICE")
MOVABLE_STAGES = ("RECEIVED", "INSTALLED", "COMMISSIONED")

_ASSET_TAG_SQL = """
INSERT INTO asset_tag_counters (facility_id, year, last_value) VALUES (%s, %s, %s)
ON CONFLICT (facility_id, year) DO UPDATE SET last_value = asset_tag_counters.last_value + EXCLUDED.last_value
RETURNING last_value
"""


# ---------------------------------------------------------------- helpers
def current_year():
    return datetime.now(IST).year


def generate_asset_tags(facility, count):
    """Reserve the next `count` numbers for the current IST year. Call inside the caller's transaction."""
    year = current_year()
    try:
        with transaction.atomic(), connection.cursor() as cur:
            cur.execute(_ASSET_TAG_SQL, [facility.id, year, count])
            end = cur.fetchone()[0]
    except IntegrityError:
        raise Conflict("The asset tag sequence for this year is exhausted.")
    return [f"EQ-{year}-{n:06d}" for n in range(end - count + 1, end + 1)]


def new_qr_code_value():
    return "BEMS-" + secrets.token_hex(6).upper()   # 12 uppercase hex chars, no meaning


def _constraint(exc):
    return getattr(getattr(exc.__cause__, "diag", None), "constraint_name", None)


def _raise_for_constraint(name):
    if name == "ux_equipment_serial_active":
        raise ValidationError({"serial_number": ["This serial number already exists for this model."]})
    if name == "ux_equipment_legacy_asset_id_active":
        raise ValidationError({"legacy_asset_id": ["This legacy asset ID is already in use."]})
    raise Conflict()


def _insert_equipment(facility, asset_tag, uid, fields):
    for _ in range(5):
        try:
            with transaction.atomic():
                return Equipment.objects.create(
                    facility=facility, asset_tag=asset_tag, qr_code_value=new_qr_code_value(),
                    lifecycle_stage="RECEIVED", created_by=uid, updated_by=uid, **fields)
        except IntegrityError as exc:
            name = _constraint(exc)
            if name == "uq_equipment_qr_code":
                continue   # random collision: retry with a new value
            _raise_for_constraint(name)
    raise Conflict()


def _lock(equipment, expected_version=None):
    try:
        eq = Equipment.objects.select_for_update().get(
            pk=equipment.pk, facility_id=equipment.facility_id, is_active=True)
    except Equipment.DoesNotExist:
        raise NotFound()
    if expected_version is not None and eq.row_version != expected_version:
        raise StaleVersion(current_row_version=eq.row_version)
    return eq


def _require_stage(eq, allowed, verb):
    if eq.lifecycle_stage not in allowed:
        raise Conflict(f"Cannot {verb} equipment that is {eq.lifecycle_stage.lower()}.")


def _same_facility(eq, obj, label):
    if obj is not None and (obj.facility_id != eq.facility_id or not obj.is_active):
        raise ValidationError({label: ["Unknown reference."]})


def _pub(model, pk):
    if pk is None:
        return None
    pid = model.objects.filter(pk=pk).values_list("public_id", flat=True).first()
    return str(pid) if pid else None


def _history(eq, change_type, from_value, to_value, reason, uid):
    EquipmentStateHistory.objects.create(
        facility_id=eq.facility_id, equipment_id=eq.pk, change_type=change_type,
        from_value=from_value, to_value=to_value, reason=reason, created_by=uid)


def _audit(request, action, eq, previous, new):
    audit.record(
        request=request, action=action, facility_id=eq.facility_id, entity_type=ENTITY,
        entity_public_id=eq.public_id, previous=previous, new=new, changed_fields=audit.diff(previous, new))


def _change_stage(request, eq, new_stage, **extra):
    eq.lifecycle_stage = new_stage
    for key, value in extra.items():
        setattr(eq, key, value)
    eq.updated_by = request.user.id
    eq.save(update_fields=["lifecycle_stage", "updated_by", *extra])   # one UPDATE: satisfies the state-pair CHECK


def _move(request, eq, to_location, to_department, reason, *, allow_noop=False, audit_it=True):
    """Core of move_equipment; `eq` must already be locked."""
    uid = request.user.id
    if eq.lifecycle_stage not in MOVABLE_STAGES:
        raise Conflict(f"Cannot move equipment that is {eq.lifecycle_stage.lower()}.")
    _same_facility(eq, to_location, "location")
    _same_facility(eq, to_department, "department")
    new_dept_id = to_department.pk if to_department is not None else eq.owning_department_id
    if not allow_noop and to_location.pk == eq.current_location_id and new_dept_id == eq.owning_department_id:
        raise ValidationError({"location": ["Equipment is already at this location and department."]})
    previous = {"current_location": _pub(Location, eq.current_location_id),
                "owning_department": _pub(Department, eq.owning_department_id)} if audit_it else None
    movement = EquipmentMovement.objects.create(
        facility_id=eq.facility_id, equipment_id=eq.pk, from_location_id=eq.current_location_id,
        to_location=to_location, from_department_id=eq.owning_department_id, to_department_id=new_dept_id,
        reason=reason, created_by=uid)
    eq.current_location = to_location
    eq.owning_department_id = new_dept_id
    eq.updated_by = uid
    eq.save(update_fields=["current_location", "owning_department", "updated_by"])
    if audit_it:
        new = {"current_location": str(to_location.public_id),
               "owning_department": _pub(Department, new_dept_id), "reason": reason}
        _audit(request, "MOVEMENT", eq, previous, new)
    return movement


# ---------------------------------------------------------------- services
def register(*, request, facility, fields, asset_tag=None, audit_create=True):
    """Create one unit at RECEIVED (+ first history row, + initial movement when a location is given)."""
    uid = request.user.id
    fields = dict(fields)
    location = fields.pop("current_location", None)
    department = fields.pop("owning_department", None)
    model = fields["equipment_model"]
    if model.facility_id != facility.id or not model.is_active:
        raise ValidationError({"equipment_model": ["Unknown reference."]})
    if not fields.get("name"):
        fields["name"] = model.model_name
    if asset_tag is None:
        asset_tag = generate_asset_tags(facility, 1)[0]
    with transaction.atomic():
        eq = _insert_equipment(facility, asset_tag, uid, fields)
        _history(eq, "LIFECYCLE", None, "RECEIVED", "Registered", uid)
        if location is not None:
            _move(request, eq, location, department, "Initial placement", allow_noop=True, audit_it=False)
        if audit_create:
            snap = audit.snapshot(eq)
            audit.record(request=request, action="CREATE", facility_id=facility.id, entity_type=ENTITY,
                         entity_public_id=eq.public_id, previous=None, new=snap,
                         changed_fields=audit.diff(None, snap))
    return eq


def bulk_register(*, request, facility, fields, quantity, serial_numbers=None, names=None):
    """All-or-nothing: one counter update, one BULK_CREATE audit event."""
    with transaction.atomic():
        tags = generate_asset_tags(facility, quantity)
        created = []
        for i, tag in enumerate(tags):
            unit = dict(fields)
            if serial_numbers:
                unit["serial_number"] = serial_numbers[i]
            if names and names[i]:
                unit["name"] = names[i]
            created.append(register(request=request, facility=facility, fields=unit,
                                    asset_tag=tag, audit_create=False))
        audit.record(request=request, action="BULK_CREATE", facility_id=facility.id, entity_type=ENTITY,
                     new={"count": quantity, "equipment_model": str(fields["equipment_model"].public_id),
                          "asset_tags": tags})
    return created


def install(*, request, equipment, expected_version=None, installation_date, installation_engineer_name=None,
            installation_vendor=None, installation_notes=None):
    uid = request.user.id
    with transaction.atomic():
        eq = _lock(equipment, expected_version)
        _require_stage(eq, ("RECEIVED",), "install")
        _same_facility(eq, installation_vendor, "installation_vendor")
        EquipmentCommissioning.objects.create(
            facility_id=eq.facility_id, equipment=eq, installation_date=installation_date,
            installation_engineer_name=installation_engineer_name, installation_vendor=installation_vendor,
            installation_notes=installation_notes, created_by=uid, updated_by=uid)
        _change_stage(request, eq, "INSTALLED")
        reason = "Installation recorded"
        _history(eq, "LIFECYCLE", "RECEIVED", "INSTALLED", reason, uid)
        _audit(request, "LIFECYCLE_CHANGE", eq, {"lifecycle_stage": "RECEIVED"},
               {"lifecycle_stage": "INSTALLED", "reason": reason})
    return eq


def commission(*, request, equipment, expected_version=None, acceptance_test_result, acceptance_date,
               department, location, handover_received_by_name, acceptance_test_notes=None,
               training_conducted=False, training_notes=None):
    if acceptance_test_result == "FAIL":
        raise ValidationError({"acceptance_test_result": [
            "Acceptance failed. Reject the equipment, or fix the issue and retest before commissioning."]})
    if acceptance_test_result not in ("PASS", "CONDITIONAL"):
        raise ValidationError({"acceptance_test_result": ["Invalid result."]})
    uid = request.user.id
    with transaction.atomic():
        eq = _lock(equipment, expected_version)
        _require_stage(eq, ("INSTALLED",), "commission")
        _same_facility(eq, department, "department")
        _same_facility(eq, location, "location")
        rec = EquipmentCommissioning.objects.select_for_update().filter(equipment_id=eq.pk, is_active=True).first()
        if rec is None:
            raise Conflict("The installation record is missing.")
        rec.acceptance_test_result = acceptance_test_result
        rec.acceptance_test_notes = acceptance_test_notes
        rec.acceptance_date = acceptance_date
        rec.accepted_by = uid
        rec.handed_over_department = department
        rec.handover_received_by_name = handover_received_by_name
        rec.training_conducted = training_conducted
        rec.training_notes = training_notes
        rec.commissioning_date = acceptance_date
        rec.updated_by = uid
        rec.save()
        _move(request, eq, location, department, "Commissioning handover", allow_noop=True)
        _change_stage(request, eq, "COMMISSIONED", operational_state="IN_SERVICE")
        reason = f"Acceptance test {acceptance_test_result}"
        _history(eq, "LIFECYCLE", "INSTALLED", "COMMISSIONED", reason, uid)
        _history(eq, "OPERATIONAL", None, "IN_SERVICE", "Commissioned", uid)
        _audit(request, "LIFECYCLE_CHANGE", eq,
               {"lifecycle_stage": "INSTALLED", "operational_state": None},
               {"lifecycle_stage": "COMMISSIONED", "operational_state": "IN_SERVICE",
                "acceptance_test_result": acceptance_test_result, "reason": reason})
    return eq


def reject(*, request, equipment, reason, expected_version=None):
    uid = request.user.id
    with transaction.atomic():
        eq = _lock(equipment, expected_version)
        _require_stage(eq, ("RECEIVED", "INSTALLED"), "reject")
        old = eq.lifecycle_stage
        _change_stage(request, eq, "REJECTED")
        _history(eq, "LIFECYCLE", old, "REJECTED", reason, uid)
        _audit(request, "LIFECYCLE_CHANGE", eq, {"lifecycle_stage": old},
               {"lifecycle_stage": "REJECTED", "reason": reason})
    return eq


def _write_operational_state(*, request, eq, new_state, reason):
    """PRIVATE writer of operational_state (equipment already locked and COMMISSIONED).
    Called only by apps.maintenance.holds.recompute_operational_state."""
    uid = request.user.id
    old = eq.operational_state
    eq.operational_state = new_state
    eq.updated_by = uid
    eq.save(update_fields=["operational_state", "updated_by"])
    _history(eq, "OPERATIONAL", old, new_state, reason, uid)
    _audit(request, "OPERATIONAL_STATE_CHANGE", eq, {"operational_state": old},
           {"operational_state": new_state, "reason": reason})


def set_operational_state(*, request, equipment, operational_state, reason, expected_version=None):
    """Manual, hold-based. OUT_OF_SERVICE places a MANUAL hold. IN_SERVICE releases MANUAL holds only and is
    rejected with 409 (listing the blocking holds) while any other hold is open. UNDER_MAINTENANCE cannot be set."""
    if operational_state not in MANUAL_OPERATIONAL_STATES:
        raise ValidationError({"operational_state": [
            "Only In service or Out of service can be set manually. Under maintenance is set by work orders."]})
    from apps.maintenance import holds   # lazy: apps.maintenance imports this module

    with transaction.atomic():
        eq = _lock(equipment, expected_version)
        _require_stage(eq, ("COMMISSIONED",), "change the operational state of")
        if operational_state == "OUT_OF_SERVICE":
            if holds.open_holds(eq.facility_id, eq.pk).filter(source_type="MANUAL", hold_type="OUT_OF_SERVICE").exists():
                raise ValidationError({"operational_state": ["Equipment is already in this state."]})
            holds.place_hold(request=request, equipment=eq, hold_type="OUT_OF_SERVICE", source_type="MANUAL",
                             work_order=None, reason=reason)
        else:
            holds.release_manual_holds(request=request, equipment=eq, reason=reason)
    return eq


def move_equipment(*, request, equipment, to_location, to_department=None, reason, expected_version=None):
    """The ONLY writer of current_location and owning_department."""
    with transaction.atomic():
        eq = _lock(equipment, expected_version)
        _move(request, eq, to_location, to_department, reason)
    return eq
