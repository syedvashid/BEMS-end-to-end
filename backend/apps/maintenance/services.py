"""Maintenance business rules. Views stay thin; every function runs in transaction.atomic(), locks the main row
with select_for_update, validates, writes events and the audit row."""
import calendar
from datetime import date, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from django.db import IntegrityError, connection, transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from apps.core import audit
from apps.core.errors import Conflict, StaleVersion
from apps.equipment.models import Equipment
from apps.foundation.models import Facility, UserFacilityRole

from . import holds
from .models import (
    ChecklistTemplateItem, MaintenancePlan, WorkOrder, WorkOrderChecklistItem, WorkOrderEvent,
)

ENTITY = "WorkOrder"
TRANSITIONS = {
    ("OPEN", "ASSIGNED"), ("OPEN", "IN_PROGRESS"), ("OPEN", "CANCELLED"),
    ("ASSIGNED", "IN_PROGRESS"), ("ASSIGNED", "OPEN"), ("ASSIGNED", "CANCELLED"),
    ("IN_PROGRESS", "WAITING_PARTS"), ("IN_PROGRESS", "COMPLETED"), ("IN_PROGRESS", "CANCELLED"),
    ("WAITING_PARTS", "IN_PROGRESS"), ("WAITING_PARTS", "CANCELLED"),
    ("COMPLETED", "CLOSED"),
}
DONE_STATUSES = ("COMPLETED", "CLOSED", "CANCELLED")
LOCKED_STATUSES = ("CLOSED", "CANCELLED")

# ------------------------------------------------------------------ system actor (scheduler)
SYSTEM_USER = SimpleNamespace(id=None, username="system", is_authenticated=True)


class SystemRequest:
    """Stand-in for a request in management commands, so audit rows record the actor as 'system'."""
    user = SYSTEM_USER
    method = "CMD"
    path = "manage.py generate_pm_work_orders"
    META = {}
    bems = None


# ------------------------------------------------------------------ helpers
def facility_tz(facility):
    try:
        return ZoneInfo(facility.timezone or "Asia/Kolkata")
    except Exception:
        return ZoneInfo("Asia/Kolkata")


def today_for(facility, now=None):
    return (now or timezone.now()).astimezone(facility_tz(facility)).date()


def add_months(d, n):
    y, m = divmod(d.month - 1 + n, 12)
    y += d.year
    m += 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def add_interval(d, frequency_type, value):
    return d + timedelta(days=value) if frequency_type == "DAYS" else add_months(d, value)


_SEQ_SQL = """
INSERT INTO number_sequences (facility_id, sequence_code, year, last_value) VALUES (%s, %s, %s, 1)
ON CONFLICT (facility_id, sequence_code, year) DO UPDATE SET last_value = number_sequences.last_value + 1
RETURNING last_value
"""


def next_number(facility, sequence_code):
    """Atomic upsert; the year is the facility-timezone year. Returns (year, number)."""
    year = timezone.now().astimezone(facility_tz(facility)).year
    try:
        with transaction.atomic(), connection.cursor() as cur:
            cur.execute(_SEQ_SQL, [facility.id, sequence_code, year])
            return year, cur.fetchone()[0]
    except IntegrityError:
        raise Conflict("The number sequence for this year is exhausted.")


def assignee_ok(facility_id, user_id):
    """Active member of the facility whose role holds work_order.execute."""
    return UserFacilityRole.objects.filter(
        facility_id=facility_id, user_id=user_id, is_active=True, user__is_active=True, role__is_active=True,
        role__role_permissions__permission__code="work_order.execute",
        role__role_permissions__permission__is_active=True).exists()


def _constraint(exc):
    return getattr(getattr(exc.__cause__, "diag", None), "constraint_name", None)


def _get_equipment(facility_id, equipment_pk, field="equipment", lock=False):
    qs = Equipment.objects.filter(pk=equipment_pk, facility_id=facility_id, is_active=True)
    eq = (qs.select_for_update() if lock else qs).first()
    if eq is None:
        raise ValidationError({field: ["Unknown reference."]})
    if eq.lifecycle_stage != "COMMISSIONED":
        raise ValidationError({field: ["Equipment must be commissioned."]})
    return eq


