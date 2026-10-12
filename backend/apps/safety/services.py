"""Safety and vigilance business rules (Phase 8). Views stay thin; every service runs in transaction.atomic(),
locks the main row with select_for_update, validates, writes history rows and the audit event.

Individual verification scans are NOT written to audit_log (volume); item rows carry scanned_by / scanned_at.
"""
import logging
import re

from django.db import connection, transaction
from django.db.models import Count, Q
from django.db.models.functions import Lower
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from apps.core import audit
from apps.core.errors import Conflict, StaleVersion
from apps.equipment import services as eq_services
from apps.equipment.models import Equipment
from apps.foundation.models import User
from apps.maintenance import holds
from apps.maintenance import services as wo_services
from apps.maintenance.models import EquipmentHold
from apps.masters.models import Location

from . import allocation
from .models import (
    EquipmentIncident, IncidentEvent, PhysicalVerification, PhysicalVerificationItem, RecallAffectedUnit,
    RecallNotice, RecallNoticeModel,
)

log = logging.getLogger("bems.safety")

INCIDENT = "EquipmentIncident"
NOTICE = "RecallNotice"
UNIT = "RecallAffectedUnit"
VERIFICATION = "PhysicalVerification"
ITEM = "PhysicalVerificationItem"

EXCLUDED_STAGES = ("DISPOSED", "REJECTED")
INCIDENT_TRANSITIONS = {
    ("REPORTED", "UNDER_INVESTIGATION"), ("REPORTED", "CLOSED"),
    ("UNDER_INVESTIGATION", "ACTION_TAKEN"), ("UNDER_INVESTIGATION", "CLOSED"),
    ("ACTION_TAKEN", "CLOSED"),
}
INCIDENT_EDITABLE = (
    "incident_type", "severity", "patient_affected", "staff_affected", "department", "location",
    "root_cause", "corrective_action", "preventive_action", "investigation_notes", "reportable_to_regulator",
)
WO_PRIORITY_BY_SEVERITY = {"SEVERE": "CRITICAL", "DEATH": "CRITICAL", "MODERATE": "HIGH"}
WO_PRIORITY_BY_URGENCY = {"CRITICAL": "CRITICAL", "HIGH": "HIGH"}
CODE_RE = re.compile(r"^[A-Za-z0-9_-]{1,100}$")


# ------------------------------------------------------------------ helpers
def _h(value):
    return str(value).lower().replace("_", " ")


def _lock(model, obj, expected_version=None):
    row = model.objects.select_for_update().filter(pk=obj.pk, facility_id=obj.facility_id, is_active=True).first()
    if row is None:
        raise NotFound()
    if expected_version is not None and row.row_version != expected_version:
        raise StaleVersion(current_row_version=row.row_version)
    return row


def _audit(request, action, entity_type, obj, previous=None, new=None):
    audit.record(request=request, action=action, facility_id=obj.facility_id, entity_type=entity_type,
                 entity_public_id=obj.public_id, previous=previous, new=new,
                 changed_fields=audit.diff(previous, new))


def audit_refused(request, action, entity_type, obj, exc):
    """A request refused by a business gate: written in autocommit, OUTSIDE the failed atomic block."""
    audit.record(request=request, action=action, facility_id=obj.facility_id, entity_type=entity_type,
                 entity_public_id=obj.public_id, new={"refused": str(exc.detail)})


def usernames(ids):
    ids = {i for i in ids if i is not None}
    return dict(User.objects.filter(id__in=ids).values_list("id", "username")) if ids else {}


def _text(value, field, required=True):
    value = (value or "").strip()
    if required and not value:
        raise ValidationError({field: ["This field is required."]})
    return value or None


def _fresh(obj):
    obj.refresh_from_db(fields=["updated_at", "row_version"])
    return obj


# ================================================================== incidents
def _incident_event(inc, event_type, uid, from_status=None, to_status=None, note=None):
    IncidentEvent.objects.create(facility_id=inc.facility_id, incident=inc, event_type=event_type,
                                 from_status=from_status, to_status=to_status, note=note, created_by=uid)


def open_incident_hold(inc):
    return EquipmentHold.objects.filter(
        facility_id=inc.facility_id, incident_id=inc.pk, is_active=True, released_at__isnull=True).first()


def _check_incident_transition(inc, to):
    if (inc.status, to) not in INCIDENT_TRANSITIONS:
        raise Conflict(f"An incident that is {_h(inc.status)} cannot be changed to {_h(to)}.")


def _change_incident_status(request, inc, to, **fields):
    _check_incident_transition(inc, to)
    uid, old = request.user.id, inc.status
    inc.status = to
    inc.updated_by = uid
    for key, value in fields.items():
        setattr(inc, key, value)
    inc.save(update_fields=["status", "updated_by", *fields])
    _incident_event(inc, "STATUS_CHANGED", uid, old, to)
    _audit(request, "INCIDENT_STATUS", INCIDENT, inc, {"status": old}, {"status": to})


