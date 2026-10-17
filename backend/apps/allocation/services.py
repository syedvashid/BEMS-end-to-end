"""Allocation, reservation, usage, transfer services. Views stay thin; every writer runs in transaction.atomic().

Lock order everywhere: equipment row first, then the allocation / transfer / reservation row (no deadlocks).
"""
import os
from datetime import timedelta
from decimal import Decimal

from django.db import IntegrityError, connection, transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from apps.core import audit
from apps.core.errors import Conflict
from apps.equipment.models import Equipment
from apps.foundation.models import Facility, UserFacilityRole
from apps.masters.models import Department, Location

from .errors import AllocationBlocked, DetailedConflict
from .models import (
    EquipmentAllocation, EquipmentReservation, EquipmentTransferRequest, EquipmentUsageLog, UserDepartment,
)

GATE_CODES = ("CALIBRATION_OVERDUE", "CALIBRATION_FAILURE_UNRESOLVED")
ACTIVE_RES = ("CONFIRMED", "FULFILLED")
CONDITIONS = ("GOOD", "NEEDS_CLEANING", "DAMAGED")
ZERO = Decimal("0")


# ------------------------------------------------------------------ small helpers
def _item(code, message, **extra):
    return {"code": code, "message": message, **extra}


def _ref(o, *fields):
    return None if o is None else {"public_id": str(o.public_id), **{f: getattr(o, f) for f in fields}}


def _pg(exc):
    cause = getattr(exc, "__cause__", None)
    diag = getattr(cause, "diag", None)
    return (getattr(cause, "sqlstate", None) or getattr(cause, "pgcode", None),
            getattr(diag, "constraint_name", None))


def _lock_equipment(fid, pk):
    eq = Equipment.objects.select_for_update().filter(pk=pk, facility_id=fid, is_active=True).first()
    if eq is None:
        raise NotFound()
    return eq


def _deny_scope(request, reason):
    """403 with an ACCESS_DENIED row written in autocommit (callers invoke this outside atomic blocks)."""
    audit.record(request=request, action="ACCESS_DENIED", new={"reason": reason})
    raise PermissionDenied()


def user_department_ids(user_id, facility_id):
    return set(UserDepartment.objects.filter(user_id=user_id, facility_id=facility_id)
               .values_list("department_id", flat=True))


def location_subtree_ids(facility_id, root_id):
    """Ids of a location and all its active descendants (parameterised recursive CTE)."""
    sql = """
        with recursive t as (
            select id from locations where id = %s and facility_id = %s and is_active
            union all
            select l.id from locations l join t on l.parent_location_id = t.id
             where l.facility_id = %s and l.is_active)
        select id from t"""
    with connection.cursor() as cur:
        cur.execute(sql, [root_id, facility_id, facility_id])
        return [r[0] for r in cur.fetchall()]


def allocation_summary(a):
    return {"public_id": str(a.public_id), "department": _ref(a.department, "code", "name") if a.department_id else None,
            "location": _ref(a.location, "code", "name") if a.location_id else None,
            "source_module": a.source_module, "patient_reference": a.patient_reference,
            "assigned_at": a.assigned_at, "expected_release_at": a.expected_release_at}


def reservation_summary(r):
    return {"public_id": str(r.public_id), "status": r.status,
            "equipment": _ref(r.equipment, "asset_tag", "name"), "department": _ref(r.department, "code", "name"),
            "start_at": r.start_at, "end_at": r.end_at, "purpose": r.purpose}


def usage_summary_item(u):
    return {"public_id": str(u.public_id), "started_at": u.started_at, "ended_at": u.ended_at,
            "operator_name": u.operator_name, "procedure_text": u.procedure_text}


def _active_allocation(fid, equipment_id):
    return EquipmentAllocation.objects.filter(
        facility_id=fid, equipment_id=equipment_id, released_at__isnull=True, is_active=True
    ).select_related("department", "location").first()


def _reservation_qs(fid, equipment_ids, start, end, statuses=ACTIVE_RES):
    qs = EquipmentReservation.objects.filter(facility_id=fid, is_active=True, status__in=statuses)
    if equipment_ids is not None:
        qs = qs.filter(equipment_id__in=equipment_ids)
    if end is None:      # open-ended: a booking blocks only when it covers `start`
        return qs.filter(start_at__lte=start, end_at__gt=start)
    return qs.filter(start_at__lt=end, end_at__gt=start)