def _lock_wo(wo, expected_version=None):
    row = WorkOrder.objects.select_for_update().filter(pk=wo.pk, facility_id=wo.facility_id).first()
    if row is None:
        raise NotFound()
    if expected_version is not None and row.row_version != expected_version:
        raise StaleVersion(current_row_version=row.row_version)
    return row


def _event(wo, event_type, uid, from_status=None, to_status=None, note=None):
    WorkOrderEvent.objects.create(
        facility_id=wo.facility_id, work_order=wo, event_type=event_type, from_status=from_status,
        to_status=to_status, note=note, created_by=uid)


def _check_transition(wo, to):
    if (wo.status, to) not in TRANSITIONS:
        raise Conflict(f"A work order that is {wo.status.lower().replace('_', ' ')} cannot be changed to "
                       f"{to.lower().replace('_', ' ')}.")


def _move_status(request, wo, to, event_type, note=None, audit_action="WORK_ORDER_STATUS", audit_extra=None, **fields):
    _check_transition(wo, to)
    uid, old = request.user.id, wo.status
    wo.status = to
    wo.status_note = note
    wo.updated_by = uid
    for k, v in fields.items():
        setattr(wo, k, v)
    wo.save(update_fields=["status", "status_note", "updated_by", *fields])
    _event(wo, event_type, uid, old, to, note)
    new = {"status": to, "note": note, **(audit_extra or {})}
    audit.record(request=request, action=audit_action, facility_id=wo.facility_id, entity_type=ENTITY,
                 entity_public_id=wo.public_id, previous={"status": old}, new=new, changed_fields=["status"])


def _snapshot_checklist(wo, template, uid):
    items = ChecklistTemplateItem.objects.filter(checklist_template_id=template.pk).order_by("sequence")
    WorkOrderChecklistItem.objects.bulk_create([
        WorkOrderChecklistItem(
            facility_id=wo.facility_id, work_order=wo, sequence=i.sequence, item_text=i.item_text,
            item_type=i.item_type, unit=i.unit, min_value=i.min_value, max_value=i.max_value,
            created_by=uid, updated_by=uid) for i in items])

def _coverage_fields(facility, eq, coverage_source, at=None):
    """When coverage_source is not supplied, fill it (and the link) from the warranty/AMC suggestion."""
    if coverage_source is not None:
        return {"coverage_source": coverage_source}
    from apps.compliance.services import find_coverage
    source, obj = find_coverage(eq, today_for(facility, at))
    if source == "WARRANTY":
        return {"coverage_source": "WARRANTY", "warranty": obj}
    if source == "AMC":
        return {"coverage_source": "AMC", "amc_contract": obj}
    return {}

def _create_wo(request, facility, *, equipment, work_order_type, priority, status="OPEN", plan=None,
               template=None, assigned_to=None, **fields):
    uid = request.user.id
    year, n = next_number(facility, "WO")
    extra = {}
    if assigned_to is not None:
        status, extra = "ASSIGNED", {"assigned_to_user": assigned_to, "assigned_at": timezone.now()}
    wo = WorkOrder.objects.create(
        facility=facility, wo_number=f"WO-{year}-{n:06d}", work_order_type=work_order_type, priority=priority,
        status=status, equipment=equipment, maintenance_plan=plan, created_by=uid, updated_by=uid, **extra, **fields)
    if template is not None:
        _snapshot_checklist(wo, template, uid)
    _event(wo, "CREATED", uid, None, status, None)
    if assigned_to is not None:
        _event(wo, "ASSIGNED", uid, None, status, f"Assigned to {assigned_to.username}")
    snap = audit.snapshot(wo)
    audit.record(request=request, action="CREATE", facility_id=facility.id, entity_type=ENTITY,
                 entity_public_id=wo.public_id, new=snap, changed_fields=audit.diff(None, snap))
    return wo