def report_incident(*, request, facility, data):
    """Returns (incident, quarantine) where quarantine = {requested, placed, message}."""
    uid = request.user.id
    data = dict(data)
    quarantine = bool(data.pop("quarantine", False))
    equipment = data.pop("equipment")
    reported_by = data.pop("reported_by_name", None) or request.user.username
    with transaction.atomic():
        eq = eq_services._lock(equipment)
        if eq.lifecycle_stage in EXCLUDED_STAGES:
            raise Conflict("Incidents cannot be reported for disposed or rejected equipment.")
        if data["occurred_at"] > timezone.now():
            raise ValidationError({"occurred_at": ["Cannot be in the future."]})
        year, n = wo_services.next_number(facility, "INC")
        inc = EquipmentIncident.objects.create(
            facility=facility, incident_number=f"INC-{year}-{n:06d}", equipment=eq, status="REPORTED",
            reported_by_name=reported_by, created_by=uid, updated_by=uid, **data)
        _incident_event(inc, "CREATED", uid, None, "REPORTED")
        result = {"requested": quarantine, "placed": False, "message": None}
        if quarantine:
            if eq.lifecycle_stage == "COMMISSIONED":
                holds.place_hold(request=request, equipment=eq, hold_type="OUT_OF_SERVICE", source_type="INCIDENT",
                                 incident=inc, reason=f"Incident {inc.incident_number}: equipment quarantined")
                _incident_event(inc, "QUARANTINE_PLACED", uid, note="Equipment quarantined (out of service)")
                result["placed"] = True
            else:
                result["message"] = "The equipment is not commissioned, so no quarantine hold could be placed."
        snap = audit.snapshot(inc)
        _audit(request, "INCIDENT_REPORTED", INCIDENT, inc, None, {**snap, "quarantine_placed": result["placed"]})
        _fresh(inc)
    return inc, result


def update_incident(*, request, incident, expected_version, fields):
    uid = request.user.id
    with transaction.atomic():
        inc = _lock(EquipmentIncident, incident, expected_version)
        if inc.status == "CLOSED":
            raise Conflict("A closed incident cannot be changed.")
        before = audit.snapshot(inc)
        changed = []
        for key, value in fields.items():
            if key not in INCIDENT_EDITABLE:
                continue
            if key in ("department", "location"):
                current, new = getattr(inc, f"{key}_id"), (value.pk if value is not None else None)
            else:
                current, new = getattr(inc, key), value
            if current != new:
                setattr(inc, key, value)
                changed.append(key)
        if not changed:
            return inc
        inc.updated_by = uid
        inc.save(update_fields=[*changed, "updated_by"])
        _fresh(inc)
        _incident_event(inc, "INVESTIGATION_UPDATED", uid, note="Changed: " + ", ".join(changed))
        _audit(request, "UPDATE", INCIDENT, inc, before, audit.snapshot(inc))
    return inc


def start_investigation(*, request, incident, expected_version=None):
    with transaction.atomic():
        inc = _lock(EquipmentIncident, incident, expected_version)
        _change_incident_status(request, inc, "UNDER_INVESTIGATION", investigated_by=request.user.id)
    return inc


def record_actions(*, request, incident, corrective_action=None, expected_version=None):
    with transaction.atomic():
        inc = _lock(EquipmentIncident, incident, expected_version)
        _check_incident_transition(inc, "ACTION_TAKEN")
        extra = {}
        if corrective_action is not None:
            extra["corrective_action"] = corrective_action.strip()
        final = extra.get("corrective_action", inc.corrective_action)
        if not (final or "").strip():
            raise ValidationError({"corrective_action": ["Required before recording actions taken."]})
        _change_incident_status(request, inc, "ACTION_TAKEN", **extra)
    return inc


def close_incident(*, request, incident, closure_notes, expected_version=None):
    with transaction.atomic():
        inc = _lock(EquipmentIncident, incident, expected_version)
        _check_incident_transition(inc, "CLOSED")
        notes = _text(closure_notes, "closure_notes")
        if open_incident_hold(inc) is not None:
            raise Conflict("The equipment is still quarantined for this incident. Release the quarantine before closing.")
        if inc.reportable_to_regulator and not (inc.regulator_report_reference or "").strip():
            raise Conflict("This incident is reportable to the regulator. Record the regulator report reference "
                           "before closing.")
        _change_incident_status(request, inc, "CLOSED", closure_notes=notes, closed_at=timezone.now(),
                                closed_by=request.user.id)
    return inc