def _upcoming_qs(fid, equipment_ids, start):
    qs = EquipmentReservation.objects.filter(
        facility_id=fid, is_active=True, status="CONFIRMED", start_at__gt=start, start_at__lte=start + timedelta(hours=24))
    return qs if equipment_ids is None else qs.filter(equipment_id__in=equipment_ids)


W_CAL_DUE = lambda d: _item("CALIBRATION_DUE_SOON", "Calibration is due soon.", next_due_date=d)           # noqa: E731
W_PM = lambda: _item("PM_DUE_IN_WINDOW", "A preventive maintenance order falls in this period.")            # noqa: E731
W_UPCOMING = lambda: _item("UPCOMING_RESERVATION", "A reservation starts within 24 hours.")                 # noqa: E731


def _pm_ids(fid, equipment_ids, w_start, w_end):
    from apps.maintenance.models import WorkOrder
    from apps.maintenance.services import DONE_STATUSES
    qs = WorkOrder.objects.filter(facility_id=fid, work_order_type="PREVENTIVE",
                                  due_date__gte=w_start, due_date__lte=w_end).exclude(status__in=DONE_STATUSES)
    if equipment_ids is not None:
        qs = qs.filter(equipment_id__in=equipment_ids)
    return set(qs.values_list("equipment_id", flat=True))


# ------------------------------------------------------------------ availability
def availability(equipment, start=None, end=None, today=None):
    from apps.compliance.services import calibration_status
    from apps.maintenance.services import today_for
    now = timezone.now()
    start = start or now
    fid = equipment.facility_id
    facility = Facility.objects.get(pk=fid)
    today = today or today_for(facility, now)
    blocking, warnings = [], []

    if equipment.lifecycle_stage != "COMMISSIONED":
        blocking.append(_item("NOT_COMMISSIONED", "Equipment is not commissioned."))
    elif equipment.operational_state != "IN_SERVICE":
        blocking.append(_item("NOT_IN_SERVICE", "Equipment is not in service.",
                              operational_state=equipment.operational_state))
    act = _active_allocation(fid, equipment.pk)
    if act is not None:
        blocking.append(_item("ACTIVE_ALLOCATION", "Equipment is already allocated.", allocation=allocation_summary(act)))
    clash = _reservation_qs(fid, [equipment.pk], start, end).select_related("equipment", "department").order_by("start_at").first()
    if clash is not None:
        blocking.append(_item("RESERVATION_CONFLICT", "Equipment is reserved for this period.",
                              reservation=reservation_summary(clash)))
    cal = calibration_status(equipment, today)
    if cal["status"] == "OVERDUE":
        blocking.append(_item("CALIBRATION_OVERDUE", "Calibration is overdue.", next_due_date=cal["next_due_date"]))
    if cal["has_unresolved_failure"]:
        blocking.append(_item("CALIBRATION_FAILURE_UNRESOLVED", "The last calibration failed and is unresolved."))
    if cal["status"] == "DUE_SOON":
        warnings.append(W_CAL_DUE(cal["next_due_date"]))
    w_start = today_for(facility, start)
    w_end = today_for(facility, end) if end else w_start
    if equipment.pk in _pm_ids(fid, [equipment.pk], w_start, w_end):
        warnings.append(W_PM())
    if end is None and _upcoming_qs(fid, [equipment.pk], start).exists():
        warnings.append(W_UPCOMING())
    return {"available": not blocking, "blocking": blocking, "warnings": warnings}