# ------------------------------------------------------------------ creation
def create_pm_work_order(*, request, plan, due_date):
    """Scheduler and 'generate now'. Returns the work order, or None when one already exists for (plan, due_date)."""
    facility = Facility.objects.get(pk=plan.facility_id)
    with transaction.atomic():
        plan = MaintenancePlan.objects.select_for_update().filter(
            pk=plan.pk, facility_id=plan.facility_id, is_active=True).first()
        if plan is None:
            raise NotFound()
        eq = _get_equipment(facility.id, plan.equipment_id)
        if WorkOrder.objects.filter(maintenance_plan_id=plan.pk, work_order_type="PREVENTIVE",
                                    due_date=due_date).exists():
            return None
        assignee = None
        if plan.default_assignee_user_id and assignee_ok(facility.id, plan.default_assignee_user_id):
            assignee = plan.default_assignee_user
        try:
            with transaction.atomic():
                return _create_wo(
                    request, facility, equipment=eq, work_order_type="PREVENTIVE", priority=plan.priority,
                    plan=plan, template=plan.checklist_template if plan.checklist_template_id else None,
                    assigned_to=assignee, due_date=due_date)
        except IntegrityError as exc:
            if _constraint(exc) == "ux_work_orders_plan_due":
                return None
            raise


def report_breakdown(*, request, facility, equipment, problem_description, priority="MEDIUM", reported_by_name=None,
                     reported_by_department=None, reported_at=None, equipment_unusable=False, coverage_source=None):
    now = timezone.now()
    reported_at = reported_at or now
    if reported_at > now:
        raise ValidationError({"reported_at": ["Reported time cannot be in the future."]})
    if not (problem_description or "").strip():
        raise ValidationError({"problem_description": ["This field is required."]})
    if reported_by_department is not None and (
            reported_by_department.facility_id != facility.id or not reported_by_department.is_active):
        raise ValidationError({"reported_by_department": ["Unknown reference."]})
    with transaction.atomic():
        eq = _get_equipment(facility.id, equipment.pk, lock=True)
        wo = _create_wo(
            request, facility, equipment=eq, work_order_type="BREAKDOWN", priority=priority,
            problem_description=problem_description.strip(), reported_at=reported_at,
            reported_by_name=reported_by_name, reported_by_department=reported_by_department,
            equipment_unusable=equipment_unusable, downtime_start=reported_at,
            **_coverage_fields(facility, eq, coverage_source, reported_at))
        if equipment_unusable:
            holds.place_hold(request=request, equipment=eq, hold_type="OUT_OF_SERVICE", source_type="WORK_ORDER",
                             work_order=wo, reason=f"Breakdown {wo.wo_number}: equipment cannot be used")
    return wo


def create_work_order(*, request, facility, work_order_type, equipment, priority="MEDIUM", due_date=None,
                      problem_description=None, parent_work_order=None, checklist_template=None, assigned_to=None,
                      coverage_source=None, source_calibration_record=None):
    """CORRECTIVE or manual PREVENTIVE."""
    if work_order_type not in ("CORRECTIVE", "PREVENTIVE"):
        raise ValidationError({"work_order_type": ["Use the breakdown report for breakdowns."]})
    if work_order_type == "PREVENTIVE" and due_date is None:
        raise ValidationError({"due_date": ["Required for a preventive work order."]})
    if parent_work_order is not None and parent_work_order.facility_id != facility.id:
        raise ValidationError({"parent_work_order": ["Unknown reference."]})
    if checklist_template is not None and (
            checklist_template.facility_id != facility.id or not checklist_template.is_active):
        raise ValidationError({"checklist_template": ["Unknown reference."]})
    if assigned_to is not None and not assignee_ok(facility.id, assigned_to.pk):
        raise ValidationError({"assigned_to": [
            "User must be an active member of this facility with permission to execute work orders."]})
    with transaction.atomic():
        eq = _get_equipment(facility.id, equipment.pk)
        extra = _coverage_fields(facility, eq, coverage_source) if work_order_type == "CORRECTIVE" \
            else ({"coverage_source": coverage_source} if coverage_source else {})
        if source_calibration_record is not None:
            extra["source_calibration_record"] = source_calibration_record
        return _create_wo(
            request, facility, equipment=eq, work_order_type=work_order_type, priority=priority,
            template=checklist_template, assigned_to=assigned_to, due_date=due_date,
            problem_description=(problem_description or "").strip() or None, parent_work_order=parent_work_order,
            **extra)