def mark_regulator_reported(*, request, incident, reference, reported_on, expected_version=None):
    """Records that a report was made. The system never submits anything to a regulator."""
    uid = request.user.id
    with transaction.atomic():
        inc = _lock(EquipmentIncident, incident, expected_version)
        if inc.status == "CLOSED":
            raise Conflict("A closed incident cannot be changed.")
        reference = _text(reference, "reference")
        if reported_on > wo_services.today_for(request.bems.facility):
            raise ValidationError({"reported_on": ["Cannot be in the future."]})
        before = {"reportable_to_regulator": inc.reportable_to_regulator,
                  "regulator_report_reference": inc.regulator_report_reference,
                  "regulator_reported_on": inc.regulator_reported_on}
        inc.reportable_to_regulator = True
        inc.regulator_report_reference = reference
        inc.regulator_reported_on = reported_on
        inc.updated_by = uid
        inc.save(update_fields=["reportable_to_regulator", "regulator_report_reference", "regulator_reported_on",
                                "updated_by"])
        _incident_event(inc, "REGULATOR_REPORTED", uid, note=f"Reference {reference}, reported on {reported_on}")
        _audit(request, "INCIDENT_REGULATOR_REPORTED", INCIDENT, inc, before,
               {"reportable_to_regulator": True, "regulator_report_reference": reference,
                "regulator_reported_on": reported_on})
    return inc


def release_quarantine(*, request, incident, reason, expected_version=None):
    with transaction.atomic():
        inc = _lock(EquipmentIncident, incident, expected_version)
        reason = _text(reason, "reason")
        hold = open_incident_hold(inc)
        if hold is None:
            raise Conflict("There is no open quarantine hold for this incident.")
        holds.release_hold(request=request, hold=hold, reason=f"Incident {inc.incident_number}: {reason}")
        _incident_event(inc, "QUARANTINE_RELEASED", request.user.id, note=reason)
    return inc


def create_incident_work_order(*, request, incident, expected_version=None):
    uid = request.user.id
    with transaction.atomic():
        inc = _lock(EquipmentIncident, incident, expected_version)
        if inc.status == "CLOSED":
            raise Conflict("A closed incident cannot be changed.")
        if inc.work_order_id is not None:
            raise Conflict("A work order is already linked to this incident.")
        eq = eq_services._lock(Equipment(pk=inc.equipment_id, facility_id=inc.facility_id))
        if eq.lifecycle_stage != "COMMISSIONED":
            raise Conflict("A work order can only be created for commissioned equipment.")
        priority = WO_PRIORITY_BY_SEVERITY.get(inc.severity, "MEDIUM")
        wo = wo_services.create_work_order(
            request=request, facility=request.bems.facility, work_order_type="CORRECTIVE", equipment=eq,
            priority=priority,
            problem_description=f"Incident {inc.incident_number} ({_h(inc.incident_type)}, {_h(inc.severity)}): "
                                f"{inc.description}")
        inc.work_order = wo
        inc.updated_by = uid
        inc.save(update_fields=["work_order", "updated_by"])
        _incident_event(inc, "WORK_ORDER_LINKED", uid, note=f"Work order {wo.wo_number}")
        _audit(request, "UPDATE", INCIDENT, inc, {"work_order": None}, {"work_order": wo.wo_number})
    return inc


def add_incident_note(*, request, incident, text):
    with transaction.atomic():
        inc = _lock(EquipmentIncident, incident)
        _incident_event(inc, "NOTE", request.user.id, inc.status, inc.status, _text(text, "note"))
    return inc


# ================================================================== recalls
def _check_notice_dates(issued, received):
    if issued and received and received < issued:
        raise ValidationError({"received_date": ["Cannot be before the issued date."]})


def _models_snapshot(notice):
    return sorted(str(p) for p in RecallNoticeModel.objects.filter(recall_notice_id=notice.pk)
                  .values_list("equipment_model__public_id", flat=True))


def create_notice(*, request, facility, data, models):
    uid = request.user.id
    data = dict(data)
    if not models:
        raise ValidationError({"models": ["Select at least one equipment model."]})
    _check_notice_dates(data.get("issued_date"), data.get("received_date"))
    if data["action_type"] == "STOP_USE":
        data["stop_use"] = True
    with transaction.atomic():
        ref = data.get("reference_number")
        if ref and RecallNotice.objects.filter(facility_id=facility.id, is_active=True,
                                               reference_number__iexact=ref).exists():
            raise ValidationError({"reference_number": ["This reference number already exists."]})
        year, n = wo_services.next_number(facility, "RCL")
        notice = RecallNotice.objects.create(
            facility=facility, notice_number=f"RCL-{year}-{n:06d}", status="OPEN", created_by=uid, updated_by=uid,
            **data)
        RecallNoticeModel.objects.bulk_create([
            RecallNoticeModel(facility_id=facility.id, recall_notice=notice, equipment_model=m, created_by=uid)
            for m in {m.pk: m for m in models}.values()])
        snap = audit.snapshot(notice)
        _audit(request, "CREATE", NOTICE, notice, None, {**snap, "models": _models_snapshot(notice)})
        _fresh(notice)
    return notice