def available_equipment(facility, *, category=None, location=None, department=None, start=None, end=None, today=None):
    """Set-based twin of availability(): constant number of queries. Returns [{equipment, warnings, calibration}]."""
    from apps.compliance.services import bulk_calibration_status
    from apps.maintenance.services import today_for
    now = timezone.now()
    start = start or now
    fid = facility.id
    today = today or today_for(facility, now)
    qs = Equipment.objects.filter(facility_id=fid, is_active=True, lifecycle_stage="COMMISSIONED",
                                  operational_state="IN_SERVICE").select_related(
        "equipment_model__category", "current_location", "owning_department")
    if category is not None:
        qs = qs.filter(equipment_model__category_id=category.pk)
    if department is not None:
        qs = qs.filter(owning_department_id=department.pk)
    if location is not None:
        qs = qs.filter(current_location_id__in=location_subtree_ids(fid, location.pk))
    qs = qs.exclude(pk__in=EquipmentAllocation.objects.filter(
        facility_id=fid, released_at__isnull=True, is_active=True).values("equipment_id"))
    qs = qs.exclude(pk__in=_reservation_qs(fid, None, start, end).values("equipment_id"))
    rows = list(qs.order_by("asset_tag", "id"))
    ids = [e.pk for e in rows]
    cal = bulk_calibration_status(ids, today)
    w_start = today_for(facility, start)
    w_end = today_for(facility, end) if end else w_start
    pm = _pm_ids(fid, ids, w_start, w_end) if ids else set()
    upcoming = set(_upcoming_qs(fid, ids, start).values_list("equipment_id", flat=True)) if (ids and end is None) else set()
    out = []
    for e in rows:
        c = cal[e.pk]
        if c["status"] == "OVERDUE" or c["has_unresolved_failure"]:
            continue
        w = []
        if c["status"] == "DUE_SOON":
            w.append(W_CAL_DUE(c["next_due_date"]))
        if e.pk in pm:
            w.append(W_PM())
        if e.pk in upcoming:
            w.append(W_UPCOMING())
        out.append({"equipment": e, "warnings": w, "calibration": c})
    return out


def bedside_equipment(facility, location, category=None, today=None):
    from apps.compliance.services import bulk_calibration_status
    from apps.maintenance.services import today_for
    fid = facility.id
    today = today or today_for(facility)
    qs = Equipment.objects.filter(
        facility_id=fid, is_active=True, lifecycle_stage="COMMISSIONED",
        current_location_id__in=location_subtree_ids(fid, location.pk)
    ).select_related("equipment_model__category", "current_location")
    if category is not None:
        qs = qs.filter(equipment_model__category_id=category.pk)
    rows = list(qs.order_by("current_location__name", "asset_tag", "id"))
    ids = [e.pk for e in rows]
    cal = bulk_calibration_status(ids, today)
    acts = {a.equipment_id: a for a in EquipmentAllocation.objects.filter(
        facility_id=fid, equipment_id__in=ids, released_at__isnull=True, is_active=True
    ).select_related("department", "location")} if ids else {}
    return [{"equipment": e, "calibration": cal[e.pk], "allocation": acts.get(e.pk)} for e in rows]


# ------------------------------------------------------------------ allocations
def _alloc_audit(a):
    """Snapshot for the audit trail. Patient and encounter references are deliberately not copied."""
    return {"equipment": str(a.equipment.public_id) if a.equipment_id else None, "department_id": a.department_id,
            "location_id": a.location_id, "source_module": a.source_module,
            "assigned_at": a.assigned_at.isoformat() if a.assigned_at else None,
            "released_at": a.released_at.isoformat() if a.released_at else None,
            "condition_on_release": a.condition_on_release, "gate_override": a.gate_override}