# ------------------------------------------------------------------ status services
def assign(*, request, wo, user, note=None, expected_version=None):
    with transaction.atomic():
        wo = _lock_wo(wo, expected_version)
        if not assignee_ok(wo.facility_id, user.pk):
            raise ValidationError({"assigned_to": [
                "User must be an active member of this facility with permission to execute work orders."]})
        extra = {"assigned_to": str(user.public_id)}
        if wo.status == "OPEN":
            _move_status(request, wo, "ASSIGNED", "ASSIGNED", note or f"Assigned to {user.username}",
                         audit_action="WORK_ORDER_ASSIGNED", audit_extra=extra,
                         assigned_to_user=user, assigned_at=timezone.now())
        elif wo.status == "ASSIGNED":   # re-assign: no status change
            wo.assigned_to_user, wo.assigned_at, wo.updated_by = user, timezone.now(), request.user.id
            wo.save(update_fields=["assigned_to_user", "assigned_at", "updated_by"])
            _event(wo, "ASSIGNED", request.user.id, "ASSIGNED", "ASSIGNED", note or f"Re-assigned to {user.username}")
            audit.record(request=request, action="WORK_ORDER_ASSIGNED", facility_id=wo.facility_id, entity_type=ENTITY,
                         entity_public_id=wo.public_id, previous={"status": "ASSIGNED"},
                         new={"status": "ASSIGNED", "note": note, **extra}, changed_fields=["assigned_to_user"])
        else:
            raise Conflict("Only open or assigned work orders can be assigned.")
    return wo


def start(*, request, wo, expected_version=None):
    with transaction.atomic():
        wo = _lock_wo(wo, expected_version)
        _check_transition(wo, "IN_PROGRESS")
        eq = _get_equipment(wo.facility_id, wo.equipment_id, lock=True)
        _move_status(request, wo, "IN_PROGRESS", "STARTED", started_at=wo.started_at or timezone.now())
        holds.place_hold(request=request, equipment=eq, hold_type="MAINTENANCE", source_type="WORK_ORDER",
                         work_order=wo, reason=f"Work order {wo.wo_number} in progress")
    return wo


def set_waiting_parts(*, request, wo, reason, expected_version=None):
    if not (reason or "").strip():
        raise ValidationError({"reason": ["This field is required."]})
    with transaction.atomic():
        wo = _lock_wo(wo, expected_version)
        _move_status(request, wo, "WAITING_PARTS", "WAITING_PARTS", reason.strip())
    return wo


def resume(*, request, wo, expected_version=None):
    with transaction.atomic():
        wo = _lock_wo(wo, expected_version)
        _move_status(request, wo, "IN_PROGRESS", "RESUMED")
    return wo


def evaluate_item(item):
    """A MEASUREMENT outside min/max is FAIL, whatever the client said."""
    v = item.measured_value
    if item.item_type == "MEASUREMENT" and item.result != "NA" and v is not None:
        if (item.min_value is not None and v < item.min_value) or (item.max_value is not None and v > item.max_value):
            return "FAIL"
    return item.result


def save_checklist(*, request, wo, results):
    with transaction.atomic():
        wo = _lock_wo(wo)
        if wo.status not in ("IN_PROGRESS", "WAITING_PARTS"):
            raise Conflict("Checklist results can only be entered while the work order is in progress or waiting for parts.")
        rows = {r.sequence: r for r in WorkOrderChecklistItem.objects.select_for_update().filter(
            work_order_id=wo.pk, is_active=True)}
        for entry in results:
            row = rows.get(entry["sequence"])
            if row is None:
                raise ValidationError({"items": [f"Unknown checklist item {entry['sequence']}."]})
            row.result = entry.get("result")
            row.measured_value = entry.get("measured_value")
            row.remarks = entry.get("remarks")
            if row.item_type == "MEASUREMENT" and row.result not in (None, "NA") and row.measured_value is None:
                raise ValidationError({"items": [f"Item {row.sequence}: enter the measured value."]})
            row.result = evaluate_item(row)
            row.updated_by = request.user.id
            row.save(update_fields=["result", "measured_value", "remarks", "updated_by"])
        audit.record(request=request, action="UPDATE", facility_id=wo.facility_id, entity_type=ENTITY,
                     entity_public_id=wo.public_id, new={"checklist_items_saved": len(results)},
                     changed_fields=["checklist"])
    return wo