def update_notice(*, request, notice, expected_version, fields, models=None):
    uid = request.user.id
    fields = dict(fields)
    with transaction.atomic():
        n = _lock(RecallNotice, notice, expected_version)
        if n.status != "OPEN":
            raise Conflict("Only an open notice can be changed.")
        before = {**audit.snapshot(n), "models": _models_snapshot(n)}
        merged = {k: fields.get(k, getattr(n, k)) for k in ("action_type", "issued_date", "received_date")}
        _check_notice_dates(merged["issued_date"], merged["received_date"])
        if merged["action_type"] == "STOP_USE":
            fields["stop_use"] = True
        has_units = RecallAffectedUnit.objects.filter(recall_notice_id=n.pk, is_active=True).exists()
        if has_units:
            if "stop_use" in fields and fields["stop_use"] != n.stop_use:
                raise Conflict("Stop use cannot be changed once affected units exist.")
            if models is not None and {m.pk for m in models} != set(
                    RecallNoticeModel.objects.filter(recall_notice_id=n.pk).values_list("equipment_model_id", flat=True)):
                raise Conflict("The model list cannot be changed once affected units exist.")
        ref = fields.get("reference_number")
        if ref and RecallNotice.objects.filter(facility_id=n.facility_id, is_active=True,
                                               reference_number__iexact=ref).exclude(pk=n.pk).exists():
            raise ValidationError({"reference_number": ["This reference number already exists."]})
        for key, value in fields.items():
            setattr(n, key, value)
        n.updated_by = uid
        n.save(update_fields=[*fields, "updated_by"])
        if models is not None and not has_units:
            if not models:
                raise ValidationError({"models": ["Select at least one equipment model."]})
            RecallNoticeModel.objects.filter(recall_notice_id=n.pk).delete()
            RecallNoticeModel.objects.bulk_create([
                RecallNoticeModel(facility_id=n.facility_id, recall_notice=n, equipment_model=m, created_by=uid)
                for m in {m.pk: m for m in models}.values()])
        _fresh(n)
        _audit(request, "UPDATE", NOTICE, n, before, {**audit.snapshot(n), "models": _models_snapshot(n)})
    return n


def _active_allocations(facility_id, equipment_ids):
    return allocation.allocated_equipment_ids(facility_id, equipment_ids)


def _add_unit_row(request, notice, eq, identified_by):
    uid = request.user.id
    unit = RecallAffectedUnit.objects.create(
        facility_id=notice.facility_id, recall_notice=notice, equipment=eq, status="PENDING",
        identified_by=identified_by, created_by=uid, updated_by=uid)
    held = False
    if notice.stop_use and eq.lifecycle_stage == "COMMISSIONED":
        holds.place_hold(request=request, equipment=eq, hold_type="OUT_OF_SERVICE", source_type="RECALL",
                         recall_unit=unit, reason=f"Recall {notice.notice_number}: {notice.title}")
        held = True
    return unit, held


def _unit_warnings(notice, created_equipment):
    warnings = []
    allocated = _active_allocations(notice.facility_id, [e.pk for e in created_equipment])
    for e in created_equipment:
        if e.pk in allocated:
            warnings.append(f"{e.asset_tag} is currently allocated. The allocation was not released automatically.")
    if notice.stop_use:
        n_not = sum(1 for e in created_equipment if e.lifecycle_stage != "COMMISSIONED")
        if n_not:
            warnings.append(f"{n_not} unit(s) are not commissioned, so no stop-use hold was placed on them.")
    return warnings


def identify_units(*, request, notice, mode, serial_numbers=None):
    if mode not in ("ALL_OF_MODELS", "SERIAL_LIST"):
        raise ValidationError({"mode": ["Invalid mode."]})
    with transaction.atomic():
        n = _lock(RecallNotice, notice)
        if n.status != "OPEN":
            raise Conflict("Units can only be identified while the notice is open.")
        model_ids = list(RecallNoticeModel.objects.filter(recall_notice_id=n.pk).values_list("equipment_model_id", flat=True))
        qs = Equipment.objects.filter(facility_id=n.facility_id, is_active=True, equipment_model_id__in=model_ids) \
            .exclude(lifecycle_stage__in=EXCLUDED_STAGES)
        unmatched = []
        if mode == "SERIAL_LIST":
            wanted = {}
            for s in serial_numbers or []:
                s = (s or "").strip()
                if s:
                    wanted.setdefault(s.lower(), s)
            if not wanted:
                raise ValidationError({"serial_numbers": ["Give at least one serial number."]})
            found = list(qs.annotate(serial_lc=Lower("serial_number")).filter(serial_lc__in=list(wanted)).order_by("id"))
            matched = {e.serial_number.lower() for e in found}
            unmatched = [orig for lc, orig in wanted.items() if lc not in matched]
        else:
            found = list(qs.order_by("id"))
        existing = set(RecallAffectedUnit.objects.filter(recall_notice_id=n.pk, is_active=True)
                       .values_list("equipment_id", flat=True))
        created, holds_placed = [], 0
        for eq in found:
            if eq.pk in existing:
                continue
            _, held = _add_unit_row(request, n, eq, mode)
            created.append(eq)
            holds_placed += 1 if held else 0
        result = {"created": len(created), "skipped": len(found) - len(created), "unmatched_serials": unmatched,
                  "holds_placed": holds_placed, "warnings": _unit_warnings(n, created)}
        _audit(request, "RECALL_UNITS_IDENTIFIED", NOTICE, n, None, {"mode": mode, **{
            k: v for k, v in result.items() if k != "warnings"}})
    return result