def allocate(*, request, equipment, data, override=False, override_reason=None):
    from apps.equipment import services as eq_services
    ctx, uid = request.bems, request.user.id
    fid = ctx.facility.id
    dept, loc = data.get("department"), data.get("location")
    if dept is None and loc is None:
        raise ValidationError({"department": ["Give a department, a location, or both."]})
    now = timezone.now()
    expected = data.get("expected_release_at")
    if expected is not None and expected <= now:
        raise ValidationError({"expected_release_at": ["Must be in the future."]})
    reason = (override_reason or "").strip() or None
    can_override = ctx.has("allocation.override")
    try:
        with transaction.atomic():
            eq = _lock_equipment(fid, equipment.pk)
            av = availability(eq, now, expected)
            hard = [b for b in av["blocking"] if b["code"] not in GATE_CODES]
            gate = [b for b in av["blocking"] if b["code"] in GATE_CODES]
            if hard or (gate and not (override and can_override)):
                raise AllocationBlocked(
                    "Equipment cannot be allocated." if hard else "Calibration gate: allocation is blocked.",
                    {"blocking": av["blocking"], "warnings": av["warnings"],
                     "can_override": bool(gate and not hard and can_override)},
                    None if hard else "calibration_gate")
            if gate and not reason:
                raise ValidationError({"override_reason": ["A reason is required to override the calibration gate."]})
            used = bool(gate)
            prev = eq.current_location_id if (loc is not None and loc.pk != eq.current_location_id) else None
            try:
                with transaction.atomic():
                    alloc = EquipmentAllocation.objects.create(
                        facility_id=fid, equipment_id=eq.pk, department=dept, location=loc,
                        source_module=data.get("source_module") or "MANUAL",
                        patient_reference=data.get("patient_reference"),
                        encounter_reference=data.get("encounter_reference"),
                        practitioner_name=data.get("practitioner_name"), purpose=data.get("purpose"),
                        assigned_at=now, expected_release_at=expected, previous_location_id=prev,
                        gate_override=used, override_reason=reason if used else None,
                        created_by=uid, updated_by=uid)
            except IntegrityError as exc:
                if _pg(exc)[1] == "ux_equipment_allocations_equipment_active":
                    raise AllocationBlocked("Equipment is already allocated.", {"blocking": [
                        _item("ACTIVE_ALLOCATION", "Equipment is already allocated.")], "warnings": [],
                        "can_override": False})
                raise
            if loc is not None and loc.pk != eq.current_location_id:
                eq_services.move_equipment(request=request, equipment=eq, expected_version=eq.row_version,
                                           to_location=loc, to_department=None, reason="Allocated")
            alloc.equipment = eq
            audit.record(request=request, action="ASSIGN", facility_id=fid, entity_type="EquipmentAllocation",
                         entity_public_id=alloc.public_id, new=_alloc_audit(alloc))
            if used:
                audit.record(request=request, action="CALIBRATION_GATE_OVERRIDDEN", facility_id=fid,
                             entity_type="EquipmentAllocation", entity_public_id=alloc.public_id,
                             new={"codes": [g["code"] for g in gate], "reason": reason})
    except AllocationBlocked as exc:     # rolled back: the refusal is audited in autocommit, outside the atomic block
        audit.record(request=request, action="ASSIGNMENT_BLOCKED", facility_id=fid, entity_type="Equipment",
                     entity_public_id=equipment.public_id,
                     new={"codes": [b["code"] for b in exc.extra.get("blocking", [])],
                          "override_attempted": bool(override)})
        raise
    return alloc, av["warnings"]


def release(*, request, allocation, condition, notes=None, return_to_previous_location=True):
    from apps.equipment import services as eq_services
    fid, uid = request.bems.facility.id, request.user.id
    if condition not in CONDITIONS:
        raise ValidationError({"condition_on_release": ["Choose Good, Needs cleaning or Damaged."]})
    with transaction.atomic():
        eq = _lock_equipment(fid, allocation.equipment_id)
        a = EquipmentAllocation.objects.select_for_update().filter(
            pk=allocation.pk, facility_id=fid, is_active=True).first()
        if a is None:
            raise NotFound()
        if a.released_at is not None:
            raise Conflict("This allocation has already been released.")
        a.released_at, a.released_by = timezone.now(), uid
        a.condition_on_release, a.release_notes, a.updated_by = condition, notes, uid
        a.save(update_fields=["released_at", "released_by", "condition_on_release", "release_notes", "updated_by"])
        moved_back = False
        if (return_to_previous_location and a.previous_location_id and a.location_id
                and eq.current_location_id == a.location_id and a.previous_location_id != a.location_id):
            prev = Location.objects.filter(pk=a.previous_location_id, facility_id=fid, is_active=True).first()
            if prev is not None:
                eq_services.move_equipment(request=request, equipment=eq, expected_version=eq.row_version,
                                           to_location=prev, to_department=None, reason="Released")
                moved_back = True
        a.equipment = eq
        audit.record(request=request, action="RELEASE", facility_id=fid, entity_type="EquipmentAllocation",
                     entity_public_id=a.public_id, new=_alloc_audit(a))
    from apps.billing.services import safe_charges_for_allocation   # Phase 11: never raises, never blocks the release
    charges = safe_charges_for_allocation(a, request=request)
    return {"allocation": a, "suggest_breakdown": condition == "DAMAGED", "moved_back": moved_back,
            "charges": charges}


# ------------------------------------------------------------------ reservations
def _res_audit(r):
    return {"equipment_id": r.equipment_id, "department_id": r.department_id, "status": r.status,
            "start_at": r.start_at.isoformat(), "end_at": r.end_at.isoformat()}