def _advance_plan(request, wo, facility, completed_at):
    plan = MaintenancePlan.objects.select_for_update().filter(
        pk=wo.maintenance_plan_id, facility_id=wo.facility_id, is_active=True).first()
    if plan is None:
        return
    done = today_for(facility, completed_at)
    before = {"last_performed_date": plan.last_performed_date, "next_due_date": plan.next_due_date}
    plan.last_performed_date = done
    plan.next_due_date = add_interval(done, plan.frequency_type, plan.frequency_value)
    plan.updated_by = request.user.id
    plan.save(update_fields=["last_performed_date", "next_due_date", "updated_by"])
    after = {"last_performed_date": plan.last_performed_date, "next_due_date": plan.next_due_date}
    audit.record(request=request, action="UPDATE", facility_id=wo.facility_id, entity_type="MaintenancePlan",
                 entity_public_id=plan.public_id, previous=before, new=after, changed_fields=audit.diff(before, after))


def complete(*, request, wo, data, expected_version=None):
    with transaction.atomic():
        wo = _lock_wo(wo, expected_version)
        _check_transition(wo, "COMPLETED")
        fields = {k: data[k] for k in ("action_taken", "root_cause", "labour_cost", "vendor_cost") if k in data}
        if wo.work_order_type in ("BREAKDOWN", "CORRECTIVE") and not (
                fields.get("action_taken", wo.action_taken) or "").strip():
            raise ValidationError({"action_taken": ["Required to complete a breakdown or corrective work order."]})
        items = list(WorkOrderChecklistItem.objects.select_for_update().filter(work_order_id=wo.pk, is_active=True))
        missing = [i.sequence for i in items if i.result is None]
        if missing:
            raise ValidationError({"checklist": [
                "Every checklist item needs a result. Missing: " + ", ".join(str(s) for s in sorted(missing))]})
        for i in items:
            final = evaluate_item(i)
            if final != i.result:
                i.result, i.updated_by = final, request.user.id
                i.save(update_fields=["result", "updated_by"])
        facility = Facility.objects.get(pk=wo.facility_id)
        now = timezone.now()
        end = data.get("downtime_end") or wo.downtime_end
        if end is None and wo.work_order_type == "BREAKDOWN":
            end = now
        if end is not None:
            if wo.downtime_start and end < wo.downtime_start:
                raise ValidationError({"downtime_end": ["Cannot be before the downtime start."]})
            fields["downtime_end"] = end
        _move_status(request, wo, "COMPLETED", "COMPLETED", completed_at=now, **fields)
        holds.release_work_order_holds(request=request, wo=wo, reason=f"Work order {wo.wo_number} completed")
        if wo.work_order_type == "PREVENTIVE" and wo.maintenance_plan_id:
            _advance_plan(request, wo, facility, now)
    return wo


def close(*, request, wo, signoff_name, expected_version=None):
    name = (signoff_name or "").strip()
    if not name:
        raise ValidationError({"signoff_name": ["Enter the name of the person who accepted the work."]})
    with transaction.atomic():
        wo = _lock_wo(wo, expected_version)
        _move_status(request, wo, "CLOSED", "CLOSED", closed_by=request.user.id, closed_at=timezone.now(),
                     signoff_name=name)
    return wo