def add_unit(*, request, notice, equipment):
    with transaction.atomic():
        n = _lock(RecallNotice, notice)
        if n.status != "OPEN":
            raise Conflict("Units can only be added while the notice is open.")
        eq = eq_services._lock(equipment)
        if eq.lifecycle_stage in EXCLUDED_STAGES:
            raise Conflict("Disposed or rejected equipment cannot be added.")
        if RecallAffectedUnit.objects.filter(recall_notice_id=n.pk, equipment_id=eq.pk, is_active=True).exists():
            raise Conflict("This equipment is already listed on the notice.")
        unit, held = _add_unit_row(request, n, eq, "MANUAL")
        warnings = _unit_warnings(n, [eq])
        _audit(request, "RECALL_UNITS_IDENTIFIED", NOTICE, n, None,
               {"mode": "MANUAL", "created": 1, "skipped": 0, "unmatched_serials": [], "holds_placed": 1 if held else 0})
        _fresh(unit)
    return unit, {"hold_placed": held, "warnings": warnings}


def resolve_unit(*, request, unit, status, notes=None, vendor_reference=None):
    if status not in ("ACTION_COMPLETED", "NOT_APPLICABLE"):
        raise ValidationError({"status": ["Invalid status."]})
    uid = request.user.id
    with transaction.atomic():
        n = _lock(RecallNotice, RecallNotice(pk=unit.recall_notice_id, facility_id=unit.facility_id))
        if n.status != "OPEN":
            raise Conflict("Units can only be resolved while the notice is open.")
        u = _lock(RecallAffectedUnit, unit)
        if u.status != "PENDING":
            raise Conflict("This unit is already resolved. A resolved unit is final.")
        u.status = status
        u.resolved_at = timezone.now()
        u.resolved_by = uid
        u.resolution_notes = (notes or "").strip() or None
        u.vendor_reference = (vendor_reference or "").strip() or None
        u.updated_by = uid
        u.save(update_fields=["status", "resolved_at", "resolved_by", "resolution_notes", "vendor_reference",
                              "updated_by"])
        released = 0
        for hold in EquipmentHold.objects.filter(facility_id=u.facility_id, recall_unit_id=u.pk, is_active=True,
                                                 released_at__isnull=True):
            holds.release_hold(request=request, hold=hold,
                               reason=f"Recall {n.notice_number}: unit resolved ({_h(status)})")
            released += 1
        _fresh(u)
        _audit(request, "RECALL_UNIT_RESOLVED", UNIT, u, {"status": "PENDING"},
               {"status": status, "notice": n.notice_number, "equipment": str(
                   Equipment.objects.filter(pk=u.equipment_id).values_list("public_id", flat=True).first()),
                "hold_released": bool(released)})
    return u


def create_unit_work_order(*, request, unit):
    uid = request.user.id
    with transaction.atomic():
        n = _lock(RecallNotice, RecallNotice(pk=unit.recall_notice_id, facility_id=unit.facility_id))
        if n.status != "OPEN":
            raise Conflict("Work orders can only be created while the notice is open.")
        u = _lock(RecallAffectedUnit, unit)
        if u.work_order_id is not None:
            raise Conflict("A work order is already linked to this unit.")
        if u.status != "PENDING":
            raise Conflict("This unit is already resolved.")
        eq = eq_services._lock(Equipment(pk=u.equipment_id, facility_id=u.facility_id))
        if eq.lifecycle_stage != "COMMISSIONED":
            raise Conflict("A work order can only be created for commissioned equipment.")
        wo = wo_services.create_work_order(
            request=request, facility=request.bems.facility, work_order_type="CORRECTIVE", equipment=eq,
            priority=WO_PRIORITY_BY_URGENCY.get(n.urgency, "MEDIUM"),
            problem_description=f"Recall {n.notice_number}: {n.title}. Required action: "
                                f"{n.required_action or _h(n.action_type)}")
        u.work_order = wo
        u.updated_by = uid
        u.save(update_fields=["work_order", "updated_by"])
        _fresh(u)
        _audit(request, "UPDATE", UNIT, u, {"work_order": None}, {"work_order": wo.wo_number})
    return u