def reserve(*, request, equipment, data):
    from apps.compliance.services import calibration_status
    from apps.maintenance.services import today_for
    ctx, uid = request.bems, request.user.id
    fid = ctx.facility.id
    dept, start, end = data["department"], data["start_at"], data["end_at"]
    purpose = (data.get("purpose") or "").strip()
    now = timezone.now()
    if not purpose:
        raise ValidationError({"purpose": ["This field may not be blank."]})
    if start < now - timedelta(minutes=5):
        raise ValidationError({"start_at": ["Start time cannot be in the past."]})
    if end <= start:
        raise ValidationError({"end_at": ["End must be after the start."]})
    if end - start > timedelta(days=7):
        raise ValidationError({"end_at": ["A reservation cannot be longer than 7 days."]})
    if not ctx.has("reservation.manage") and dept.pk not in user_department_ids(uid, fid):
        _deny_scope(request, "reservation_department_scope")
    with transaction.atomic():
        eq = Equipment.objects.filter(pk=equipment.pk, facility_id=fid, is_active=True).first()
        if eq is None:
            raise NotFound()
        if eq.lifecycle_stage != "COMMISSIONED":
            raise Conflict("Only commissioned equipment can be reserved.")
        try:
            with transaction.atomic():
                r = EquipmentReservation.objects.create(
                    facility_id=fid, equipment_id=eq.pk, department=dept, start_at=start, end_at=end,
                    purpose=purpose, procedure_reference=data.get("procedure_reference"),
                    status="CONFIRMED", created_by=uid, updated_by=uid)
        except IntegrityError as exc:
            if _pg(exc)[0] != "23P01":
                raise
            clash = _reservation_qs(fid, [eq.pk], start, end).select_related("equipment", "department").first()
            raise DetailedConflict("Equipment is already booked for this time.",
                                   {"clashing_reservation": reservation_summary(clash) if clash else None})
        warnings = []
        if eq.operational_state != "IN_SERVICE":
            warnings.append(_item("NOT_IN_SERVICE", "Equipment is not currently in service.",
                                  operational_state=eq.operational_state))
        cal = calibration_status(eq, today_for(Facility.objects.get(pk=fid)))
        if cal["status"] == "OVERDUE":
            warnings.append(_item("CALIBRATION_OVERDUE", "Calibration is overdue.", next_due_date=cal["next_due_date"]))
        elif cal["status"] == "DUE_SOON":
            warnings.append(W_CAL_DUE(cal["next_due_date"]))
        audit.record(request=request, action="RESERVE", facility_id=fid, entity_type="EquipmentReservation",
                     entity_public_id=r.public_id, new=_res_audit(r))
    return r, warnings


def _lock_reservation(fid, reservation):
    r = EquipmentReservation.objects.select_for_update().filter(
        pk=reservation.pk, facility_id=fid, is_active=True).first()
    if r is None:
        raise NotFound()
    if r.status != "CONFIRMED":
        raise Conflict("Only a confirmed reservation can be changed.")
    return r


def cancel_reservation(*, request, reservation, reason):
    ctx, uid = request.bems, request.user.id
    fid = ctx.facility.id
    reason = (reason or "").strip()
    if not reason:
        raise ValidationError({"reason": ["This field may not be blank."]})
    if reservation.created_by != uid and not ctx.has("reservation.manage"):
        _deny_scope(request, "reservation_cancel_not_creator")
    with transaction.atomic():
        r = _lock_reservation(fid, reservation)
        before = _res_audit(r)
        r.status, r.cancel_reason, r.updated_by = "CANCELLED", reason, uid
        r.save(update_fields=["status", "cancel_reason", "updated_by"])
        audit.record(request=request, action="RESERVATION_CANCEL", facility_id=fid, entity_type="EquipmentReservation",
                     entity_public_id=r.public_id, previous=before, new=_res_audit(r), changed_fields=["status"])
    return r


def mark_reservation(*, request, reservation, status):
    if status not in ("FULFILLED", "NO_SHOW"):
        raise ValidationError({"status": ["Invalid status."]})
    fid, uid = request.bems.facility.id, request.user.id
    with transaction.atomic():
        r = _lock_reservation(fid, reservation)
        before = _res_audit(r)
        r.status, r.updated_by = status, uid
        r.save(update_fields=["status", "updated_by"])
        audit.record(request=request, action="RESERVATION_STATUS", facility_id=fid, entity_type="EquipmentReservation",
                     entity_public_id=r.public_id, previous=before, new=_res_audit(r), changed_fields=["status"])
    return r