def cancel(*, request, wo, reason, next_due_date=None, expected_version=None):
    if not (reason or "").strip():
        raise ValidationError({"reason": ["This field is required."]})
    with transaction.atomic():
        wo = _lock_wo(wo, expected_version)
        _check_transition(wo, "CANCELLED")
        facility = Facility.objects.get(pk=wo.facility_id)
        plan = None
        if wo.work_order_type == "PREVENTIVE" and wo.maintenance_plan_id:
            if next_due_date is None:
                raise ValidationError({"next_due_date": ["Required when cancelling a preventive work order."]})
            if next_due_date < today_for(facility):
                raise ValidationError({"next_due_date": ["Cannot be in the past."]})
            plan = MaintenancePlan.objects.select_for_update().filter(
                pk=wo.maintenance_plan_id, facility_id=wo.facility_id).first()
        _move_status(request, wo, "CANCELLED", "CANCELLED", reason.strip(), cancel_reason=reason.strip())
        holds.release_work_order_holds(request=request, wo=wo, reason=f"Work order {wo.wo_number} cancelled")
        if plan is not None and plan.is_active:
            before = {"next_due_date": plan.next_due_date}
            plan.next_due_date, plan.updated_by = next_due_date, request.user.id
            plan.save(update_fields=["next_due_date", "updated_by"])
            audit.record(request=request, action="UPDATE", facility_id=wo.facility_id, entity_type="MaintenancePlan",
                         entity_public_id=plan.public_id, previous=before, new={"next_due_date": next_due_date},
                         changed_fields=["next_due_date"])
    return wo


def add_note(*, request, wo, text):
    text = (text or "").strip()
    if not text:
        raise ValidationError({"note": ["This field is required."]})
    with transaction.atomic():
        wo = _lock_wo(wo)
        _event(wo, "NOTE", request.user.id, wo.status, wo.status, text)
    return wo


# ------------------------------------------------------------------ plan generation
def generate_plans(*, request, facility, name, equipment_model=None, category=None, frequency_type=None,
                   frequency_value=None, checklist_template=None, lead_days=7, priority="MEDIUM",
                   default_assignee=None, last_performed_date=None, start_date=None):
    if (equipment_model is None) == (category is None):
        raise ValidationError({"scope": ["Give either equipment_model or category."]})
    if (frequency_type is None) != (frequency_value is None):
        raise ValidationError({"frequency_value": ["Give frequency_type and frequency_value together."]})
    if default_assignee is not None and not assignee_ok(facility.id, default_assignee.pk):
        raise ValidationError({"default_assignee": [
            "User must be an active member of this facility with permission to execute work orders."]})
    start_date = start_date or today_for(facility)
    qs = Equipment.objects.filter(facility_id=facility.id, is_active=True, lifecycle_stage="COMMISSIONED") \
        .select_related("equipment_model__category")
    qs = qs.filter(equipment_model=equipment_model) if equipment_model is not None \
        else qs.filter(equipment_model__category=category)
    created = skipped_existing = skipped_no_interval = 0
    uid = request.user.id
    with transaction.atomic():
        for eq in qs.order_by("id"):
            if MaintenancePlan.objects.filter(facility_id=facility.id, equipment_id=eq.pk, is_active=True,
                                              name__iexact=name).exists():
                skipped_existing += 1
                continue
            if frequency_type:
                ftype, fval = frequency_type, frequency_value
            else:
                m = eq.equipment_model
                interval = m.default_pm_interval_days if m.default_pm_interval_days is not None \
                    else m.category.default_pm_interval_days
                if not interval:
                    skipped_no_interval += 1
                    continue
                ftype, fval = "DAYS", interval
            MaintenancePlan.objects.create(
                facility=facility, name=name, equipment=eq, checklist_template=checklist_template,
                frequency_type=ftype, frequency_value=fval, lead_days=lead_days, priority=priority,
                default_assignee_user=default_assignee, start_date=start_date,
                last_performed_date=last_performed_date,
                next_due_date=add_interval(last_performed_date, ftype, fval) if last_performed_date else start_date,
                created_by=uid, updated_by=uid)
            created += 1
        result = {"created": created, "skipped_existing": skipped_existing, "skipped_no_interval": skipped_no_interval}
        audit.record(request=request, action="BULK_CREATE", facility_id=facility.id, entity_type="MaintenancePlan",
                     new={**result, "name": name, "scope": str((equipment_model or category).public_id)})
    return result