def close_notice(*, request, notice, close_notes, expected_version=None):
    uid = request.user.id
    with transaction.atomic():
        n = _lock(RecallNotice, notice, expected_version)
        if n.status != "OPEN":
            raise Conflict("Only an open notice can be closed.")
        notes = _text(close_notes, "close_notes")
        pending = RecallAffectedUnit.objects.filter(recall_notice_id=n.pk, is_active=True, status="PENDING").count()
        if pending:
            exc = Conflict(f"Cannot close: {pending} affected unit(s) are still pending.")
            exc.extra = {"pending": pending}
            raise exc
        n.status, n.closed_at, n.closed_by, n.close_notes, n.updated_by = "CLOSED", timezone.now(), uid, notes, uid
        n.save(update_fields=["status", "closed_at", "closed_by", "close_notes", "updated_by"])
        _fresh(n)
        _audit(request, "RECALL_CLOSED", NOTICE, n, {"status": "OPEN"}, {"status": "CLOSED", "close_notes": notes})
    return n


def cancel_notice(*, request, notice, reason, expected_version=None):
    uid = request.user.id
    with transaction.atomic():
        n = _lock(RecallNotice, notice, expected_version)
        if n.status != "OPEN":
            raise Conflict("Only an open notice can be cancelled.")
        reason = _text(reason, "reason")
        unit_ids = list(RecallAffectedUnit.objects.filter(recall_notice_id=n.pk, is_active=True).values_list("pk", flat=True))
        released = 0
        for hold in EquipmentHold.objects.filter(facility_id=n.facility_id, recall_unit_id__in=unit_ids, is_active=True,
                                                 released_at__isnull=True):
            holds.release_hold(request=request, hold=hold, reason=f"Recall {n.notice_number} cancelled: {reason}")
            released += 1
        n.status, n.cancel_reason, n.updated_by = "CANCELLED", reason, uid
        n.save(update_fields=["status", "cancel_reason", "updated_by"])
        _fresh(n)
        _audit(request, "RECALL_CANCELLED", NOTICE, n, {"status": "OPEN"},
               {"status": "CANCELLED", "cancel_reason": reason, "holds_released": released})
    return n


def notice_counts(notice_ids):
    """{notice_pk: {units, pending, completed, not_applicable}} in one query."""
    rows = RecallAffectedUnit.objects.filter(recall_notice_id__in=list(notice_ids), is_active=True) \
        .values("recall_notice_id").annotate(
            units=Count("pk"), pending=Count("pk", filter=Q(status="PENDING")),
            completed=Count("pk", filter=Q(status="ACTION_COMPLETED")),
            not_applicable=Count("pk", filter=Q(status="NOT_APPLICABLE")))
    out = {r["recall_notice_id"]: {k: r[k] for k in ("units", "pending", "completed", "not_applicable")} for r in rows}
    return {pk: out.get(pk, {"units": 0, "pending": 0, "completed": 0, "not_applicable": 0}) for pk in notice_ids}


# ================================================================== physical verification
def _scope_check(scope_type, department, location):
    if scope_type == "FACILITY" and (department is not None or location is not None):
        raise ValidationError({"scope_type": ["A facility-wide verification has no department or location."]})
    if scope_type == "DEPARTMENT" and (department is None or location is not None):
        raise ValidationError({"department": ["Choose a department (and no location) for this scope."]})
    if scope_type == "LOCATION" and (location is None or department is not None):
        raise ValidationError({"location": ["Choose a location (and no department) for this scope."]})


def create_verification(*, request, facility, data):
    uid = request.user.id
    data = dict(data)
    _scope_check(data["scope_type"], data.get("department"), data.get("location"))
    with transaction.atomic():
        year, n = wo_services.next_number(facility, "VER")
        v = PhysicalVerification.objects.create(
            facility=facility, verification_number=f"VER-{year}-{n:06d}", status="PLANNED",
            created_by=uid, updated_by=uid, **data)
        _audit(request, "CREATE", VERIFICATION, v, None, audit.snapshot(v))
        _fresh(v)
    return v


def update_verification(*, request, verification, expected_version, fields):
    with transaction.atomic():
        v = _lock(PhysicalVerification, verification, expected_version)
        if v.status != "PLANNED":
            raise Conflict("Only a planned verification can be changed.")
        before = audit.snapshot(v)
        merged = {
            "scope_type": fields.get("scope_type", v.scope_type),
            "department": fields["department"] if "department" in fields else v.department,
            "location": fields["location"] if "location" in fields else v.location,
        }
        if "scope_type" in fields and "department" not in fields and merged["scope_type"] != "DEPARTMENT":
            merged["department"] = None
        if "scope_type" in fields and "location" not in fields and merged["scope_type"] != "LOCATION":
            merged["location"] = None
        _scope_check(merged["scope_type"], merged["department"], merged["location"])
        for key, value in {**fields, **merged}.items():
            setattr(v, key, value)
        v.updated_by = request.user.id
        v.save(update_fields=[*{**fields, **merged}, "updated_by"])
        _fresh(v)
        _audit(request, "UPDATE", VERIFICATION, v, before, audit.snapshot(v))
    return v