def close_expired_reservations(*, request, facility, now=None):
    """Settle past CONFIRMED bookings: FULFILLED when usage was logged in the window, else NO_SHOW. Idempotent."""
    try:
        grace = timedelta(minutes=int(os.environ.get("BEMS_RESERVATION_GRACE_MINUTES", "60")))
    except ValueError:
        grace = timedelta(minutes=60)
    now = now or timezone.now()
    ids = list(EquipmentReservation.objects.filter(
        facility_id=facility.id, is_active=True, status="CONFIRMED", end_at__lt=now - grace
    ).order_by("id").values_list("pk", flat=True))
    counts = {"FULFILLED": 0, "NO_SHOW": 0}
    for pk in ids:
        with transaction.atomic():
            r = EquipmentReservation.objects.select_for_update().filter(pk=pk, status="CONFIRMED", is_active=True).first()
            if r is None:
                continue
            used = EquipmentUsageLog.objects.filter(
                facility_id=facility.id, equipment_id=r.equipment_id, is_active=True,
                started_at__lt=r.end_at, ended_at__gt=r.start_at).exists()
            before = _res_audit(r)
            r.status = "FULFILLED" if used else "NO_SHOW"
            r.save(update_fields=["status"])
            audit.record(request=request, action="RESERVATION_STATUS", facility_id=facility.id,
                         entity_type="EquipmentReservation", entity_public_id=r.public_id,
                         previous=before, new=_res_audit(r), changed_fields=["status"])
            counts[r.status] += 1
    return counts


# ------------------------------------------------------------------ usage logs
def usage_hours_total(equipment):
    mins = EquipmentUsageLog.objects.filter(
        facility_id=equipment.facility_id, equipment_id=equipment.pk, is_active=True
    ).aggregate(s=Sum("duration_minutes"))["s"] or ZERO
    return (Decimal(mins) / Decimal(60)).quantize(Decimal("0.01"))


def _usage_audit(u):
    return {"equipment_id": u.equipment_id, "started_at": u.started_at.isoformat(), "ended_at": u.ended_at.isoformat(),
            "department_id": u.department_id, "allocation_id": u.allocation_id}


def save_usage_log(*, request, equipment, data, instance=None, expected_version=None):
    """Create (instance=None) or update a usage log. Overlap exclusion -> 409 naming the other session."""
    from apps.core.errors import StaleVersion
    fid, uid = request.bems.facility.id, request.user.id
    start = data.get("started_at", instance.started_at if instance else None)
    end = data.get("ended_at", instance.ended_at if instance else None)
    if end > timezone.now():
        raise ValidationError({"ended_at": ["Cannot be in the future."]})
    if end < start:
        raise ValidationError({"ended_at": ["Cannot be before the start."]})
    if end - start > timedelta(days=30):
        raise ValidationError({"ended_at": ["A session cannot be longer than 30 days."]})
    alloc = data.get("allocation")
    if alloc is not None and alloc.equipment_id != equipment.pk:
        raise ValidationError({"allocation": ["Unknown reference."]})
    fields = {k: v for k, v in data.items() if k not in ("equipment",)}
    with transaction.atomic():
        eq = _lock_equipment(fid, equipment.pk)
        if eq.lifecycle_stage != "COMMISSIONED":
            raise Conflict("Usage can only be logged for commissioned equipment.")
        try:
            with transaction.atomic():
                if instance is None:
                    u = EquipmentUsageLog.objects.create(facility_id=fid, equipment_id=eq.pk, created_by=uid,
                                                         updated_by=uid, **fields)
                    before = None
                else:
                    u = EquipmentUsageLog.objects.select_for_update().filter(
                        pk=instance.pk, facility_id=fid, is_active=True).first()
                    if u is None:
                        raise NotFound()
                    if expected_version is not None and u.row_version != expected_version:
                        raise StaleVersion(current_row_version=u.row_version)
                    from apps.billing.gates import ensure_usage_log_unbilled   # Phase 11
                    ensure_usage_log_unbilled(u)
                    before = _usage_audit(u)
                    for k, v in fields.items():
                        setattr(u, k, v)
                    u.updated_by = uid
                    u.save(update_fields=list(fields) + ["updated_by"])
        except IntegrityError as exc:
            if _pg(exc)[0] != "23P01":
                raise
            other = EquipmentUsageLog.objects.filter(
                facility_id=fid, equipment_id=eq.pk, is_active=True, started_at__lt=end, ended_at__gt=start)
            if instance is not None:
                other = other.exclude(pk=instance.pk)
            other = other.first()
            raise DetailedConflict("This overlaps another usage session of the same equipment.",
                                   {"overlapping_session": usage_summary_item(other) if other else None})
        audit.record(request=request, action="USAGE_REPORTED" if instance is None else "UPDATE", facility_id=fid,
                     entity_type="EquipmentUsageLog", entity_public_id=u.public_id,
                     previous=before, new=_usage_audit(u),
                     changed_fields=None if instance is None else audit.diff(before, _usage_audit(u)))
    u.refresh_from_db()
    if instance is None:
        from apps.billing.services import safe_charges_for_usage_log   # Phase 11: never raises
        u.charges = safe_charges_for_usage_log(u, request=request)
    return u


# ------------------------------------------------------------------ transfers
def _xfer_audit(t):
    return {"equipment_id": t.equipment_id, "status": t.status, "from_location_id": t.from_location_id,
            "to_location_id": t.to_location_id, "to_department_id": t.to_department_id}


def request_transfer(*, request, equipment, data):
    ctx, uid = request.bems, request.user.id
    fid = ctx.facility.id
    to_loc, to_dept = data["location"], data.get("department")
    reason = (data.get("reason") or "").strip()
    if not reason:
        raise ValidationError({"reason": ["This field may not be blank."]})
    if not ctx.has("transfer.approve"):
        if to_dept is None or to_dept.pk not in user_department_ids(uid, fid):
            _deny_scope(request, "transfer_department_scope")
    with transaction.atomic():
        eq = _lock_equipment(fid, equipment.pk)
        if eq.lifecycle_stage != "COMMISSIONED":
            raise Conflict("Only commissioned equipment can be transferred.")
        if _active_allocation(fid, eq.pk) is not None:
            raise Conflict("Equipment is allocated. Release it before requesting a transfer.")
        if eq.current_location_id == to_loc.pk and (to_dept is None or to_dept.pk == eq.owning_department_id):
            raise ValidationError({"location": ["Equipment is already there."]})
        try:
            with transaction.atomic():
                t = EquipmentTransferRequest.objects.create(
                    facility_id=fid, equipment_id=eq.pk, from_department_id=eq.owning_department_id,
                    from_location_id=eq.current_location_id, to_location=to_loc, to_department=to_dept,
                    reason=reason, status="PENDING", created_by=uid, updated_by=uid)
        except IntegrityError as exc:
            if _pg(exc)[1] == "ux_equipment_transfer_requests_pending_active":
                raise Conflict("This equipment already has a pending transfer request.")
            raise
        audit.record(request=request, action="TRANSFER_REQUESTED", facility_id=fid,
                     entity_type="EquipmentTransferRequest", entity_public_id=t.public_id, new=_xfer_audit(t))
    return t


def _lock_pending(fid, transfer):
    t = EquipmentTransferRequest.objects.select_for_update().filter(
        pk=transfer.pk, facility_id=fid, is_active=True).first()
    if t is None:
        raise NotFound()
    if t.status != "PENDING":
        raise Conflict("This request has already been decided.")
    return t


def _decide(request, t, status, note):
    before = _xfer_audit(t)
    t.status, t.decided_by, t.decided_at, t.decision_note = status, request.user.id, timezone.now(), note
    t.updated_by = request.user.id
    t.save(update_fields=["status", "decided_by", "decided_at", "decision_note", "updated_by"])
    return before


def approve_transfer(*, request, transfer, note=None):
    from apps.equipment import services as eq_services
    ctx, uid = request.bems, request.user.id
    fid = ctx.facility.id
    if not ctx.has("transfer.approve") or transfer.created_by == uid:
        _deny_scope(request, "transfer_self_approval" if ctx.has("transfer.approve") else "transfer_approve_permission")
    with transaction.atomic():
        eq = _lock_equipment(fid, transfer.equipment_id)
        t = _lock_pending(fid, transfer)
        if eq.lifecycle_stage != "COMMISSIONED":
            raise Conflict("Equipment is no longer commissioned.")
        if _active_allocation(fid, eq.pk) is not None:
            raise Conflict("Equipment is allocated. Release it first.")
        if eq.current_location_id != t.from_location_id:
            raise Conflict("Equipment moved since the request.")
        eq_services.move_equipment(request=request, equipment=eq, expected_version=eq.row_version,
                                   to_location=t.to_location, to_department=t.to_department, reason=t.reason)
        before = _decide(request, t, "APPROVED", (note or "").strip() or None)
        audit.record(request=request, action="TRANSFER_APPROVED", facility_id=fid,
                     entity_type="EquipmentTransferRequest", entity_public_id=t.public_id,
                     previous=before, new=_xfer_audit(t), changed_fields=["status"])
    return t