def _subtree_ids(facility_id, root_id):
    with connection.cursor() as cur:
        cur.execute("select * from location_subtree_ids(%s, %s)", [facility_id, root_id])
        return [r[0] for r in cur.fetchall()]


def start_verification(*, request, verification):
    uid = request.user.id
    with transaction.atomic():
        v = _lock(PhysicalVerification, verification)
        if v.status != "PLANNED":
            raise Conflict("Only a planned verification can be started.")
        qs = Equipment.objects.filter(facility_id=v.facility_id, is_active=True).exclude(lifecycle_stage__in=EXCLUDED_STAGES)
        if v.scope_type == "DEPARTMENT":
            qs = qs.filter(owning_department_id=v.department_id)
        elif v.scope_type == "LOCATION":
            qs = qs.filter(current_location_id__in=_subtree_ids(v.facility_id, v.location_id))
        rows = list(qs.order_by("id").values_list("pk", "current_location_id", "owning_department_id"))
        PhysicalVerificationItem.objects.bulk_create([
            PhysicalVerificationItem(
                facility_id=v.facility_id, verification=v, equipment_id=pk, expected_location_id=loc,
                expected_department_id=dept, result="PENDING", created_by=uid, updated_by=uid)
            for pk, loc, dept in rows], batch_size=1000)
        v.status, v.started_at, v.updated_by = "IN_PROGRESS", timezone.now(), uid
        v.save(update_fields=["status", "started_at", "updated_by"])
        _fresh(v)
        _audit(request, "VERIFICATION_STARTED", VERIFICATION, v, {"status": "PLANNED"},
               {"status": "IN_PROGRESS", "expected_items": len(rows)})
    return v


def verification_counters(verification_pk):
    agg = PhysicalVerificationItem.objects.filter(verification_id=verification_pk, is_active=True).aggregate(
        expected=Count("pk", filter=~Q(result="UNEXPECTED")), pending=Count("pk", filter=Q(result="PENDING")),
        found=Count("pk", filter=Q(result="FOUND")), elsewhere=Count("pk", filter=Q(result="FOUND_ELSEWHERE")),
        missing=Count("pk", filter=Q(result="MISSING")), unexpected=Count("pk", filter=Q(result="UNEXPECTED")))
    return agg


def scan(*, request, verification, code, found_location=None):
    """Returns (item, equipment, counters). Individual scans are not audited."""
    code = (code or "").strip()
    if not CODE_RE.match(code):
        raise NotFound()
    uid = request.user.id
    with transaction.atomic():
        v = _lock(PhysicalVerification, verification)
        if v.status != "IN_PROGRESS":
            raise Conflict("Scanning is only possible while the verification is in progress.")
        eq = eq_services.find_by_code(Equipment.objects.filter(facility_id=v.facility_id, is_active=True), code)
        if eq is None:
            raise NotFound()
        loc_id = found_location.pk if found_location is not None else (v.location_id if v.scope_type == "LOCATION" else None)
        if loc_id is None:
            raise ValidationError({"found_location": ["Choose the location where the equipment was found."]})
        now = timezone.now()
        item = PhysicalVerificationItem.objects.select_for_update().filter(verification_id=v.pk, equipment_id=eq.pk).first()
        if item is None:
            item = PhysicalVerificationItem.objects.create(
                facility_id=v.facility_id, verification=v, equipment=eq, expected_location_id=eq.current_location_id,
                expected_department_id=eq.owning_department_id, result="UNEXPECTED", found_location_id=loc_id,
                scanned_at=now, scanned_by=uid, created_by=uid, updated_by=uid)
        else:
            if item.result != "UNEXPECTED":
                item.result = "FOUND" if item.expected_location_id == loc_id else "FOUND_ELSEWHERE"
            item.found_location_id, item.scanned_at, item.scanned_by, item.updated_by = loc_id, now, uid, uid
            item.save(update_fields=["result", "found_location", "scanned_at", "scanned_by", "updated_by"])
        item.refresh_from_db(fields=["row_version", "updated_at"])
        counters = verification_counters(v.pk)
    return item, eq, counters