def reject_transfer(*, request, transfer, note):
    fid = request.bems.facility.id
    note = (note or "").strip()
    if not note:
        raise ValidationError({"note": ["A note is required to reject a request."]})
    with transaction.atomic():
        t = _lock_pending(fid, transfer)
        before = _decide(request, t, "REJECTED", note)
        audit.record(request=request, action="TRANSFER_REJECTED", facility_id=fid,
                     entity_type="EquipmentTransferRequest", entity_public_id=t.public_id,
                     previous=before, new=_xfer_audit(t), changed_fields=["status"])
    return t


def cancel_transfer(*, request, transfer):
    fid, uid = request.bems.facility.id, request.user.id
    if transfer.created_by != uid:
        _deny_scope(request, "transfer_cancel_not_requester")
    with transaction.atomic():
        t = _lock_pending(fid, transfer)
        before = _decide(request, t, "CANCELLED", None)
        audit.record(request=request, action="TRANSFER_CANCELLED", facility_id=fid,
                     entity_type="EquipmentTransferRequest", entity_public_id=t.public_id,
                     previous=before, new=_xfer_audit(t), changed_fields=["status"])
    return t


# ------------------------------------------------------------------ user departments
def set_user_departments(*, request, user, departments):
    fid, uid = request.bems.facility.id, request.user.id
    if not UserFacilityRole.objects.filter(user_id=user.pk, facility_id=fid, is_active=True,
                                           role__is_active=True).exists():
        raise NotFound()
    wanted = {d.pk: d for d in departments}
    with transaction.atomic():
        cur = {ud.department_id: ud for ud in UserDepartment.objects.filter(
            facility_id=fid, user_id=user.pk)}
        pub = lambda ids: sorted(str(p) for p in Department.objects.filter(pk__in=ids).values_list("public_id", flat=True))  # noqa: E731
        before = pub(cur.keys())
        drop = [ud.pk for dep, ud in cur.items() if dep not in wanted]
        if drop:
            UserDepartment.objects.filter(pk__in=drop, facility_id=fid).delete()
        add = [UserDepartment(facility_id=fid, user_id=user.pk, department_id=dep, created_by=uid)
               for dep in wanted if dep not in cur]
        if add:
            UserDepartment.objects.bulk_create(add)
        after = pub(wanted.keys())
        if before != after:
            audit.record(request=request, action="USER_DEPARTMENTS_CHANGED", facility_id=fid, entity_type="User",
                         entity_public_id=user.public_id, previous={"departments": before},
                         new={"departments": after}, changed_fields=["departments"])
    return list(wanted.values())



def bulk_calibration_status(equipment_ids, today=None):
    """Set-based twin of calibration_status() for lists: a fixed number of queries whatever the list size.
    Returns {equipment_id: {status, next_due_date, has_unresolved_failure, schedule_public_id}}."""
    from apps.equipment.models import Equipment            # lazy: avoids a circular import
    ids = list(dict.fromkeys(equipment_ids))
    if not ids:
        return {}
    fac_of = dict(Equipment.objects.filter(pk__in=ids).values_list("pk", "facility_id"))
    facilities = {f.pk: f for f in Facility.objects.filter(pk__in=set(fac_of.values()))}
    today_of = {fid: (today or today_for(f)) for fid, f in facilities.items()}
    schedules = {s.equipment_id: s for s in CalibrationSchedule.objects.filter(
        equipment_id__in=ids, is_active=True)}
    last = {r["equipment_id"]: r["result"] for r in CalibrationRecord.objects.filter(
        equipment_id__in=ids).order_by("equipment_id", "-performed_date", "-id").distinct("equipment_id").values(
        "equipment_id", "result")}
    out = {}
    for eid in ids:
        s = schedules.get(eid)
        t = today_of.get(fac_of.get(eid))
        out[eid] = {
            "status": "NOT_REQUIRED" if s is None else status_code(s.next_due_date, s.lead_days, t),
            "next_due_date": s.next_due_date if s else None,
            "has_unresolved_failure": last.get(eid) == "FAIL",
            "schedule_public_id": str(s.public_id) if s else None,
        }
    return out