def update_item(*, request, verification, item, expected_version, tag_status=None, notes=None, notes_given=False):
    with transaction.atomic():
        v = _lock(PhysicalVerification, verification)
        if v.status != "IN_PROGRESS":
            raise Conflict("Items can only be changed while the verification is in progress.")
        i = _lock(PhysicalVerificationItem, item, expected_version)
        if tag_status is not None:
            i.tag_status = tag_status
        if notes_given:
            i.notes = (notes or "").strip() or None
        i.updated_by = request.user.id
        i.save(update_fields=["tag_status", "notes", "updated_by"])
        _fresh(i)
    return i


def complete_verification(*, request, verification):
    uid = request.user.id
    with transaction.atomic():
        v = _lock(PhysicalVerification, verification)
        if v.status != "IN_PROGRESS":
            raise Conflict("Only a verification in progress can be completed.")
        PhysicalVerificationItem.objects.filter(verification_id=v.pk, result="PENDING").update(
            result="MISSING", updated_by=uid)
        c = verification_counters(v.pk)
        v.status, v.completed_at, v.updated_by = "COMPLETED", timezone.now(), uid
        v.expected_count, v.found_count, v.elsewhere_count = c["expected"], c["found"], c["elsewhere"]
        v.missing_count, v.unexpected_count = c["missing"], c["unexpected"]
        v.save(update_fields=["status", "completed_at", "updated_by", "expected_count", "found_count",
                              "elsewhere_count", "missing_count", "unexpected_count"])
        _fresh(v)
        _audit(request, "VERIFICATION_COMPLETED", VERIFICATION, v, {"status": "IN_PROGRESS"}, {"status": "COMPLETED", **c})
    return v


def cancel_verification(*, request, verification, reason):
    with transaction.atomic():
        v = _lock(PhysicalVerification, verification)
        if v.status not in ("PLANNED", "IN_PROGRESS"):
            raise Conflict("Only a planned or in-progress verification can be cancelled.")
        reason = _text(reason, "reason")
        old = v.status
        v.status, v.cancel_reason, v.updated_by = "CANCELLED", reason, request.user.id
        v.save(update_fields=["status", "cancel_reason", "updated_by"])
        _fresh(v)
        _audit(request, "VERIFICATION_CANCELLED", VERIFICATION, v, {"status": old},
               {"status": "CANCELLED", "cancel_reason": reason})
    return v


def resolve_item(*, request, verification, item, resolution, notes=None):
    if resolution not in ("LOCATION_UPDATED", "CONFIRMED_MISSING", "FOUND_LATER", "IGNORED"):
        raise ValidationError({"resolution": ["Invalid resolution."]})
    uid = request.user.id
    with transaction.atomic():
        v = _lock(PhysicalVerification, verification)
        if v.status != "COMPLETED":
            raise Conflict("Items can only be resolved after the verification is completed.")
        i = _lock(PhysicalVerificationItem, item)
        if i.result not in ("FOUND_ELSEWHERE", "MISSING", "UNEXPECTED"):
            raise Conflict("Only items that are elsewhere, missing or unexpected can be resolved.")
        if i.resolution != "NONE":
            raise Conflict("This item is already resolved.")
        moved = False
        if resolution == "LOCATION_UPDATED":
            if i.found_location_id is None:
                raise Conflict("No found location was recorded for this item.")
            eq = eq_services._lock(Equipment(pk=i.equipment_id, facility_id=i.facility_id))
            if allocation.allocated_equipment_ids(i.facility_id, [eq.pk]):
                raise Conflict("This equipment is allocated. Release the allocation before updating its location.")
            if eq.current_location_id != i.found_location_id:
                loc = Location.objects.filter(pk=i.found_location_id, facility_id=i.facility_id, is_active=True).first()
                if loc is None:
                    raise Conflict("The found location is no longer active.")
                eq_services.move_equipment(request=request, equipment=eq, to_location=loc,
                                           reason=f"Physical verification {v.verification_number}")
                moved = True
        i.resolution, i.resolution_notes = resolution, (notes or "").strip() or None
        i.resolved_by, i.resolved_at, i.updated_by = uid, timezone.now(), uid
        i.save(update_fields=["resolution", "resolution_notes", "resolved_by", "resolved_at", "updated_by"])
        _fresh(i)
        _audit(request, "VERIFICATION_ITEM_RESOLVED", ITEM, i, {"resolution": "NONE"},
               {"resolution": resolution, "result": i.result, "verification": v.verification_number,
                "equipment": str(Equipment.objects.filter(pk=i.equipment_id).values_list("public_id", flat=True).first()),
                "equipment_moved": moved})
    return i


# ================================================================== read helpers
def open_incident_count(equipment):
    return EquipmentIncident.objects.filter(facility_id=equipment.facility_id, equipment_id=equipment.pk,
                                            is_active=True).exclude(status="CLOSED").count()


def pending_recall_count(equipment):
    return RecallAffectedUnit.objects.filter(
        facility_id=equipment.facility_id, equipment_id=equipment.pk, is_active=True, status="PENDING",
        recall_notice__status="OPEN").count()
